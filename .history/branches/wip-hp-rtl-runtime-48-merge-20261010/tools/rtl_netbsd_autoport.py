#!/usr/bin/env python3
"""Bounded Linux-to-NetBSD source audit and deterministic include repair.

Only fixes *unconditional* C preprocessor includes in the 50 selected native
RTL8723BE translation units. Does not infer DMA, IRQ, PCI, MMIO, firmware or
net80211 semantics from error messages. Read-only by default. --apply needs
a clean exact Git SHA and is forbidden on the HP host.
"""
from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import platform
import re
import socket
import subprocess
import sys

HEADER_MAP = {
    "errno.h": "sys/errno.h",
    "stdbool.h": "sys/stdbool.h",
    "stddef.h": "sys/stddef.h",
    "stdint.h": "sys/stdint.h",
    "string.h": "sys/systm.h",
}
MANIFEST = re.compile(
    r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native\s*$",
    re.M,
)
INCLUDE = re.compile(r"^(\s*#\s*include\s*)<([^>]+)>(.*)$")
CONTROL = re.compile(r"^\s*#\s*(if|ifdef|ifndef|endif)\b")
ISSUE_PATTERNS = (
    ("UNSUPPORTED_LINUX_HEADER", re.compile(r"(fatal error|error):.*\blinux/[\w/.-]+\.h", re.I), "MANUAL"),
    ("MISSING_SYMBOL_PROVIDER", re.compile(r"undefined reference to|undefined symbol", re.I), "MANUAL"),
    ("KERNEL_API_CALL", re.compile(r"implicit declaration of function|incompatible pointer type", re.I), "MANUAL"),
    ("DMA_OR_IRQ_LIFETIME", re.compile(r"(DMA|PCI|interrupt|IRQ).*(panic|fault|timeout)|(panic|fault).*(DMA|PCI|interrupt|IRQ)", re.I), "MANUAL"),
    ("GPU_BLACK_SCREEN", re.compile(r"black[ -]?screen|i915.*(AUX|PLL|eDP|KMS).*fail", re.I), "MANUAL"),
)


def translate_includes(text: str) -> tuple[str, list[dict], list[dict]]:
    """Apply only semantically equivalent, top-level kernel-header swaps."""
    result, changes, hazards = [], [], []
    depth = 0
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        control = CONTROL.match(line)
        if control:
            directive = control.group(1)
            if directive in ("if", "ifdef", "ifndef"):
                depth += 1
            elif directive == "endif":
                depth = max(0, depth - 1)
        m = INCLUDE.match(line)
        if m is not None:
            name = m.group(2)
            if name in HEADER_MAP:
                if depth:
                    hazards.append({"line": number, "type": "CONDITIONAL_INCLUDE",
                                    "include": name, "action": "MANUAL"})
                else:
                    replacement = HEADER_MAP[name]
                    # The regex dollar anchor stops *before* the final
                    # LF; reconstruct it explicitly or two #include lines
                    # silently concatenate into invalid NetBSD C.
                    newline = "\n" if line.endswith("\n") else ""
                    line = (m.group(1) + "<" + replacement + ">" +
                            m.group(3) + newline)
                    changes.append({"line": number, "from": name, "to": replacement})
            elif name.startswith(("linux/", "asm/")):
                hazards.append({"line": number, "type": "LINUX_KERNEL_ABI",
                                "include": name, "action": "MANUAL"})
        result.append(line)
    if depth:
        hazards.append({"line": len(result), "type": "UNBALANCED_CPP_IF",
                        "action": "MANUAL"})
    return "".join(result), changes, hazards


def classify_diagnostics(text: str) -> list[dict]:
    items = []
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern, strategy in ISSUE_PATTERNS:
            if pattern.search(line):
                items.append({"line": number, "kind": kind,
                              "strategy": strategy, "example": line[:240]})
                break
        else:
            if re.search(r"(fatal error|error):.*\b("
                         r"errno|stdbool|stddef|stdint|string)\.h\b", line):
                items.append({"line": number, "kind": "SAFE_INCLUDE_TRANSLATION",
                              "strategy": "APPLY_IF_UNCONDITIONAL",
                              "example": line[:240]})
    return items


def git(root: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        timeout=20, check=False,
    )
    if result.returncode:
        raise RuntimeError("Git verification failed: " + " ".join(args))
    return result.stdout.strip()


def source_units(root: pathlib.Path) -> list[pathlib.Path]:
    lines = (root / "config/files.rtwn8723be_native").read_text()
    selected = MANIFEST.findall(lines)
    if len(selected) != 50 or len(set(selected)) != 50:
        raise RuntimeError("Expected exactly 50 uniquely owned NetBSD C units")
    paths = [root / "src" / name for name in selected]
    for path in paths:
        if not path.is_file() or path.is_symlink() or path.parent != root / "src":
            raise RuntimeError("Selected C file missing, symbolic, or escaped: " + str(path))
    return paths


def audit(root: pathlib.Path) -> tuple[dict, dict[pathlib.Path, str]]:
    patches, hazards = [], []
    changed = {}
    units = source_units(root)
    for file in units:
        original = file.read_text()
        updated, replacements, warnings = translate_includes(original)
        if replacements:
            changed[file] = updated
            patches.append({
                "file": str(file.relative_to(root)), "replacements": replacements,
                "unified_diff": "".join(difflib.unified_diff(
                    original.splitlines(keepends=True),
                    updated.splitlines(keepends=True),
                    fromfile=str(file.relative_to(root)) + ":before",
                    tofile=str(file.relative_to(root)) + ":NetBSD",
                )),
            })
        for item in warnings:
            hazards.append({"file": str(file.relative_to(root)), **item})
    return {
        "native_c_units": len(units),
        "auto_fixable_files": len(changed),
        "proposed_patches": patches,
        "manual_review": hazards,
    }, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parents[1])
    parser.add_argument("--diagnostics", type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-sha")
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        if git(root, "rev-parse", "--show-toplevel") != str(root):
            raise RuntimeError("root must be a standalone source Git checkout")
        observed = git(root, "rev-parse", "HEAD")
        findings, changes = audit(root)
        findings["source_sha"] = observed
        if args.diagnostics:
            findings["compiler_diagnostics"] = classify_diagnostics(
                args.diagnostics.read_text(errors="replace"))
        if args.apply:
            if platform.system() == "NetBSD" and socket.gethostname().startswith("hp-"):
                raise RuntimeError("HP modifications blocked; source changes must be reviewed via GitHub")
            if (not args.expected_sha or args.expected_sha != observed or
                    not re.fullmatch(r"[0-9a-f]{40}", observed)):
                raise RuntimeError("apply requires matching exact source SHA")
            if git(root, "status", "--porcelain=v1"):
                raise RuntimeError("apply refuses a dirty worktree")
            if findings["manual_review"]:
                raise RuntimeError("unsafe OS-dependent includes; review before apply")
            for file, updated in changes.items():
                # Preserve inodes only when explicitly applying to a clean
                # working copy, never in a kernel/private build snapshot.
                file.write_text(updated)
            findings["applied_files"] = len(changes)
        print(json.dumps(findings, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print("RTL_NETBSD_AUTOPORT_REFUSED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
