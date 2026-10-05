#!/usr/bin/env python3
"""Compile the actual NetBSD RF adapter under mocked bus_space and lifecycle.

Runs the production adapter C code, not a reimplementation. The portable
RF-serial/RFENV/table engines have separate tests. HOST ONLY, not NetBSD ABI.
"""
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
native = (SRC / "rtwn8723be_rf_native.c").read_text()
for anchor in (
    "rtwn8723be_rf_native_ready",
    "sc->sc_phy_identity_valid",
    "sc->sc_rf_path_count_valid",
    "R23BE_STAGE_PHY_RF",
    "!sc->sc_irq_enabled",
    "rtwn8723be_rf_path_configure",
    "rtwn8723be_phy_run_radio_a",
):
    assert anchor in native, "missing native RF prerequisite: " + anchor

actual_netbsd = SRC / "rtwn8723be_netbsd.c"
if actual_netbsd.exists():
    assert ".phy_rf_config = rtwn8723be_netbsd_phy_rf_config" in actual_netbsd.read_text()
    actual_softc = (SRC / "rtwn8723be_netbsd.h").read_text()
    for field in ("sc_phy_identity_valid", "sc_rf_path_count_valid",
                  "sc_rf_path_count", "struct rtwn8723be_phy_identity"):
        assert field in actual_softc
    assert "dev/pci/rtwn8723be_rf_native.c" in (
        ROOT / "config/files.rtwn8723be_native").read_text()

