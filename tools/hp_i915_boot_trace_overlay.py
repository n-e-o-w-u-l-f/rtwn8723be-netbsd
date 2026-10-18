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
PHASE_LABELS = {
    "G01": "pci_attach", "G02": "early_probe",
    "G03": "mmio_probe", "G04": "hardware_ggtt_probe",
    "G05": "bios_vbt_init", "G06": "power_domains_init_hw",
    "G07": "irq_install", "G08": "modeset_init", "G09": "fbdev_init",
}
VOID_PHASES = {"G05", "G06"}
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


def apply_exact_patch(original: bytes, patch: bytes, *,
                      source_path: str = I915_DRV_PATH,
                      pinned_sha256: str = PINNED_SOURCE_SHA256,
                      verifier=None) -> bytes:
    """Apply strictly one pinned-path unified diff; reject drift/replacements.

    Includes bounded hunk parsing and exact source/content reconstruction.
    Do not run git apply against NetBSD or a symlink mirror.
    """
    if hashlib.sha256(original).hexdigest() != pinned_sha256:
        refuse("BASE_SOURCE_SHA_MISMATCH")
    if len(patch) > 32768 or len(patch) < 600:
        refuse("PATCH_SIZE_INVALID")
    try:
        raw = original.decode("utf-8")
        diff = patch.decode("utf-8")
    except UnicodeDecodeError:
        refuse("NON_UTF8_INPUT")
    before = "--- a/" + source_path + "\n"
    after = "+++ b/" + source_path + "\n"
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
        fromfile="a/" + source_path, tofile="b/" + source_path))
    if expected != diff:
        # For this narrowly scoped i915 owner patch the canonical unified
        # hunk layout must match the exact pinned generator, not a rewrite.
        refuse("PATCH_CANONICAL_DIFF_MISMATCH")
    result = changed.encode("utf-8")
    (verifier or verify_trace_overlay)(original, result)
    return result


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
    for m in markers:
        key, label, phase = m[1], m[2], m[3]
        if label != PHASE_LABELS[key]:
            refuse("PHASE_LABEL_CHANGED")
        with_rc = phase == "END" and key not in VOID_PHASES
        code = m[0]
        if with_rc != ("END ret=%d" in code and ", ret);" in code):
            refuse("PHASE_RETURN_FORMAT_CHANGED")
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


# The i915 owner supplies this independent NetBSD-only G08 eDP/AUX patch.
# Its source never overlaps the older i915_drv.c G01-G09 overlay.
I915_DP_PATH = "sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"
G08_OWNER_PATCH = "patches/0039-netbsd11-i915-chv-edp-aux-phase-trace.patch"
G08_PINNED_SHA256 = (
    "7f79318fee13fd67da6d0c0b21da90a372310e297c38767397bfd96129db0141"
)
G08_PHASE_LABELS = {
    "G08.A1": "AUX_INIT", "G08.A2": "EDP_DPCD",
    "G08.C1": "CHV_PHY", "G08.C2": "CHV_PLL",
    "G08.P1": "EDP_PANEL", "G08.L1": "LINK_TRAIN",
    "G08.L2": "LINK_STOP",
}
G08_GUARD = re.compile(
    r'#ifdef __NetBSD__\n'
    r'\tprintf\("\[I915 G08\.[A-Z][12]\] [^"\n]+\\n"(?:, has_dpcd)?\);\n'
    r'#endif\n'
)
G08_MARKER = re.compile(
    r'\tprintf\("\[I915 (G08\.[A-Z][12])\] ([A-Z_]+) '
    r'(BEGIN|END)( success=%d)?\\n"(?:, has_dpcd)?\);\n'
)


def verify_g08_overlay(original: bytes, changed: bytes) -> None:
    """Reject alterations to the real NetBSD execution path and unpaired tags."""
    base = original.decode("utf-8")
    text = changed.decode("utf-8")
    restored, removed = G08_GUARD.subn("", text)
    if removed != 14 or restored != base:
        refuse("G08_CHANGED_NATIVE_CONTROL_FLOW")
    tagged = [line for line in text.splitlines(keepends=True)
              if 'printf("[I915 G08.' in line]
    if len(tagged) != 14:
        refuse("G08_TRACE_MESSAGES_NOT_14")
    phases = Counter()
    for line in tagged:
        match = G08_MARKER.fullmatch(line)
        if not match or G08_PHASE_LABELS.get(match[1]) != match[2]:
            refuse("G08_TRACE_MARKER_INVALID")
        if bool(match[4]) != (match[1] == "G08.A2" and match[3] == "END"):
            refuse("G08_DPCD_RESULT_INVALID")
        phases[(match[1], match[3])] += 1
    if phases != Counter({(key, phase): 1 for key in G08_PHASE_LABELS
                          for phase in ("BEGIN", "END")}):
        refuse("G08_TRACE_NOT_PAIRED")
    if text.count("#ifdef __NetBSD__") - base.count("#ifdef __NetBSD__") != 14:
        refuse("G08_TRACE_NOT_NETBSD_GUARDED")


def build_g08_private_overlay(i915_repo: Path, base_source: bytes,
                             existing: bytes | None = None) -> tuple[bytes, dict]:
    """Stage the producer's unmodified 0039 diff in memory, never on source."""
    if existing is not None and existing != base_source:
        refuse("G08_OWNER_SOURCE_CONFLICT_REBASE_REQUIRED")
    path = i915_repo / G08_OWNER_PATCH
    if not path.is_file() or path.is_symlink():
        refuse("G08_OWNER_PATCH_MISSING")
    patch = path.read_bytes()
    result = apply_exact_patch(
        base_source, patch, source_path=I915_DP_PATH,
        pinned_sha256=G08_PINNED_SHA256, verifier=verify_g08_overlay)
    return result, {
        "i915_g08_trace_state": "VERIFIED_PINNED_G08_PRIVATE_OVERLAY",
        "i915_g08_trace_source": I915_DP_PATH,
        "i915_g08_trace_print_calls": 14,
        "i915_g08_trace_patch_sha256": hashlib.sha256(patch).hexdigest(),
        "i915_g08_trace_input_sha256": hashlib.sha256(base_source).hexdigest(),
        "i915_g08_trace_output_sha256": hashlib.sha256(result).hexdigest(),
    }
