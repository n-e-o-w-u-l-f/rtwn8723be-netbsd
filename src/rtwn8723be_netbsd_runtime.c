#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>

#include "rtwn8723be_netbsd.h"

static uint8_t
rtwn8723be_dbi_read(struct rtwn8723be_softc *sc, uint16_t addr)
{
    uint16_t read_addr;
    uint8_t tmp;
    unsigned int count;

    read_addr = addr & 0xfffc;
    rtwn8723be_write_2(sc, R23BE_REG_DBI_ADDR, read_addr);
    rtwn8723be_write_1(sc, R23BE_REG_DBI_FLAG, 0x02);
    for (count = 0; count < 20; count++) {
        tmp = rtwn8723be_read_1(sc, R23BE_REG_DBI_FLAG);
        if (tmp == 0)
            return rtwn8723be_read_1(sc,
                R23BE_REG_DBI_RDATA + (addr & 3));
        delay(10);
    }
    return 0;
}

static void
rtwn8723be_dbi_write(struct rtwn8723be_softc *sc, uint16_t addr,
    uint8_t data)
{
    uint16_t write_addr;
    unsigned int remainder, count;

    remainder = addr & 3;
    rtwn8723be_write_1(sc, R23BE_REG_DBI_WDATA + remainder, data);
    write_addr = (addr & 0xfffc) | (1U << (remainder + 12));
    rtwn8723be_write_2(sc, R23BE_REG_DBI_ADDR, write_addr);
    rtwn8723be_write_1(sc, R23BE_REG_DBI_FLAG, 0x01);
    for (count = 0; count < 20; count++) {
        if (rtwn8723be_read_1(sc, R23BE_REG_DBI_FLAG) == 0)
            break;
        delay(10);
    }
}

static uint16_t
rtwn8723be_mdio_read(struct rtwn8723be_softc *sc, uint8_t addr)
{
    unsigned int count;

    rtwn8723be_write_1(sc, R23BE_REG_MDIO_CTL, addr | (1U << 6));
    for (count = 0; count < 20; count++) {
        if ((rtwn8723be_read_1(sc, R23BE_REG_MDIO_CTL) &
            (1U << 6)) == 0)
            return rtwn8723be_read_2(sc, R23BE_REG_MDIO_RDATA);
        delay(10);
    }
    return 0;
}

static void
rtwn8723be_mdio_write(struct rtwn8723be_softc *sc, uint8_t addr,
    uint16_t data)
{
    unsigned int count;

    rtwn8723be_write_2(sc, R23BE_REG_MDIO_WDATA, data);
    rtwn8723be_write_1(sc, R23BE_REG_MDIO_CTL, addr | (1U << 5));
    for (count = 0; count < 20; count++) {
        if ((rtwn8723be_read_1(sc, R23BE_REG_MDIO_CTL) &
            (1U << 5)) == 0)
            break;
        delay(10);
    }
}

int
rtwn8723be_netbsd_rcr_postprocess(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    sc->sc_receive_config = rtwn8723be_read_4(sc, R23BE_REG_RCR);
    sc->sc_receive_config &= ~(R23BE_RCR_ACRC32 | R23BE_RCR_AICV);
    rtwn8723be_write_4(sc, R23BE_REG_RCR, sc->sc_receive_config);
    sc->sc_rx_conf = sc->sc_receive_config;
    return 0;
}

int
rtwn8723be_netbsd_cam_reset_all(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    rtwn8723be_write_4(sc, R23BE_REG_CAMCMD,
        R23BE_CAM_POLLING | R23BE_CAM_CLR);
    return 0;
}

int
rtwn8723be_netbsd_enable_hw_security(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint8_t sec;

    sec = R23BE_SCR_TXENCENABLE | R23BE_SCR_RXDECENABLE |
        R23BE_SCR_TXBCUSEDK | R23BE_SCR_RXBCUSEDK;
    rtwn8723be_write_1(sc, R23BE_REG_CR + 1, 0x02);
    rtwn8723be_write_1(sc, R23BE_REG_SECCFG, sec);
    return 0;
}

