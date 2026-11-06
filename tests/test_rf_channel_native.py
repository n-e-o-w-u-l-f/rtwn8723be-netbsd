#!/usr/bin/env python3
"""Compile the real RF channel NetBSD binding under a strict host mock.

Tests the native stage/preflight, bus I/O, atomic publication and failure
invalidation. This is NOT a native NetBSD object or an HP hardware test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
NATIVE = (SRC / "rtwn8723be_rf_channel_native.c").read_text()
NETBSD = (SRC / "rtwn8723be_netbsd.c").read_text()
CONFIG = (ROOT / "config/files.rtwn8723be_native").read_text()
assert ".rf_channel_state_init = rtwn8723be_netbsd_rf_channel_state_init" in NETBSD
assert "dev/pci/rtwn8723be_rf_channel_native.c" in CONFIG
assert "dev/pci/rtwn8723be_rf_channel_state.c" in CONFIG
for term in ("R23BE_STAGE_RF_CHANNEL_STATE", "!sc->sc_irq_enabled",
             "sc->sc_rf_chnlval_valid = false", "sc->sc_rf_chnlval_valid = true"):
    assert term in NATIVE

FAKE = r"""
#ifndef _RTWN8723BE_NETBSD_H_
#define _RTWN8723BE_NETBSD_H_
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "rtwn8723be_phy_exec.h"
#define R23BE_STAGE_RF_CHANNEL_STATE 43U
struct rtwn8723be_softc {
    bool sc_mapped, sc_core_initialized, sc_efuse_autoload_ok;
    bool sc_bt_ant_valid, sc_package_valid, sc_phy_identity_valid;
    bool sc_rf_path_count_valid, sc_irq_enabled, sc_rf_chnlval_valid;
    size_t sc_mapsize;
    uint8_t sc_package_type, sc_rf_path_count;
    uint32_t sc_rf_chnlval[2];
    struct rtwn8723be_phy_identity sc_phy_identity;
    struct {
        bool fw_ready, being_init_adapter, started;
        unsigned int stage;
    } sc_linux;
};
uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *, size_t);
void rtwn8723be_write_4(struct rtwn8723be_softc *, size_t, uint32_t);
#endif
"""

HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_rf_native.h"
#include "rtwn8723be_rf_serial.h"
#include "rtwn8723be_rf_channel_state.h"

static int reads, writes, delays, calls, fail_at;
static size_t lastreg;
uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *sc, size_t reg)
{ (void)sc; reads++; lastreg = reg; return 0x987U; }
void rtwn8723be_write_4(struct rtwn8723be_softc *sc, size_t reg, uint32_t v)
{ (void)sc; (void)v; writes++; lastreg = reg; }
void delay(unsigned int us) { assert(us == 120U); delays++; }

/* Serial framing itself is independently checked by test_rf_serial.py. */
int rtwn8723be_rf_serial_read(const struct rtwn8723be_rf_serial_ctx *ctx,
    unsigned int path, uint32_t reg, uint32_t *value)
{
    uint32_t tmp;
    int error;
    assert(path == (unsigned int)calls && reg == 0x18U);
    if (!ctx->io->ready(ctx->dev))
        return ENXIO;
    calls++;
    error = ctx->io->read_bb(ctx->dev, path == 0 ? 0x824U : 0x82cU,
        &tmp);
    if (error != 0)
        return error;
    assert(tmp == 0x987U);
    error = ctx->io->write_bb(ctx->dev, 0x824U, 0x123U);
    if (error != 0)
        return error;
    ctx->io->delay_us(ctx->dev, 120U);
    if (calls == fail_at)
        return EIO;
    *value = path == 0 ? 0xfffffU : 0x54321U;
    return 0;
}

static void valid(struct rtwn8723be_softc *s)
{
    memset(s, 0, sizeof(*s));
    s->sc_mapped = s->sc_core_initialized = true;
    s->sc_efuse_autoload_ok = s->sc_bt_ant_valid = true;
    s->sc_package_valid = s->sc_phy_identity_valid = true;
    s->sc_rf_path_count_valid = s->sc_linux.fw_ready = true;
    s->sc_linux.being_init_adapter = true;
    s->sc_linux.stage = R23BE_STAGE_RF_CHANNEL_STATE;
    s->sc_mapsize = 0x900U;
    s->sc_rf_path_count = 1U; /* Linux still reads RF channel B. */
    s->sc_package_type = s->sc_phy_identity.package_type = 1U;
    s->sc_phy_identity.pci_interface = true;
}
static void reset_observations(void)
{ reads = writes = delays = calls = fail_at = 0; }
#define BLOCKED do { \
    reset_observations(); \
    s.sc_rf_chnlval_valid = true; \
    assert(rtwn8723be_netbsd_rf_channel_state_init(&s) == ENXIO); \
    assert(!s.sc_rf_chnlval_valid && calls == 0 && \
           reads == 0 && writes == 0 && delays == 0); \
} while (0)

int main(void)
{
    struct rtwn8723be_softc s;
    assert(rtwn8723be_netbsd_rf_channel_state_init(NULL) == EINVAL);
    valid(&s);
    s.sc_linux.stage++;
    BLOCKED;
    s.sc_linux.stage = R23BE_STAGE_RF_CHANNEL_STATE;
    s.sc_package_type = 2U;
    BLOCKED;
    s.sc_package_type = 1U;
    s.sc_mapsize = 0x8bcU;
    BLOCKED;
    s.sc_mapsize = 0x900U;
    s.sc_irq_enabled = true;
    BLOCKED;
    s.sc_irq_enabled = false;
    s.sc_phy_identity_valid = false;
    BLOCKED;
    s.sc_phy_identity_valid = true;
    s.sc_rf_path_count = 3U;
    BLOCKED;
    s.sc_rf_path_count = 1U;
    s.sc_linux.started = true;
    BLOCKED;
    s.sc_linux.started = false;

    reset_observations();
    assert(rtwn8723be_netbsd_rf_channel_state_init(&s) == 0);
    assert(s.sc_rf_chnlval_valid && s.sc_rf_chnlval[0] == 0xf0fffU);
    assert(s.sc_rf_chnlval[1] == 0x54321U);
    assert(calls == 2 && reads == 2 && writes == 2 && delays == 2);
    assert(lastreg == 0x824U);

    reset_observations();
    fail_at = 2;
    assert(rtwn8723be_netbsd_rf_channel_state_init(&s) == EIO);
    assert(!s.sc_rf_chnlval_valid);
    assert(s.sc_rf_chnlval[0] == 0xf0fffU &&
           s.sc_rf_chnlval[1] == 0x54321U);
    assert(calls == 2 && reads == 2 && writes == 2 && delays == 2);
    puts("RTL_RF_CHANNEL_NATIVE_C11_UBSAN_OK phase/preflight/MMIO/atomic");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-rf-channel-native-") as tmp:
    target = Path(tmp)
    for name in ("rtwn8723be_rf_channel_state.h",
                 "rtwn8723be_rf_native.h",
                 "rtwn8723be_rf_serial.h",
                 "rtwn8723be_phy_exec.h",
                 "rtwn8723be_os_compat.h"):
        shutil.copyfile(SRC / name, target / name)
    (target / "sys").mkdir()
    (target / "sys/systm.h").write_text("void delay(unsigned int);\n")
    (target / "sys/errno.h").write_text("#include <errno.h>\n")
    (target / "rtwn8723be_netbsd.h").write_text(FAKE)
    (target / "native.c").write_text(
        '#define __KERNEL_RCSID(a,b) _Static_assert(1, "kernel rcsid")\n'
        + NATIVE)
    (target / "harness.c").write_text(HARNESS)
    exe = target / "check"
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(target), str(target / "native.c"),
        str(SRC / "rtwn8723be_rf_channel_state.c"),
        str(target / "harness.c"), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
