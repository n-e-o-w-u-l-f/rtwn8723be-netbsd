#!/usr/bin/env python3
"""HP-only real C IQK/LCK versus frozen Linux oracle + fallible I/O checks.

This verifies the calibration engine's emitted masked writes and delays,
state/recovery results, and error paths under a fake register backend.
It does not verify NetBSD bus_space, on-device RF, BTC/DM integration or parity.
"""
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
    raise SystemExit("REFUSED: calibration compilation/tests are HP-only")
subprocess.run([sys.executable,
    str(ROOT / 'tools/validate_calibration_sources.py')], check=True)
with tempfile.TemporaryDirectory(prefix="hp-calibration-", dir=ROOT) as tmp:
    exe = Path(tmp) / "check"
    portable = Path(tmp) / "calibration.o"
    flags = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-fsanitize=undefined", "-fno-sanitize-recover=all"]
    subprocess.run(flags + ["-I", str(ROOT / "src"), "-c",
        str(ROOT / "src/rtwn8723be_calibration.c"), "-o", str(portable)], check=True)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-Wno-unused-parameter", "-Wno-unused-variable", "-Wno-unused-function",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(ROOT / "src"), "-I", str(ROOT / "tests"),
        str(portable),
        str(ROOT / "tests/calibration_linux_oracle.c"),
        str(ROOT / "tests/calibration_check.c"), "-o", str(exe)
    ], check=True)
    subprocess.run([str(exe)], check=True)
