#!/usr/bin/env python3
"""HP-only regression batch; durable per-test logs and completion state."""
import argparse, datetime, json, os, pathlib, platform, resource, socket, subprocess, sys
p=argparse.ArgumentParser()
p.add_argument("repo",type=pathlib.Path)
p.add_argument("--output",type=pathlib.Path,required=True)
p.add_argument("--linux-tree",type=pathlib.Path,default=pathlib.Path("/root/linux-rtl8723be-ref-fresh"))
a=p.parse_args()
a.repo=a.repo.resolve(strict=True)
a.output=a.output.resolve()
a.linux_tree=a.linux_tree.resolve(strict=True)
env=dict(os.environ, RTWN8723BE_LINUX_TREE=str(a.linux_tree))
if platform.system()!="NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
    sys.exit("REFUSED: compilation/regressions are authorized only on HP/NetBSD")
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
a.output.mkdir(parents=True,exist_ok=True)
state={"state":"RUNNING","host":socket.gethostname(),"started":datetime.datetime.now(datetime.timezone.utc).isoformat(),"tests":[]}
status=a.output/"status.json"
def save():
    state["updated"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
    tmp=status.with_suffix(".tmp")
    tmp.write_text(json.dumps(state,indent=2)+"\n")
    tmp.replace(status)
save()
for test in sorted((a.repo/"tests").glob("test_*.py")):
    cmd=[sys.executable,str(test)]
    if test.name in ("test_oem.py","test_package.py","test_phy_bb_sequence.py"):
        cmd+=["--linux-tree",str(a.linux_tree)]
    with (a.output/(test.stem+".log")).open("w") as log:
        try: rc=subprocess.run(cmd,cwd=a.repo,stdout=log,stderr=subprocess.STDOUT,timeout=180,env=env).returncode
        except subprocess.TimeoutExpired: rc=124
    state["tests"].append({"name":test.name,"exit":rc})
    save()
    print(test.name,rc,flush=True)
state["state"]="PASSED" if all(t["exit"]==0 for t in state["tests"]) else "FAILED"
save()
sys.exit(0 if state["state"]=="PASSED" else 1)
