#!/usr/bin/env python3
"""Verify/apply one i915-owned G01-G09 NetBSD trace patch in memory.

Returns bytes for a private mirror replacement. Never writes the pinned tree
or applies a patch to the symlink-based shadow source tree.
"""
from __future__ import annotations
from collections import Counter
import difflib
import hashlib
from pathlib import Path
import re

I915_DRV_PATH = "sys/external/bsd/drm2/dist/drm/i915/i915_drv.c"
OWNER_PATCH = "patches/0038-netbsd11-i915-g01-g09-boottrace.patch"
PINNED_SOURCE_SHA256 = (
    "88c9e4c4ffb0669fdec14fd6a3589ab4aae43b2ef32ad5f6deb78b86ffd1d8e8"
)
PHASES = {f"G{i:02d}" for i in range(1, 10)}
HUNK = re.compile(r"^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@.*\n$")
TAG = re.compile(
    r'^\tprintf\("\[I915 (G0[1-9])\] ([a-z0-9_]+) '
    r'(BEGIN|END)(?: ret=%d)?\\n"(?:, ret)?\);\n$'
)
GUARD = re.compile(
    r'#ifdef __NetBSD__\n'
    r'\tprintf\("\[I915 G0[1-9]\] [^"\n]+\\n"(?:, ret)?\);\n'
    r'#endif\n'
)


def refuse(message: str) -> None:
    raise ValueError("I915_BOOT_TRACE_" + message)


def apply_exact_patch(original: bytes, patch: bytes) -> bytes:
    """Apply strictly one pinned-path unified diff; reject drift/replacements.

    Includes bounded hunk parsing and exact source/content reconstruction.
    Do not run git apply against NetBSD or a symlink mirror.
    """
    if hashlib.sha256(original).hexdigest() != PINNED_SOURCE_SHA256:
        refuse("BASE_SOURCE_SHA_MISMATCH")
    if len(patch) > 32768 or len(patch) < 600:
        refuse("PATCH_SIZE_INVALID")
    try:
        raw = original.decode("utf-8")
        diff = patch.decode("utf-8")
    except UnicodeDecodeError:
        refuse("NON_UTF8_INPUT")
    before = "--- a/" + I915_DRV_PATH + "\n"
    after = "+++ b/" + I915_DRV_PATH + "\n"
    if not diff.startswith(before + after):
        refuse("PATCH_TARGET_MISMATCH")
    lines = diff.splitlines(keepends=True)[2:]
    base = raw.splitlines(keepends=True)
    out: list[str] = []
    cursor = 0
    idx = 0
    old_total = 0
    new_total = 0
    while idx < len(lines):
        marker = HUNK.fullmatch(lines[idx])
        if not marker:
            refuse("MALFORMED_HUNK_HEADER")
        old_start = int(marker[1]) - 1
        old_count = int(marker[2] or "1")
        new_start = int(marker[3]) - 1
        new_count = int(marker[4] or "1")
        if old_start < cursor or old_start > len(base):
            refuse("HUNK_ORDER_OR_RANGE")
        out.extend(base[cursor:old_start])
        idx += 1
        cur = old_start
        seen_old = 0
        seen_new = 0
        while idx < len(lines) and not lines[idx].startswith("@@ "):
            line = lines[idx]
            if not line or line[0] not in " +-":
                refuse("UNKNOWN_PATCH_INSTRUCTION")
            if line[0] in " -":
                if cur >= len(base) or line[1:] != base[cur]:
                    refuse("HUNK_CONTEXT_OR_DELETE_MISMATCH")
                cur += 1
                seen_old += 1
            if line[0] in " +":
                out.append(line[1:])
                seen_new += 1
            idx += 1
        if (seen_old, seen_new) != (old_count, new_count):
            refuse("HUNK_LENGTH_MISMATCH")
        if len(out) - seen_new != new_start:
            # The section start must include only preceding source chunks.
            refuse("NEW_LINE_OFFSET_MISMATCH")
        cursor = cur
        old_total += seen_old
        new_total += seen_new
    if old_total == 0 or new_total == 0:
        refuse("PATCH_EMPTY")
    out.extend(base[cursor:])
    changed = "".join(out)
    expected = "".join(difflib.unified_diff(
        raw.splitlines(keepends=True), changed.splitlines(keepends=True),
        fromfile="a/" + I915_DRV_PATH, tofile="b/" + I915_DRV_PATH))
    if expected != diff:
        # For this narrowly scoped i915 owner patch the canonical unified
        # hunk layout must match the exact pinned generator, not a rewrite.
        refuse("PATCH_CANONICAL_DIFF_MISMATCH")
    return changed.encode("utf-8")


def verify_trace_overlay(original: bytes, changed: bytes) -> None:
    try:
        text = changed.decode("utf-8")
        base = original.decode("utf-8")
    except UnicodeDecodeError:
        refuse("OVERLAY_NOT_UTF8")
    clean, removed = GUARD.subn("", text)
    if clean != base or removed != 18:
        refuse("CHANGED_NATIVE_CONTROL_FLOW")
    captures = [TAG.fullmatch(line) for line in text.splitlines(keepends=True)]
    markers = [m for m in captures if m is not None]
    if len(markers) != 18:
        refuse("TRACE_MESSAGES_NOT_18")
    counted = Counter((m[1], m[3]) for m in markers)
    if counted != Counter({(p,s):1 for p in PHASES for s in ("BEGIN","END")}):
        refuse("TRACE_NOT_PAIRED")
    if text.count("#ifdef __NetBSD__") - base.count("#ifdef __NetBSD__") != 18:
        refuse("TRACE_NOT_NETBSD_GUARDED")


def build_private_overlay(i915_repo: Path, base_source: bytes,
                          existing: bytes | None = None) -> tuple[bytes, dict]:
    """Fail closed on a customized i915_drv.c; no silent overlay clobber."""
    path = i915_repo / OWNER_PATCH
    if not path.is_file() or path.is_symlink():
        refuse("I915_OWNER_PATCH_MISSING")
    if existing is not None and existing != base_source:
        refuse("I915_OWNER_SOURCE_CONFLICT_REBASE_REQUIRED")
    patch = path.read_bytes()
    output = apply_exact_patch(base_source, patch)
    verify_trace_overlay(base_source, output)
    return output, {
        "i915_trace_state": "VERIFIED_PINNED_G01_G09_PRIVATE_OVERLAY",
        "i915_trace_patch_sha256": hashlib.sha256(patch).hexdigest(),
        "i915_trace_input_sha256": hashlib.sha256(base_source).hexdigest(),
        "i915_trace_output_sha256": hashlib.sha256(output).hexdigest(),
        "i915_trace_print_calls": 18,
        "i915_trace_source": I915_DRV_PATH,
    }
