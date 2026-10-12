#!/usr/bin/env python3
"""Read-only HP NetBSD RTL50 post-panic inventory (never reads core memory).

Lists artifact identities and savecore metadata, not a guessed panic cause.
Safe on a recovered generic/F77 kernel; requires no root, build, reboot, or
network. Run against the same HP where the panic occurred. Crash dumps can
contain sensitive memory: never upload them automatically.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys

FAILED_SOURCE = "2e5a2cc97b9bbae3e55aa984e1477e7c29858bce"
FAILED_SHA256 = "2eecc4e188c247514d5bc5b639c2773f3d8a823e4f84cc3a65e7e4960471a423"
BUILD = Path("/home/andreas/projects/netbsd-driver-recovery-20261011")
ARTIFACTS = (
    Path("/netbsd.rtl50"),
    BUILD / ("rtl-kconfig-live-" + FAILED_SOURCE[:12]) / "obj/netbsd",
)
CRASH = Path("/var/crash")
BOOTCFG = Path("/boot.cfg")

def command(*args):
    try:
        cp = subprocess.run(args, capture_output=True, text=True,
                            timeout=8, check=False)
        return {"exit": cp.returncode, "stdout": cp.stdout[:4000].strip(),
                "stderr": cp.stderr[:500].strip()}
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return {"error": type(exc).__name__}

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()

def stat_only(path):
    try:
        if path.is_symlink():
            return {"path": str(path), "status": "SYMLINK_REFUSED"}
        if not path.is_file():
            return {"path": str(path), "status": "NOT_REGULAR_OR_MISSING"}
        st = path.stat()
        return {"path": str(path), "status": "REGULAR",
                "bytes": st.st_size, "mode": oct(st.st_mode & 0o777)}
    except OSError as exc:
        return {"path": str(path), "status": type(exc).__name__}

def inspect():
    report = {
        "scope": "READ_ONLY_METADATA_ONLY_NOT_A_PANIC_BACKTRACE",
        "panicking_source_sha": FAILED_SOURCE,
        "panicking_kernel_sha256_expected": FAILED_SHA256,
        "kernel": command("/sbin/sysctl", "-n", "kern.version"),
        "bootfile": command("/sbin/sysctl", "-n", "kern.bootfile"),
        "uptime": command("/usr/bin/uptime"),
        "savecore_configured": None,
        "kernel_artifacts": [],
        "crash_entries": [],
        "boot_menu": [],
    }
    for f in ARTIFACTS:
        item = stat_only(f)
        if item["status"] == "REGULAR":
            try:
                item["sha256"] = sha256(f)
                item["is_exact_failed_build"] = item["sha256"] == FAILED_SHA256
            except OSError as exc:
                item["hash_error"] = type(exc).__name__
        report["kernel_artifacts"].append(item)
    try:
        if BOOTCFG.is_file() and not BOOTCFG.is_symlink():
            for line in BOOTCFG.read_text(errors="replace").splitlines():
                if re.match(r"^(menu|default|timeout)=", line):
                    report["boot_menu"].append(line[:300])
    except OSError as exc:
        report["boot_menu_error"] = type(exc).__name__
    for conf in (Path("/etc/rc.conf"), Path("/etc/defaults/rc.conf")):
        try:
            if conf.is_file() and not conf.is_symlink():
                values = [line[:250] for line in
                          conf.read_text(errors="replace").splitlines()
                          if re.match(r"^\s*(savecore|savecore_flags|savecore_dir)=", line)]
                if values:
                    report["savecore_configured"] = report["savecore_configured"] or {}
                    report["savecore_configured"][str(conf)] = values
        except OSError as exc:
            report.setdefault("savecore_errors", {})[str(conf)] = type(exc).__name__
    try:
        if CRASH.is_dir() and not CRASH.is_symlink():
            for entry in sorted(CRASH.iterdir(), key=lambda e: e.name)[:100]:
                if not re.match(r"^(netbsd\.|bounds$|minfree$|info\.)", entry.name):
                    continue
                report["crash_entries"].append(stat_only(entry))
        else:
            report["crash_dir"] = "NOT_READABLE_DIRECTORY"
    except OSError as exc:
        report["crash_dir"] = type(exc).__name__
    report["interpretation"] = (
        "Presence of a matching saved core+kernel enables offline crash analysis; "
        "absence does not prove a clean boot. A stack trace, panic text, failing "
        "function and causal diff remain UNKNOWN until read from the real dump/console.")
    return report

def main():
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        print("REFUSED: inspection is scoped to original HP NetBSD only", file=sys.stderr)
        return 2
    report = inspect()
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
    return 0

if __name__ == "__main__":
    sys.exit(main())
