/* SPDX-License-Identifier: GPL-2.0
 * Native NetBSD binding of Linux fd179f8a rtl8723be_phy_bb_config().
 * RF register definitions are immutable in rf_serial.c/rf_path.c; Linux's
 * rtl8723_phy_init_bb_rf_reg_def() therefore needs no mutable adapter copy.
 * The owning lifecycle serializes initialization before enabling DMA/IRQ.
 * Runtime TX-power programming, RF calibration and locking are separate
 * full-port requirements, not supplied by the BB/PG initialization below.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_bb_native.h"
#include "rtwn8723be_phy_bb_sequence.h"
#include "rtwn8723be_txpwr_pg.h"

static bool
rtwn8723be_bb_native_ready(const struct rtwn8723be_softc *sc)
{
    return sc != NULL && sc->sc_mapped && sc->sc_core_initialized &&
        sc->sc_linux.fw_ready && sc->sc_efuse_autoload_ok &&
        sc->sc_bt_ant_valid && sc->sc_package_valid &&
        sc->sc_phy_identity_valid && sc->sc_xtal_valid &&
        sc->sc_phy_identity.pci_interface &&
        sc->sc_phy_identity.package_type == sc->sc_package_type &&
        sc->sc_mapsize >= 0x948U + sizeof(uint32_t) &&
        sc->sc_linux.being_init_adapter &&
        sc->sc_linux.stage == R23BE_STAGE_PHY_BB &&
        !sc->sc_linux.started && !sc->sc_irq_enabled;
}

static int
rtwn8723be_bb_native_check_agc(void *arg, uint32_t reg, uint32_t value)
{
    const struct rtwn8723be_softc *sc = arg;

    (void)value;
    if ((reg & 3U) != 0 || reg > sc->sc_mapsize ||
        sc->sc_mapsize - reg < sizeof(uint32_t))
        return EINVAL;
    return 0;
}

static int
rtwn8723be_bb_native_check_bb(void *arg, uint32_t reg, uint32_t value)
{
    /* The six BB delay tokens are not MMIO register addresses. */
    if (reg >= 0xf9U && reg <= 0xfeU)
        return 0;
    return rtwn8723be_bb_native_check_agc(arg, reg, value);
}

static int
rtwn8723be_bb_native_write_bb(void *arg, uint32_t reg, uint32_t value)
{
    int error;

    if (!rtwn8723be_bb_native_ready(arg))
        return ENXIO;
    error = rtwn8723be_bb_native_check_bb(arg, reg, value);
    return error != 0 ? error :
        rtwn8723be_netbsd_phy_bb_write(arg, reg, value);
}

static int
rtwn8723be_bb_native_write_agc(void *arg, uint32_t reg, uint32_t value)
{
    int error;

    if (!rtwn8723be_bb_native_ready(arg))
        return ENXIO;
    error = rtwn8723be_bb_native_check_agc(arg, reg, value);
    return error != 0 ? error :
        rtwn8723be_netbsd_phy_agc_write(arg, reg, value);
}

static int
rtwn8723be_bb_native_select_antenna(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    rtwn8723be_write_4(sc, 0x948, sc->sc_single_ant_path == 0 ? 0x280 : 0);
    return 0;
}

static int
rtwn8723be_bb_native_init_txpower(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    rtwn8723be_txpwr_pg_reset(&sc->sc_txpwr_pg);
    return 0;
}

static int
rtwn8723be_bb_native_reset_pwrgroup(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    sc->sc_pwrgroup_cnt = 0;
    return 0;
}

static int
rtwn8723be_bb_native_store_pg(void *arg, const struct rtwn8723be_pg_entry *entry)
{
    struct rtwn8723be_softc *sc = arg;

    return rtwn8723be_txpwr_pg_store(&sc->sc_txpwr_pg, entry);
}

static int
rtwn8723be_bb_native_convert_txpower(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    rtwn8723be_txpwr_pg_convert(&sc->sc_txpwr_pg);
    return 0;
}

static int
rtwn8723be_bb_native_read_cck(void *arg, bool *high_power)
{
    struct rtwn8723be_softc *sc = arg;

    *high_power = (rtwn8723be_read_4(sc, 0x824) & 0x200U) != 0;
    return 0;
}

static const struct rtwn8723be_bb_sequence_ops rtwn8723be_bb_native_ops = {
    .select_antenna = rtwn8723be_bb_native_select_antenna,
    .write_bb = rtwn8723be_bb_native_write_bb,
    .init_txpower = rtwn8723be_bb_native_init_txpower,
    .reset_pwrgroup = rtwn8723be_bb_native_reset_pwrgroup,
    .store_pg = rtwn8723be_bb_native_store_pg,
    .convert_txpower = rtwn8723be_bb_native_convert_txpower,
    .write_agc = rtwn8723be_bb_native_write_agc,
    .read_cck_high_power = rtwn8723be_bb_native_read_cck,
};

int
rtwn8723be_netbsd_phy_bb_config(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint16_t regval;
    uint32_t tmp, crystal;
    bool high_power;
    int error;

    if (sc == NULL)
        return EINVAL;
    sc->sc_bb_valid = false;
    if (!rtwn8723be_bb_native_ready(sc))
        return ENXIO;
    if (sc->sc_single_ant_path > 1)
        return EINVAL;
    /* Validate every frozen BB/AGC register before the first setup write. */
    error = rtwn8723be_phy_run_bb(sc, rtwn8723be_bb_native_check_bb);
    if (error == 0)
        error = rtwn8723be_phy_run_agc(sc, rtwn8723be_bb_native_check_agc);
    if (error != 0)
        return error;

    regval = rtwn8723be_read_2(sc, 0x2);
    rtwn8723be_write_2(sc, 0x2, regval | (1U << 13) | 3U);
    rtwn8723be_write_1(sc, 0x1f, 7);
    rtwn8723be_write_1(sc, 0x2, 0xe3);
    tmp = rtwn8723be_read_4(sc, 0x4c);
    rtwn8723be_write_4(sc, 0x4c, tmp | (1U << 23));
    rtwn8723be_write_1(sc, 0x25, 0x80);

    error = rtwn8723be_phy_bb_sequence(sc, &rtwn8723be_bb_native_ops,
        sc->sc_efuse_autoload_ok, &high_power);
    /* Linux programs crystal capacitance even if parafile returns false. */
    crystal = sc->sc_xtal_cap & 0x3fU;
    rtwn8723be_netbsd_set_bbreg(sc, 0x2c, 0xfff000U,
        crystal | (crystal << 6));
    if (error != 0)
        return error;
    sc->sc_cck_high_power = high_power;
    sc->sc_bb_valid = true;
    return 0;
}
