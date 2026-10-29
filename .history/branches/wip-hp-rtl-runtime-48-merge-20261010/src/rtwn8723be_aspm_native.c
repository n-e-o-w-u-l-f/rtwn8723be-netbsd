/* SPDX-License-Identifier: GPL-2.0
 * Linux fd179f8a rtl8723be/hw.c DBI/MDIO and ASPM ePHY backdoor.
 * Native bus_space accessors preserve the upstream byte/word widths and
 * ordering. Initialization is serialized before interrupts/DMA traffic.
 * A 20 x 10us timeout returns ETIMEDOUT rather than upstream's ambiguous
 * zero read/void write; the lifecycle must abort further programming.
 * Partial ePHY writes cannot be assumed undone after a transport timeout.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_aspm_native.h"

#define R23BE_DBI_WDATA 0x348U
#define R23BE_DBI_RDATA 0x34cU
#define R23BE_DBI_ADDR  0x350U
#define R23BE_DBI_FLAG  0x352U
#define R23BE_MDIO_WDATA 0x354U
#define R23BE_MDIO_RDATA 0x356U
#define R23BE_MDIO_CTL   0x358U

static bool
rtwn8723be_aspm_native_ready(const struct rtwn8723be_softc *sc)
{
    return sc != NULL && sc->sc_mapped && sc->sc_core_initialized &&
        sc->sc_bb_valid && sc->sc_rf_chnlval_valid &&
        sc->sc_efuse_autoload_ok && sc->sc_package_valid &&
        sc->sc_phy_identity_valid && sc->sc_phy_identity.pci_interface &&
        sc->sc_phy_identity.package_type == sc->sc_package_type &&
        sc->sc_mapsize >= R23BE_MDIO_CTL + sizeof(uint8_t) &&
        sc->sc_linux.fw_ready && sc->sc_linux.being_init_adapter &&
        sc->sc_linux.stage == R23BE_STAGE_ASPM_RESTORE &&
        !sc->sc_linux.started && !sc->sc_irq_enabled;
}

static int
rtwn8723be_aspm_native_wait(struct rtwn8723be_softc *sc,
    bus_size_t reg, uint8_t mask)
{
    uint8_t busy;
    unsigned int count;

    busy = rtwn8723be_read_1(sc, reg) & mask;
    for (count = 0; busy != 0 && count < 20; count++) {
        delay(10);
        busy = rtwn8723be_read_1(sc, reg) & mask;
    }
    return busy == 0 ? 0 : ETIMEDOUT;
}

int
rtwn8723be_netbsd_dbi_read(void *arg, uint16_t addr, uint8_t *value)
{
    struct rtwn8723be_softc *sc = arg;
    int error;

    if (sc == NULL || value == NULL || addr >= 0x1000U)
        return EINVAL;
    if (!rtwn8723be_aspm_native_ready(sc))
        return ENXIO;
    rtwn8723be_write_2(sc, R23BE_DBI_ADDR, addr & 0xfffcU);
    rtwn8723be_write_1(sc, R23BE_DBI_FLAG, 2);
    error = rtwn8723be_aspm_native_wait(sc, R23BE_DBI_FLAG, 0xff);
    if (error != 0)
        return error;
    *value = rtwn8723be_read_1(sc, R23BE_DBI_RDATA + addr % 4);
    return 0;
}

int
rtwn8723be_netbsd_dbi_write(void *arg, uint16_t addr, uint8_t value)
{
    struct rtwn8723be_softc *sc = arg;
    uint16_t lane;

    if (sc == NULL || addr >= 0x1000U)
        return EINVAL;
    if (!rtwn8723be_aspm_native_ready(sc))
        return ENXIO;
    lane = addr % 4;
    rtwn8723be_write_1(sc, R23BE_DBI_WDATA + lane, value);
    rtwn8723be_write_2(sc, R23BE_DBI_ADDR,
        (addr & 0xfffcU) | (1U << (lane + 12)));
    rtwn8723be_write_1(sc, R23BE_DBI_FLAG, 1);
    return rtwn8723be_aspm_native_wait(sc, R23BE_DBI_FLAG, 0xff);
}

int
rtwn8723be_netbsd_mdio_read(void *arg, uint8_t addr, uint16_t *value)
{
    struct rtwn8723be_softc *sc = arg;
    int error;

    if (sc == NULL || value == NULL || addr >= 32)
        return EINVAL;
    if (!rtwn8723be_aspm_native_ready(sc))
        return ENXIO;
    rtwn8723be_write_1(sc, R23BE_MDIO_CTL, addr | (1U << 6));
    error = rtwn8723be_aspm_native_wait(sc, R23BE_MDIO_CTL, 1U << 6);
    if (error != 0)
        return error;
    *value = rtwn8723be_read_2(sc, R23BE_MDIO_RDATA);
    return 0;
}

int
rtwn8723be_netbsd_mdio_write(void *arg, uint8_t addr, uint16_t value)
{
    struct rtwn8723be_softc *sc = arg;

    if (sc == NULL || addr >= 32)
        return EINVAL;
    if (!rtwn8723be_aspm_native_ready(sc))
        return ENXIO;
    rtwn8723be_write_2(sc, R23BE_MDIO_WDATA, value);
    rtwn8723be_write_1(sc, R23BE_MDIO_CTL, addr | (1U << 5));
    return rtwn8723be_aspm_native_wait(sc, R23BE_MDIO_CTL, 1U << 5);
}

int
rtwn8723be_netbsd_enable_aspm_backdoor(void *arg)
{
    static const struct {
        uint8_t index;
        uint16_t value;
    } ephy[] = {
        {0x01, 0x0663}, {0x04, 0x7544}, {0x06, 0xb880}, {0x07, 0x4000},
        {0x08, 0x9003}, {0x09, 0x0d03}, {0x0a, 0x4037}, {0x0b, 0x0070},
    };
    struct rtwn8723be_softc *sc = arg;
    uint16_t word;
    uint8_t byte;
    unsigned int i;
    int error;

    if (sc == NULL)
        return EINVAL;
    sc->sc_aspm_backdoor_valid = false;
    if (!rtwn8723be_aspm_native_ready(sc))
        return ENXIO;
    for (i = 0; i < sizeof(ephy) / sizeof(ephy[0]); i++) {
        error = rtwn8723be_netbsd_mdio_read(sc, ephy[i].index, &word);
        if (error != 0)
            return error;
        if (word != ephy[i].value) {
            error = rtwn8723be_netbsd_mdio_write(sc, ephy[i].index, ephy[i].value);
            if (error != 0)
                return error;
        }
    }
    error = rtwn8723be_netbsd_dbi_read(sc, 0x70f, &byte);
    if (error != 0)
        return error;
    /* Frozen rtlwifi/wifi.h: ASPM_L1_LATENCY = 7. */
    error = rtwn8723be_netbsd_dbi_write(sc, 0x70f,
        byte | (1U << 7) | (7U << 3));
    if (error != 0)
        return error;
    error = rtwn8723be_netbsd_dbi_read(sc, 0x719, &byte);
    if (error != 0)
        return error;
    error = rtwn8723be_netbsd_dbi_write(sc, 0x719,
        byte | (1U << 3) | (1U << 4));
    if (error != 0)
        return error;
    sc->sc_aspm_backdoor_valid = true;
    return 0;
}
