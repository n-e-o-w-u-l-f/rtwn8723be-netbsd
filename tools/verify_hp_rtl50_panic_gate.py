#!/usr/bin/env python3
"""Fail-closed, read-only HP RTL50 full-kernel prebuild panic evidence gate.

No compiler, NetBSD configuration, hardware access, install or reboot.
This schema verifies traceability, NOT the truth of an asserted root cause.
The mandatory external human/source review remains independently required.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FAILED_SOURCE = "2e5a2cc97b9bbae3e55aa984e1477e7c29858bce"
FAILED_SHA256 = "2eecc4e188c247514d5bc5b639c2773f3d8a823e4f84cc3a65e7e4960471a423"

def stop(msg: str) -> None:
    raise ValueError("PANIC_PREBUILD_REFUSED: " + msg)

def text_value(obj: dict, field: str, minimum: int = 20) -> str:
    value = obj.get(field)
    if not isinstance(value, str) or len(value.strip()) < minimum:
        stop("missing/short " + field)
    return value

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", required=True, type=Path,
                   help="read-only, reviewed HP panic dossier JSON (not a generated fake)")
    p.add_argument("--new-source", required=True,
                   help="exact clean 40-hex Git commit being built")
    args = p.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.new_source) is None:
        stop("new source commit must be 40 lowercase Git hex digits")
    if args.new_source == FAILED_SOURCE:
        stop("the panicking source revision must never be rebuilt unchanged")
    if args.evidence.is_symlink() or not args.evidence.is_file():
        stop("panic evidence must be an existing regular non-symlinked file")
    try:
        data = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        stop("cannot read valid panic evidence JSON: " + str(exc))
    if not isinstance(data, dict):
        stop("evidence root must be a JSON object")
    if data.get("panicking_source_commit") != FAILED_SOURCE or (
            data.get("panicking_kernel_sha256") != FAILED_SHA256):
        stop("panic trace is not tied to the actually booted RTL50 kernel")
    if data.get("candidate_source_commit") != args.new_source:
        stop("evidence is not tied to the exact proposed new candidate")
    for key in ("panic_console_or_savecore_log", "stacktrace_analysis",
                "failed_lifecycle_stage", "root_cause_with_negative_controls",
                "frozen_linux_function_and_commit",
                "netbsd_11_native_api_and_lifetime_mapping",
                "reviewed_source_diff", "regression_run_result",
                "recovery_boot_and_kernel_identity"):
        text_value(data, key)
    frames = data.get("panic_backtrace_frames")
    if (not isinstance(frames, list) or len(frames) < 2 or
            not all(isinstance(f, str) and len(f.strip()) > 5 for f in frames)):
        stop("actual crash backtrace with at least 2 frames required")
    blockers = data.get("build_plan_open_critical_blockers")
    if not isinstance(blockers, list) or blockers:
        stop("critical build-plan blockers must be an explicitly empty reviewed list")
    if data.get("manual_crash_root_cause_review_pass") is not True:
        stop("independent root-cause and source-review gate not approved")
    if data.get("native_hp_regression_pass") is not True:
        stop("HP-native revised candidate regression not verified")
    if data.get("boot_default_preserved") is not True:
        stop("verified known-good boot fallback is required")
    print("RTL50_PANIC_SOURCE_CAUSE_PREBUILD_EVIDENCE_ACCEPTED", args.new_source)
    print("NOTICE: documentary evidence schema passed, hardware safety still needs independent review")

if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        sys.exit(3)
