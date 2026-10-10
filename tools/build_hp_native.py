#!/usr/bin/env python3
"""Compile the experimental native closure on HP in the isolated source stage.

Uses existing HP NetBSD tools through an isolated make wrapper. Does not
install a kernel or interpret an object/kernel build as full driver parity.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--netbsd-tree", type=Path, required=True)
parser.add_argument("--objdir", type=Path, required=True)
parser.add_argument("--target", choices=("objects", "kernel"), default="objects")
args = parser.parse_args()
if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
    sys.exit("REFUSED: this build is authorized only on HP/NetBSD")
tree = args.netbsd_tree.resolve(strict=True)
obj = args.objdir.resolve()
workspace = tree.parent
if (tree.name != "netbsd-native" or obj.parent != workspace or
        not obj.name.startswith("native-obj") or tree == Path("/usr/src") or
        not (workspace / "native-stage.status").read_text().startswith("DONE ")):
    sys.exit("REFUSED: expected the separately prepared native source/object workspace")
tools = workspace / "native-tools"
obj.mkdir(exist_ok=True)
report = obj / (args.target + "-status.json")
state = {"state": "RUNNING", "host": socket.gethostname(), "target": args.target,
         "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "tree": str(tree), "objdir": str(obj), "commands": []}
def save():
    state["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tmp = report.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(report)
def run(command):
    state["commands"].append(command)
    save()
    print("RUN", command, flush=True)
    subprocess.run(command, check=True)
save()
try:
    manifest = (ROOT / "config/files.rtwn8723be_native").read_text(encoding="utf-8")
    units = re.findall(r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native$",
                       manifest, re.M)
    # The native manifest now includes the separate real TX-DMA owner (42 units).
    if len(units) != 42 or len(set(units)) != len(units):
        raise RuntimeError("unexpected native C manifest; re-inventory first")
    dest = tree / "sys/dev/pci"
    sources = [ROOT / "src" / name for name in units]
    sources.extend(sorted((ROOT / "src").glob("rtwn8723be*.h")))
    sources.extend(sorted((ROOT / "src").glob("rtwn8723be*.inc")))
    state["source_sha256"] = {}
    for source in sources:
        data = source.read_bytes()
        if b"[executed on device:" in data:
            raise RuntimeError("tool transcript in native source: " + source.name)
        target = dest / source.name
        target.write_bytes(data)
        if target.read_bytes() != data:
            raise RuntimeError("source copy mismatch: " + source.name)
        state["source_sha256"][source.name] = hashlib.sha256(data).hexdigest()
    files = dest / "files.pci"
    old = files.read_text(encoding="utf-8")
    begin = "# BEGIN HP RTL NATIVE ISOLATED STAGE\n"
    end = "# END HP RTL NATIVE ISOLATED STAGE\n"
    if begin in old:
        if old.count(begin) != 1 or old.count(end) != 1:
            raise RuntimeError("ambiguous previous native manifest")
        left, tail = old.split(begin, 1)
        old = left + tail.split(end, 1)[1]
    files.write_text(old.rstrip("\n") + "\n" + begin + manifest.rstrip("\n") +
                     "\n" + end, encoding="utf-8")
    config = tree / "sys/arch/amd64/conf/HP-RTL-NATIVE-20261005"
    config.write_text('include "arch/amd64/conf/GENERIC"\n'
                      'ident "HP-RTL-NATIVE-20261005"\n'
                      'no rtwn*\n'
                      'rtwn8723be_native* at pci? dev ? function ?\n', encoding="utf-8")
    # Keep /usr/tools and its source-root-specific wrapper untouched.
    tools.mkdir(exist_ok=True)
    (tools / "bin").mkdir(exist_ok=True)
    original_tools = Path("/usr/tools")
    for source in original_tools.iterdir():
        if source.name == "bin":
            continue
        target = tools / source.name
        if not target.exists():
            target.symlink_to(source, target_is_directory=source.is_dir())
    for source in (original_tools / "bin").iterdir():
        if source.name == "nbmake-amd64":
            continue
        target = tools / "bin" / source.name
        if not target.exists():
            target.symlink_to(source)
    wrapper_text = (original_tools / "bin/nbmake-amd64").read_text(encoding="utf-8")
    for before, after in (("/usr/src", str(tree)), ("/usr/obj", str(obj)),
                          ("/usr/tools", str(tools))):
        wrapper_text = wrapper_text.replace(before, after)
    wrapper = tools / "bin/nbmake-amd64"
    wrapper.write_text(wrapper_text, encoding="utf-8")
    wrapper.chmod(0o755)
    run([str(tools / "bin/nbconfig"), "-s", str(tree / "sys"), "-b", str(obj), str(config)])
    targets = [Path(name).stem + ".o" for name in units] if args.target == "objects" else ["netbsd"]
    # A native-object check needs the selected C dependency files, not
    # serial preprocessing of every unrelated GENERIC driver.
    dependencies = [Path(name).stem + ".d" for name in units] if args.target == "objects" else ["depend"]
    run([str(wrapper), "-C", str(obj), "-j2", *dependencies])
    run([str(wrapper), "-C", str(obj), "-j2", *targets])
    state["artifacts"] = {}
    for name in targets:
        artifact = obj / name
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise RuntimeError("missing or empty build artifact: " + name)
        state["artifacts"][name] = {"bytes": artifact.stat().st_size,
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
    state["state"] = "PASSED"
    state["limitation"] = "experimental compile only; full-port and hardware gates remain open"
except Exception as exc:
    state["state"] = "FAILED"
    state["error"] = str(exc)
    save()
    raise
save()
print("HP_NATIVE_" + args.target.upper() + "_BUILD_PASS", flush=True)
