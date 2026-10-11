#!/usr/bin/env python3
"""Create a private HP NetBSD source/config overlay selecting 50 RTL native units.

Inputs: *unchanged* /usr/src/sys, /usr/src/common, /usr/tools and
/usr/obj/destdir.amd64. Output only inside new owner directory adjacent to
the WIP checkout. This does not install a kernel, boot, touch PCI or replace
the F77 fallback. It intentionally disables i915drmkms in this RTL-only
candidate to prevent conflating F83/F84 black-screen with WLAN testing.
"""
from __future__ import annotations
import argparse,hashlib,json,os,platform,re,shutil,socket,subprocess
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
    # The previous kernel linked successfully but used a pre-RX-filter
    # snapshot. Never give multiple source generations the SAME kernel
    # identity; require a clean, exact Git revision before staging.
    git_head=subprocess.run(
        ["git","-C",str(ROOT),"rev-parse","HEAD"],
        capture_output=True,text=True,timeout=20,check=True).stdout.strip()
    git_branch=subprocess.run(
        ["git","-C",str(ROOT),"branch","--show-current"],
        capture_output=True,text=True,timeout=20,check=True).stdout.strip()
    git_dirty=subprocess.run(
        ["git","-C",str(ROOT),"status","--porcelain=v1"],
        capture_output=True,text=True,timeout=20,check=True).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}",git_head):
        ap.error("invalid source commit identity")
    if git_dirty or git_branch != "wip/hp-rtl-runtime-48-merge-20261010":
        ap.error("source checkout must be clean and on the WIP branch")
    baseline=BASE.read_text()
    if "rtwn8723be_native" in baseline: ap.error("native source already selected; reconcile")
    out=a.output.resolve()
    if out.exists() or out.parent!=ROOT.parent.resolve() or not out.name.startswith("rtl-kconfig-live-"):
        ap.error("new rtl-kconfig-live-* sibling directory required")
    rootsha=sha(BASE)
    out.mkdir(mode=0o700)
    status=out/"status.json"
    state={"state":"STAGING","host":socket.gethostname(),
           "source_commit":git_head,
           "kernel_ident":"HP-RTL50-"+git_head[:12]+"-SAFE-GENFB",
           "root_pci_sha256":rootsha,"selected":units,
           "output":str(out),"started":datetime.now(timezone.utc).isoformat()}
    def save():
        t=status.with_suffix(".tmp");t.write_text(json.dumps(state,indent=2)+"\n");t.replace(status)
    save()
    try:
        (out/"common").symlink_to(COMMON,target_is_directory=True)
        mirror(SRC,out/"sys",{"dev"})
        mirror(SRC/"dev",out/"sys/dev",{"pci"})
        # The frozen BTC antenna algorithms include generated .inc sources
        # (e.g. rtwn8723be_btc1_linux.inc). They are owned text, not
        # compiler-generated outputs; omit them and the selected kernel
        # compile fails even when the 50 C manifest parses correctly.
        owned={p.name:p for p in (ROOT/"src").iterdir() if p.is_file() and
               p.name.startswith("rtwn8723be_") and p.suffix in (".c",".h",".inc")}
        # Never symlink mutable Git worktree source into a long-running
        # kernel build: an unrelated fast-forward during nbmake would mix
        # different commits into the same apparently source-pinned ELF.
        # Snapshot C, H and frozen Linux-generated .inc files byte-for-byte
        # under this private owner directory. The kernel build sees only
        # these copies and unchanged read-only NetBSD base source.
        owned_hashes={name:sha(path) for name,path in sorted(owned.items())}
        mirror(SRC/"dev/pci",out/"sys/dev/pci",{"files.pci"}|set(owned))
        for name,path in owned.items():
            dst=out/"sys/dev/pci"/name
            shutil.copyfile(path,dst)
            if not dst.is_file() or dst.is_symlink() or sha(dst)!=owned_hashes[name]:
                raise RuntimeError("source changed during copy: "+name)
        state["source_snapshot_sha256"]=owned_hashes
        state["source_snapshot_files"]=len(owned_hashes)
        state["source_snapshot_private_copies_pass"]=True
        save()
        (out/"sys/dev/pci/files.pci").write_text(
            baseline.rstrip()+"\n\n# HP RTL WIP-50 isolated source selection\n"+wip+"\n")
        config=out/"HP-RTL-WIP50"
        config.write_text('include "arch/amd64/conf/GENERIC"\n'
                          'ident "'+state["kernel_ident"]+'"\n'
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
        # Cross GCC's collect2 expects executable 'ld' in PATH, whereas
        # NetBSD build.sh installed only x86_64--netbsd-ld. The exact
        # failure was "collect2: fatal error: cannot find 'ld'" at
        # libkern.o with a clean 50-object native compile. An isolated
        # PATH and private symlink fix this toolchain lookup, not the
        # kernel source and not the installed host's linker.
        cross_cc=Path("/usr/tools/bin/x86_64--netbsd-gcc")
        cross_ld=Path("/usr/tools/bin/x86_64--netbsd-ld")
        if not cross_cc.is_file() or not cross_ld.is_file():
            raise RuntimeError("NetBSD target cross-gcc/linker unavailable")
        owner_tools=out/"toolchain"
        owner_tools.mkdir(mode=0o700)
        (owner_tools/"ld").symlink_to(cross_ld)
        old_exec='exec "${TOOLDIR}/bin/nbmake"'
        if old_exec not in wrapper:
            raise RuntimeError("NetBSD make wrapper entry changed; must audit")
        wrapper=wrapper.replace(old_exec,
            'PATH="'+str(owner_tools)+':${TOOLDIR}/bin:$PATH"; export PATH\n'+old_exec)
        wrapper_path=out/"nbmake-owner"
        wrapper_path.write_text(wrapper);wrapper_path.chmod(0o700)
        test_c=out/"cross-linker-probe.c"
        test_o=out/"cross-linker-probe.o"
        test_link=out/"cross-linker-probe-linked.o"
        test_c.write_text("int netbsd_owner_link_probe(void){return 0;}\n")
        env=os.environ.copy()
        env["PATH"]=str(owner_tools)+":/usr/tools/bin:"+env.get("PATH","")
        compile_result=subprocess.run(
            [str(cross_cc),"-ffreestanding","-c","-o",str(test_o),str(test_c)],
            text=True,capture_output=True,env=env,timeout=45)
        link_result=subprocess.run(
            [str(cross_cc),"-nostdlib","-r","-o",str(test_link),str(test_o)],
            text=True,capture_output=True,env=env,timeout=45) if compile_result.returncode==0 else None
        state["target_linker_preflight_pass"]=(
            compile_result.returncode==0 and link_result is not None and
            link_result.returncode==0 and test_link.stat().st_size>0
            if link_result is not None and test_link.exists() else False)
        if not state["target_linker_preflight_pass"]:
            raise RuntimeError("NetBSD cross GCC cannot find target ld: "+
                compile_result.stderr[-400:]+
                (link_result.stderr[-400:] if link_result else ""))
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
        if any(sha(out/"sys/dev/pci"/name)!=digest
               for name,digest in owned_hashes.items()):
            raise RuntimeError("private RTL source snapshot changed during config")
        if any(sha(path)!=owned_hashes[name] for name,path in owned.items()):
            raise RuntimeError("Git source changed while taking RTL snapshot")
        if subprocess.run(["git","-C",str(ROOT),"rev-parse","HEAD"],
                          capture_output=True,text=True,check=True,
                          timeout=20).stdout.strip()!=git_head:
            raise RuntimeError("Git source HEAD changed during config")
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
