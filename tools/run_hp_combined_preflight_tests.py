#!/usr/bin/env python3
"""Run combined-kernel source/native ABI gates without running RTL-only builder.

--list is read-only and runnable on Legion. --run is HP/NetBSD-only and
requires a release-checked invoking shell. It runs all existing RTL
regressions AND the independent i915+RTL combined negative test contracts.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REGRESSION_SOURCE = ROOT / "tools/build_hp_rtl50_next_candidate.sh"
COMBINED = (
    "test_hp_combined_source_contract.py",
    "test_hp_combined_full_link_map_source.py",
    "test_hp_i915_trace_overlay_source.py",
    "test_hp_combined_trace_manifest_source.py",
)
TRACE_TESTS = {
    "test_hp_i915_trace_overlay_source.py",
    "test_hp_combined_trace_manifest_source.py",
}
TRACE_NATIVE_REL = "sys/external/bsd/drm2/dist/drm/i915/i915_drv.c"
VALID = re.compile(r"^test_[a-z0-9_]+\.py$")


def selected(test_source: str) -> tuple[str, ...]:
    start = "for testname in \\"
    if test_source.count(start) != 1:
        raise ValueError("cannot locate unique RTL regression selection")
    tail = test_source.split(start, 1)[1]
    if "\ndo\n" not in tail:
        raise ValueError("unterminated RTL regression selection")
    fragment = tail.split("\ndo\n", 1)[0]
    lines = fragment.splitlines()
    found = []
    for line in lines:
        match = re.fullmatch(r"\s*(test_[a-z0-9_]+\.py)\s*(?:\\)?\s*", line)
        if not match:
            if line.strip():
                raise ValueError("unsafe RTL source regression selector")
            continue
        found.append(match.group(1))
    if len(found) < 38 or len(set(found)) != len(found):
        raise ValueError("incomplete or duplicate RTL source regression list")
    all_tests = tuple(found) + COMBINED
    if len(set(all_tests)) != len(all_tests) or any(
            not VALID.fullmatch(name) for name in all_tests):
        raise ValueError("duplicate or invalid combined source test")
    return all_tests


def main() -> int:
    parser = argparse.ArgumentParser()
    p = parser.add_mutually_exclusive_group(required=True)
    p.add_argument("--list", action="store_true")
    p.add_argument("--run", action="store_true")
    parser.add_argument("--i915-repo", type=Path)
    parser.add_argument("--netbsd-src", type=Path)
    args = parser.parse_args()
    try:
        tests = selected(REGRESSION_SOURCE.read_text())
        for name in tests:
            path = ROOT / "tests" / name
            if not path.is_file() or path.is_symlink():
                raise ValueError("missing/linked test: " + name)
        if args.list:
            print("COMBINED_GATE_LIST_PASS count=" + str(len(tests)))
            for name in tests:
                print(name)
            return 0
        if platform.system() != "NetBSD" or platform.machine() != "amd64" or \
                not socket.gethostname().startswith("hp-tpnw121"):
            raise ValueError("source/native HP gate runner restricted to HP NetBSD")
        if args.i915_repo is None or args.netbsd_src is None:
            raise ValueError("--run requires --i915-repo and --netbsd-src")
        original = args.netbsd_src / TRACE_NATIVE_REL
        if not original.is_file() or original.is_symlink():
            raise ValueError("missing/linked pinned i915 trace source")
        if not (args.i915_repo / "patches/0038-netbsd11-i915-g01-g09-boottrace.patch").is_file():
            raise ValueError("missing owning i915 trace patch")
        for name in tests:
            trace_args = ([
                "--netbsd-i915", str(original),
                "--i915-repo", str(args.i915_repo),
            ] if name in TRACE_TESTS else [])
            proc = subprocess.run(
                [sys.executable, "-B", str(ROOT / "tests" / name),
                 *trace_args],
                cwd=ROOT, check=False, text=True, capture_output=True,
                timeout=120,
            )
            print(f"GATE {name} EXIT={proc.returncode}", flush=True)
            if proc.stdout.strip():
                print(proc.stdout[-2000:], flush=True)
            if proc.returncode:
                print(proc.stderr[-2400:], file=sys.stderr)
                raise ValueError("HP combined regression failed: " + name)
        print("COMBINED_SOURCE_NATIVE_GATES_PASS count=" + str(len(tests)))
        return 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as err:
        print("COMBINED_GATES_REFUSED: " + str(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
