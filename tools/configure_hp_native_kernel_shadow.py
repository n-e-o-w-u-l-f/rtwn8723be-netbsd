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
MANIFEST = ROOT / "config/files.rtwn8723be_native"
SELECTED = re.compile(
    r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native\s*$", re.M)
OLD_DECLARATION = re.compile(
    r"^\s*(?:device\s+rtwn8723be_native:|"
    r"attach\s+rtwn8723be_native\s+at\s+pci|"
    r"file\s+dev/pci/rtwn8723be_\w+\.c\s+rtwn8723be_native\s*$)")
PRIVATE_CONFIG_NAME = "RTWN8723BE-NATIVE-SHADOW"
NATIVE_C_UNIT_COUNT = 44
# Generated kernel compiler rules use these paths relative to sys/.. .  Keep
# this list explicit so a dry-run cannot hide a missing immutable sibling.
COMMON_REQUIRED_RELATIVE_PATHS = (
    "include/prop/proplib.h",
    "lib/libx86emu",
    "lib/libc/misc",
    "lib/libc/quad",
    "lib/libc/string",
    "lib/libc/arch/x86_64/string",
    "lib/libc/arch/x86_64/atomic",
    "lib/libc/hash/sha3",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def default_hp_shadow_inputs() -> dict[str, Path]:
    """Return the immutable NetBSD 11 source and tool locations on HP."""
    return {
        "sys": Path("/usr/src/sys"),
        "nbconfig": Path("/usr/tools/bin/nbconfig"),
        "make": Path("/usr/tools/bin/nbmake-amd64"),
    }


def hp_shadow_paths(inputs: dict[str, Path]) -> dict[str, Path]:
    """Derive only read-only source paths from the HP tool locations."""
    source_sys = inputs["sys"]
    return {
        "pci_manifest": source_sys / "dev/pci/files.pci",
        "baseline_config": source_sys / "arch/amd64/conf/GENERIC",
        # Generated kernel compiler flags use sys/../common/include for
        # <prop/proplib.h>.  The private sys overlay therefore needs this
        # immutable sibling, too; it is never copied or made writable.
        "common": source_sys.parent / "common",
    }


def render_private_pci_manifest(base: str, native_manifest: str) -> str:
    """Replace only native declarations with the canonical project manifest."""
    selected = SELECTED.findall(native_manifest)
    declarations = native_manifest.splitlines()
    if (len(selected) != NATIVE_C_UNIT_COUNT or
            len(set(selected)) != NATIVE_C_UNIT_COUNT or
            sum(line.startswith("device  rtwn8723be_native:")
                for line in declarations) != 1 or
            sum(line.startswith("attach  rtwn8723be_native at pci")
                for line in declarations) != 1):
        raise RuntimeError("canonical native manifest is incomplete")
    filtered = [line for line in base.splitlines()
                if not OLD_DECLARATION.match(line)]
    return "\n".join(filtered).rstrip("\n") + "\n\n" + \
        native_manifest.rstrip("\n") + "\n"


def private_dryrun_rule_present(output: str, source_name: str,
    objname: str, shadow: Path) -> bool:
    """Accept only a compiler rule wholly rooted in the private overlay."""
    return (" -c " in output and " -o " + objname in output and
            (shadow / "dev/pci" / source_name).as_posix() in output and
            "/usr/src/" not in output)


def render_private_config(baseline_include: str) -> str:
    """Keep an unbootable i915 path out of every private RTL candidate."""
    return (
        f'include "{baseline_include}"\n'
        f'ident "{PRIVATE_CONFIG_NAME}"\n'
        'no rtwn*\n'
        'no i915drmkms*\n'
        'rtwn8723be_native* at pci? dev ? function ?\n')


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
    inputs = default_hp_shadow_inputs()
    source_sys = inputs["sys"]
    nbconfig = inputs["nbconfig"]
    make = inputs["make"]
    paths = hp_shadow_paths(inputs)
    old_pci = paths["pci_manifest"]
    baseline_config = paths["baseline_config"]
    source_common = paths["common"]
    if (not baseline_config.is_file() or not nbconfig.is_file() or
            not make.is_file()):
        parser.error("immutable NetBSD 11 source/config/tools unavailable")
    if not old_pci.is_file():
        parser.error("NetBSD PCI manifest unavailable")
    if any(not (source_common / relative).exists()
           for relative in COMMON_REQUIRED_RELATIVE_PATHS):
        parser.error("immutable NetBSD common include tree unavailable")
    selected = SELECTED.findall(MANIFEST.read_text())
    if (len(selected) != NATIVE_C_UNIT_COUNT or
            len(set(selected)) != NATIVE_C_UNIT_COUNT):
        parser.error("unexpected native C-unit manifest cardinality")
    expected_c = {p.name for p in (ROOT / "src").glob("rtwn8723be_*.c")}
    if not set(selected).issubset(expected_c):
        parser.error("native manifest references unknown repository sources")
    out = args.output.resolve()
    if out.exists() or out.parent != ROOT.parent.resolve() or not out.name.startswith("rtl-kconfig-"):
        parser.error("must use a NEW rtl-kconfig-* directory alongside HP checkouts")
    out.mkdir(mode=0o700)
    shadow = out / "sys"
    out_obj = out / "obj"
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
        # Keep the relative include location used by generated kernel build
        # rules (sys/../common/include), while retaining the original tree as
        # the immutable owner of every non-project file.
        private_common = out / "common"
        private_common.symlink_to(source_common, target_is_directory=True)
        if (not private_common.is_symlink() or
                private_common.resolve() != source_common.resolve()):
            raise RuntimeError("private common sibling did not resolve to source")
        populate_links(source_sys, shadow, {"dev"})
        for name in ("arch", "conf", "external", "lib"):
            private = shadow / name
            original = source_sys / name
            if (not private.is_symlink() or
                    private.resolve() != original.resolve()):
                raise RuntimeError("private source sibling invalid: " + name)
        populate_links(source_sys / "dev", shadow / "dev", {"pci"})
        # Root source is NEVER a writable symlink path or hardlink target.
        # All owners under the virtual dev/pci dir point to reviewed current
        # GitHub text, with remaining ordinary NetBSD files left untouched.
        current = {
            p.name: p for p in (ROOT / "src").iterdir()
            if p.is_file() and p.name.startswith("rtwn8723be_")
            and p.suffix in {".c", ".h", ".inc"}
        }
        populate_links(source_sys / "dev/pci", shadow / "dev/pci",
                       {"files.pci"} | set(current))
        for name, source in current.items():
            (shadow / "dev/pci" / name).symlink_to(source)

        shadow_manifest = shadow / "dev/pci/files.pci"
        shadow_manifest.write_text(render_private_pci_manifest(
            old_pci.read_text(), MANIFEST.read_text()))
        generated = SELECTED.findall(shadow_manifest.read_text())
        if generated != selected or sha(old_pci) != old_hash:
            raise RuntimeError("shadow source closure invalid or original source changed")

        private_config = out / PRIVATE_CONFIG_NAME
        baseline_include = baseline_config.relative_to(source_sys).as_posix()
        private_config.write_text(render_private_config(baseline_include))
        command = [str(nbconfig), "-s", str(shadow), "-b", str(out_obj),
                   str(private_config)]
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
        # Every manifest-selected source must have an actual generated rule.
        # Do not special-case the old six missing BTC rules: that hid later
        # selection drift and made historical smaller checkpoints look current.
        for name in selected:
            objname = name[:-2] + ".o"
            dry = subprocess.run([str(make), "-C", str(out_obj),
                                  "-n", "-B", objname],
                                 cwd=out, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, timeout=90)
            (out / (name[:-2] + ".dryrun.log")).write_text(dry.stdout)
            valid = (dry.returncode == 0 and
                     private_dryrun_rule_present(dry.stdout, name, objname,
                                                 shadow))
            checks.append({"name": name, "exit": dry.returncode,
                           "rule_present": valid})
            evidence["rules"] = checks
            save()
            if not valid:
                raise RuntimeError("missing native compile rule after regenerate: " + name)
        if sha(old_pci) != old_hash:
            raise RuntimeError("root native PCI source was unexpectedly modified")
        evidence["state"] = (
            f"CONFIGURED_{NATIVE_C_UNIT_COUNT}_RULES_DRYRUN_PASS")
        evidence["limit"] = (
            "Candidate-only NetBSD kernel config & Makefile; source selection "
            "checked for every selected source. NO full native "
            "compile from this new shadow, kernel "
            "final link, runtime/WPA2 or actual hardware acceptance."
        )
        print(f"HP_RTL_ISOLATED_CONFIG_{NATIVE_C_UNIT_COUNT}_SELECTED_RULES_PASS",
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
