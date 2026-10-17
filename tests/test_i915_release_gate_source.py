#!/usr/bin/env python3
"""Source-only synthetic Git release acceptance for the i915 dependency.

Tests actual gate logic using disposable *local Git repositories*. No C
compiler, NetBSD kernel or HP hardware is accessed or modified.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_i915_kernel_release import (  # noqa: E402
    EXPECTED_REMOTE, EXPECTED_SCOPE, EXPECTED_TARGET, PASS_FLAGS,
    RELEASE_PATH, check,
)

RTL_SHA = "a" * 40


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args], text=True, capture_output=True,
        check=True, timeout=15,
    )
    return r.stdout.strip()


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=RTL Test", "-c",
        "user.email=rtl-test@example.invalid", "commit", "--quiet", "-m",
        message)
    return git(repo, "rev-parse", "HEAD")


def release_data(base: str) -> dict:
    return {
        "schema": 1,
        "target": EXPECTED_TARGET,
        "decision": "APPROVED",
        "scope": EXPECTED_SCOPE,
        "rtl_source_sha": RTL_SHA,
        "validated_i915_source_sha": base,
        "verification": {key: "PASS" for key in PASS_FLAGS},
        "approval": {"owner": "HP-I915", "release_id": "synthetic-unit-test"},
    }


def write_release(repo: Path, data: dict | str) -> None:
    path = repo / RELEASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        data if isinstance(data, str) else json.dumps(data, sort_keys=True),
        encoding="utf-8",
    )
    commit(repo, "synthetic approval for gating unit test")


def assert_gate(repo: Path, rtl: str, expected: bool, label: str) -> None:
    ok, reason = check(repo, rtl)
    assert ok is expected, (label, ok, reason)


with tempfile.TemporaryDirectory(prefix="rtl-i915-release-gate-") as temp:
    repo = Path(temp) / "fake-i915"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "remote", "add", "origin",
        "https://github.com/" + EXPECTED_REMOTE + ".git")
    (repo / "readme.txt").write_text("source baseline\n", encoding="utf-8")
    base = commit(repo, "initial source snapshot")
    assert_gate(repo, RTL_SHA, False, "release missing")
    assert_gate(repo, "broken", False, "invalid rtl hash")
    good = release_data(base)
    write_release(repo, good)
    assert_gate(repo, RTL_SHA, True, "complete i915-owned release")
    assert_gate(repo, "b" * 40, False, "unrelated RTL SHA")
    # The release must reside in the actual canonical i915 repo, not in
    # a writable local file or a similarly named unrelated remote.
    git(repo, "remote", "set-url", "origin",
        "https://github.com/someone-else/i915-cherryview-braswell-netbsd.git")
    assert_gate(repo, RTL_SHA, False, "wrong origin")
    git(repo, "remote", "set-url", "origin",
        "https://github.com/" + EXPECTED_REMOTE + ".git")
    (repo / "readme.txt").write_text("uncommitted mutation", encoding="utf-8")
    assert_gate(repo, RTL_SHA, False, "dirty git worktree")
    git(repo, "restore", "readme.txt")
    assert_gate(repo, RTL_SHA, True, "restored checkout")
    mutants = [
        ("decision", {"decision": "PENDING"}),
        ("target", {"target": "some-other-host"}),
        ("scope", {"scope": "SOURCE_ONLY"}),
        ("rtl_source_sha", {"rtl_source_sha": "b" * 40}),
        ("verified_i915_missing", {"validated_i915_source_sha": ""}),
        ("verified_i915_not_in_history",
         {"validated_i915_source_sha": "0" * 40}),
        ("approval_wrong_owner", {"approval": {"owner": "RTL8723BE",
           "release_id": "not-issued-by-i915"}}),
        ("approval_id_missing", {"approval": {"owner": "HP-I915",
           "release_id": ""}}),
        ("wrong_schema", {"schema": 2}),
    ]
    cases = 5
    for label, replacements in mutants:
        altered = release_data(base)
        altered.update(replacements)
        write_release(repo, altered)
        assert_gate(repo, RTL_SHA, False, label)
        cases += 1
    for flag in PASS_FLAGS:
        altered = release_data(base)
        altered["verification"][flag] = "OPEN"
        write_release(repo, altered)
        assert_gate(repo, RTL_SHA, False, "missing evidence " + flag)
        cases += 1
    write_release(repo, "{broken JSON")
    assert_gate(repo, RTL_SHA, False, "invalid JSON")
    cases += 1
    write_release(repo, release_data(base))
    assert_gate(repo, RTL_SHA, True, "valid recovery after negative tests")
    cases += 1

# Protect the shell entrypoint from deletion or relocation of the guard.
builder = (ROOT / "tools/build_hp_rtl50_next_candidate.sh").read_text()
gate = '"$PYTHON" -B "$ROOT/tools/check_i915_kernel_release.py"'
assert builder.count(gate) == 2, "i915 gate must guard preflight and staging"
assert builder.index(gate) < builder.index("for testname in")
assert builder.index(gate, builder.index(gate) + 1) < builder.index('OUT="$WORK/')
assert "I915_REPO=" in builder
print(f"I915_KERNEL_BUILD_RELEASE_GATE_PASS: {cases} synthetic release "
      "and rejection cases; dual shell guard; no HP/kernel execution")
