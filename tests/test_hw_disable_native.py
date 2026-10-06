#!/usr/bin/env python3
"""HP-only actual native stop adapter under fake held owner and bus_space.

Delegated poweroff is mocked here; the existing real power-flow tests and
native full-object build are separate evidence. This is not hardware proof.
"""
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT if (ROOT / 'src/rtwn8723be_calibration.c').is_file() else ROOT.parent
if platform.system() != 'NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
    raise SystemExit('REFUSED: native hw-disable compilation/tests are HP-only')
subprocess.run([sys.executable, str(ROOT / 'tools/validate_hw_disable_sources.py')], check=True)
with tempfile.TemporaryDirectory(prefix='hp-hw-disable-native-', dir=ROOT) as tmp:
    tmp = Path(tmp)
    (tmp / 'sys').mkdir()
    (tmp / 'sys/systm.h').write_text('#include <string.h>\n')
    (tmp / 'rtwn8723be_netbsd.h').write_text((ROOT / 'tests/hw_disable_fake_netbsd.h').read_text())
    native = (ROOT / 'src/rtwn8723be_hw_disable_native.c').read_text()
    native = native.replace('__KERNEL_RCSID(0, "$NetBSD$");', '')
    source = tmp / 'rtwn8723be_hw_disable_native.c'
    source.write_text(native)
    check = tmp / 'check.c'
    check.write_text((ROOT / 'tests/hw_disable_native_check.c').read_text())
    exe = tmp / 'check'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-fsanitize=undefined', '-fno-sanitize-recover=all',
        '-Wno-unused-parameter', '-Wno-unused-variable',
        '-I', str(tmp), '-I', str(ROOT / 'src'), '-I', str(CORE / 'src'),
        '-I', str(ROOT / 'tests'), str(source),
        str(ROOT / 'src/rtwn8723be_hw_disable.c'),
        str(ROOT / 'tests/hw_disable_linux_oracle.c'), str(check), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