int
rtwn8723be_netbsd_set_mac_address(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    unsigned int i;

    for (i = 0; i < sizeof(sc->sc_macaddr); i++)
        rtwn8723be_write_1(sc, R23BE_REG_MACID + i, sc->sc_macaddr[i]);
    return 0;
}

int
rtwn8723be_netbsd_enable_aspm_backdoor(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    static const struct {
        uint8_t reg;
        uint16_t value;
    } ephy[] = {
        { 0x01, 0x0663 }, { 0x04, 0x7544 }, { 0x06, 0xb880 },
        { 0x07, 0x4000 }, { 0x08, 0x9003 }, { 0x09, 0x0d03 },
        { 0x0a, 0x4037 }, { 0x0b, 0x0070 },
    };
    uint8_t tmp;
    unsigned int i;

    for (i = 0; i < __arraycount(ephy); i++) {
        if (rtwn8723be_mdio_read(sc, ephy[i].reg) != ephy[i].value)
            rtwn8723be_mdio_write(sc, ephy[i].reg, ephy[i].value);
    }

    tmp = rtwn8723be_dbi_read(sc, 0x70f);
    rtwn8723be_dbi_write(sc, 0x70f, tmp | (1U << 7) |
        (R23BE_ASPM_L1_LATENCY << 3));
    tmp = rtwn8723be_dbi_read(sc, 0x719);
    rtwn8723be_dbi_write(sc, 0x719, tmp | (1U << 3) | (1U << 4));
    return 0;
}

int
rtwn8723be_netbsd_set_nav_upper_235(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    rtwn8723be_write_1(sc, R23BE_REG_NAV_UPPER, 235);
    return 0;
}

int
rtwn8723be_netbsd_release_rx_dma(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint8_t value;

    value = rtwn8723be_read_1(sc, R23BE_REG_RXDMA_CONTROL);
    if (value & R23BE_RXDMA_PAUSE)
        rtwn8723be_write_1(sc, R23BE_REG_RXDMA_CONTROL,
            value & ~R23BE_RXDMA_PAUSE);
    return 0;
}

int
rtwn8723be_netbsd_release_pcie_dma(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    rtwn8723be_write_1(sc, R23BE_REG_PCIE_CTRL_REG + 1, 0);
    return 0;
}

int
rtwn8723be_netbsd_set_retry_limit(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint16_t value;

    value = ((uint16_t)sc->sc_retry_long <<
        R23BE_RETRY_LIMIT_SHORT_SHIFT) |
        ((uint16_t)sc->sc_retry_long << R23BE_RETRY_LIMIT_LONG_SHIFT);
    rtwn8723be_write_2(sc, R23BE_REG_RL, value);
    return 0;
}

int
rtwn8723be_netbsd_init_rx_config(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    sc->sc_rx_conf = sc->sc_receive_config;
    return 0;
}

int
rtwn8723be_netbsd_mark_hal_start(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    sc->sc_hal_started = true;
    sc->sc_driver_unloading = false;
    sc->sc_up_first_time = false;
    return 0;
}

int
rtwn8723be_netbsd_mark_hal_stop(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    sc->sc_hal_started = false;
    sc->sc_driver_unloading = true;
    return 0;
}

int
rtwn8723be_netbsd_wait_rf_change_idle(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    unsigned int timeout;

    for (timeout = 0; sc->sc_rfchange_inprogress && timeout <= 100;
        timeout++)
        delay(1000);
    sc->sc_rfchange_inprogress = true;
    return 0;
}

int
rtwn8723be_netbsd_hw_disable(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    int error;

    error = rtwn8723be_netbsd_poweroff_adapter(sc);
    sc->sc_rfchange_inprogress = false;
    return error;
}
