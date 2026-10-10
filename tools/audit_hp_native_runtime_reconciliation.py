#!/usr/bin/env python3
"""Audit frozen HP 48-unit runtime vs current GitHub 42-unit native RTL port.

This is a SOURCE RECONCILIATION GATE, not a native link/driver acceptance.
It cannot write the old root stage, modify firmware, change the kernel,
configure a radio, or authenticate via SSH. The only output is the JSON
file explicitly requested under the ordinary NetBSD owner's workdir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SYS = Path("/root/hp-driver-port-20261005/netbsd-native/sys")
ORIGINAL = ORIGINAL_SYS / "dev/pci"
OWNER = ROOT.parent.resolve()
FROZEN = ROOT / "reference/hp-native-20261006"
MANIFEST = ROOT / "config/files.rtwn8723be_native"
ROOT_FILES = ORIGINAL / "files.pci"
FROZEN_18 = (
    "rtwn8723be_runtime.c", "rtwn8723be_runtime.h",
    "rtwn8723be_dm_native.c", "rtwn8723be_dm_native.h",
    "rtwn8723be_dm_linux.inc",
    "rtwn8723be_channel_native.c", "rtwn8723be_channel_native.h",
    "rtwn8723be_media_native.c", "rtwn8723be_media_native.h",
    "rtwn8723be_btc_provider_native.c", "rtwn8723be_btc_provider_native.h",
    "rtwn8723be_net80211_tx.c", "rtwn8723be_net80211_tx.h",
    "rtwn8723be_reserved_native.c", "rtwn8723be_reserved_native.h",
    "rtwn8723be_netbsd.h", "rtwn8723be_netbsd.c",
    "rtwn8723be_native.c", "rtwn8723be_net80211.c",
)
EXPECTED_SOURCE_ONLY_CALLBACKS = (
    "register_ieee80211", "init_rfkill", "bt_prepare", "dm_init",
)
FILE_RULE = re.compile(
    r"^file\s+dev/pci/(rtwn8723be_[A-Za-z0-9_]+\.c)\s+rtwn8723be_native\s*$",
    re.M,
)

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-config", type=Path,
                        default=OWNER / "rtl-native-config-48-20261010")
    args = parser.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        parser.error("HP-only frozen reference audit; not a workstation host model")
    if os.geteuid() == 0:
        parser.error("Do not run as root: no kernel/root staging modifications")
    output = args.output.resolve()
    if output.exists() or output.parent != OWNER or not output.name.startswith("rtl-runtime-audit-"):
        parser.error("Require a fresh rtl-runtime-audit-* owner-owned JSON output")
    checked = {}
    for name in FROZEN_18:
        actual = ORIGINAL / name
        saved = FROZEN / name
        if not saved.is_file() or not actual.is_file():
            parser.error("reference source missing: " + name)
        match = actual.read_bytes() == saved.read_bytes()
        checked[name] = {
            "source_sha256": sha256(actual),
            "reference_sha256": sha256(saved),
            "byte_exact": match,
            "bytes": actual.stat().st_size,
        }
        if not match:
            parser.error("HP reference drift: " + name)
    current_files = FILE_RULE.findall(MANIFEST.read_text())
    frozen_files = FILE_RULE.findall(ROOT_FILES.read_text())
    if len(current_files) != 42 or len(frozen_files) != 48:
        parser.error(f"unexpected manifest selection: github={len(current_files)}, HP={len(frozen_files)}")
    if len(set(current_files)) != len(current_files) or len(set(frozen_files)) != len(frozen_files):
        parser.error("duplicate source selection in native files")
    only_hp = sorted(set(frozen_files) - set(current_files))
    only_github = sorted(set(current_files) - set(frozen_files))
    if len(only_hp) != 7 or only_github != ["rtwn8723be_btc_providers_native.c"]:
        parser.error("unreviewed manifest delta, cannot reuse old reconcile decision")
    all_current = ROOT / "src"
    modified_common = []
    equal_common = []
    for name in sorted(set(current_files) & set(frozen_files)):
        new = all_current / name
        old = ORIGINAL / name
        if not new.is_file() or not old.is_file():
            parser.error("selected source missing: " + name)
        row = {"name": name, "github_sha256": sha256(new),
               "hp_sha256": sha256(old)}
        (modified_common if row["github_sha256"] != row["hp_sha256"]
         else equal_common).append(row)
    current_ops = (all_current / "rtwn8723be_netbsd.c").read_text()
    older_ops = (ORIGINAL / "rtwn8723be_netbsd.c").read_text()
    callback_rows = {}
    for name in EXPECTED_SOURCE_ONLY_CALLBACKS:
        pat = re.compile(r"\." + name + r"\s*=\s*(rtwn8723be_runtime_[A-Za-z0-9_]+)")
        root_callbacks = pat.findall(older_ops)
        now_callbacks = pat.findall(current_ops)
        if len(root_callbacks) != 1 or now_callbacks:
            parser.error("native callback ownership changed; manual review: " + name)
        callback_rows[name] = {
            "older_hp_owner": root_callbacks[0],
            "github_current_owner": None,
            "port_complete": False,
        }
    cfg = args.native_config.resolve()
    generated = cfg / "Makefile"
    if not generated.is_file() or cfg.parent != OWNER:
        parser.error("owner-isolated native config Makefile missing")
    generated_text = generated.read_text()
    configured_only = {}
    for name in only_hp:
        selected = ("dev/pci/" + name) in generated_text
        configured_only[name] = selected
        if not selected:
            parser.error("generated candidate Kconfig missing HP callback owner source: " + name)
    state = {
        "state": "REFERENCE_AUDIT_PASS_NOT_MERGED",
        "scope": "HP-only immutable 2026-10-06 runtime recovery vs 2026-10-10 source",
        "current_git_commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "frozen_reference_files": len(FROZEN_18),
        "frozen_references_byte_exact": all(v["byte_exact"] for v in checked.values()),
        "current_selected_c": len(current_files),
        "older_hp_selected_c": len(frozen_files),
        "older_hp_extra_c": only_hp,
        "github_extra_c": only_github,
        "unchanged_common": len(equal_common),
        "modified_common": modified_common,
        "modified_common_count": len(modified_common),
        "callbacks": callback_rows,
        "isolation": {"native_config": str(cfg), "extra_generated_rules": configured_only},
        "warning": (
            "No merge, kernel link, net80211 registration, IRQ, DMA, "
            "WPA2 association or radio operation verified. The old HP "
            "runtime must be reconciled with newer TX DMA/RF cleanup "
            "and teardown before enabling PCI attach."
        ),
    }
    output.write_text(json.dumps(state, indent=2) + "\n")
    os.chmod(output, 0o600)
    print("HP_RUNTIME_REFERENCE_SOURCE_AUDIT_PASS", len(FROZEN_18),
          "snapshots", len(current_files), "current", len(frozen_files),
          "older", len(modified_common), "differing common",
          len(only_hp), "missing current", "NO_ACTIVE_CALLBACK_BINDINGS")
    print("OUTPUT", output)

if __name__ == "__main__":
    main()
