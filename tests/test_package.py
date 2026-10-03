#!/usr/bin/env python3
"""Strict host-C test of production raw-PHY-EFUSE package decoder.

Frozen Linux pin is verified using the supplied Linux source tree.
This does not test NetBSD bus_space, efuse_power_switch, real hardware
or the still-unwired native softc/lifecycle adapter.
"""
from pathlib import Path
import argparse
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEST = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "rtwn8723be_package.h"
struct trace {
    int on, off, read;
    int fail_on, fail_off, fail_read;
    uint8_t raw;
};
static int power(void *p, bool enable) {
    struct trace *t = p;
    if (enable) { t->on++; return t->fail_on; }
    t->off++;
    return t->fail_off;
}
static int read_byte(void *p, uint16_t offset, uint8_t *out) {
    struct trace *t = p;
    assert(offset == RTWN8723BE_PACKAGE_EFUSE_ADDRESS);
    t->read++;
    if (t->fail_read) return t->fail_read;
    *out = t->raw;
    return 0;
}
int main(void) {
    const uint8_t expected[8] = {0,0,0,0,4,2,1,3};
    unsigned i;
    struct trace t;
    uint8_t out;
    for (i=0;i<256;i++)
        assert(rtwn8723be_package_decode((uint8_t)i) == expected[i & 7]);
    for (i=0;i<8;i++) {
        t=(struct trace){.raw=(uint8_t)i}; out=255;
        assert(rtwn8723be_package_read(&t,power,read_byte,&out)==0);
        assert(t.on==1 && t.read==1 && t.off==1 && out==expected[i]);
    }
    t=(struct trace){.fail_on=ENXIO};out=99;
    assert(rtwn8723be_package_read(&t,power,read_byte,&out)==ENXIO);
    assert(t.on==1 && t.off==1 && t.read==0 && out==0);
    t=(struct trace){.fail_read=EIO};out=99;
    assert(rtwn8723be_package_read(&t,power,read_byte,&out)==EIO);
    assert(t.on==1 && t.off==1 && t.read==1 && out==0);
    t=(struct trace){.fail_off=EBUSY,.raw=6};out=99;
    assert(rtwn8723be_package_read(&t,power,read_byte,&out)==EBUSY);
    assert(t.on==1 && t.off==1 && t.read==1 && out==0);
    t=(struct trace){.fail_read=EIO,.fail_off=EBUSY};out=99;
    assert(rtwn8723be_package_read(&t,power,read_byte,&out)==EIO);
    assert(t.on==1 && t.off==1 && t.read==1 && out==0);
    assert(rtwn8723be_package_read(&t,NULL,read_byte,&out)==EINVAL);
    assert(rtwn8723be_package_read(&t,power,NULL,&out)==EINVAL);
    assert(rtwn8723be_package_read(&t,power,read_byte,NULL)==EINVAL);
    puts("RTL_PACKAGE_C_TESTS_OK: all 256 bytes, physical offset, on/read/off and failures");
    return 0;
}
"""


def validate_linux(tree: Path) -> None:
    base = tree / "drivers/net/wireless/realtek/rtlwifi"
    hw = (base / "rtl8723be/hw.c").read_text()
    wifi = (base / "wifi.h").read_text()
    start = hw.index("static u8 _rtl8723be_read_package_type(")
    end = hw.index("static void _rtl8723be_read_adapter_info(", start)
    src = hw[start:end]
    assert "efuse_one_byte_read(hw, 0x1FB, &value)" in src
    assert "efuse_power_switch(hw, false, true)" in src
    assert "efuse_power_switch(hw, false, false)" in src
    assert "if (!efuse_one_byte_read(hw, 0x1FB, &value))" in src
    for index, label in ((4, "TFBGA79"), (5, "TFBGA90"),
                         (6, "QFN68"), (7, "TFBGA80")):
        assert "case 0x%x:" % index in src
        assert "PACKAGE_" + label in src
    order = ["PACKAGE_DEFAULT", "PACKAGE_QFN68", "PACKAGE_TFBGA90",
             "PACKAGE_TFBGA80", "PACKAGE_TFBGA79"]
    enum = wifi[wifi.index("enum package_type {"):].split("};", 1)[0]
    positions = [enum.index(label) for label in order]
    assert positions == sorted(positions)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--linux-tree", type=Path,
                        default=Path("/opt/ChatGPT/hp-driver-port/linux"))
    args = parser.parse_args()
    validate_linux(args.linux_tree)
    with tempfile.TemporaryDirectory() as folder:
        src = Path(folder) / "package_test.c"
        exe = Path(folder) / "package_test"
        src.write_text(TEST)
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-fsanitize=undefined", "-fno-sanitize-recover=all",
            "-I", str(ROOT / "src"), str(ROOT / "src/rtwn8723be_package.c"),
            str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print("LIMITATION: standalone C callbacks, not native NetBSD or HP hardware")


if __name__ == "__main__":
    main()
