#!/usr/bin/env python3
"""Compile exact current RTL native owner source under the real HP NetBSD ABI.

A read-only dry-run of the previously configured NetBSD native kernel
Makefile provides the real cross-compiler arguments. The only -c and -o
paths are redirected to current repository files and private new
output objects; never install, link a boot kernel, or modify /usr/src.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STAGE = Path("/root/hp-driver-port-20261005")
NATIVE_SRC = STAGE / "netbsd-native/sys/dev/pci"
OBJDIR = STAGE / "native-obj"
MAKE = STAGE / "native-tools/bin/nbmake-amd64"
COMPILER = str(STAGE / "native-tools/bin/x86_64--netbsd-gcc")
MANIFEST = ROOT / "config/files.rtwn8723be_native"
RULE = re.compile(r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native\s*$", re.M)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", help="Single exact native source filename")
    parser.add_argument("--abi-only", action="store_true",
                        help="For missing generated Makefile rules, compile with exact "
                             "native TX unit kernel-C flags; result is ABI source-only "
                             "and does NOT satisfy kernel configuration/link")
    args = parser.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        parser.error("REFUSED: only actual HP/NetBSD may run this compiler gate")
    if os.geteuid() == 0:
        parser.error("REFUSED: use a normal owner account, never root or kernel installer")
    if not (OBJDIR / "machine/cdefs.h").is_file() or not MAKE.is_file():
        parser.error("original generated native build tree is unavailable")
    all_units = RULE.findall(MANIFEST.read_text())
    if len(all_units) != 42 or len(set(all_units)) != 42:
        parser.error("unexpected native source closure; verify current manifest")
    if args.only is not None:
        if args.only not in all_units:
            parser.error("--only must name exactly one selected manifest source")
        all_units = [args.only]
    destination = args.output.resolve()
    if destination.exists() or destination.parent != ROOT.parent.resolve() or not destination.name.startswith("rtl-native-"):
        parser.error("output must be a fresh rtl-native-* sibling of both source checkouts")
    destination.mkdir(mode=0o700)
    status = destination / "status.json"
    result = {
        "state": "RUNNING", "host": socket.gethostname(),
        "source_repo": str(ROOT), "manifest_sha256": sha(MANIFEST),
        "selection_count": len(all_units),
        "compiler": COMPILER,
        "abi_only": bool(args.abi_only),
        "generated_rules_missing": [], "base_kernel_stage": str(STAGE),
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "units": []
    }
    def save():
        temp = destination / "status.tmp"
        temp.write_text(json.dumps(result, indent=2) + "\n")
        temp.replace(status)
    save()
    try:
        for filename in all_units:
            source = ROOT / "src" / filename
            frozen = NATIVE_SRC / filename
            if not source.is_file():
                raise RuntimeError("missing current native source: " + filename)
            if not frozen.is_file() and not args.abi_only:
                raise RuntimeError("missing source from generated kernel tree: " + filename)
            objname = source.stem + ".o"
            dryrun = subprocess.run(
                [str(MAKE), "-C", str(OBJDIR), "-n", "-B", objname],
                cwd=ROOT, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=90)
            rule_mode = "GENERATED_MAKE_RULE"
            compiler_src = frozen
            compiler_obj = objname
            if dryrun.returncode != 0:
                missing_rule = "don't know how to make " + objname
                if not args.abi_only or missing_rule not in dryrun.stdout:
                    raise RuntimeError("NetBSD make dry-run failed for " + filename + ": " + dryrun.stdout[-500:])
                # This proves the ABI/compiler against already-generated kernel
                # headers, but is NOT evidence that the owning kernel config
                # selected the added source file. Keep the missing rule explicit.
                rule_mode = "ABI_ONLY_MISSING_GENERATED_MAKE_RULE"
                compiler_src = NATIVE_SRC / "rtwn8723be_tx_native.c"
                compiler_obj = "rtwn8723be_tx_native.o"
                dryrun = subprocess.run(
                    [str(MAKE), "-C", str(OBJDIR), "-n", "-B", compiler_obj],
                    cwd=ROOT, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, timeout=90)
                if dryrun.returncode != 0:
                    raise RuntimeError("native generic kernel compile flags unavailable")
                result["generated_rules_missing"].append(filename)
            compiled = []
            for line in dryrun.stdout.splitlines():
                for part in re.split(r"\s+&&\s+", line):
                    cmd = part.strip()
                    if cmd.startswith(COMPILER + " ") and " -c " in cmd and " -o " in cmd:
                        parts = shlex.split(cmd)
                        if "-c" in parts and parts[parts.index("-c") + 1] == str(compiler_src):
                            compiled.append(parts)
            if len(compiled) != 1:
                raise RuntimeError("native compiler command missing/ambiguous for " + filename)
            command = compiled[0]
            if command[0] != COMPILER or command[command.index("-o") + 1] != compiler_obj:
                raise RuntimeError("compiler/output mismatch")
            objout = destination / objname
            command[command.index("-c") + 1] = str(source)
            command[command.index("-o") + 1] = str(objout)
            old_sha = sha(source)
            compiled_process = subprocess.run(
                command, cwd=OBJDIR, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=150)
            logfile = destination / (source.stem + ".log")
            logfile.write_text(compiled_process.stdout)
            entry = {
                "source": filename, "exit": compiled_process.returncode,
                "rule_mode": rule_mode,
                "frozen_staging_source_present": frozen.is_file(),
                "source_sha256": old_sha,
                "source_unchanged": sha(source) == old_sha,
                "object_size": objout.stat().st_size if objout.is_file() else 0,
                "object_sha256": sha(objout) if objout.is_file() else None,
                "log_sha256": sha(logfile)
            }
            result["units"].append(entry)
            save()
            print("HP_RTL_NATIVE_OBJECT", filename, "exit", compiled_process.returncode,
                  "bytes", entry["object_size"], flush=True)
            if compiled_process.returncode != 0 or not entry["source_unchanged"] or not entry["object_size"]:
                # Preserve durable evidence, no blind retry or partial success claim.
                raise RuntimeError("native object compile/verification failed: " + filename)
        result["state"] = ("ABI_ONLY_PASSED" if result["generated_rules_missing"]
                           else "PASSED")
        result["limitation"] = (
            "Native NetBSD kernel-C ABI objects ONLY. Missing generated "
            "Makefile rules remain open and are listed explicitly; no full "
            "kernel configuration/link, attach, Wi-Fi/WPA2, DMA/IRQ hardware, "
            "PM or reboot accepted."
        )
    except Exception as exc:
        result["state"] = "FAILED"
        result["error"] = str(exc)
        raise
    finally:
        result["finished"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    print(("HP_RTL_NATIVE_ABI_ONLY_OBJECTS_PASS__KCONFIG_OPEN"
           if result["generated_rules_missing"]
           else "HP_RTL_NATIVE_OBJECT_CLOSURE_PASS"),
          len(all_units), "missing_generated_rules",
          len(result["generated_rules_missing"]), destination)

if __name__ == "__main__":
    main()
