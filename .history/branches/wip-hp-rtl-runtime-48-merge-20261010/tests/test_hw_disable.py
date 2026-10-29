#!/usr/bin/env python3
"""HP-only real card-disable engine against frozen hw.c/led.c function oracle."""
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT if (ROOT / 'src/rtwn8723be_calibration.c').is_file() else ROOT.parent
if platform.system() != 'NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
    raise SystemExit('REFUSED: hw-disable compilation/tests are HP-only')
subprocess.run([sys.executable, str(ROOT / 'tools/validate_hw_disable_sources.py')], check=True)
with tempfile.TemporaryDirectory(prefix='hp-hw-disable-', dir=ROOT) as tmp:
    tmp = Path(tmp)
    flags = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic',
             '-fsanitize=undefined', '-fno-sanitize-recover=all',
             '-I', str(ROOT / 'src'), '-I', str(CORE / 'src'),
             '-I', str(ROOT / 'tests')]
    obj = tmp / 'hw-disable.o'
    subprocess.run(flags + ['-c', str(ROOT / 'src/rtwn8723be_hw_disable.c'),
                            '-o', str(obj)], check=True)
    exe = tmp / 'check'
    subprocess.run(flags + ['-Wno-unused-parameter', '-Wno-unused-variable',
        str(ROOT / 'tests/hw_disable_linux_oracle.c'),
        str(ROOT / 'tests/hw_disable_check.c'), str(obj), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
