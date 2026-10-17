#!/usr/bin/env python3
"""Read-only, fail-closed i915drmkms dependency gate for an HP kernel build.

An i915-owned, Git-tracked release in the validated local i915 repository
must explicitly authorize the exact RTL source SHA. This script cannot grant
a release; no override flag or status inference exists. It is called before
RTL native tests, source staging or NetBSD kernel compilation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

EXPECTED_REMOTE = "n-e-o-w-u-l-f/i915-cherryview-braswell-netbsd"
RELEASE_PATH = "governance/HP_I915DRMKMS_KERNEL_RELEASE.json"
EXPECTED_TARGET = "HP-TPN-W121-RTL8723BE-I915DRMKMS"
EXPECTED_SCOPE = "HP_COMBINED_KERNEL_BUILD_ALLOWED"
SHA = re.compile(r"^[0-9a-f]{40}$")
PASS_FLAGS = (
    "full_i915_drm_ttm_port",
    "netbsd_native_i915_kernel_link",
    "hp_physical_kms_display",
    "f83_f84_black_screen_resolved",
    "hp_recovery_boot_verified",
    "i915_runtime_pm_verified",
)


def refuse(reason: str) -> int:
    print("REFUSED_I915_RELEASE: " + reason, file=sys.stderr)
    return 2


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if proc.returncode != 0:
        raise ValueError("Git evidence unavailable: " + " ".join(args))
    return proc.stdout.strip()


def original_remote(value: str) -> bool:
    value = value.strip().removesuffix(".git").removesuffix("/")
    return value in (
        "https://github.com/" + EXPECTED_REMOTE,
        "ssh://git@github.com/" + EXPECTED_REMOTE,
        "git@github.com:" + EXPECTED_REMOTE,
    )


def check(i915_repo: Path, rtl_head: str) -> tuple[bool, str]:
    if not SHA.fullmatch(rtl_head):
        return False, "Invalid current RTL source SHA"
    try:
        repo = i915_repo.resolve(strict=True)
        if not repo.is_dir() or git(repo, "rev-parse", "--show-toplevel") != str(repo):
            return False, "Expected a standalone i915 source checkout"
        if not original_remote(git(repo, "remote", "get-url", "origin")):
            return False, "i915 source remote is not the canonical owning repository"
        if git(repo, "status", "--porcelain=v1"):
            return False, "i915 checkout is dirty: approval source not reproducible"
        i915_head = git(repo, "rev-parse", "HEAD")
        if not SHA.fullmatch(i915_head):
            return False, "Invalid i915 source commit SHA"
        # The release artifact must be committed *in* the owning i915 repository,
        # not created by the RTL port or injected as an environment variable.
        manifest = json.loads(git(repo, "show", "HEAD:" + RELEASE_PATH))
        if not isinstance(manifest, dict):
            return False, "i915 release manifest is not an object"
        if (manifest.get("schema") != 1 or
                manifest.get("target") != EXPECTED_TARGET or
                manifest.get("decision") != "APPROVED" or
                manifest.get("scope") != EXPECTED_SCOPE):
            return False, "No explicit i915-owned combined-kernel approval"
        if manifest.get("rtl_source_sha") != rtl_head:
            return False, "Approval does not target this exact RTL source revision"
        validated = manifest.get("validated_i915_source_sha")
        if not isinstance(validated, str) or not SHA.fullmatch(validated):
            return False, "No validated i915 source SHA"
        # The approval commit may add only the approval file, so requiring
        # the same SHA as HEAD would create an impossible self-reference.
        probe = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor",
             validated, i915_head], timeout=15, check=False,
            capture_output=True,
        )
        if probe.returncode != 0:
            return False, "Verified i915 source is not in current release history"
        evidence = manifest.get("verification")
        if not isinstance(evidence, dict) or any(
                evidence.get(flag) != "PASS" for flag in PASS_FLAGS):
            return False, "i915 full port, KMS, recovery and runtime evidence incomplete"
        approval = manifest.get("approval")
        if (not isinstance(approval, dict) or
                approval.get("owner") != "HP-I915" or
                not isinstance(approval.get("release_id"), str) or
                not approval["release_id"].strip()):
            return False, "No traceable HP-I915 project approval identity"
        return True, "I915_RELEASE_VERIFIED i915=" + i915_head + " rtl=" + rtl_head
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        return False, "Release unavailable/unverifiable: " + str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--i915-repo", type=Path, required=True)
    parser.add_argument("--rtl-head", required=True)
    args = parser.parse_args()
    permitted, message = check(args.i915_repo, args.rtl_head)
    if not permitted:
        return refuse(message)
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
