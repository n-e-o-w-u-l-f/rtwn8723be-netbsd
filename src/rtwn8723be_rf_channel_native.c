/* SPDX-License-Identifier: GPL-2.0
 * Native NetBSD bus_space binding for Linux rtl8723be/hw.c RF_CHNLBW
 * snapshot. Called only after PHY_RF, in the exclusive RF_CHANNEL_STATE
 * init phase, before enabling IRQ or normal runtime operation.
 *
 * Linux reads A and B even on the RTL8723BE 1T1R target; neither the
 * second sample nor a partially failed snapshot is made valid on error.
 * Runtime channel switching and RF-lock ownership are separate gates.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>

#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_rf_native.h"
#include "rtwn8723be_rf_channel_state.h"

/* B PI readback at 0x8bc is the largest BB register in RF serial read. */
#define RTWN8723BE_RF_CHANNEL_LAST_BB 0x8bcU

static bool
rtwn8723be_rf_channel_native_ready(void *arg)
{
    const struct rtwn8723be_softc *sc = arg;

    return sc != NULL && sc->sc_mapped && sc->sc_core_initialized &&
        sc->sc_linux.fw_ready && sc->sc_efuse_autoload_ok &&
        sc->sc_bt_ant_valid && sc->sc_package_valid &&
        sc->sc_phy_identity_valid && sc->sc_rf_path_count_valid &&
        (sc->sc_rf_path_count == 1 || sc->sc_rf_path_count == 2) &&
        sc->sc_phy_identity.pci_interface &&
        sc->sc_phy_identity.package_type == sc->sc_package_type &&
        sc->sc_mapsize >= RTWN8723BE_RF_CHANNEL_LAST_BB +
            sizeof(uint32_t) &&
        sc->sc_linux.being_init_adapter &&
        sc->sc_linux.stage == R23BE_STAGE_RF_CHANNEL_STATE &&
        !sc->sc_linux.started && !sc->sc_irq_enabled;
}

static int
rtwn8723be_rf_channel_check_reg(struct rtwn8723be_softc *sc, uint32_t reg)
{
    if (!rtwn8723be_rf_channel_native_ready(sc))
        return ENXIO;
    if ((reg & 3U) != 0 || reg > sc->sc_mapsize ||
        sc->sc_mapsize - reg < sizeof(uint32_t))
        return EINVAL;
    return 0;
}

static int
rtwn8723be_rf_channel_read_bb(void *arg, uint32_t reg, uint32_t *value)
{
    struct rtwn8723be_softc *sc = arg;
    int error;

    if (value == NULL)
        return EINVAL;
    error = rtwn8723be_rf_channel_check_reg(sc, reg);
    if (error != 0)
        return error;
    *value = rtwn8723be_read_4(sc, reg);
    return 0;
}

static int
rtwn8723be_rf_channel_write_bb(void *arg, uint32_t reg, uint32_t value)
{
    struct rtwn8723be_softc *sc = arg;
    int error;

    error = rtwn8723be_rf_channel_check_reg(sc, reg);
    if (error != 0)
        return error;
    rtwn8723be_write_4(sc, reg, value); /* NetBSD bus_space barrier. */
    return 0;
}

static void
rtwn8723be_rf_channel_delay(void *arg, unsigned int usec)
{
    (void)arg;
    delay(usec);
}

static const struct rtwn8723be_rf_serial_io rtwn8723be_rf_channel_io = {
    .ready = rtwn8723be_rf_channel_native_ready,
    .read_bb = rtwn8723be_rf_channel_read_bb,
    .write_bb = rtwn8723be_rf_channel_write_bb,
    .delay_us = rtwn8723be_rf_channel_delay,
};

int
rtwn8723be_netbsd_rf_channel_state_init(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_rf_serial_ctx ctx;
    uint32_t next[2];
    int error;

    if (sc == NULL)
        return EINVAL;
    sc->sc_rf_chnlval_valid = false;
    if (!rtwn8723be_rf_channel_native_ready(sc))
        return ENXIO;
    ctx.io = &rtwn8723be_rf_channel_io;
    ctx.dev = sc;
    error = rtwn8723be_rf_channel_state_read(&ctx, next);
    if (error != 0)
        return error;
    sc->sc_rf_chnlval[0] = next[0];
    sc->sc_rf_chnlval[1] = next[1];
    sc->sc_rf_chnlval_valid = true;
    return 0;
}
