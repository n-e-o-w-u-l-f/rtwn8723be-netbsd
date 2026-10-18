#!/usr/bin/env python3
"""SHA-bound native DRM VBlank core/provider for nonrelease HP source staging.

No HP command, compile, kernel install or boot. This does NOT demonstrate
NetBSD target ABI, runtime scheduling, IRQ, 323 i915 parity or KMS success.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile

NETBSD_CORE = "sys/external/bsd/drm2/dist/drm/drm_vblank.c"
NETBSD_HEADER = "sys/external/bsd/drm2/dist/include/drm/drm_vblank.h"
NETBSD_FILELIST = "sys/external/bsd/drm2/drm/files.drmkms"
NATIVE_WORKER = "sys/external/bsd/drm2/dist/drm/drm_vblank_work.c"
NATIVE_WORKER_HEADER = "sys/external/bsd/drm2/dist/include/drm/drm_vblank_work.h"
CORE_HOOKS = "compat/native-runtime/drm-vblank/patches/netbsd-drm-vblank-core-hooks.patch"
REF_BOUNDS = "candidates/0018-netbsd11-drm-vblank-ref-guard-pipe-bounds.patch"
WORKER_C = "compat/native-runtime/drm-vblank/src/drm_vblank_work.c"
WORKER_H = "compat/native-runtime/drm-vblank/include/drm/drm_vblank_work.h"

PINNED = {
    NETBSD_CORE: "06434bfc9f6693a1b61069c5c0e839b24671a5ba4d826fb001b0a897ceac206e",
    NETBSD_HEADER: "41a6574745795608b43bec288f04f0ae622271e604ff8b6e6d894e754acc37a9",
    NETBSD_FILELIST: "e507627bf8a6219ff38a79a2c6cebc98b1ee61540d354ce0eb15d2ee77785cb3",
}
# Headers consumed by the worker and DRM core, inherited unchanged from the
# frozen NetBSD source tree rather than silently supplied by the host.
PINNED_DEPENDENCIES = {
    "sys/external/bsd/drm2/include/drm/drm_wait_netbsd.h":
        "8630611df53db86e97889a7da1a3b6707e9339db805c2471de269875bdbd8d96",
    "sys/external/bsd/drm2/include/drm_trace.h":
        "ea4b78e89fa0615ce58af5fffb25076108ae3c5c5b09029b5e3e27fc42ae65ce",
}

OWNER_SHA = {
    CORE_HOOKS: "0acc6a3e68a9276a734752b78d4e07d725efafc84ebc2bacaa11a0825832d919",
    REF_BOUNDS: "2a4cc2546abd9e9e7be38a7e972d619a49991a1f02cff8333cacc35db9a1dd0f",
    WORKER_C: "fe31c46d491a4b93589d6c8308895266de22ee66913864ddde8b1234c29b12be",
    WORKER_H: "f01168bf73570113b94cf07a2c424dd3c4cfcc4061db6c4f984f4c518e8e008d",
}


def refuse(reason: str) -> None:
    raise ValueError("HP_VBLANK_PRIVATE_STAGE_REFUSED: " + reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_owner(i915: Path, path: str) -> bytes:
    file = i915 / path
    if not file.is_file() or file.is_symlink():
        refuse("missing or symlink owner source " + path)
    raw = file.read_bytes()
    if sha(raw) != OWNER_SHA[path]:
        refuse("owner SHA drift " + path)
    return raw


def _bounds(core: str) -> None:
    for name in ("drm_vblank_get_locked", "drm_vblank_put_locked"):
        marker = "static " + ("int " if "get" in name else "void ") + name + "("
        if core.count(marker) != 1:
            refuse("missing native ref owner " + name)
        f = core[core.index(marker):]
        f = f[:f.index("\n}\n") + 3]
        guarded = "if (WARN_ON(pipe >= dev->num_crtcs))"
        assignment = "vblank = &dev->vblank[pipe];"
        if (f.count(guarded) != 1 or f.count(assignment) != 1 or
                f.index(guarded) >= f.index(assignment)):
            refuse("eager or unguarded pointer " + name)


def build_vblank_private_core(i915_repo: Path, frozen: dict[str, bytes]
                              ) -> tuple[dict[str, bytes], dict]:
    """Apply pinned owner patches exclusively in a fresh, temporary real tree.

    The original three NetBSD files are byte-identically restored and never
    written in-place. Return replacements for a NEW private staging mirror.
    """
    if set(frozen) != set(PINNED):
        refuse("native source set mismatch")
    for p, raw in frozen.items():
        if sha(raw) != PINNED[p]:
            refuse("wrong frozen NetBSD revision for " + p)
    owner = {name: read_owner(i915_repo, name) for name in OWNER_SHA}
    # Patch lengths are small and intentionally bound to immutable hashes.
    if any(len(owner[p]) > 32768 for p in (CORE_HOOKS, REF_BOUNDS)):
        refuse("oversized owner patch")
    with tempfile.TemporaryDirectory(prefix="hp-vblank-private-core-") as temp:
        root = Path(temp)
        for p, raw in frozen.items():
            out = root / p
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(raw)
        # Source integration order is explicit: core hooks then bounds.
        for p in (CORE_HOOKS, REF_BOUNDS):
            for check in (True, False):
                try:
                    result = subprocess.run(
                        ["git", "apply", *(["--check"] if check else []),
                         str((i915_repo / p).resolve(strict=True))],
                        cwd=root, capture_output=True, timeout=20,
                        check=False)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    refuse("patch tool error " + type(exc).__name__)
                if result.returncode:
                    refuse("native overlay context mismatch " + p)
        changed = {p: (root / p).read_bytes() for p in PINNED}
        source = changed[NETBSD_CORE].decode("utf-8")
        _bounds(source)
        if (source.count("nb_i915_vblank_ref_get_locked(") != 1 or
                source.count("nb_i915_vblank_ref_put_locked(") != 1 or
                "drm_handle_vblank_works(vblank);" not in source or
                "drm_vblank_cancel_pending_works(vblank);" not in source):
            refuse("native VBlank core hooks lost")
        if ("struct lwp *work_thread;" not in
                changed[NETBSD_HEADER].decode("utf-8")):
            refuse("missing native VBlank worker lifecycle field")
        filelist = changed[NETBSD_FILELIST].decode("utf-8")
        selected = "file\texternal/bsd/drm2/dist/drm/drm_vblank_work.c\tdrmkms"
        if filelist.count(selected) != 1:
            refuse("worker not selected by DRM native file list")
        # A second application must fail closed; reversal must exactly
        # reconstruct all original pinned files.
        if subprocess.run(
                ["git", "apply", "--check", str(i915_repo / REF_BOUNDS)],
                cwd=root, capture_output=True, check=False).returncode == 0:
            refuse("duplicate bounds patch accepted")
        for p in (REF_BOUNDS, CORE_HOOKS):
            res = subprocess.run(
                ["git", "apply", "--reverse", str(i915_repo / p)],
                cwd=root, capture_output=True, timeout=20, check=False)
            if res.returncode:
                refuse("reverse failed " + p)
        for p, raw in frozen.items():
            if (root / p).read_bytes() != raw:
                refuse("original source failed exact reverse " + p)

    if b"drm_vblank_worker_init(" not in owner[WORKER_C] or (
            b"drm_vblank_worker_fini(" not in owner[WORKER_C]):
        refuse("native worker implementation incomplete")
    if b"drm_vblank_work_schedule(" not in owner[WORKER_H]:
        refuse("native worker API header incomplete")
    replacements = {
        **changed,
        NATIVE_WORKER: owner[WORKER_C],
        NATIVE_WORKER_HEADER: owner[WORKER_H],
    }
    return replacements, {
        "i915_drm_vblank_status": "VERIFIED_PINNED_NONRELEASE_CORE_AND_0018",
        "i915_drm_vblank_core_hooks_sha256": sha(owner[CORE_HOOKS]),
        "i915_drm_vblank_ref_bounds_patch_sha256": sha(owner[REF_BOUNDS]),
        "i915_drm_vblank_native_worker_sha256": sha(owner[WORKER_C]),
        "i915_drm_vblank_native_worker_header_sha256": sha(owner[WORKER_H]),
        "i915_drm_vblank_original_core_sha256": PINNED[NETBSD_CORE],
        "i915_drm_vblank_staged_core_sha256": sha(changed[NETBSD_CORE]),
        "i915_drm_vblank_native_filelist_sha256": sha(changed[NETBSD_FILELIST]),
        "i915_drm_vblank_staged_files": sorted(replacements),
        "i915_drm_vblank_scheduler_class_parity": "NOT_VERIFIED_SCHED_RR_VS_FIFO",
        "i915_drm_vblank_native_compile": "NOT_RUN",
        "i915_drm_vblank_full_323_semantic_closure": False,
    }
