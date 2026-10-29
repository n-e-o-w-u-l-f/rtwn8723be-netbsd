#!/usr/bin/env python3
"""Combined snapshot must bind the executable source to verified G01-G09 trace.

All data is a synthetic in-memory/temporary fixture. No HP kernel is built.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hp_i915_boot_trace_overlay import I915_DRV_PATH, build_private_overlay
from verify_hp_combined_kernel import load_snapshot


def denied(task, label):
    try:
        task()
    except (ValueError, OSError):
        return
    raise AssertionError("expected denied trace manifest: " + label)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--netbsd-i915", required=True, type=Path)
    p.add_argument("--i915-repo", required=True, type=Path)
    args = p.parse_args()
    data = args.netbsd_i915.read_bytes()
    patched, evidence = build_private_overlay(args.i915_repo, data)
    with tempfile.TemporaryDirectory(prefix="rtl-trace-manifest-") as d:
        root = Path(d)
        dest = root / "source" / I915_DRV_PATH
        dest.parent.mkdir(parents=True)
        dest.write_bytes(patched)
        file = root / "combined-source-manifest.json"
        snapshot = {
            "status":"CONFIGURED_SOURCE_ONLY_NO_KERNEL_BUILD",
            "RTL_SHA":"a"*40, "I915_SHA":"b"*40,
            "identity":"HP-COMBINED-I915-" + "b"*12 + "-RTL-" + "a"*12,
            "rtl_native_units":["r"+str(i)+".c" for i in range(50)],
            "i915_selected_native":[I915_DRV_PATH,
                "sys/external/bsd/drm2/dist/drm/drm_drv.c",
                "sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c"],
            "source_sha256":{I915_DRV_PATH: hashlib.sha256(patched).hexdigest()},
            **evidence,
        }
        def write(obj):
            file.write_text(json.dumps(obj))
        write(snapshot)
        result = load_snapshot(root)
        assert result["i915_trace_print_calls"] == 18
        assert result["i915_trace_output_sha256"] == hashlib.sha256(patched).hexdigest()
        for name, value in [
            ("missing trace", None), ("wrong trace", "NOT_VERIFIED"),
        ]:
            copy = dict(snapshot, i915_trace_state=value)
            write(copy)
            denied(lambda: load_snapshot(root), name)
        for key, wrong in [
            ("i915_trace_input_sha256", "f"*64),
            ("i915_trace_output_sha256", "0"*64),
            ("i915_trace_print_calls", 17),
            ("i915_trace_patch_sha256", "broken"),
            ("i915_trace_source", "sys/dev/pci/other.c"),
        ]:
            write({**snapshot, key:wrong})
            denied(lambda: load_snapshot(root), key)
        write({**snapshot, "i915_selected_native":
                   snapshot["i915_selected_native"][1:]})
        denied(lambda: load_snapshot(root), "i915 source not selected")
        write(snapshot)
        dest.write_bytes(patched + b"/* tampered */\n")
        denied(lambda: load_snapshot(root), "source hash tampered")
        dest.unlink()
        dest.symlink_to(args.netbsd_i915)
        denied(lambda: load_snapshot(root), "source symlink to pinned NetBSD")
        assert args.netbsd_i915.read_bytes() == data

    print("HP_COMBINED_I915_TRACE_MANIFEST_SOURCE_PASS")
    print("Private source sha, 18 messages, missing/altered fields and symlink refusal; native link NOT_RUN")


if __name__ == "__main__":
    main()
