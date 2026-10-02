#!/usr/bin/env python3
"""Strict host-C mock tests of the production Linux-derived RTL8723BE RF serial bridge.
No NetBSD kernel object, bus_space mapping or hardware-ready claim.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINUX = Path("/opt/ChatGPT/hp-driver-port/linux/drivers/net/wireless/realtek/rtlwifi")
P = r"""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_rf_serial.h"
#include "rtwn8723be_phy_exec.h"

struct event { char kind; uint32_t reg, val; };
struct mock {
    uint32_t bb[0x1000];
    struct event ev[600];
    unsigned int n, writes, reads;
    int fail_write_at, fail_read_at;
    bool powered;
};

static void ev(struct mock *m, char kind, uint32_t reg, uint32_t val)
{
    assert(m->n < sizeof(m->ev) / sizeof(m->ev[0]));
    m->ev[m->n++] = (struct event){kind, reg, val};
}
static bool ready(void *ctx)
{
    return ((struct mock *)ctx)->powered;
}
static int rbb(void *ctx, uint32_t reg, uint32_t *value)
{
    struct mock *m = ctx;
    assert(reg < 0x1000);
    m->reads++;
    ev(m, 'R', reg, 0);
    if (m->fail_read_at != 0 && m->reads == (unsigned int)m->fail_read_at)
        return EIO;
    *value = m->bb[reg];
    return 0;
}
static int wbb(void *ctx, uint32_t reg, uint32_t value)
{
    struct mock *m = ctx;
    assert(reg < 0x1000);
    m->writes++;
    ev(m, 'W', reg, value);
    if (m->fail_write_at != 0 &&
        m->writes == (unsigned int)m->fail_write_at)
        return EIO;
    m->bb[reg] = value;
    return 0;
}
static void waitus(void *ctx, unsigned int usec)
{
    ev(ctx, 'D', 0, usec);
}
static void reset(struct mock *m)
{
    *m = (struct mock){.powered=true};
}
int main(void)
{
    const struct rtwn8723be_rf_serial_io ops = {
        .ready=ready, .read_bb=rbb, .write_bb=wbb, .delay_us=waitus
    };
    struct mock m;
    struct rtwn8723be_rf_serial_ctx ctx = {&ops, &m};
    uint32_t data = 0;
    struct rtwn8723be_phy_identity id = {.pci_interface = true};

    reset(&m);
    assert(rtwn8723be_rf_serial_write(&ctx, 0, 0x1a2, 0x12abcdeU) == 0);
    assert(m.n == 1 && m.ev[0].kind == 'W');
    assert(m.ev[0].reg == 0x840 && m.ev[0].val == 0x0a2abcdeU);
    assert(rtwn8723be_rf_serial_write(&ctx, 1, 0x52, 0x7e4bd) == 0);
    assert(m.n == 2 && m.ev[1].reg == 0x844);
    assert(m.ev[1].val == 0x0527e4bdU);

    reset(&m);
    m.bb[0x824] = 0x10200405U;
    m.bb[0x820] = 0;
    m.bb[0x8a0] = 0x01abcde1U;
    data = 0x55aa55aaU;
    assert(rtwn8723be_rf_serial_read(&ctx, 0, 0x1a2, &data) == 0);
    assert(data == (0x01abcde1U & 0xfffffU));
    assert(m.n == 7);
    assert(m.ev[0].kind == 'R' && m.ev[0].reg == 0x824);
    assert(m.ev[1].kind == 'W' && m.ev[1].reg == 0x824);
    assert(m.ev[1].val == (0x10200405U & ~0x80000000U));
    assert(m.ev[2].kind == 'W' && m.ev[2].reg == 0x824);
    assert(m.ev[2].val ==
        ((0x10200405U & ~0x7f800000U) | (0xa2U << 23) | 0x80000000U));
    assert(m.ev[3].kind == 'W' && m.ev[3].reg == 0x824);
    assert(m.ev[3].val == (0x10200405U | 0x80000000U));
    assert(m.ev[4].kind == 'D' && m.ev[4].val == 120);
    assert(m.ev[5].kind == 'R' && m.ev[5].reg == 0x820);
    assert(m.ev[6].kind == 'R' && m.ev[6].reg == 0x8a0);

    reset(&m);
    m.bb[0x824] = 0x81234567U;
    m.bb[0x82c] = 0x07654321U;
    m.bb[0x828] = 1U << 8; /* B path PI enabled. */
    m.bb[0x8bc] = 0x12345678U;
    assert(rtwn8723be_rf_serial_read(&ctx, 1, 0x39, &data) == 0);
    assert(data == (0x12345678U & 0xfffffU));
    assert(m.n == 8);
    assert(m.ev[0].kind == 'R' && m.ev[0].reg == 0x824);
    assert(m.ev[1].kind == 'R' && m.ev[1].reg == 0x82c);
    assert(m.ev[2].kind == 'W' && m.ev[2].reg == 0x824);
    assert(m.ev[3].kind == 'W' && m.ev[3].reg == 0x82c);
    assert(m.ev[4].kind == 'W' && m.ev[4].reg == 0x824);
    assert(m.ev[5].kind == 'D' && m.ev[5].val == 120);
    assert(m.ev[6].kind == 'R' && m.ev[6].reg == 0x828);
    assert(m.ev[7].kind == 'R' && m.ev[7].reg == 0x8bc);

    reset(&m);
    m.bb[0x8a0] = 0xabcdeU;
    assert(rtwn8723be_rf_masked_write(&ctx, 0, 0x52,
        0xff00U, 0x22U) == 0);
    assert(m.bb[0x840] == 0x052a22deU);
    assert(rtwn8723be_rf_masked_write(&ctx, 0, 0x52,
        0xfffffU, 0x7e4bdU) == 0);
    assert(m.bb[0x840] == 0x0527e4bdU);

    reset(&m);
    assert(rtwn8723be_rf_radio_a_apply(&ctx, 0xfe, 0) == 0);
    assert(rtwn8723be_rf_radio_a_apply(&ctx, 0xffe, 0) == 0);
    assert(m.writes == 0 && m.n == 2);
    assert(m.ev[0].kind == 'D' && m.ev[0].val == 50000);
    assert(m.ev[1].kind == 'D' && m.ev[1].val == 50000);
    assert(rtwn8723be_rf_radio_a_apply(&ctx, 0x52, 0x7e4bdU) == 0);
    assert(m.n == 4 && m.ev[2].kind == 'W');
    assert(m.ev[2].reg == 0x840 && m.ev[2].val == 0x0527e4bdU);
    assert(m.ev[3].kind == 'D' && m.ev[3].val == 1);

    reset(&m);
    assert(rtwn8723be_phy_run_radio_a(&id, &ctx,
        rtwn8723be_rf_radio_a_apply) == 0);
    assert(m.writes != 0 && m.n > m.writes);
    /* All RF serial writes must address path A: 0x840. */
    for (unsigned int i = 0; i < m.n; i++)
        if (m.ev[i].kind == 'W')
            assert(m.ev[i].reg == 0x840);

    reset(&m);
    m.powered = false;
    assert(rtwn8723be_rf_serial_write(&ctx, 0, 0, 0) == ENXIO);
    assert(rtwn8723be_rf_serial_read(&ctx, 0, 0, &data) == ENXIO);
    assert(rtwn8723be_rf_radio_a_apply(&ctx, 0xfe, 0) == ENXIO);
    assert(m.n == 0);
    m.powered = true;
    assert(rtwn8723be_rf_serial_write(&ctx, 2, 0, 0) == EINVAL);
    assert(rtwn8723be_rf_serial_read(&ctx, 2, 0, &data) == EINVAL);
    assert(rtwn8723be_rf_serial_read(&ctx, 0, 0, NULL) == EINVAL);
    assert(rtwn8723be_rf_masked_write(&ctx, 0, 0, 0, 0) == EINVAL);
    assert(rtwn8723be_rf_masked_write(&ctx, 0, 0, 0x100000U, 0) == EINVAL);

    reset(&m);
    m.fail_read_at = 1;
    data = 0x11111111U;
    assert(rtwn8723be_rf_serial_read(&ctx, 0, 0, &data) == EIO);
    assert(data == 0x11111111U && m.writes == 0);
    reset(&m);
    m.fail_write_at = 1;
    data = 0x22222222U;
    assert(rtwn8723be_rf_serial_read(&ctx, 0, 0, &data) == EIO);
    assert(data == 0x22222222U && m.writes == 1);
    reset(&m);
    m.fail_write_at = 1;
    assert(rtwn8723be_rf_radio_a_apply(&ctx, 0x52, 0) == EIO);
    assert(m.n == 1 && m.ev[0].kind == 'W');

    puts("RF_SERIAL_C_TESTS_OK: A/B pack, read edge, PI/LSSI, 120us, masked RMW, Radio-A, error guards");
    return 0;
}
"""


def main():
    source = (LINUX / "rtl8723com/phy_common.c").read_text()
    other = (LINUX / "rtl8723be/phy.c").read_text()
    for needle in ("offset &= 0xff;", "data & 0x000fffff",
                   "udelay(120);", "BLSSIREADEDGE", "BLSSIREADBACKDATA"):
        if needle not in source:
            raise AssertionError("frozen Linux RF reference changed: " + needle)
    for needle in ("rtl8723_phy_rf_serial_read(", "rtl8723_phy_rf_serial_write(",
                   "addr == 0xfe || addr == 0xffe"):
        if needle not in other:
            raise AssertionError("frozen Linux radio layer changed: " + needle)
    with tempfile.TemporaryDirectory() as td:
        inp = Path(td) / "test.c"
        out = Path(td) / "test"
        inp.write_text(P)
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-I", str(ROOT / "src"), str(inp),
             str(ROOT / "src/rtwn8723be_rf_serial.c"),
             str(ROOT / "src/rtwn8723be_phy_exec.c"),
             "-o", str(out)], check=True)
        subprocess.run([str(out)], check=True)


if __name__ == "__main__":
    main()
