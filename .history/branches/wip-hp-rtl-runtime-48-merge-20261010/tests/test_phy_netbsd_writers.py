#!/usr/bin/env python3
"""Strict host-C smoke test of the real NetBSD BB/AGC table-writer bodies.

Isolates MMIO and delays. It does not validate native NetBSD compilation,
EFUSE identity, PG power conversion, RF serial I/O or physical hardware.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
NAMES = ("rtwn8723be_netbsd_phy_bb_write",
         "rtwn8723be_netbsd_phy_agc_write")


def extract(name):
    marker = "\nint\n" + name + "(void *arg, uint32_t reg, uint32_t value)\n{"
    if SRC.count(marker) != 1:
        raise AssertionError("missing or duplicated real callback " + name)
    start = SRC.index(marker) + 1
    opening = SRC.index("{", start)
    depth = 0
    for i in range(opening, len(SRC)):
        if SRC[i] == "{":
            depth += 1
        elif SRC[i] == "}":
            depth -= 1
            if depth == 0:
                return SRC[start : i + 1]
    raise AssertionError("unclosed body " + name)


PRELUDE = r"""
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <assert.h>
#include <errno.h>
struct rtwn8723be_softc { bool sc_mapped; };
struct observation {
    unsigned writes;
    unsigned delays;
    uint32_t reg, mask, val, wait_us;
} obs;
static void delay(unsigned int us) { obs.delays++; obs.wait_us = us; }
static void
rtwn8723be_netbsd_set_bbreg(struct rtwn8723be_softc *sc,
                            uint32_t reg, uint32_t mask, uint32_t val)
{
    assert(sc->sc_mapped);
    obs.writes++;
    obs.reg = reg;
    obs.mask = mask;
    obs.val = val;
}
static void reset(void)
{
    obs = (struct observation){0};
}
"""

MAIN = r"""
int main(void)
{
    struct rtwn8723be_softc sc = { .sc_mapped = false };
    const struct { uint32_t reg, us; } tokens[] = {
        {0xfe, 50000}, {0xfd, 5000}, {0xfc, 1000},
        {0xfb, 50}, {0xfa, 5}, {0xf9, 1}
    };

    assert(rtwn8723be_netbsd_phy_bb_write(NULL, 0x800, 0) == EINVAL);
    assert(rtwn8723be_netbsd_phy_agc_write(NULL, 0xc78, 0) == EINVAL);
    assert(rtwn8723be_netbsd_phy_bb_write(&sc, 0x800, 0) == ENXIO);
    assert(rtwn8723be_netbsd_phy_agc_write(&sc, 0xc78, 0) == ENXIO);
    assert(obs.writes == 0 && obs.delays == 0);
    sc.sc_mapped = true;

    for (unsigned i = 0; i < sizeof(tokens)/sizeof(tokens[0]); i++) {
        reset();
        assert(rtwn8723be_netbsd_phy_bb_write(
            &sc, tokens[i].reg, 0xdeadbeefU) == 0);
        assert(obs.writes == 0 && obs.delays == 1);
        assert(obs.wait_us == tokens[i].us);
    }
    reset();
    assert(rtwn8723be_netbsd_phy_bb_write(&sc, 0x800, 0x12345678U) == 0);
    assert(obs.writes == 1 && obs.reg == 0x800);
    assert(obs.mask == 0xffffffffU && obs.val == 0x12345678U);
    assert(obs.delays == 1 && obs.wait_us == 1);

    reset();
    assert(rtwn8723be_netbsd_phy_agc_write(&sc, 0xc78, 0x98765432U) == 0);
    assert(obs.writes == 1 && obs.reg == 0xc78);
    assert(obs.mask == 0xffffffffU && obs.val == 0x98765432U);
    assert(obs.delays == 0);
    puts("PHY_NETBSD_WRITERS_C_TESTS_OK: BB6 delays, BB write+1us, AGC no delay, NULL/unmapped");
    return 0;
}
"""


def main():
    linux = (Path(os.environ.get("RTWN8723BE_LINUX_TREE",
                         "/opt/ChatGPT/hp-driver-port/linux")) /
             "drivers/net/wireless/realtek/rtlwifi/rtl8723be/phy.c").read_text()
    original = linux[linux.index("static void _rtl8723be_config_bb_reg("):
                     linux.index("static void _rtl8723be_phy_set_txpower_by_rate_base(")]
    for token, delay_type, us in (
        ("0xfe", "mdelay", 50), ("0xfd", "mdelay", 5),
        ("0xfc", "mdelay", 1), ("0xfb", "udelay", 50),
        ("0xfa", "udelay", 5), ("0xf9", "udelay", 1),
    ):
        if "addr == " + token not in original or (
                delay_type + "(" + str(us) + ")") not in original:
            raise AssertionError("missing frozen Linux delay evidence " + token)
    source = PRELUDE + "\n".join(extract(n) for n in NAMES) + MAIN
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "writers.c"
        out = Path(td) / "writers"
        src.write_text(source)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra",
                        "-Werror", "-pedantic", str(src), "-o", str(out)],
                       check=True)
        subprocess.run([str(out)], check=True)


if __name__ == "__main__":
    main()
