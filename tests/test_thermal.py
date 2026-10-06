#!/usr/bin/env python3
"""HP-only real thermal and calibration C against frozen Linux bodies."""
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT if (ROOT / 'src/rtwn8723be_calibration.c').is_file() else ROOT.parent
if platform.system() != 'NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
    raise SystemExit('REFUSED: thermal compilation/tests are HP-only')
subprocess.run([sys.executable, str(CORE / 'tools/validate_calibration_sources.py')], check=True)
subprocess.run([sys.executable, str(ROOT / 'tools/validate_thermal_sources.py')], check=True)
with tempfile.TemporaryDirectory(prefix='hp-thermal-', dir=ROOT) as tmp:
    tmp = Path(tmp)
    flags = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic',
             '-fsanitize=undefined', '-fno-sanitize-recover=all']
    includes = ['-I', str(ROOT / 'src'), '-I', str(CORE / 'src'),
                '-I', str(CORE / 'tests')]
    units = []
    for source in (ROOT / 'src/rtwn8723be_thermal.c', CORE / 'src/rtwn8723be_calibration.c'):
        obj = tmp / (source.stem + '.o')
        subprocess.run(flags + includes + ['-c', str(source), '-o', str(obj)], check=True)
        units.append(str(obj))
    exe = tmp / 'check'
    subprocess.run(flags + includes + [
        '-Wno-unused-parameter', '-Wno-unused-variable', '-Wno-unused-function',
        str(CORE / 'tests/calibration_linux_oracle.c'),
        str(ROOT / 'tests/thermal_linux_oracle.c'),
        str(ROOT / 'tests/thermal_check.c'), *units, '-o', str(exe)
    ], check=True)
    subprocess.run([str(exe)], check=True)
