#!/usr/bin/env python3
"""Pinned source-only integration test of native NetBSD VBlank into RTL50.

Requires an independently frozen NetBSD source subset with GENERIC/i915
and three DRM core files. Does NOT run NetBSD compiler or change target HP.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hp_i915_native_vblank_overlay import (  # noqa: E402
    CORE_HOOKS, REF_BOUNDS, WORKER_C, WORKER_H, PINNED,
    PINNED_DEPENDENCIES, OWNER_SHA,
    NATIVE_WORKER, NATIVE_WORKER_HEADER, NETBSD_CORE, NETBSD_FILELIST,
    build_vblank_private_core,
)
from stage_hp_combined_diagnostic_source import (  # noqa: E402
    prepare, I915_DRV_PATH, I915_DP_PATH, CHV_POWER_PATH,
)


def must(test: bool, message: str) -> None:
    if not test:
        raise AssertionError("HP_VBLANK_PRIVATE_STAGE_TEST: " + message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def head(repo: Path) -> str:
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse",
                                    "HEAD"], text=True).strip()


def reject(fn, label: str) -> None:
    try:
        fn()
    except (ValueError, RuntimeError):
        return
    raise AssertionError("unsafe change accepted: " + label)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--netbsd-fixture", type=Path, required=True)
    ap.add_argument("--i915-repo", type=Path, required=True)
    ap.add_argument("--rtl-repo", type=Path, default=ROOT)
    args = ap.parse_args()
    src = args.netbsd_fixture.resolve(strict=True)
    i915 = args.i915_repo.resolve(strict=True)
    rtl = args.rtl_repo.resolve(strict=True)

    original = {p: (src / p).read_bytes() for p in PINNED}
    must({p: sha(raw) for p, raw in original.items()} == PINNED,
         "pinned NetBSD 3 core bytes changed")
    files, meta = build_vblank_private_core(i915, original)
    must(len(files) == 5 and len(meta["i915_drm_vblank_staged_files"]) == 5,
         "VBlank source manifest missing owners")
    must(b"drm_vblank_worker_init(vblank);" in files[NETBSD_CORE],
         "VBlank core implementation not selected")
    must(b"drm_vblank_work_schedule(" in files[NATIVE_WORKER_HEADER],
         "VBlank public worker entrypoint absent")

    with tempfile.TemporaryDirectory(prefix="hp-vblank-stage-test-") as temp:
        root = Path(temp)
        output = root / "stage"
        snapshot = prepare(src, rtl, i915, output, head(rtl), head(i915))
        must(snapshot["status"] == "STAGED_DIAGNOSTIC_NONRELEASE_NO_KERNEL_BUILD" and
             snapshot["kernel_build"] == "NOT_RUN" and
             not snapshot["eligible_for_install"] and
             not snapshot["eligible_for_boot"], "diagnostic-only gate lost")
        must(len(snapshot["rtl_native_units"]) == 50,
             "RTL50 source file inventory regressed")
        must(snapshot["i915_drm_vblank_status"] ==
             "VERIFIED_PINNED_NONRELEASE_CORE_AND_0018",
             "missing exact candidate stage")
        must(snapshot["i915_drm_vblank_scheduler_class_parity"] ==
             "NOT_VERIFIED_SCHED_RR_VS_FIFO",
             "unverified scheduling falsely accepted")
        must(snapshot["i915_drm_vblank_pinned_dependencies_sha256"] ==
             PINNED_DEPENDENCIES, "VBlank frozen dependencies not recorded")
        for name, digest in PINNED_DEPENDENCIES.items():
            must(sha((src / name).read_bytes()) == digest,
                 "VBlank missing/unpinned header " + name)
        for p, raw in files.items():
            staged = output / "source" / p
            must(staged.is_file() and not staged.is_symlink() and
                 staged.read_bytes() == raw, "staged VBlank mismatch " + p)
            must(snapshot["source_sha256"][p] == sha(raw),
                 "staged VBlank SHA mismatch " + p)
        dp = (output / "source" / I915_DP_PATH).read_bytes()
        must(dp.count(b'printf("[I915 G08.') == 14,
             "14 guarded G08 trace records not retained")
        must(b"memset(sink_rates, 0, sizeof(sink_rates));" in dp and
             b"if (!cold && i915->drm.irq_enabled &&" in dp and
             b"(3 << DP_AUX_CH_CTL_PRECHARGE_2US_SHIFT)" in dp,
             "CHV/IRQ/DPCD source integration regressed")
        must((output / "source" / CHV_POWER_PATH).is_file() and
             (output / "source" / I915_DRV_PATH).is_file(),
             "other i915 private source missing")
        must((output / "source" / NETBSD_FILELIST).read_bytes() ==
             files[NETBSD_FILELIST], "native VBlank filelist not materialized")
        for p, before in original.items():
            must((src / p).read_bytes() == before,
                 "wrote to frozen NetBSD original " + p)
        print("VBLANK_0018_RTL50_G08_CHV_NONRELEASE_SOURCE_STAGE_PASS")

        # Mutate inputs one at a time in genuinely separate scratch copies.
        for p in PINNED:
            bad = dict(original)
            bad[p] = bad[p] + b"\n/* invalid frozen source */\n"
            reject(lambda bad=bad: build_vblank_private_core(i915, bad),
                   "native source corrupt " + p)
        print("VBLANK_0018_THREE_NATIVE_SOURCE_MUTATIONS_REFUSED")

        owner_copy = root / "owner"
        for p in OWNER_SHA:
            srcfile = i915 / p
            dst = owner_copy / p
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(srcfile, dst)
        for p in OWNER_SHA:
            dst = owner_copy / p
            before = dst.read_bytes()
            dst.write_bytes(before + b"\nX")
            reject(lambda: build_vblank_private_core(owner_copy, original),
                   "owner source/patch tamper " + p)
            dst.write_bytes(before)
        print("VBLANK_0018_FOUR_OWNER_SOURCE_PATCH_SHA_MUTATIONS_REFUSED")

        # The native selected-source condition may not silently regress.
        must(snapshot["source_sha256"][NETBSD_FILELIST] ==
             sha(files[NETBSD_FILELIST]), "file selector SHA drift")
        symlinked = root / "symlink-owner"
        for p in OWNER_SHA:
            dest = symlinked / p
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(i915 / p, dest)
        victim = symlinked / CORE_HOOKS
        victim.unlink()
        victim.symlink_to(i915 / CORE_HOOKS)
        reject(lambda: build_vblank_private_core(symlinked, original),
               "linked owner hook")
        print("VBLANK_0018_OWNER_SYMLINK_REFUSED")

        for i, name in enumerate(PINNED_DEPENDENCIES):
            mutated_source = root / ("tampered-dependency-" + str(i))
            shutil.copytree(src, mutated_source, symlinks=True)
            target = mutated_source / name
            target.write_bytes(target.read_bytes() + b"X")
            reject(lambda s=mutated_source, i=i: prepare(
                s, rtl, i915, root / ("refused-tampered-" + str(i)),
                head(rtl), head(i915)), "altered native prerequisite " + name)
            missing_source = root / ("missing-dependency-" + str(i))
            shutil.copytree(src, missing_source, symlinks=True)
            (missing_source / name).unlink()
            reject(lambda s=missing_source, i=i: prepare(
                s, rtl, i915, root / ("refused-missing-" + str(i)),
                head(rtl), head(i915)), "missing native prerequisite " + name)
        print("VBLANK_0018_FOUR_NATIVE_HEADER_MISSING_DRIFT_REFUSALS_PASS")
    print("I915_VBLANK_0018_STAGING_12_NEGATIVE_CASES_PASS")
    print("LIMIT: source-only private shadow on Legion, NO NetBSD HP compile/boot")


if __name__ == "__main__":
    main()
