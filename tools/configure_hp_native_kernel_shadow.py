#!/usr/bin/env python3
"""Prepare and configure a PRIVATE HP NetBSD native kernel source overlay.

The pinned root-owned NetBSD source tree, native tools, F77 kernel and live
network remain UNTOUCHED. All selected RTL native C and H files come from
the clean GitHub checkout; non-owned NetBSD files are read-only symlinks.
Never run as root; never install or boot this candidate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STAGE = Path("/root/hp-driver-port-20261005/netbsd-native/sys")
CONFIG = STAGE / "arch/amd64/conf/HP-RTL-NATIVE-20261005"
NBTCONFIG = Path("/root/hp-driver-port-20261005/native-tools/bin/nbconfig")
MAKE = Path("/root/hp-driver-port-20261005/native-tools/bin/nbmake-amd64")
MANIFEST = ROOT / "config/files.rtwn8723be_native"
SELECTED = re.compile(
    r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native\s*$", re.M)
OLD_FILE = re.compile(
    r"^file\s+dev/pci/rtwn8723be_\w+\.c\s+rtwn8723be_native\s*$")
ROOT_CONFIG_NAME = "HP-RTL-NATIVE-20261005"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def populate_links(base: Path, dest: Path, ignore: set[str]) -> None:
    dest.mkdir(mode=0o700)
    for item in base.iterdir():
        if item.name in ignore:
            continue
        if item.name == "." or item.name == ".." or (dest / item.name).exists():
            raise RuntimeError("ambiguous original overlay tree entry")
        (dest / item.name).symlink_to(item)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        parser.error("REFUSED: NetBSD kernel configure is HP-only")
    if os.geteuid() == 0:
        parser.error("REFUSED: owner workspace only, no root/privilege escalation")
    if not CONFIG.is_file() or not NBTCONFIG.is_file() or not MAKE.is_file():
        parser.error("unchanged native NetBSD source/config/tools unavailable")
    if not (STAGE / "dev/pci/files.pci").is_file():
        parser.error("pinned native PCI manifest absent")
    selected = SELECTED.findall(MANIFEST.read_text())
    if len(selected) != 42 or len(set(selected)) != 42:
        parser.error("expected exactly 42 unique native C units")
    expected_c = {p.name for p in (ROOT / "src").glob("rtwn8723be_*.c")}
    if not set(selected).issubset(expected_c):
        parser.error("native manifest references unknown repository sources")
    out = args.output.resolve()
    if out.exists() or out.parent != ROOT.parent.resolve() or not out.name.startswith("rtl-kconfig-"):
        parser.error("must use a NEW rtl-kconfig-* directory alongside HP checkouts")
    out.mkdir(mode=0o700)
    shadow = out / "sys"
    out_obj = out / "obj"
    old_pci = STAGE / "dev/pci/files.pci"
    old_hash = sha(old_pci)
    status = out / "status.json"
    evidence = {
        "state": "RUNNING",
        "host": socket.gethostname(),
        "source_head": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "selected_sources": selected,
        "owner_shadow": str(shadow),
        "owner_objdir": str(out_obj),
        "baseline_stage_sha256": old_hash,
        "manifest_sha256": sha(MANIFEST),
        "started": datetime.now(timezone.utc).isoformat(),
    }
    def save():
        temp = out / "status.tmp"
        temp.write_text(json.dumps(evidence, indent=2) + "\n")
        temp.replace(status)
    save()

    try:
        populate_links(STAGE, shadow, {"dev"})
        populate_links(STAGE / "dev", shadow / "dev", {"pci"})
        # Root source is NEVER a writable symlink path or hardlink target.
        # All owners under the virtual dev/pci dir point to reviewed current
        # GitHub text, with remaining ordinary NetBSD files left untouched.
        current = {
            p.name: p for p in (ROOT / "src").iterdir()
            if p.is_file() and p.name.startswith("rtwn8723be_")
            and p.suffix in {".c", ".h"}
        }
        populate_links(STAGE / "dev/pci", shadow / "dev/pci",
                       {"files.pci"} | set(current))
        for name, source in current.items():
            (shadow / "dev/pci" / name).symlink_to(source)

        lines = old_pci.read_text().splitlines()
        previous = [line for line in lines if OLD_FILE.match(line)]
        if len(previous) < 36:
            raise RuntimeError("unexpected original native PCI manifest baseline")
        filtered = [line for line in lines if not OLD_FILE.match(line)]
        if sum(line.strip().startswith("device  rtwn8723be_native:") for line in filtered) != 1:
            raise RuntimeError("native device definition nonunique")
        if sum(line.strip().startswith("attach  rtwn8723be_native at pci") for line in filtered) != 1:
            raise RuntimeError("native attachment definition nonunique")
        filtered.extend([
            "",
            "# HP owner-only source-derived RTL candidate: exactly 42 C units",
            "# No native device installed/started; this changes no root files.",
        ])
        filtered.extend(f"file dev/pci/{name} rtwn8723be_native" for name in selected)
        shadow_manifest = shadow / "dev/pci/files.pci"
        shadow_manifest.write_text("\n".join(filtered) + "\n")
        generated = SELECTED.findall(shadow_manifest.read_text())
        if generated != selected or sha(old_pci) != old_hash:
            raise RuntimeError("shadow source closure invalid or original source changed")

        command = [str(NBTCONFIG), "-s", str(shadow), "-b", str(out_obj), str(CONFIG)]
        cp = subprocess.run(command, cwd=out, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=180)
        (out / "config.log").write_text(cp.stdout)
        evidence["config_exit"] = cp.returncode
        evidence["config_log_sha256"] = sha(out / "config.log")
        if cp.returncode != 0:
            raise RuntimeError("NetBSD native config rejected private shadow: " +
                               cp.stdout[-1200:])
        makefile = out_obj / "Makefile"
        if not makefile.is_file():
            raise RuntimeError("native config did not create a Makefile")
        checks = []
        # Test all newly selected native BTC rules, not only the first one.
        for name in (
            "rtwn8723be_btc_mp_native.c", "rtwn8723be_btc1.c",
            "rtwn8723be_btc2.c", "rtwn8723be_btc_engine.c",
            "rtwn8723be_btc_native.c",
            "rtwn8723be_btc_providers_native.c",
        ):
            objname = name[:-2] + ".o"
            dry = subprocess.run([str(MAKE), "-C", str(out_obj),
                                  "-n", "-B", objname],
                                 cwd=out, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, timeout=90)
            (out / (name[:-2] + ".dryrun.log")).write_text(dry.stdout)
            valid = (dry.returncode == 0 and
                     " -c " in dry.stdout and
                     "dev/pci/" + name in dry.stdout and
                     " -o " + objname in dry.stdout)
            checks.append({"name": name, "exit": dry.returncode,
                           "rule_present": valid})
            evidence["rules"] = checks
            save()
            if not valid:
                raise RuntimeError("missing native compile rule after regenerate: " + name)
        if sha(old_pci) != old_hash:
            raise RuntimeError("root native PCI source was unexpectedly modified")
        evidence["state"] = "CONFIGURED_42_RULES_DRYRUN_PASS"
        evidence["limit"] = (
            "Candidate-only NetBSD kernel config & Makefile; source selection "
            "checked, 6 previously missing native compilation rules resolved. "
            "NO 42-object full native compile from this new shadow, kernel "
            "final link, runtime/WPA2 or actual hardware acceptance."
        )
        print("HP_RTL_ISOLATED_CONFIG_42_SELECTED_SIX_RULES_PASS",
              out_obj, flush=True)
    except Exception as e:
        evidence["state"] = "FAILED"
        evidence["error"] = str(e)
        raise
    finally:
        evidence["finished"] = datetime.now(timezone.utc).isoformat()
        evidence["unchanged_original_pci"] = sha(old_pci) == old_hash
        save()

if __name__ == "__main__":
    main()
