#!/usr/bin/env python3
"""Read-only HP NetBSD private RTL50 build source-integrity verifier.

A kernel must be linked from a byte-identical, owner-local snapshot of its
Git-identified RTL C/H/INC inputs. This script never invokes a compiler,
writes to the filesystem, installs a kernel, touches firmware or reboots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        parser.error("snapshot integrity verification requires the real HP NetBSD host")
    if re.fullmatch(r"[a-f0-9]{40}", args.source_commit) is None:
        parser.error("full source commit required")
    if args.output.is_symlink():
        parser.error("owner output path is unexpectedly a symlink")
    out = args.output.resolve(strict=True)
    if out.parent != ROOT.parent.resolve() or not out.name.startswith("rtl-kconfig-live-"):
        parser.error("output must be one private rtl-kconfig-live-* sibling")
    status_path = out / "status.json"
    if status_path.is_symlink():
        parser.error("status must be a regular owner file")
    status = json.loads(status_path.read_text())
    expected_ident = "HP-RTL50-" + args.source_commit[:12] + "-SAFE-GENFB"
    if (status.get("state") != "CONFIGURED_50_WIP_RULES_PASS"
        or status.get("source_commit") != args.source_commit
        or status.get("kernel_ident") != expected_ident
        or status.get("source_snapshot_private_copies_pass") is not True):
        raise RuntimeError("kernel config / full Git identity mismatch")
    hashes = status.get("source_snapshot_sha256")
    sources = status.get("selected")
    if (not isinstance(hashes, dict) or not isinstance(sources, list)
        or len(sources) != 50 or len(set(sources)) != 50
        or len(hashes) != status.get("source_snapshot_files")
        or not all(name in hashes for name in sources)):
        raise RuntimeError("incomplete RTL50 source snapshot manifest")
    pci = out / "sys/dev/pci"
    if pci.is_symlink() or not pci.is_dir():
        raise RuntimeError("private PCI overlay must not be symlinked")
    checked = 0
    for name, expected_sha in sorted(hashes.items()):
        if (not isinstance(name, str) or
            re.fullmatch(r"rtwn8723be_[A-Za-z0-9_]+\.(c|h|inc)", name) is None):
            raise RuntimeError("invalid snapshot source name")
        if not isinstance(expected_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_sha):
            raise RuntimeError("invalid source digest")
        file = pci / name
        if not file.is_file() or file.is_symlink() or digest(file) != expected_sha:
            raise RuntimeError("RTL source snapshot differs from recorded Git input: " + name)
        checked += 1
    print("HP_RTL50_SNAPSHOT_VERIFIED", args.source_commit, "FILES", checked,
          "IDENT", expected_ident, flush=True)


if __name__ == "__main__":
    main()
