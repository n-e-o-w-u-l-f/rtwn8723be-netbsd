#!/usr/bin/env python3
"""Create a private HP NetBSD source/config overlay selecting 50 RTL native units.

Inputs: *unchanged* /usr/src/sys, /usr/src/common, /usr/tools and
/usr/obj/destdir.amd64. Output only inside new owner directory adjacent to
the WIP checkout. This does not install a kernel, boot, touch PCI or replace
the F77 fallback. It intentionally disables i915drmkms in this RTL-only
candidate to prevent conflating F83/F84 black-screen with WLAN testing.
"""
from __future__ import annotations
import argparse,hashlib,json,os,platform,re,socket,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=Path("/usr/src/sys")
COMMON=Path("/usr/src/common")
BASE=SRC/"dev/pci/files.pci"
MAKE_ORIG=Path("/usr/tools/bin/nbmake-amd64")
CONFIG=Path("/usr/tools/bin/nbconfig")
SELECT=re.compile(r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native\s*$",re.M)

def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def mirror(base:Path,dest:Path,omit:set[str]):
    dest.mkdir(mode=0o700)
    for source in base.iterdir():
        if source.name in omit: continue
        path=dest/source.name
        if path.exists() or path.is_symlink(): raise RuntimeError("overlay collision "+str(path))
        path.symlink_to(source,target_is_directory=source.is_dir())
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    if platform.system()!="NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        ap.error("HP NetBSD only")
    if os.geteuid()==0: ap.error("owner-only, no root")
    if not all(p.is_file() for p in (BASE,CONFIG,MAKE_ORIG,
                                    SRC/"arch/amd64/conf/GENERIC",
                                    COMMON/"include/prop/proplib.h")):
        ap.error("original NetBSD sources/tools missing")
    wip=(ROOT/"config/files.rtwn8723be_native").read_text()
    units=SELECT.findall(wip)
    if len(units)!=50 or len(set(units))!=50: ap.error("50 unique sources required")
    if any(not (ROOT/"src"/name).is_file() for name in units):
        ap.error("source missing")
    baseline=BASE.read_text()
    if "rtwn8723be_native" in baseline: ap.error("native source already selected; reconcile")
    out=a.output.resolve()
    if out.exists() or out.parent!=ROOT.parent.resolve() or not out.name.startswith("rtl-kconfig-live-"):
        ap.error("new rtl-kconfig-live-* sibling directory required")
    rootsha=sha(BASE)
    out.mkdir(mode=0o700)
    status=out/"status.json"
    state={"state":"STAGING","host":socket.gethostname(),
           "root_pci_sha256":rootsha,"selected":units,
           "output":str(out),"started":datetime.now(timezone.utc).isoformat()}
    def save():
        t=status.with_suffix(".tmp");t.write_text(json.dumps(state,indent=2)+"\n");t.replace(status)
    save()
    try:
        (out/"common").symlink_to(COMMON,target_is_directory=True)
        mirror(SRC,out/"sys",{"dev"})
        mirror(SRC/"dev",out/"sys/dev",{"pci"})
        owned={p.name:p for p in (ROOT/"src").iterdir() if p.is_file() and
               p.name.startswith("rtwn8723be_") and p.suffix in (".c",".h")}
        mirror(SRC/"dev/pci",out/"sys/dev/pci",{"files.pci"}|set(owned))
        for name,path in owned.items():
            (out/"sys/dev/pci"/name).symlink_to(path)
        (out/"sys/dev/pci/files.pci").write_text(
            baseline.rstrip()+"\n\n# HP RTL WIP-50 isolated source selection\n"+wip+"\n")
        config=out/"HP-RTL-WIP50"
        config.write_text('include "arch/amd64/conf/GENERIC"\n'
                          'ident "HP-RTL-WIP50-SAFE-GENFB"\n'
                          'no rtwn*\n'
                          'no i915drmkms*\n'
                          'rtwn8723be_native* at pci? dev ? function ?\n')
        p=subprocess.run([str(CONFIG),"-s",str(out/"sys"),"-b",str(out/"obj"),str(config)],
            text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        (out/"config.log").write_text(p.stdout)
        state["config_exit"]=p.returncode
        if p.returncode or not (out/"obj/Makefile").is_file():
            raise RuntimeError("NetBSD config failed: "+p.stdout[-1600:])
        # Root source is always used as read-only and DESTDIR unchanged.
        wrapper=MAKE_ORIG.read_text()
        wrapper=wrapper.replace('NETBSDSRCDIR=/usr/src;',f'NETBSDSRCDIR={out};')
        wrapper=wrapper.replace("MAKEOBJDIR='${.CURDIR:C,^/usr/src,/usr/obj,}'",
                                "MAKEOBJDIR='${.CURDIR:C,^"+str(out)+","+str(out/"obj")+",}'")
        wrapper_path=out/"nbmake-owner"
        wrapper_path.write_text(wrapper);wrapper_path.chmod(0o700)
        rules=[]
        for name in ("rtwn8723be_native.c","rtwn8723be_netbsd.c",
                     "rtwn8723be_runtime.c","rtwn8723be_net80211.c",
                     "rtwn8723be_rx_native.c","rtwn8723be_net80211_tx.c",
                     "rtwn8723be_reserved_native.c"):
            obj=name[:-2]+".o"
            dry=subprocess.run([str(wrapper_path),"-C",str(out/"obj"),"-n","-B",obj],
                               capture_output=True,text=True,timeout=100)
            present=dry.returncode==0 and " -c " in dry.stdout and (
                "dev/pci/"+name in dry.stdout)
            rules.append({"file":name,"object":obj,"rule":present,"exit":dry.returncode})
            save()
            if not present: raise RuntimeError("missing compiled NetBSD rule: "+name+" "+dry.stdout[-550:])
        state["rules"]=rules
        if sha(BASE)!=rootsha:raise RuntimeError("NetBSD root source changed during config")
        state["state"]="CONFIGURED_50_WIP_RULES_PASS"
        print("HP_RTL50_NETBSD_OWNER_KCONFIG_PASS",len(units),len(rules),out,flush=True)
    except Exception as ex:
        state["state"]="FAILED";state["error"]=str(ex)
        raise
    finally:
        state["root_source_unchanged"]=sha(BASE)==rootsha
        state["finished"]=datetime.now(timezone.utc).isoformat()
        save()
if __name__=="__main__":
    main()
