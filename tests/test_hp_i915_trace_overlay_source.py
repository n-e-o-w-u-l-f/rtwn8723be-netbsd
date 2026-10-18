#!/usr/bin/env python3
"""G01-G09 owner patch -> private combined NetBSD source overlay regression.

Runs on a disposable checkout with a separately verified frozen i915_drv.c.
It is NOT a native HP kernel build, i915 KMS pass or release authorization.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hp_i915_boot_trace_overlay import (
    I915_DRV_PATH, OWNER_PATCH, PINNED_SOURCE_SHA256,
    apply_exact_patch, build_private_overlay, verify_trace_overlay,
)


def denied(task, marker):
    try:
        task()
    except ValueError as err:
        assert marker in str(err), str(err)
        return
    raise AssertionError("expected diagnostic source denial " + marker)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--netbsd-i915", required=True, type=Path)
    p.add_argument("--i915-repo", required=True, type=Path)
    a = p.parse_args()
    baseline = a.netbsd_i915.read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == PINNED_SOURCE_SHA256
    assert (a.i915_repo / OWNER_PATCH).is_file()
    source_before = hashlib.sha256(baseline).hexdigest()
    patch_before = (a.i915_repo / OWNER_PATCH).read_bytes()
    output, audit = build_private_overlay(a.i915_repo, baseline)
    assert output != baseline
    assert audit["i915_trace_input_sha256"] == PINNED_SOURCE_SHA256
    assert audit["i915_trace_output_sha256"] == hashlib.sha256(output).hexdigest()
    assert audit["i915_trace_print_calls"] == 18
    assert audit["i915_trace_source"] == I915_DRV_PATH
    verify_trace_overlay(baseline, output)
    assert build_private_overlay(a.i915_repo, baseline, existing=baseline)[0] == output
    assert hashlib.sha256(a.netbsd_i915.read_bytes()).hexdigest() == source_before
    assert (a.i915_repo / OWNER_PATCH).read_bytes() == patch_before

    # Refuse an owner-adjusted i915_drv.c: silently replacing a real source
    # integration overlay would lose functional fixes and is prohibited.
    denied(lambda: build_private_overlay(a.i915_repo, baseline,
                  existing=baseline+b"\n"), "I915_OWNER_SOURCE_CONFLICT")
    denied(lambda: build_private_overlay(a.i915_repo, baseline+b"\n"),
           "BASE_SOURCE_SHA_MISMATCH")
    denied(lambda: verify_trace_overlay(baseline, baseline),
           "CHANGED_NATIVE_CONTROL_FLOW")
    denied(lambda: verify_trace_overlay(baseline, output.replace(
           b"[I915 G09]", b"[I915 G19]", 1)), "CHANGED_NATIVE_CONTROL_FLOW")
    bad = [
        patch_before.replace(b"+++ b/", b"+++ z/", 1),
        patch_before.replace(b"@@ ", b"@@ -9999,1 +9999,1 @@", 1),
        patch_before.replace(b"pci_attach", b"pci_atach", 1),
        patch_before + b"\nMALICIOUS_EXTRA_CONTENT",
        patch_before.replace(b"+\tprintf(", b"+\treturn -1; /*", 1),
    ]
    for altered in bad:
        denied(lambda v=altered: apply_exact_patch(baseline, v), "I915_BOOT_TRACE_")

    with tempfile.TemporaryDirectory(prefix="rtl-trace-negative-") as td:
        i915_copy = Path(td) / "i915"
        (i915_copy / "patches").mkdir(parents=True)
        denied(lambda: build_private_overlay(i915_copy, baseline),
               "I915_OWNER_PATCH_MISSING")
        (i915_copy / OWNER_PATCH).symlink_to(a.i915_repo / OWNER_PATCH)
        denied(lambda: build_private_overlay(i915_copy, baseline),
               "I915_OWNER_PATCH_MISSING")

    print("HP_COMBINED_I915_TRACE_PRIVATE_OVERLAY_SOURCE_PASS")
    print("18 paired prints; frozen original unchanged; 7 negative/altered inputs refused")
    print("LIMIT: no live NetBSD, no 323-closure, no kernel link, no install/boot")


if __name__ == "__main__":
    main()
