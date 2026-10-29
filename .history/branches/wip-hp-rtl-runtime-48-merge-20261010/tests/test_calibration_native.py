#!/usr/bin/env python3
"""HP-only actual native adapter under fake lifecycle owner and bus_space.

RF serial is mocked here; the separate real RF serial engine tests cover its
protocol. This check is not on-device calibration or BTC/DM parity.
"""
from pathlib import Path
import platform
import socket
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
    raise SystemExit("REFUSED: native calibration compilation/tests are HP-only")
with tempfile.TemporaryDirectory(prefix="hp-calibration-native-", dir=ROOT) as tmp:
    tmp = Path(tmp)
    (tmp / 'sys').mkdir()
    (tmp / 'sys/systm.h').write_text('#include <string.h>\nvoid delay(unsigned int);\n')
    (tmp / 'rtwn8723be_netbsd.h').write_text((ROOT / 'tests/calibration_fake_netbsd.h').read_text())
    # Keep the production body intact; the host lacks the kernel RCS macro.
    native = (ROOT / 'src/rtwn8723be_calibration_native.c').read_text()
    native = native.replace('__KERNEL_RCSID(0, "$NetBSD$");', '')
    source = tmp / 'rtwn8723be_calibration_native.c'
    source.write_text(native)
    check = tmp / 'check.c'
    check.write_text((ROOT / 'tests/calibration_native_check.c').read_text())
    exe = tmp / 'check'
    subprocess.run([
        'cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-fsanitize=undefined', '-fno-sanitize-recover=all',
        '-I', str(tmp), '-I', str(ROOT / 'src'), str(source),
        str(ROOT / 'src/rtwn8723be_calibration.c'), str(check), '-o', str(exe)
    ], check=True)
    subprocess.run([str(exe)], check=True)