FAKE_NETBSD = r"""
#ifndef _RTWN8723BE_NETBSD_H_
#define _RTWN8723BE_NETBSD_H_
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "rtwn8723be_phy_exec.h"
#define R23BE_STAGE_PHY_RF 42U
#define R23BE_STAGE_RF_CHANNEL_STATE 43U
struct rtwn8723be_softc {
    bool sc_mapped, sc_core_initialized, sc_efuse_autoload_ok;
    bool sc_bt_ant_valid, sc_package_valid, sc_phy_identity_valid;
    bool sc_rf_path_count_valid, sc_irq_enabled;
    bool sc_bb_valid;
    size_t sc_mapsize;
    uint8_t sc_package_type, sc_rf_path_count;
    uint32_t sc_rf_chnlval[2];
    bool sc_rf_chnlval_valid;
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
#include "rtwn8723be_rf_path.h"
#include "rtwn8723be_phy_exec.h"
/* Declared here so the pre-port test fails at link time, not parsing. */
int rtwn8723be_netbsd_rf_channel_state_init(void *);

static uint32_t regs[0x900U/4U];
static unsigned int reads, writes, delays, path_a, path_b, radio_a, b_oe;
static bool invalid_reg, invalid_output, fail_radio;
static unsigned int channel_reads;
static int fail_channel_path = -1;

int rtwn8723be_rf_serial_read(const struct rtwn8723be_rf_serial_ctx *ctx,
    unsigned int path, uint32_t reg, uint32_t *value)
{
    uint32_t ignored;
    assert(ctx != NULL && ctx->io->ready(ctx->dev));
    assert(path <= 1U && reg == 0x18U && value != NULL);
    assert(path == channel_reads);
    channel_reads++;
    assert(ctx->io->read_bb(ctx->dev, 0x8a0U, &ignored) == 0);
    if ((int)path == fail_channel_path)
        return EIO;
    *value = path == 0U ? 0x12345U : 0x6789aU;
    return 0;
}

uint32_t
rtwn8723be_read_4(struct rtwn8723be_softc *sc, size_t reg)
{
    (void)sc;
    assert((reg & 3U) == 0 && reg / 4U < sizeof(regs)/sizeof(regs[0]));
    reads++;
    return regs[reg / 4U];
}
void
rtwn8723be_write_4(struct rtwn8723be_softc *sc, size_t reg, uint32_t v)
{
    (void)sc;
    assert((reg & 3U) == 0 && reg / 4U < sizeof(regs)/sizeof(regs[0]));
    writes++;
    if (reg == 0x864U)
        b_oe++;
    regs[reg / 4U] = v;
}
void delay(unsigned int us)
{
    assert(us == 1U || us == 120U || us == 50000U);
    delays++;
}
int
rtwn8723be_rf_radio_a_apply(void *arg, uint32_t reg, uint32_t value)
{
    const struct rtwn8723be_rf_serial_ctx *ctx = arg;
    assert(reg == 0x18U && value == 0x77777U);
    return ctx->io->write_bb(ctx->dev, 0x840U, value);
}
int
rtwn8723be_phy_run_radio_a(const struct rtwn8723be_phy_identity *id,
    void *arg, rtwn8723be_phy_write_fn apply)
{
    radio_a++;
    assert(id != NULL && id->package_type == 1U && id->pci_interface);
    if (fail_radio)
        return EIO;
    return apply(arg, 0x18U, 0x77777U);
}
int
rtwn8723be_rf_path_configure(const struct rtwn8723be_rf_serial_ctx *ctx,
    unsigned int path, rtwn8723be_rf_path_init_fn init, void *init_arg)
{
    uint32_t original = 0;
    int error;

    assert(ctx != NULL && ctx->io != NULL && ctx->io->ready(ctx->dev));
    if (path == RTWN8723BE_RF_PATH_A) {
        path_a++;
        assert(init != NULL && init_arg == ctx);
    } else {
        assert(path == RTWN8723BE_RF_PATH_B);
        path_b++;
        assert(init == NULL && init_arg == NULL);
    }

    if (invalid_output)
        return ctx->io->read_bb(ctx->dev, 0x870U, NULL);
    error = ctx->io->read_bb(ctx->dev, 0x870U, &original);
    if (error != 0)
        return error;
    error = ctx->io->write_bb(ctx->dev,
        invalid_reg ? 0x863U :
        (path == RTWN8723BE_RF_PATH_A ? 0x860U : 0x864U),
        original | 0x10U);
    if (error != 0)
        return error;
    ctx->io->delay_us(ctx->dev, 1U);
    return init == NULL ? 0 : init(init_arg, path);
}
static void
clear_observations(void)
{
    memset(regs, 0, sizeof(regs));
    reads = writes = delays = path_a = path_b = radio_a = b_oe = 0;
    invalid_reg = invalid_output = fail_radio = false;
    channel_reads = 0;
    fail_channel_path = -1;
}
static void
make_valid(struct rtwn8723be_softc *sc)
{
    memset(sc, 0, sizeof(*sc));
    sc->sc_mapped = sc->sc_core_initialized = true;
    sc->sc_bb_valid = true;
    sc->sc_efuse_autoload_ok = sc->sc_bt_ant_valid = true;
    sc->sc_package_valid = sc->sc_phy_identity_valid = true;
    sc->sc_rf_path_count_valid = sc->sc_linux.fw_ready = true;
    sc->sc_linux.being_init_adapter = true;
    sc->sc_linux.stage = R23BE_STAGE_PHY_RF;
    sc->sc_mapsize = 0x900U;
    sc->sc_package_type = sc->sc_phy_identity.package_type = 1U;
    sc->sc_phy_identity.pci_interface = true;
    sc->sc_rf_path_count = 1U;
}
#define MUST_BE_BLOCKED(expected) do { \
    assert(rtwn8723be_netbsd_phy_rf_config(&sc) == (expected)); \
    assert(reads == 0 && writes == 0 && delays == 0); \
} while (0)
int main(void)
{
    struct rtwn8723be_softc sc;

    assert(rtwn8723be_netbsd_phy_rf_config(NULL) == EINVAL);
    make_valid(&sc);
    clear_observations();
    sc.sc_phy_identity_valid = false;
    MUST_BE_BLOCKED(ENXIO);
    sc.sc_phy_identity_valid = true;
    sc.sc_bb_valid = false;
    MUST_BE_BLOCKED(ENXIO);
    sc.sc_bb_valid = true;
    sc.sc_rf_path_count_valid = false;
    MUST_BE_BLOCKED(ENXIO);
    sc.sc_rf_path_count_valid = true;
    sc.sc_rf_path_count = 0;
    MUST_BE_BLOCKED(EINVAL);
    sc.sc_rf_path_count = 3;
    MUST_BE_BLOCKED(EINVAL);
    sc.sc_rf_path_count = 1;

    sc.sc_phy_identity.package_type = 2;
    MUST_BE_BLOCKED(ENXIO);
    sc.sc_phy_identity.package_type = sc.sc_package_type;
    sc.sc_mapsize = 0x8bcU;
    MUST_BE_BLOCKED(ENXIO);
    sc.sc_mapsize = 0x900U;
    sc.sc_linux.stage++;
    MUST_BE_BLOCKED(ENXIO);
    sc.sc_linux.stage = R23BE_STAGE_PHY_RF;
    sc.sc_irq_enabled = true;
    MUST_BE_BLOCKED(ENXIO);
    sc.sc_irq_enabled = false;
    sc.sc_linux.fw_ready = false;
    MUST_BE_BLOCKED(ENXIO);
    sc.sc_linux.fw_ready = true;
    sc.sc_linux.started = true;
    MUST_BE_BLOCKED(ENXIO);
    sc.sc_linux.started = false;

    invalid_output = true;
    assert(rtwn8723be_netbsd_phy_rf_config(&sc) == EINVAL);
    assert(reads == 0 && writes == 0);
    clear_observations();
    invalid_reg = true;
    assert(rtwn8723be_netbsd_phy_rf_config(&sc) == EINVAL);
    assert(reads == 1 && writes == 0);
    clear_observations();
    fail_radio = true;
    assert(rtwn8723be_netbsd_phy_rf_config(&sc) == EIO);
    assert(path_a == 1 && path_b == 0);
    clear_observations();

    assert(rtwn8723be_netbsd_phy_rf_config(&sc) == 0);
    assert(path_a == 1 && path_b == 0 && radio_a == 1);
    assert(reads == 1 && writes == 2 && delays == 1);
    clear_observations();
    sc.sc_rf_path_count = 2U;
    assert(rtwn8723be_netbsd_phy_rf_config(&sc) == 0);
    assert(path_a == 1 && path_b == 1 && radio_a == 1 && b_oe == 1);
    assert(reads == 2 && writes == 3 && delays == 2);

    clear_observations();
    assert(rtwn8723be_netbsd_rf_channel_state_init(NULL) == EINVAL);
    make_valid(&sc);
    sc.sc_rf_chnlval_valid = true;
    assert(rtwn8723be_netbsd_rf_channel_state_init(&sc) == ENXIO);
    assert(!sc.sc_rf_chnlval_valid && channel_reads == 0);
    sc.sc_linux.stage = R23BE_STAGE_RF_CHANNEL_STATE;
    MUST_BE_BLOCKED(ENXIO); /* RF table writes cannot run in snapshot phase. */
    sc.sc_rf_chnlval[0] = 0xaaaU;
    sc.sc_rf_chnlval[1] = 0xbbbU;
    for (int path = 0; path <= 1; ++path) {
        clear_observations();
        fail_channel_path = path;
        sc.sc_rf_chnlval_valid = true;
        assert(rtwn8723be_netbsd_rf_channel_state_init(&sc) == EIO);
        assert(!sc.sc_rf_chnlval_valid && channel_reads == (unsigned int)path + 1U);
        assert(sc.sc_rf_chnlval[0] == 0xaaaU && sc.sc_rf_chnlval[1] == 0xbbbU);
    }
    clear_observations();
    assert(rtwn8723be_netbsd_rf_channel_state_init(&sc) == 0);
    assert(channel_reads == 2 && sc.sc_rf_chnlval_valid);
    assert(sc.sc_rf_chnlval[0] == ((0x12345U & 0xfff03ffU) | 0xc00U));
    assert(sc.sc_rf_chnlval[1] == 0x6789aU);
    clear_observations();
    sc.sc_irq_enabled = true;
    assert(rtwn8723be_netbsd_rf_channel_state_init(&sc) == ENXIO);
    assert(!sc.sc_rf_chnlval_valid && channel_reads == 0);
    puts("RTL_RF_NATIVE_C11_UBSAN_OK: guard, MMIO, A/B, ordering, errors");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-rf-native-") as tmp:
    target = Path(tmp)
    for header in ("rtwn8723be_rf_native.h", "rtwn8723be_rf_serial.h",
                   "rtwn8723be_rf_path.h", "rtwn8723be_phy_exec.h",
                   "rtwn8723be_rf_channel_state.h",
                   "rtwn8723be_os_compat.h"):
        shutil.copyfile(SRC / header, target / header)
    (target / "sys").mkdir()
    (target / "sys/systm.h").write_text("void delay(unsigned int);\n")
    # NetBSD errno.h includes sys/errno.h; shadowing it would recurse and
    # hide every errno constant. Linux needs the compatibility stub.
    if platform.system() != "NetBSD":
        (target / "sys/errno.h").write_text("#include <errno.h>\n")
    (target / "rtwn8723be_netbsd.h").write_text(FAKE_NETBSD)
    (target / "native.c").write_text("#define __KERNEL_RCSID(a,b) _Static_assert(1, \"kernel rcsid\")\n" + native)
    (target / "harness.c").write_text(HARNESS)
    exe = target / "rf-test"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all", "-I", str(target),
                    str(target / "native.c"), str(target / "harness.c"),
                    str(SRC / "rtwn8723be_rf_channel_state.c"),
                    "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
