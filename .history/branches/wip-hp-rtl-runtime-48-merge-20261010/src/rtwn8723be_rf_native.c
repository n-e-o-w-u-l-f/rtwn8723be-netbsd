/* SPDX-License-Identifier: GPL-2.0 */
/*
 * NetBSD hardware binding for frozen Linux rtl8723be/rf.c and
 * rtl8723com/phy_common.c RF6052 serial / RFENV initialization.
 *
 * The portable RF-serial, RFENV and conditional Radio-A table engines live
 * in rf_serial.c, rf_path.c and phy_exec.c. This module ONLY translates
 * their full-width BB I/O into the actual NetBSD bus_space adapter.
 *
 * Initialization must be serialized by the owning lifecycle and occur
 * before IRQ/DMA traffic is enabled. Never hold a spin lock across the
 * Radio-A table's 50 ms delay tokens. Runtime channel changes and RF-lock
 * ownership remain separate, unimplemented full-port prerequisites.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>

#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_rf_native.h"
#include "rtwn8723be_rf_serial.h"
#include "rtwn8723be_rf_path.h"
#include "rtwn8723be_rf_channel_state.h"
#include "rtwn8723be_phy_exec.h"

/* RF_B_PI_RB is the highest BB register used by the frozen RF protocol. */
#define RTWN8723BE_RF_LAST_BB_REG  0x8bcU

static bool
rtwn8723be_rf_native_ready(void *arg)
{
    const struct rtwn8723be_softc *sc = arg;

    return sc != NULL && sc->sc_mapped && sc->sc_core_initialized &&
        sc->sc_bb_valid &&
        sc->sc_linux.fw_ready && sc->sc_efuse_autoload_ok &&
        sc->sc_bt_ant_valid && sc->sc_package_valid &&
        sc->sc_phy_identity_valid && sc->sc_rf_path_count_valid &&
        sc->sc_phy_identity.pci_interface &&
        sc->sc_phy_identity.package_type == sc->sc_package_type &&
        sc->sc_mapsize >= RTWN8723BE_RF_LAST_BB_REG +
            sizeof(uint32_t) &&
        sc->sc_linux.being_init_adapter &&
        (sc->sc_linux.stage == R23BE_STAGE_PHY_RF ||
         sc->sc_linux.stage == R23BE_STAGE_RF_CHANNEL_STATE) &&
        !sc->sc_linux.started && !sc->sc_irq_enabled;
}

static int
rtwn8723be_rf_native_check_reg(struct rtwn8723be_softc *sc, uint32_t reg)
{
    if (!rtwn8723be_rf_native_ready(sc))
        return ENXIO;
    if ((reg & 3U) != 0 || reg > sc->sc_mapsize ||
        sc->sc_mapsize - reg < sizeof(uint32_t))
        return EINVAL;
    return 0;
}

static int
rtwn8723be_rf_native_read_bb(void *arg, uint32_t reg, uint32_t *value)
{
    struct rtwn8723be_softc *sc = arg;
    int error;

    if (value == NULL)
        return EINVAL;
    error = rtwn8723be_rf_native_check_reg(sc, reg);
    if (error != 0)
        return error;
    *value = rtwn8723be_read_4(sc, reg);
    return 0;
}

static int
rtwn8723be_rf_native_write_bb(void *arg, uint32_t reg, uint32_t value)
{
    struct rtwn8723be_softc *sc = arg;
    int error;

    error = rtwn8723be_rf_native_check_reg(sc, reg);
    if (error != 0)
        return error;
    /* rtwn8723be_write_4() supplies the NetBSD bus_space write barrier. */
    rtwn8723be_write_4(sc, reg, value);
    return 0;
}

static void
rtwn8723be_rf_native_delay_us(void *arg, unsigned int usec)
{
    (void)arg;
    delay(usec);
}

static const struct rtwn8723be_rf_serial_io rtwn8723be_rf_native_io = {
    .ready = rtwn8723be_rf_native_ready,
    .read_bb = rtwn8723be_rf_native_read_bb,
    .write_bb = rtwn8723be_rf_native_write_bb,
    .delay_us = rtwn8723be_rf_native_delay_us,
};

static int
rtwn8723be_rf_native_radio_a(void *arg, unsigned int path)
{
    struct rtwn8723be_rf_serial_ctx *ctx = arg;
    struct rtwn8723be_softc *sc;

    if (ctx == NULL || ctx->dev == NULL ||
        path != RTWN8723BE_RF_PATH_A)
        return EINVAL;
    sc = ctx->dev;
    return rtwn8723be_phy_run_radio_a(&sc->sc_phy_identity, ctx,
        rtwn8723be_rf_radio_a_apply);
}

int
rtwn8723be_netbsd_phy_rf_config(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_rf_serial_ctx ctx;
    int error;

    if (sc == NULL)
        return EINVAL;
    /*
     * A real board/cut/RF-type parser must publish both validity flags
     * before this callback can perform a single hardware access. Do not
     * guess the RF path count from the PCI vendor/device IDs.
     */
    if (!sc->sc_rf_path_count_valid ||
        !sc->sc_phy_identity_valid)
        return ENXIO;
    if (sc->sc_rf_path_count != 1 &&
        sc->sc_rf_path_count != 2)
        return EINVAL;
    if (sc->sc_linux.stage != R23BE_STAGE_PHY_RF ||
        !rtwn8723be_rf_native_ready(sc))
        return ENXIO;

    ctx.io = &rtwn8723be_rf_native_io;
    ctx.dev = sc;
    error = rtwn8723be_rf_path_configure(&ctx,
        RTWN8723BE_RF_PATH_A, rtwn8723be_rf_native_radio_a, &ctx);
    if (error != 0)
        return error;
    if (sc->sc_rf_path_count == 2)
        error = rtwn8723be_rf_path_configure(&ctx,
            RTWN8723BE_RF_PATH_B, NULL, NULL);
    return error;
}

int
rtwn8723be_netbsd_rf_channel_state_init(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_rf_serial_ctx ctx;
    uint32_t values[2];
    int error;

    if (sc == NULL)
        return EINVAL;
    sc->sc_rf_chnlval_valid = false;
    if (sc->sc_linux.stage != R23BE_STAGE_RF_CHANNEL_STATE ||
        !rtwn8723be_rf_native_ready(sc))
        return ENXIO;
    if (sc->sc_rf_path_count != 1 && sc->sc_rf_path_count != 2)
        return EINVAL;

    /* Linux reads both paths, including on the one-transmitter board. */
    ctx.io = &rtwn8723be_rf_native_io;
    ctx.dev = sc;
    error = rtwn8723be_rf_channel_state_read(&ctx, values);
    if (error != 0)
        return error;
    sc->sc_rf_chnlval[0] = values[0];
    sc->sc_rf_chnlval[1] = values[1];
    sc->sc_rf_chnlval_valid = true;
    return 0;
}
