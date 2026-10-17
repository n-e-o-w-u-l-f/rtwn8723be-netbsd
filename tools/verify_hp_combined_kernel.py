#!/usr/bin/env python3
"""Verify a *combined* NetBSD kernel object graph and final full ELF link.

Never treats a partial ld -r, RTL-only kernel, old genfb-only output or source
test as a linked combined candidate. Read-only verification by default;
--postlink writes a report only to the private output directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from configure_hp_combined_i915_rtl import (
    refuse, selected_i915_objects, verify_make_objects, RTL_UNIT,
)


def run(*argv: str) -> str:
    proc = subprocess.run(argv, text=True, capture_output=True, timeout=30)
    if proc.returncode:
        refuse("command failed " + repr(argv) + ": " + proc.stderr[-600:])
    return proc.stdout


def load_snapshot(output: Path) -> dict:
    manifest = output / "combined-source-manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        refuse("missing immutable combined-source-manifest.json")
    data = json.loads(manifest.read_text())
    if data.get("status") != "CONFIGURED_SOURCE_ONLY_NO_KERNEL_BUILD":
        refuse("combined source manifest has no qualified producer")
    rtl, i915 = data.get("RTL_SHA"), data.get("I915_SHA")
    if not (isinstance(rtl, str) and re.fullmatch("[0-9a-f]{40}", rtl) and
            isinstance(i915, str) and re.fullmatch("[0-9a-f]{40}", i915)):
        refuse("missing exact dual source SHAs")
    identity = "HP-COMBINED-I915-" + i915[:12] + "-RTL-" + rtl[:12]
    if data.get("identity") != identity:
        refuse("combined kernel identifier missing dual exact SHAs")
    units = data.get("rtl_native_units")
    if not isinstance(units, list) or len(units) != 50 or len(set(units)) != 50:
        refuse("RTL50 native snapshot incomplete")
    gpu = data.get("i915_selected_native")
    if not isinstance(gpu, list) or len(gpu) < 3:
        refuse("missing i915 owner/object closure in snapshot")
    for name, digest in data.get("source_sha256", {}).items():
        if not isinstance(name, str) or not name.startswith("sys/") or ".." in Path(name).parts:
            refuse("unsafe source snapshot path")
        file = output / "source" / name
        if not file.is_file() or file.is_symlink():
            refuse("missing/linked staged file: " + name)
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            refuse("source snapshot changed: " + name)
    return data


def verify_ownership(source: dict, obj_output: str) -> dict:
    result = verify_make_objects(
        obj_output, source["rtl_native_units"], source["i915_selected_native"])
    if result["rtl_objects"] != 50 or result["gpu_and_drm_objects"] < 3:
        refuse("wrong combined device object counts")
    return result


def verify_elf(output: Path, manifest: dict, objects: dict) -> dict:
    kernel = output / "obj/netbsd"
    if not kernel.is_file() or kernel.is_symlink() or kernel.stat().st_size < 8192:
        refuse("missing, suspiciously small or linked final kernel ELF")
    file_result = run("/usr/bin/file", str(kernel))
    if "ELF" not in file_result or "x86-64" not in file_result:
        refuse("not NetBSD/amd64 ELF")
    what = run("/usr/bin/what", str(kernel))
    if manifest["identity"] not in what:
        refuse("full combined kernel identity missing in what(1)")
    mapfile = output / "obj/netbsd.map"
    if not mapfile.is_file() or mapfile.stat().st_size < 200:
        refuse("full LD map absent - partial link cannot be called combined")
    maptext = mapfile.read_text(errors="replace")
    rtlname = Path(manifest["rtl_native_units"][0]).stem + ".o"
    required_gpu = selected_i915_objects(manifest["i915_selected_native"])
    if rtlname not in maptext or not any(name in maptext for name in required_gpu):
        refuse("both driver families not present in final linked map")
    return {"file":file_result.strip(), "what":what[-3000:],
            "sha256":hashlib.sha256(kernel.read_bytes()).hexdigest(),
            "bytes":kernel.stat().st_size,
            "map_sha256":hashlib.sha256(mapfile.read_bytes()).hexdigest(),
            **objects}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--make", default="/usr/tools/bin/nbmake-amd64")
    p.add_argument("--postlink", action="store_true")
    a = p.parse_args()
    try:
        output = a.output.resolve(strict=True)
        source = load_snapshot(output)
        expanded = run(a.make, "-C", str(output / "obj"), "-V", "OBJS")
        objects = verify_ownership(source, expanded)
        if not a.postlink:
            print(json.dumps({"status":"NATIVE_OBJECT_OWNERS_PRESENT",
                              "identity":source["identity"], **objects}))
            return 0
        result = verify_elf(output, source, objects)
        result.update({"status":"COMBINED_KERNEL_LINKED_NO_INSTALL",
                       "identity":source["identity"],
                       "rtl_sha":source["RTL_SHA"], "i915_sha":source["I915_SHA"],
                       "installed":False, "booted":False})
        file = output / "combined-link-verification.json"
        if file.exists() or file.is_symlink():
            refuse("refusing overwrite of previous combined result")
        file.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status":result["status"],
                          "identity":result["identity"],
                          "kernel_sha256":result["sha256"]}))
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as e:
        print("COMBINED_KERNEL_NOT_LINKED: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
