#!/usr/bin/env python3
"""Actual-source strict C tests for RTL8723BE RFENV/HSSI path setup and restore.
Host mocks only; the native NetBSD RF mutex, MMIO and hardware remain untested.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINUX_RF = (Path("/opt/ChatGPT/hp-driver-port/linux") /
            "drivers/net/wireless/realtek/rtlwifi/rtl8723be/rf.c")
P = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include "rtwn8723be_rf_path.h"

struct event { char kind; uint32_t reg, val; };
struct mock {
    uint32_t bb[0x1000];
    struct event ev[128];
    unsigned int n, writes, calls;
    bool powered;
    unsigned int callback_path;
    int callback_failure, fail_write_at;
};

static void log_event(struct mock *m, char type, uint32_t reg, uint32_t val)
{
    assert(m->n < sizeof(m->ev) / sizeof(m->ev[0]));
    m->ev[m->n++] = (struct event){type, reg, val};
}
static bool ready(void *ctx) { return ((struct mock *)ctx)->powered; }
static int rbb(void *ctx, uint32_t reg, uint32_t *out)
{
    struct mock *m = ctx;
    assert(reg < 0x1000);
    log_event(m, 'R', reg, 0);
    *out = m->bb[reg];
    return 0;
}
static int wbb(void *ctx, uint32_t reg, uint32_t value)
{
    struct mock *m = ctx;
    assert(reg < 0x1000);
    m->writes++;
    log_event(m, 'W', reg, value);
    if (m->fail_write_at != 0 &&
        m->writes == (unsigned int)m->fail_write_at)
        return EIO;
    m->bb[reg] = value;
    return 0;
}
static void waitus(void *ctx, unsigned int microseconds)
{
    log_event(ctx, 'D', 0, microseconds);
}
static int initialize(void *ctx, unsigned int path)
{
    struct mock *m = ctx;
    m->calls++;
    m->callback_path = path;
    log_event(m, 'C', path, 0);
    assert(path == 0);
    assert((m->bb[0x860] & 0x00100010U) == 0x00100010U);
    assert((m->bb[0x824] & 0x00000c00U) == 0);
    /* Force a changed RFENV state: restore must use the saved value. */
    m->bb[0x870] &= ~0x10U;
    return m->callback_failure;
}
static void reset(struct mock *m)
{
    *m = (struct mock){.powered=true};
}
int main(void)
{
    struct mock m;
    const struct rtwn8723be_rf_serial_io ops = {
        .ready=ready, .read_bb=rbb, .write_bb=wbb, .delay_us=waitus
    };
    struct rtwn8723be_rf_serial_ctx ctx = {&ops, &m};

    reset(&m);
    m.bb[0x870] = 0x00000010U;
    m.bb[0x824] = 0x00000c00U;
    assert(rtwn8723be_rf_path_configure(&ctx, 0, initialize, &m) == 0);
    assert(m.calls == 1 && m.callback_path == 0);
    assert(m.bb[0x870] == 0x00000010U);
    assert((m.bb[0x860] & 0x00100010U) == 0x00100010U);
    assert((m.bb[0x824] & 0x00000c00U) == 0);
    assert(m.n == 16 && m.writes == 5);
    assert(m.ev[0].kind == 'R' && m.ev[0].reg == 0x870);
    assert(m.ev[1].kind == 'R' && m.ev[1].reg == 0x860);
    assert(m.ev[2].kind == 'W' && m.ev[2].reg == 0x860);
    assert(m.ev[3].kind == 'D' && m.ev[3].val == 1);
    assert(m.ev[4].kind == 'R' && m.ev[4].reg == 0x860);
    assert(m.ev[5].kind == 'W' && m.ev[5].reg == 0x860);
    assert(m.ev[6].kind == 'D' && m.ev[6].val == 1);
    assert(m.ev[7].kind == 'R' && m.ev[7].reg == 0x824);
    assert(m.ev[8].kind == 'W' && m.ev[8].reg == 0x824);
    assert(m.ev[9].kind == 'D' && m.ev[9].val == 1);
    assert(m.ev[10].kind == 'R' && m.ev[10].reg == 0x824);
    assert(m.ev[11].kind == 'W' && m.ev[11].reg == 0x824);
    assert(m.ev[12].kind == 'D' && m.ev[12].val == 1);
    assert(m.ev[13].kind == 'C' && m.ev[13].reg == 0);
    assert(m.ev[14].kind == 'R' && m.ev[14].reg == 0x870);
    assert(m.ev[15].kind == 'W' && m.ev[15].reg == 0x870);

    reset(&m);
    m.bb[0x870] = 0x00100010U;
    m.bb[0x82c] = 0x00000c00U;
    assert(rtwn8723be_rf_path_configure(&ctx, 1, NULL, NULL) == 0);
    assert(m.calls == 0 && m.n == 15 && m.writes == 5);
    assert(m.bb[0x870] == 0x00100010U);
    assert((m.bb[0x864] & 0x00100010U) == 0x00100010U);
    assert((m.bb[0x82c] & 0x00000c00U) == 0);
    assert(m.ev[2].kind == 'W' && m.ev[2].reg == 0x864);
    assert(m.ev[8].kind == 'W' && m.ev[8].reg == 0x82c);
    assert(m.ev[14].kind == 'W' && m.ev[14].reg == 0x870);

    reset(&m);
    m.bb[0x870] = 0x10U;
    m.callback_failure = EIO;
    assert(rtwn8723be_rf_path_configure(&ctx, 0, initialize, &m) == EIO);
    assert(m.calls == 1 && m.bb[0x870] == 0x10U);

    reset(&m);
    m.bb[0x870] = 0x10U;
    m.fail_write_at = 2;
    assert(rtwn8723be_rf_path_configure(&ctx, 0, initialize, &m) == EIO);
    assert(m.calls == 0 && m.writes == 3);
    assert(m.bb[0x870] == 0x10U);
    assert(m.ev[m.n-1].kind == 'W' && m.ev[m.n-1].reg == 0x870);

    reset(&m);
    m.powered = false;
    assert(rtwn8723be_rf_path_configure(&ctx, 0, initialize, &m) == ENXIO);
    assert(m.n == 0 && m.calls == 0);
    m.powered = true;
    assert(rtwn8723be_rf_path_configure(&ctx, 2, initialize, &m) == EINVAL);
    assert(rtwn8723be_rf_path_configure(&ctx, 0, NULL, &m) == EINVAL);
    assert(rtwn8723be_rf_path_configure(NULL, 0, initialize, &m) == EINVAL);

    puts("RF_PATH_C_TESTS_OK: A/B setup, four 1us waits, table callback, success/failure RFENV restoration");
    return 0;
}
"""


def main():
    linux = LINUX_RF.read_text()
    for needle in ("BRFSI_RFENV << 16", "B3WIREADDREAALENGTH",
                   "B3WIREDATALENGTH", "rfintfs", "rfintfe",
                   "rfintfo", "rtl8723be_phy_config_rf_with_headerfile"):
        if needle not in linux:
            raise AssertionError("frozen Linux RF init changed: " + needle)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "test.c"
        binary = Path(td) / "test"
        path.write_text(P)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra",
                        "-Werror", "-pedantic", "-I", str(ROOT / "src"),
                        str(path), str(ROOT / "src/rtwn8723be_rf_path.c"),
                        "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
