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
import subprocess
import tempfile

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


# CHV hardware fixes are owned by the i915 provider; they do not substitute
# for modern Linux-323 semantic source closure or authorize any kernel boot.
CHV_POWER_PATH = "sys/external/bsd/drm2/dist/drm/i915/display/intel_display_power.c"
CHV_FIXES = {
    CHV_POWER_PATH: {
        "patch": "patches/0002-chv-defer-phy-control-powerwell-linux-1a2466fe-netbsd11.patch",
        "patch_sha256": "e75157d717a3e90e8ae51f38e8ea4b679772f9705630fee30813606818823905",
        "original_sha256": "07b4d1fb0b1983c77310d375bdae87a6a1cec5c5689cde82e72cccb13993f730",
    },
    I915_DP_PATH: {
        "patch": "patches/0004-pre-skl-dp-aux-precharge-linux-8ec7d10a-netbsd11.patch",
        "patch_sha256": "9fe5faccdda6cb55a1f0966cc076a46ea7356d533174a67da377d4ce228662ee",
        "original_sha256": G08_PINNED_SHA256,
    },
}


def _checked_chv_apply(i915_repo: Path, source_path: str, source: bytes) -> bytes:
    """Apply only one fixed owner patch to an isolated real-file copy."""
    record = CHV_FIXES[source_path]
    patch_file = i915_repo / record["patch"]
    if not patch_file.is_file() or patch_file.is_symlink():
        refuse("CHV_OWNER_PATCH_MISSING")
    patch = patch_file.read_bytes()
    if hashlib.sha256(patch).hexdigest() != record["patch_sha256"]:
        refuse("CHV_OWNER_PATCH_SHA_MISMATCH")
    with tempfile.TemporaryDirectory(prefix="hp-i915-chv-source-") as tmp:
        root = Path(tmp)
        target = root / source_path
        target.parent.mkdir(parents=True)
        target.write_bytes(source)
        for mode in ("--check", ""):
            command = ["git", "apply", *( [mode] if mode else []), str(patch_file)]
            try:
                result = subprocess.run(
                    command, cwd=root, capture_output=True, timeout=20,
                    check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                refuse("CHV_PATCH_APPLY_TOOL_FAILURE_" + type(exc).__name__)
            if result.returncode != 0:
                refuse("CHV_PATCH_CONTEXT_OR_DUPLICATE_" + source_path)
        updated = target.read_bytes()
    if updated == source or b"\x00" in updated:
        refuse("CHV_PATCH_NO_ACTUAL_CHANGE")
    return updated


def build_chv_hardware_fixes(
    i915_repo: Path, base_dp: bytes, traced_dp: bytes, base_power: bytes
) -> tuple[bytes, bytes, dict]:
    """Only pins/applies CHV AUX precharge + delayed PHY write.

    Apply DP hardware correction both with and without G08 trace; after both
    runs, the existing 14 guarded trace blocks must remain the SOLE delta.
    """
    if hashlib.sha256(base_dp).hexdigest() != G08_PINNED_SHA256:
        refuse("CHV_DP_BASE_SHA_MISMATCH")
    expected_power_sha = CHV_FIXES[CHV_POWER_PATH]["original_sha256"]
    if hashlib.sha256(base_power).hexdigest() != expected_power_sha:
        refuse("CHV_POWER_BASE_SHA_MISMATCH")
    verify_g08_overlay(base_dp, traced_dp)
    patched_power = _checked_chv_apply(i915_repo, CHV_POWER_PATH, base_power)
    bare_dp = _checked_chv_apply(i915_repo, I915_DP_PATH, base_dp)
    final_dp = _checked_chv_apply(i915_repo, I915_DP_PATH, traced_dp)
    verify_g08_overlay(bare_dp, final_dp)
    power_text = patched_power.decode("utf-8")
    dp_text = final_dp.decode("utf-8")
    if (".sync_hw = chv_pipe_power_well_sync_hw," not in power_text or
            "I915_WRITE(DISPLAY_PHY_CONTROL, dev_priv->chv_phy_control);" not in power_text):
        refuse("CHV_POWER_WELL_SYNC_SEMANTICS_INVALID")
    if "(3 << DP_AUX_CH_CTL_PRECHARGE_2US_SHIFT)" not in dp_text:
        refuse("CHV_AUX_PRECHARGE_SEMANTICS_INVALID")
    return final_dp, patched_power, {
        "i915_chv_hw_state": "VERIFIED_PINNED_CHV_AUX3_PHY_SYNC_PRIVATE_FIX",
        "i915_chv_hw_patch_sha256": {
            path: record["patch_sha256"] for path, record in CHV_FIXES.items()
        },
        "i915_chv_phy_original_sha256": expected_power_sha,
        "i915_chv_phy_output_sha256": hashlib.sha256(patched_power).hexdigest(),
        "i915_chv_dp_original_sha256": G08_PINNED_SHA256,
        "i915_chv_dp_output_sha256": hashlib.sha256(final_dp).hexdigest(),
        "i915_chv_dp_g08_blocks_preserved": 14,
        "i915_chv_semantic_parity_323_proven": False,
    }


# Existing i915-owner candidate 0013: without an installed and runtime-enabled
# IRQ, an early eDP AUX wait must poll rather than enter the IRQ-only wait.
AUX_IRQ_PATCH = "candidates/0013-i915-edp-aux-poll-when-irqs-disabled-netbsd11.patch"
AUX_IRQ_PATCH_SHA256 = (
    "3806db3f9ef738d1d1d79b3adc96237ea9e3cdf1f43fc4ec4c9ddeb0f591f997"
)
AUX_IRQ_OLD = "\tif (!cold) {\n"
AUX_IRQ_NEW = (
    "\tif (!cold && i915->drm.irq_enabled &&\n"
    "\t    i915->runtime_pm.irqs_enabled) {\n"
)


def _aux_irq_checked_patch(i915_repo: Path, source: bytes) -> bytes:
    """Apply only the pinned producer's 0013 inside the real AUX wait."""
    path = i915_repo / AUX_IRQ_PATCH
    if not path.is_file() or path.is_symlink():
        refuse("AUX_IRQ_OWNER_PATCH_MISSING")
    patch = path.read_bytes()
    if hashlib.sha256(patch).hexdigest() != AUX_IRQ_PATCH_SHA256:
        refuse("AUX_IRQ_OWNER_PATCH_SHA_MISMATCH")
    original = source.decode("utf-8")
    start = "static u32\nintel_dp_aux_wait_done("
    stop = "static u32 g4x_get_aux_clock_divider("
    if original.count(start) != 1 or original.count(stop) != 1:
        refuse("AUX_IRQ_WAIT_BOUNDARY_DRIFT")
    i = original.index(start)
    j = original.index(stop, i)
    block = original[i:j]
    if ("#ifdef __NetBSD__\n" + AUX_IRQ_OLD) not in block:
        refuse("AUX_IRQ_NETBSD_BRANCH_DRIFT")
    if block.count(AUX_IRQ_OLD) != 1 or AUX_IRQ_NEW in block:
        refuse("AUX_IRQ_DUPLICATE_OR_BRANCH_DRIFT")
    if "done = wait_for_atomic(C, timeout_ms) == 0;" not in block:
        refuse("AUX_IRQ_ATOMIC_FALLBACK_MISSING")
    expected = (original[:i] + block.replace(AUX_IRQ_OLD, AUX_IRQ_NEW, 1)
                + original[j:]).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="hp-i915-aux-irq-source-") as tmp:
        root = Path(tmp)
        target = root / I915_DP_PATH
        target.parent.mkdir(parents=True)
        target.write_bytes(source)
        for action in (["--check"], []):
            try:
                proc = subprocess.run(
                    ["git", "apply", *action, str(path)], cwd=root,
                    capture_output=True, timeout=20, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                refuse("AUX_IRQ_PATCH_TOOL_FAILURE_" + type(exc).__name__)
            if proc.returncode:
                refuse("AUX_IRQ_CONTEXT_CONFLICT_OR_DRIFT")
        changed = target.read_bytes()
    if changed != expected:
        refuse("AUX_IRQ_UNRELATED_DRIVER_CHANGE")
    return changed


def build_aux_irq_private_overlay(
    i915_repo: Path, g08_chv_traced_dp: bytes
) -> tuple[bytes, dict]:
    """Append 0013 to 0004+0039, preserve exact G08 traces and precharge."""
    text = g08_chv_traced_dp.decode("utf-8")
    bare, count = G08_GUARD.subn("", text)
    if count != 14:
        refuse("AUX_IRQ_G08_TRACE_COUNT_DRIFT")
    verify_g08_overlay(bare.encode("utf-8"), g08_chv_traced_dp)
    bare_patched = _aux_irq_checked_patch(i915_repo, bare.encode("utf-8"))
    final = _aux_irq_checked_patch(i915_repo, g08_chv_traced_dp)
    verify_g08_overlay(bare_patched, final)
    if b"(3 << DP_AUX_CH_CTL_PRECHARGE_2US_SHIFT)" not in final:
        refuse("AUX_IRQ_PRECHARGE_LOST")
    return final, {
        "i915_aux_irq_state": "VERIFIED_PINNED_IRQ_UNAVAILABLE_POLL_PRIVATE_OVERLAY",
        "i915_aux_irq_patch_sha256": AUX_IRQ_PATCH_SHA256,
        "i915_aux_irq_input_sha256": hashlib.sha256(
            g08_chv_traced_dp).hexdigest(),
        "i915_aux_irq_output_sha256": hashlib.sha256(final).hexdigest(),
        "i915_aux_irq_g08_blocks_preserved": 14,
        "i915_aux_irq_full_323_semantic_closure": False,
    }


# Existing i915-owner source correction 0012: a truncated eDP DPCD rates
# response must not leave uninitialized stack entries in the rate decoder.
EDP_DPCD_PATCH = "candidates/0012-i915-edp-dpcd-rates-failed-aux-read-netbsd11.patch"
EDP_DPCD_SHA256 = (
    "a50717c043eff10e31c5dd8d9582632d71197203c5a13738e12e7e520817a5fa"
)
EDP_DPCD_OLD = (
    "\t\tdrm_dp_dpcd_read(&intel_dp->aux, DP_SUPPORTED_LINK_RATES,\n"
    "\t\t\t\tsink_rates, sizeof(sink_rates));"
)
EDP_DPCD_NEW = (
    "\t\tif (drm_dp_dpcd_read(&intel_dp->aux, DP_SUPPORTED_LINK_RATES,\n"
    "\t\t\t\t     sink_rates, sizeof(sink_rates)) !=\n"
    "\t\t    (ssize_t)sizeof(sink_rates)) {\n"
    "\t\t\tDRM_DEBUG_KMS(\"Unable to read eDP supported link rates, \"\n"
    "\t\t\t\t      \"using default rates\\n\");\n"
    "\t\t\tmemset(sink_rates, 0, sizeof(sink_rates));\n"
    "\t\t}"
)


def _checked_edp_rate_apply(i915_repo: Path, source: bytes) -> bytes:
    path = i915_repo / EDP_DPCD_PATCH
    if not path.is_file() or path.is_symlink():
        refuse("EDP_DPCD_OWNER_PATCH_MISSING")
    patch = path.read_bytes()
    if hashlib.sha256(patch).hexdigest() != EDP_DPCD_SHA256:
        refuse("EDP_DPCD_PATCH_SHA_MISMATCH")
    original = source.decode("utf-8")
    start = "static bool\nintel_edp_init_dpcd("
    stop = "static bool\nintel_dp_get_dpcd("
    if original.count(start) != 1 or original.count(stop) != 1:
        refuse("EDP_DPCD_FN_BOUNDARY_DRIFT")
    i = original.index(start)
    j = original.index(stop, i)
    fragment = original[i:j]
    if fragment.count(EDP_DPCD_OLD) != 1 or EDP_DPCD_NEW in fragment:
        refuse("EDP_DPCD_DUPLICATE_OR_CONTEXT_DRIFT")
    if "intel_dp->num_sink_rates = i;" not in fragment or (
            "intel_dp_set_sink_rates(intel_dp);" not in fragment):
        refuse("EDP_DPCD_FALLBACK_OR_DECODER_DRIFT")
    expected = (original[:i] +
                fragment.replace(EDP_DPCD_OLD, EDP_DPCD_NEW, 1) +
                original[j:]).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="hp-i915-edp-rate-source-") as tmp:
        root = Path(tmp)
        target = root / I915_DP_PATH
        target.parent.mkdir(parents=True)
        target.write_bytes(source)
        for check_args in (["--check"], []):
            try:
                proc = subprocess.run(
                    ["git", "apply", *check_args, str(path)], cwd=root,
                    capture_output=True, timeout=20, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                refuse("EDP_DPCD_APPLY_TOOL_FAILURE_" + type(exc).__name__)
            if proc.returncode:
                refuse("EDP_DPCD_PATCH_CONTEXT_OR_DUPLICATE")
        changed = target.read_bytes()
    if changed != expected:
        refuse("EDP_DPCD_UNRELATED_SOURCE_DELTA")
    return changed


def build_edp_dpcd_private_overlay(
    i915_repo: Path, dp_after_g08_chv_and_irq: bytes
) -> tuple[bytes, dict]:
    """After 0004+0013+0039: checked 0012; 14 G08 guards stay unchanged."""
    text = dp_after_g08_chv_and_irq.decode("utf-8")
    bare, count = G08_GUARD.subn("", text)
    if count != 14:
        refuse("EDP_DPCD_G08_TRACE_DRIFT")
    verify_g08_overlay(bare.encode("utf-8"), dp_after_g08_chv_and_irq)
    if "(3 << DP_AUX_CH_CTL_PRECHARGE_2US_SHIFT)" not in text or (
            "if (!cold && i915->drm.irq_enabled &&" not in text):
        refuse("EDP_DPCD_PRECONDITION_MISSING")
    bare_updated = _checked_edp_rate_apply(i915_repo, bare.encode("utf-8"))
    final = _checked_edp_rate_apply(i915_repo, dp_after_g08_chv_and_irq)
    verify_g08_overlay(bare_updated, final)
    if final.count(b"memset(sink_rates, 0, sizeof(sink_rates));") != 1:
        refuse("EDP_DPCD_CLEAR_NOT_UNIQUE")
    return final, {
        "i915_edp_dpcd_state": "VERIFIED_PINNED_SHORT_READ_SAFE_PRIVATE_OVERLAY",
        "i915_edp_dpcd_patch_sha256": EDP_DPCD_SHA256,
        "i915_edp_dpcd_input_sha256": hashlib.sha256(
            dp_after_g08_chv_and_irq).hexdigest(),
        "i915_edp_dpcd_output_sha256": hashlib.sha256(final).hexdigest(),
        "i915_edp_dpcd_g08_blocks_preserved": 14,
        "i915_edp_dpcd_full_323_semantic_closure": False,
    }


# Exact upstream NetBSD PPS timeout-log correction; changes no timings/IO.
# Applies ONLY to the private, pinned nonrelease display/intel_dp.c overlay.
PPS_TIMEOUT_PATCH = "patches/0041-netbsd11-i915-chv-pps-timeout-no-false-success.patch"
PPS_TIMEOUT_SHA256 = (
    "4eda6344f97d6e9a5d5c3677150878f9b008c376f9a387799c0bc3c82c3eeb45"
)
PPS_WAIT_OLD = (
    b'\tif (intel_de_wait_for_register(dev_priv, pp_stat_reg,\n'
    b'\t\t\t\t       mask, value, 5000))\n'
    b'\t\tDRM_ERROR("Panel status timeout: status %08x control %08x\\n",\n'
    b'\t\t\t\tI915_READ(pp_stat_reg),\n'
    b'\t\t\t\tI915_READ(pp_ctrl_reg));\n'
    b'\n'
    b'\tDRM_DEBUG_KMS("Wait complete\\n");'
)
PPS_WAIT_NEW = (
    b'\tif (intel_de_wait_for_register(dev_priv, pp_stat_reg,\n'
    b'\t\t\t\t       mask, value, 5000)) {\n'
    b'\t\tDRM_ERROR("Panel status timeout: status %08x control %08x\\n",\n'
    b'\t\t\t\tI915_READ(pp_stat_reg),\n'
    b'\t\t\t\tI915_READ(pp_ctrl_reg));\n'
    b'\t\treturn;\n'
    b'\t}\n'
    b'\n'
    b'\tDRM_DEBUG_KMS("Wait complete\\n");'
)


def build_pps_timeout_private_overlay(
    i915_repo: Path, staged_dp: bytes
) -> tuple[bytes, dict]:
    """Apply source-pinned 0041 after all previous CHV/AUX/eDP overlays."""
    if staged_dp.count(PPS_WAIT_OLD) != 1 or PPS_WAIT_NEW in staged_dp:
        refuse("PPS_TIMEOUT_OLD_SOURCE_MISSING_OR_ALREADY_FIXED")
    text = staged_dp.decode("utf-8")
    bare, count = G08_GUARD.subn("", text)
    if count != 14:
        refuse("PPS_TIMEOUT_EXPECTED_14_G08_TRACES")
    verify_g08_overlay(bare.encode("utf-8"), staged_dp)
    patch_file = i915_repo / PPS_TIMEOUT_PATCH
    if not patch_file.is_file() or patch_file.is_symlink():
        refuse("PPS_TIMEOUT_OWNER_PATCH_MISSING")
    patch = patch_file.read_bytes()
    if hashlib.sha256(patch).hexdigest() != PPS_TIMEOUT_SHA256:
        refuse("PPS_TIMEOUT_OWNER_PATCH_SHA_MISMATCH")
    with tempfile.TemporaryDirectory(prefix="hp-pps-chv-nonrelease-") as tmp:
        root = Path(tmp)
        target = root / I915_DP_PATH
        target.parent.mkdir(parents=True)
        target.write_bytes(staged_dp)
        for option in ("--check", None):
            cmd = ["git", "apply"]
            if option is not None:
                cmd.append(option)
            cmd.append(str(patch_file))
            try:
                completed = subprocess.run(
                    cmd, cwd=root, capture_output=True, check=False,
                    timeout=20)
            except (OSError, subprocess.TimeoutExpired) as err:
                refuse("PPS_TIMEOUT_GIT_TOOL_" + type(err).__name__)
            if completed.returncode != 0:
                refuse("PPS_TIMEOUT_PATCH_CONTEXT_OR_DUPLICATE")
        final = target.read_bytes()
    if final != staged_dp.replace(PPS_WAIT_OLD, PPS_WAIT_NEW, 1):
        refuse("PPS_TIMEOUT_PATCH_UNRELATED_DELTA")
    final_text = final.decode("utf-8")
    bare_final, n = G08_GUARD.subn("", final_text)
    if n != 14:
        refuse("PPS_TIMEOUT_G08_CORRUPTION")
    verify_g08_overlay(bare_final.encode("utf-8"), final)
    return final, {
        "i915_pps_timeout_state": "PINNED_DIAGNOSTIC_FALSE_SUCCESS_GUARD_NONRELEASE",
        "i915_pps_timeout_patch_sha256": PPS_TIMEOUT_SHA256,
        "i915_pps_timeout_input_sha256": hashlib.sha256(staged_dp).hexdigest(),
        "i915_pps_timeout_output_sha256": hashlib.sha256(final).hexdigest(),
        "i915_pps_timeout_g08_preserved": 14,
        "i915_pps_timeout_kernel_build": False,
        "i915_pps_timeout_full_323_semantic_closure": False,
    }
