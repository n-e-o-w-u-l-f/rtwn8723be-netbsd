#!/usr/bin/env python3
"""Compile the selected RTL native WIP C files with HP NetBSD F77 kernel flags.

The validated working F77 kernel and /usr/src are inputs ONLY. This tool
replays the real F77 compiler recipe after replacing solely its input C file
and output object into a new private owner directory. No kernel install,
root file mutation, reboot or claim of selected-kernel full link is made.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import shlex
import socket
import subprocess

ROOT=Path(__file__).resolve().parents[1]
F77=Path("/usr/obj/sys/arch/amd64/compile/RTWN8723BE-F77-LINUX-EFUSE-MAP")
MAKE=Path("/usr/tools/bin/nbmake-amd64")
CC="/usr/tools/bin/x86_64--netbsd-gcc"
SOURCE=Path("/usr/src/sys/dev/pci/rtwn8723be.c")
MANIFEST=ROOT/"config/files.rtwn8723be_native"
SELECT=re.compile(r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native\s*$",re.M)

def digest(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main()->None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--only",action="append",required=True,
                    help="Selected exact native C basename, repeatable")
    a=ap.parse_args()
    if platform.system()!="NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        ap.error("only real HP NetBSD may run the native compiler gate")
    if not F77.joinpath("machine/cdefs.h").is_file() or not MAKE.is_file() or not SOURCE.is_file():
        ap.error("live F77 native compiler environment unavailable")
    selected=SELECT.findall(MANIFEST.read_text())
    if len(selected)!=50 or len(set(selected))!=50:
        ap.error("current WIP manifest must have exactly 50 distinct native units")
    units=list(dict.fromkeys(a.only))
    if len(units)!=len(a.only) or not all(x in selected for x in units):
        ap.error("--only must name unique manifest-selected WIP C units")
    out=a.output.resolve()
    if out.exists() or out.parent!=ROOT.parent.resolve() or not out.name.startswith("rtl-native-f77-"):
        ap.error("must use new rtl-native-f77-* directory adjacent to checkout")
    dry=subprocess.run([str(MAKE),"-C",str(F77),"-n","-B","rtwn8723be.o"],
                       text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
    if dry.returncode:
        ap.error("F77 recipe unavailable: "+dry.stdout[-400:])
    commands=[]
    for line in dry.stdout.splitlines():
        for part in re.split(r"\s+&&\s+",line):
            s=part.strip()
            if not s.startswith(CC+" ") or " -c " not in s or " -o " not in s:
                continue
            argv=shlex.split(s)
            if (argv[argv.index("-c")+1]==str(SOURCE) and
                argv[argv.index("-o")+1]=="rtwn8723be.o"):
                commands.append(argv)
    if len(commands)!=1:
        ap.error("F77 compiler recipe ambiguous or source/output mismatch")
    out.mkdir(mode=0o700)
    state={"state":"RUNNING","host":socket.gethostname(),"f77_source":str(SOURCE),
           "f77_recipe_sha256":hashlib.sha256(" ".join(commands[0]).encode()).hexdigest(),
           "manifest_sha256":digest(MANIFEST),"selected_count":len(selected),
           "units":[],"started":datetime.now(timezone.utc).isoformat(),
           "limitation":"ABI-only compiler test; not kernel object selection/link or hardware"}
    def save()->None:
        p=out/"status.tmp"
        p.write_text(json.dumps(state,indent=2)+"\n")
        p.replace(out/"status.json")
    save()
    try:
        for filename in units:
            source=ROOT/"src"/filename
            if not source.is_file():
                raise RuntimeError("selected source missing: "+filename)
            obj=out/(source.stem+".o")
            command=commands[0].copy()
            command[command.index("-c")+1]=str(source)
            command[command.index("-o")+1]=str(obj)
            sha=digest(source)
            run=subprocess.run(command,cwd=F77,text=True,stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,timeout=180)
            (out/(source.stem+".log")).write_text(run.stdout)
            record={"file":filename,"source_sha256":sha,
                    "source_unchanged":digest(source)==sha,
                    "compiler_exit":run.returncode,
                    "object_bytes":obj.stat().st_size if obj.is_file() else 0,
                    "object_sha256":digest(obj) if obj.is_file() else None,
                    "diagnostics":[l[:500] for l in run.stdout.splitlines()
                                   if "error:" in l or "warning:" in l][:12]}
            state["units"].append(record)
            save()
            print("HP_F77_ABI",filename,"exit",run.returncode,
                  "bytes",record["object_bytes"],flush=True)
            if run.returncode or not record["object_bytes"] or not record["source_unchanged"]:
                raise RuntimeError("native F77 ABI object failed: "+filename)
        state["state"]="ABI_ONLY_PASSED"
    except Exception as exc:
        state["state"]="FAILED"
        state["error"]=str(exc)
        raise
    finally:
        state["finished"]=datetime.now(timezone.utc).isoformat()
        save()
    print("HP_F77_NATIVE_WIP_ABI_ONLY_PASS",len(units),flush=True)

if __name__=="__main__":
    main()
