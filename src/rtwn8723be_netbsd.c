#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/intr.h>
#include <sys/mbuf.h>
#include <sys/endian.h>
#include <sys/kmem.h>

#include <dev/pci/pcireg.h>
#include <dev/pci/pcivar.h>
#include <dev/pci/pcidevs.h>
#include <dev/firmload.h>

#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_fw.h"
#include "rtwn8723be_pwrseq_plan.h"
#include "rtwn8723be_mac_table.h"

static int rtwn8723be_netbsd_intr(void *);
static void rtwn8723be_netbsd_softintr(void *);

static void
rtwn8723be_pci_conf_write_1(struct rtwn8723be_softc *sc, int reg,
    uint8_t value)
{
    const int aligned = reg & ~3;
    const unsigned int shift = (unsigned int)(reg & 3) * 8;
    pcireg_t v;

    v = pci_conf_read(sc->sc_pc, sc->sc_tag, aligned);
    v &= ~((pcireg_t)0xff << shift);
    v |= (pcireg_t)value << shift;
    pci_conf_write(sc->sc_pc, sc->sc_tag, aligned, v);
}

void
rtwn8723be_netbsd_context_init(struct rtwn8723be_softc *sc,
    device_t self, const struct pci_attach_args *pa)
{
    memset(sc, 0, sizeof(*sc));
    sc->sc_dev = self;
    sc->sc_pa = *pa;
    sc->sc_pc = pa->pa_pc;
    sc->sc_tag = pa->pa_tag;
    sc->sc_dmat_parent = pa->pa_dmat;
    sc->sc_dmat = pa->pa_dmat;

    /*
     * Linux rtl8723be_mod_params leaves dma64 false, so rtl_pci_probe()
     * selects the 32-bit DMA mask/coherent mask path.  dma_configure()
     * turns this into a NetBSD bus_dma subregion tag.
     */
    sc->sc_dma_32bit = false;
    /* Linux rtl_pci_init(): retry_short = retry_long = 7. */
    sc->sc_retry_limit = 7;

    sc->sc_irq_mask[0] = R23BE_IMR0_DEFAULT;
    sc->sc_irq_mask[1] = R23BE_IMR1_DEFAULT;
    sc->sc_sys_irq_mask = R23BE_HSIMR_PDN_INT_EN |
        R23BE_HSIMR_RON_INT_EN;
}

uint8_t
rtwn8723be_read_1(struct rtwn8723be_softc *sc, bus_size_t reg)
{
    return bus_space_read_1(sc->sc_st, sc->sc_sh, reg);
}

uint16_t
rtwn8723be_read_2(struct rtwn8723be_softc *sc, bus_size_t reg)
{
    return bus_space_read_2(sc->sc_st, sc->sc_sh, reg);
}

uint32_t
rtwn8723be_read_4(struct rtwn8723be_softc *sc, bus_size_t reg)
{
    return bus_space_read_4(sc->sc_st, sc->sc_sh, reg);
}

void
rtwn8723be_write_1(struct rtwn8723be_softc *sc, bus_size_t reg,
    uint8_t value)
{
    bus_space_write_1(sc->sc_st, sc->sc_sh, reg, value);
    bus_space_barrier(sc->sc_st, sc->sc_sh, reg, 1,
        BUS_SPACE_BARRIER_WRITE);
}

void
rtwn8723be_write_2(struct rtwn8723be_softc *sc, bus_size_t reg,
    uint16_t value)
{
    bus_space_write_2(sc->sc_st, sc->sc_sh, reg, value);
    bus_space_barrier(sc->sc_st, sc->sc_sh, reg, 2,
        BUS_SPACE_BARRIER_WRITE);
}

void
rtwn8723be_write_4(struct rtwn8723be_softc *sc, bus_size_t reg,
    uint32_t value)
{
    bus_space_write_4(sc->sc_st, sc->sc_sh, reg, value);
    bus_space_barrier(sc->sc_st, sc->sc_sh, reg, 4,
        BUS_SPACE_BARRIER_WRITE);
}

static unsigned int
rtwn8723be_netbsd_bit_shift(uint32_t bitmask)
{
    unsigned int shift = 0;

    KASSERT(bitmask != 0);
    while ((bitmask & 1U) == 0) {
        bitmask >>= 1;
        shift++;
    }
    return shift;
}

uint32_t
rtwn8723be_netbsd_get_bbreg(struct rtwn8723be_softc *sc,
    bus_size_t reg, uint32_t bitmask)
{
    uint32_t value;

    KASSERT(bitmask != 0);
    value = rtwn8723be_read_4(sc, reg);
    return (value & bitmask) >> rtwn8723be_netbsd_bit_shift(bitmask);
}

void
rtwn8723be_netbsd_set_bbreg(struct rtwn8723be_softc *sc,
    bus_size_t reg, uint32_t bitmask, uint32_t data)
{
    uint32_t value;

    KASSERT(bitmask != 0);
    if (bitmask != 0xffffffffU) {
        value = rtwn8723be_read_4(sc, reg);
        data = (value & ~bitmask) |
            (data << rtwn8723be_netbsd_bit_shift(bitmask));
    }
    rtwn8723be_write_4(sc, reg, data);
}

int
rtwn8723be_netbsd_pci_enable(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    pcireg_t command;

    command = pci_conf_read(sc->sc_pc, sc->sc_tag,
        PCI_COMMAND_STATUS_REG);
    command |= PCI_COMMAND_IO_ENABLE | PCI_COMMAND_MEM_ENABLE;
    pci_conf_write(sc->sc_pc, sc->sc_tag, PCI_COMMAND_STATUS_REG,
        command);
    return 0;
}

int
rtwn8723be_netbsd_dma_configure(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    bus_dma_tag_t dmat;
    int error;

    if (sc->sc_dmat_parent == NULL)
        return ENXIO;
    if (sc->sc_dmat_owned)
        return 0;

    /*
     * Linux RTL8723BE defaults to a 32-bit dma_set_mask() and coherent mask.
     * NetBSD expresses the same hardware addressability constraint with a
     * DMA subregion tag, so allocations and packet mappings can never escape
     * the device-visible 0..0xffffffff range.
     */
    error = bus_dmatag_subregion(sc->sc_dmat_parent, 0,
        (bus_addr_t)RTWN8723BE_DMA_MAXADDR, &dmat, BUS_DMA_WAITOK);
    if (error != 0)
        return error;

    sc->sc_dmat = dmat;
    sc->sc_dmat_owned = true;
    sc->sc_dma_32bit = true;
    return 0;
}

void
rtwn8723be_netbsd_dma_release(struct rtwn8723be_softc *sc)
{
    if (sc->sc_dmat_owned) {
        bus_dmatag_destroy(sc->sc_dmat);
        sc->sc_dmat_owned = false;
    }
    sc->sc_dmat = sc->sc_dmat_parent;
}

int
rtwn8723be_netbsd_pci_set_master(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    pcireg_t command;

    command = pci_conf_read(sc->sc_pc, sc->sc_tag,
        PCI_COMMAND_STATUS_REG);
    command |= PCI_COMMAND_MASTER_ENABLE;
    pci_conf_write(sc->sc_pc, sc->sc_tag, PCI_COMMAND_STATUS_REG,
        command);
    return 0;
}

int
rtwn8723be_netbsd_alloc_softc(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    /* NetBSD autoconf already allocated device_private(self). */
    return sc->sc_dev != NULL ? 0 : ENXIO;
}

int
rtwn8723be_netbsd_map_bar(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    pcireg_t memtype;
    int error;

    if (sc->sc_mapped)
        return 0;

    memtype = pci_mapreg_type(sc->sc_pc, sc->sc_tag,
        RTWN8723BE_PCI_BAR_MMIO);
    error = pci_mapreg_map(&sc->sc_pa, RTWN8723BE_PCI_BAR_MMIO,
        memtype, 0, &sc->sc_st, &sc->sc_sh, &sc->sc_base,
        &sc->sc_mapsize);
    if (error != 0)
        return error;

    sc->sc_mapped = true;
    return 0;
}

int
rtwn8723be_netbsd_pci_prepare_d0(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    /*
     * Linux rtl_pci_probe() after BAR mapping:
     *   config[0x81] = 0       (disable CLKREQ)
     *   config[0x44] = 0       (leave D3)
     *   command byte = 0x06, then 0x07
     *
     * pci_set_powerstate() performs the NetBSD PM transition.  The byte
     * writes are retained because they are part of the RTL PCI reference
     * sequence, not an inferred workaround.
     */
    int error;

    error = pci_set_powerstate(sc->sc_pc, sc->sc_tag,
        PCI_PMCSR_STATE_D0);
    if (error != 0)
        return error;

    rtwn8723be_pci_conf_write_1(sc, 0x81, 0x00);
    rtwn8723be_pci_conf_write_1(sc, 0x44, 0x00);
    rtwn8723be_pci_conf_write_1(sc, 0x04, 0x06);
    rtwn8723be_pci_conf_write_1(sc, 0x04, 0x07);
    return 0;
}

int
rtwn8723be_netbsd_find_adapter(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    if (PCI_VENDOR(sc->sc_pa.pa_id) != PCI_VENDOR_REALTEK ||
        PCI_PRODUCT(sc->sc_pa.pa_id) != 0xb723)
        return ENODEV;

    return 0;
}

int
rtwn8723be_netbsd_init_io(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    return sc->sc_mapped ? 0 : ENXIO;
}

static uint16_t
rtwn8723be_le16(const uint8_t *p)
{
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static void
rtwn8723be_netbsd_efuse_power(struct rtwn8723be_softc *sc, bool on)
{
    uint16_t value;

    if (on) {
        /* Pinned Linux efuse_power_switch(), RTL8723BE read path. */
        rtwn8723be_write_1(sc, R23BE_REG_EFUSE_ACCESS, 0x69);

        value = rtwn8723be_read_2(sc, R23BE_REG_SYS_FUNC_EN);
        if ((value & R23BE_EFUSE_FEN_ELDR) == 0)
            rtwn8723be_write_2(sc, R23BE_REG_SYS_FUNC_EN,
                value | R23BE_EFUSE_FEN_ELDR);

        value = rtwn8723be_read_2(sc, R23BE_REG_SYS_CLKR);
        if ((value & (R23BE_EFUSE_LOADER_CLK_EN |
            R23BE_EFUSE_ANA8M)) !=
            (R23BE_EFUSE_LOADER_CLK_EN | R23BE_EFUSE_ANA8M))
            rtwn8723be_write_2(sc, R23BE_REG_SYS_CLKR,
                value | R23BE_EFUSE_LOADER_CLK_EN |
                R23BE_EFUSE_ANA8M);
    } else {
        rtwn8723be_write_1(sc, R23BE_REG_EFUSE_ACCESS, 0x00);
    }
}

static int
rtwn8723be_netbsd_efuse_read_1(struct rtwn8723be_softc *sc,
    uint16_t addr, uint8_t *data)
{
    uint8_t value8;
    uint32_t value32;
    unsigned int retry;

    if (addr >= R23BE_EFUSE_REAL_CONTENT_LEN || data == NULL)
        return EINVAL;

    rtwn8723be_write_1(sc, R23BE_REG_EFUSE_CTRL + 1,
        (uint8_t)(addr & 0xff));

    value8 = rtwn8723be_read_1(sc, R23BE_REG_EFUSE_CTRL + 2);
    rtwn8723be_write_1(sc, R23BE_REG_EFUSE_CTRL + 2,
        (uint8_t)(((addr >> 8) & 0x03) | (value8 & 0xfc)));

    value8 = rtwn8723be_read_1(sc, R23BE_REG_EFUSE_CTRL + 3);
    rtwn8723be_write_1(sc, R23BE_REG_EFUSE_CTRL + 3,
        value8 & 0x7f);

    for (retry = 0; retry < 10000; retry++) {
        value32 = rtwn8723be_read_4(sc, R23BE_REG_EFUSE_CTRL);
        if ((value32 & 0x80000000U) != 0)
            break;
    }
    if (retry == 10000)
        return ETIMEDOUT;

    delay(50);
    value32 = rtwn8723be_read_4(sc, R23BE_REG_EFUSE_CTRL);
    *data = (uint8_t)(value32 & 0xff);
    return 0;
}

static int
rtwn8723be_netbsd_efuse_shadow_read(struct rtwn8723be_softc *sc)
{
    uint16_t addr = 0;
    uint8_t header, ext, offset, wren;
    unsigned int word;
    int error = 0;

    memset(sc->sc_efuse_map, 0xff, sizeof(sc->sc_efuse_map));
    rtwn8723be_netbsd_efuse_power(sc, true);

    while (addr < R23BE_EFUSE_REAL_CONTENT_LEN) {
        error = rtwn8723be_netbsd_efuse_read_1(sc, addr++, &header);
        if (error != 0)
            goto out;
        if (header == 0xff)
            break;

        if ((header & 0x1f) == 0x0f) {
            if (addr >= R23BE_EFUSE_REAL_CONTENT_LEN)
                break;
            error = rtwn8723be_netbsd_efuse_read_1(sc, addr++, &ext);
            if (error != 0)
                goto out;

            /* Linux skips extended headers with all words disabled. */
            if ((ext & 0x0f) == 0x0f)
                continue;

            offset = (uint8_t)(((ext & 0xf0) >> 1) |
                ((header & 0xe0) >> 5));
            wren = ext & 0x0f;
        } else {
            offset = (header >> 4) & 0x0f;
            wren = header & 0x0f;
        }

        if (offset >= R23BE_EFUSE_MAX_SECTION)
            continue;

        for (word = 0; word < R23BE_EFUSE_MAX_WORD_UNIT; word++) {
            size_t mapoff = (size_t)offset * 8 + word * 2;

            if ((wren & 0x01) == 0) {
                if (addr + 1 >= R23BE_EFUSE_REAL_CONTENT_LEN) {
                    error = EINVAL;
                    goto out;
                }
                error = rtwn8723be_netbsd_efuse_read_1(sc, addr++,
                    &sc->sc_efuse_map[mapoff]);
                if (error != 0)
                    goto out;
                error = rtwn8723be_netbsd_efuse_read_1(sc, addr++,
                    &sc->sc_efuse_map[mapoff + 1]);
                if (error != 0)
                    goto out;
            }
            wren >>= 1;
        }
    }

out:
    rtwn8723be_netbsd_efuse_power(sc, false);
    return error;
}

int
rtwn8723be_netbsd_read_eeprom_info(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint8_t cr9346, bt;
    int error;

    if (!sc->sc_mapped)
        return ENXIO;

    cr9346 = rtwn8723be_read_1(sc, R23BE_REG_9346CR);
    sc->sc_boot_from_efuse = (cr9346 & (1U << 4)) == 0;
    sc->sc_efuse_autoload_ok = (cr9346 & (1U << 5)) != 0;

    /*
     * Pinned rtlwifi does not implement the 93C46 path for this device;
     * reject it rather than silently treating EEPROM bytes as EFUSE.
     */
    if (!sc->sc_boot_from_efuse)
        return EOPNOTSUPP;
    if (!sc->sc_efuse_autoload_ok)
        return EIO;

    error = rtwn8723be_netbsd_efuse_shadow_read(sc);
    if (error != 0)
        return error;

    sc->sc_eeprom_id = rtwn8723be_le16(&sc->sc_efuse_map[0]);
    if (sc->sc_eeprom_id != R23BE_EEPROM_ID)
        return EINVAL;

    sc->sc_eeprom_vid =
        rtwn8723be_le16(&sc->sc_efuse_map[R23BE_EEPROM_VID]);
    sc->sc_eeprom_did =
        rtwn8723be_le16(&sc->sc_efuse_map[R23BE_EEPROM_DID]);
    sc->sc_eeprom_svid =
        rtwn8723be_le16(&sc->sc_efuse_map[R23BE_EEPROM_SVID]);
    sc->sc_eeprom_smid =
        rtwn8723be_le16(&sc->sc_efuse_map[R23BE_EEPROM_SMID]);
    memcpy(sc->sc_macaddr,
        &sc->sc_efuse_map[R23BE_EEPROM_MAC_ADDR],
        sizeof(sc->sc_macaddr));

    sc->sc_btcoexist =
        (rtwn8723be_read_4(sc, R23BE_REG_MULTI_FUNC_CTRL) &
        (1U << 18)) != 0;

    bt = sc->sc_efuse_map[R23BE_EEPROM_RF_BT_SETTING];
    sc->sc_btdm_ant_num = bt & 0x01; /* Linux enum ANT_X2=0, ANT_X1=1. */
    sc->sc_single_ant_path = (bt & 0x40) != 0 ?
        RTWN8723BE_ANT_AUX : RTWN8723BE_ANT_MAIN;
    sc->sc_bt_ant_valid = true;

    /* _rtl8723be_hal_customized_behavior() always enables open-drain LED. */
    sc->sc_led_opendrain = true;
    return 0;
}

int
rtwn8723be_netbsd_init_sw_vars(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    /*
     * Exact pinned-Linux rtl8723be_init_sw_vars() state relevant to the
     * PCI/MAC hardware path.  BT coexistence is mandatory for 8723BE.
     */
    sc->sc_transmit_config = RTWN8723BE_TCR_DEFAULT;
    sc->sc_receive_config = RTWN8723BE_RCR_DEFAULT;
    sc->sc_firmware_name = RTWN8723BE_FIRMWARE_NAME;
    sc->sc_bt_stop_coex_dm = false;
    sc->sc_up_first_time = true;
    sc->sc_led_opendrain = true;
    sc->sc_rfoff_reason = 0; /* RF_CHANGE_BY_INIT */

    return 0;
}

int
rtwn8723be_netbsd_init_leds(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    /* Exact rtl_init_sw_leds() defaults from pinned Linux. */
    sc->sc_sw_led0 = RTWN8723BE_LED_PIN_LED0;
    sc->sc_sw_led1 = RTWN8723BE_LED_PIN_LED1;
    return 0;
}

int
rtwn8723be_netbsd_init_core(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct ieee80211com *ic = &sc->sc_ic;
    struct ifnet *ifp = &sc->sc_ec.ec_if;
    unsigned int i;

    if (!sc->sc_efuse_autoload_ok)
        return ENXIO;

    /*
     * Native NetBSD mapping of Linux rtl_init_core()/_rtl_init_mac80211():
     * initialize the 802.11 software object and immutable HW capabilities.
     * Registration and driver callbacks remain in register_ieee80211().
     */
    memset(ic, 0, sizeof(*ic));
    memset(ifp, 0, sizeof(*ifp));

    ic->ic_ifp = ifp;
    ic->ic_phytype = IEEE80211_T_OFDM;
    ic->ic_opmode = IEEE80211_M_STA;
    ic->ic_state = IEEE80211_S_INIT;
    ic->ic_caps =
        IEEE80211_C_MONITOR |
        IEEE80211_C_IBSS |
        IEEE80211_C_HOSTAP |
        IEEE80211_C_SHPREAMBLE |
        IEEE80211_C_SHSLOT |
        IEEE80211_C_WME |
        IEEE80211_C_WPA;

#ifndef IEEE80211_NO_HT
    ic->ic_htcaps =
        IEEE80211_HTCAP_CBW20_40 |
        IEEE80211_HTCAP_DSSSCCK40;
    /* RTL8723BE is a 1T1R WLAN path in this target. */
    ic->ic_sup_mcs[0] = 0xff;
#endif

    ic->ic_sup_rates[IEEE80211_MODE_11B] = ieee80211_std_rateset_11b;
    ic->ic_sup_rates[IEEE80211_MODE_11G] = ieee80211_std_rateset_11g;

    for (i = 1; i <= 14; i++) {
        ic->ic_channels[i].ic_freq =
            ieee80211_ieee2mhz(i, IEEE80211_CHAN_2GHZ);
        ic->ic_channels[i].ic_flags =
            IEEE80211_CHAN_CCK | IEEE80211_CHAN_OFDM |
            IEEE80211_CHAN_DYN | IEEE80211_CHAN_2GHZ;
    }

    IEEE80211_ADDR_COPY(ic->ic_myaddr, sc->sc_macaddr);
    sc->sc_core_initialized = true;
    return 0;
}

static uint32_t
rtwn8723be_netbsd_tx_ring_count(unsigned int qid)
{
    if (qid == RTWN8723BE_BE_QUEUE)
        return RTWN8723BE_TX_RING_BE_COUNT;
    if (qid == RTWN8723BE_BEACON_QUEUE)
        return RTWN8723BE_TX_RING_BCN_COUNT;
    return RTWN8723BE_TX_RING_COUNT;
}

void
rtwn8723be_netbsd_free_pci_rings(struct rtwn8723be_softc *sc)
{
    unsigned int i;

    for (i = 0; i < RTWN8723BE_RX_QUEUE_COUNT; i++)
        rtwn8723be_f16_1_rx_ring_free(sc->sc_dmat,
            &sc->sc_rx_ring[i]);
    for (i = 0; i < RTWN8723BE_TX_QUEUE_COUNT; i++)
        rtwn8723be_f16_1_tx_ring_free(sc->sc_dmat,
            &sc->sc_tx_ring[i]);

    sc->sc_rings_allocated = false;
}

int
rtwn8723be_netbsd_init_pci_rings(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    unsigned int i;
    int error;

    if (!sc->sc_dma_32bit || sc->sc_dmat == NULL)
        return ENXIO;
    if (sc->sc_rings_allocated)
        return 0;

    for (i = 0; i < RTWN8723BE_RX_QUEUE_COUNT; i++) {
        error = rtwn8723be_f16_1_rx_ring_alloc(sc->sc_dmat,
            &sc->sc_rx_ring[i], RTWN8723BE_RX_RING_COUNT);
        if (error != 0)
            goto fail;
    }

    for (i = 0; i < RTWN8723BE_TX_QUEUE_COUNT; i++) {
        error = rtwn8723be_f16_1_tx_ring_alloc(sc->sc_dmat,
            &sc->sc_tx_ring[i], rtwn8723be_netbsd_tx_ring_count(i));
        if (error != 0)
            goto fail;
    }

    sc->sc_rings_allocated = true;
    return 0;

fail:
    rtwn8723be_netbsd_free_pci_rings(sc);
    return error;
}

int
rtwn8723be_netbsd_reset_trx_ring(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    unsigned int q, i;

    if (!sc->sc_rings_allocated)
        return ENXIO;

    /*
     * Pinned Linux rtl_pci_reset_trx_ring(): rebuild both RX rings with
     * their existing DMA buffers, restore OWN/EOR, then empty all TX queues
     * and return every producer/consumer index to zero.
     */
    for (q = 0; q < RTWN8723BE_RX_QUEUE_COUNT; q++) {
        struct rtwn8723be_rx_ring *ring = &sc->sc_rx_ring[q];
        struct rtwn8723be_rx_desc *desc = ring->desc_dma.kva;

        rtwn8723be_f16_1_dma_sync_for_cpu(sc->sc_dmat,
            &ring->desc_dma, 0, ring->desc_dma.size);
        memset(desc, 0, ring->desc_dma.size);

        for (i = 0; i < ring->count; i++) {
            uint32_t d0 = RTWN8723BE_RX_BUFFER_SIZE |
                R23BE_RXD0_OWN;

            if (i == ring->count - 1)
                d0 |= R23BE_RXD0_EOR;

            if (ring->slot[i].map == NULL ||
                ring->slot[i].map->dm_nsegs != 1)
                return EIO;

            bus_dmamap_sync(sc->sc_dmat, ring->slot[i].map, 0,
                RTWN8723BE_RX_BUFFER_SIZE, BUS_DMASYNC_POSTREAD);
            bus_dmamap_sync(sc->sc_dmat, ring->slot[i].map, 0,
                RTWN8723BE_RX_BUFFER_SIZE, BUS_DMASYNC_PREREAD);

            desc[i].d[0] = htole32(d0);
            desc[i].d[6] = htole32((uint32_t)
                ring->slot[i].map->dm_segs[0].ds_addr);
        }

        ring->consumer = 0;
        rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,
            &ring->desc_dma, 0, ring->desc_dma.size);
    }

    for (q = 0; q < RTWN8723BE_TX_QUEUE_COUNT; q++) {
        struct rtwn8723be_tx_ring *ring = &sc->sc_tx_ring[q];
        struct rtwn8723be_tx_desc *desc = ring->desc_dma.kva;

        rtwn8723be_f16_1_dma_sync_for_cpu(sc->sc_dmat,
            &ring->desc_dma, 0, ring->desc_dma.size);

        for (i = 0; i < ring->count; i++) {
            bus_addr_t next;

            if (ring->slot[i].m != NULL) {
                if (ring->slot[i].map != NULL &&
                    ring->slot[i].map->dm_nsegs != 0) {
                    bus_dmamap_sync(sc->sc_dmat,
                        ring->slot[i].map, 0,
                        ring->slot[i].map->dm_mapsize,
                        BUS_DMASYNC_POSTWRITE);
                    bus_dmamap_unload(sc->sc_dmat,
                        ring->slot[i].map);
                }
                m_freem(ring->slot[i].m);
                ring->slot[i].m = NULL;
            }

            memset(&desc[i], 0, sizeof(desc[i]));
            next = ring->desc_dma.paddr +
                (bus_addr_t)(((i + 1) % ring->count) *
                sizeof(*desc));
            KASSERT(next <= (bus_addr_t)RTWN8723BE_DMA_MAXADDR);
            desc[i].d[RTWN8723BE_TX_NEXT_DESC_DW] =
                htole32((uint32_t)next);
        }

        ring->producer = 0;
        ring->consumer = 0;
        rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,
            &ring->desc_dma, 0, ring->desc_dma.size);
    }

    return 0;
}

void
rtwn8723be_netbsd_irq_set_dispatch(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_irq_dispatch *dispatch, void *dispatch_arg)
{
    if (dispatch == NULL) {
        memset(&sc->sc_irq_dispatch, 0, sizeof(sc->sc_irq_dispatch));
        sc->sc_irq_arg = NULL;
        sc->sc_irq_dispatch_ready = false;
        return;
    }

    sc->sc_irq_dispatch = *dispatch;
    sc->sc_irq_arg = dispatch_arg;

    /*
     * Linux enables IRQ only after the rings and RX path exist.
     * Require both packet directions before allowing HIMR/HIMRE on.
     */
    sc->sc_irq_dispatch_ready =
        sc->sc_irq_dispatch.rx != NULL &&
        sc->sc_irq_dispatch.tx_done != NULL;
}

int
rtwn8723be_netbsd_establish_irq(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    const char *intrstr;
    char intrbuf[PCI_INTRSTR_LEN];

    if (sc->sc_ih != NULL)
        return 0;

    sc->sc_soft_ih = softint_establish(SOFTINT_NET,
        rtwn8723be_netbsd_softintr, sc);
    if (sc->sc_soft_ih == NULL)
        return ENOMEM;

    if (pci_intr_alloc(&sc->sc_pa, &sc->sc_pihp, NULL, 0) != 0) {
        softint_disestablish(sc->sc_soft_ih);
        sc->sc_soft_ih = NULL;
        return ENXIO;
    }

    intrstr = pci_intr_string(sc->sc_pc, sc->sc_pihp[0], intrbuf,
        sizeof(intrbuf));
    sc->sc_ih = pci_intr_establish_xname(sc->sc_pc, sc->sc_pihp[0],
        IPL_NET, rtwn8723be_netbsd_intr, sc, device_xname(sc->sc_dev));
    if (sc->sc_ih == NULL) {
        pci_intr_release(sc->sc_pc, sc->sc_pihp, 1);
        sc->sc_pihp = NULL;
        softint_disestablish(sc->sc_soft_ih);
        sc->sc_soft_ih = NULL;
        return ENXIO;
    }

    if (intrstr != NULL)
        aprint_normal_dev(sc->sc_dev, "interrupting at %s\n", intrstr);

    return 0;
}

void
rtwn8723be_netbsd_disestablish_irq(struct rtwn8723be_softc *sc)
{
    (void)rtwn8723be_netbsd_disable_interrupt(sc);

    if (sc->sc_ih != NULL) {
        pci_intr_disestablish(sc->sc_pc, sc->sc_ih);
        sc->sc_ih = NULL;
    }
    if (sc->sc_pihp != NULL) {
        pci_intr_release(sc->sc_pc, sc->sc_pihp, 1);
        sc->sc_pihp = NULL;
    }
    if (sc->sc_soft_ih != NULL) {
        softint_disestablish(sc->sc_soft_ih);
        sc->sc_soft_ih = NULL;
    }
}

int
rtwn8723be_netbsd_enable_interrupt(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    if (!sc->sc_mapped || sc->sc_ih == NULL)
        return ENXIO;
    if (!sc->sc_irq_dispatch_ready)
        return EAGAIN;

    /* Exact RTL8723BE Linux ordering: HIMR, HIMRE, then HSIMR. */
    rtwn8723be_write_4(sc, R23BE_REG_HIMR, sc->sc_irq_mask[0]);
    rtwn8723be_write_4(sc, R23BE_REG_HIMRE, sc->sc_irq_mask[1]);
    sc->sc_irq_enabled = true;
    rtwn8723be_write_4(sc, R23BE_REG_HSIMR, sc->sc_sys_irq_mask);
    return 0;
}

int
rtwn8723be_netbsd_disable_interrupt(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    if (!sc->sc_mapped) {
        sc->sc_irq_enabled = false;
        return 0;
    }

    /* Linux rtl8723be_disable_interrupt() masks HIMR and HIMRE only. */
    rtwn8723be_write_4(sc, R23BE_REG_HIMR, 0);
    rtwn8723be_write_4(sc, R23BE_REG_HIMRE, 0);
    sc->sc_irq_enabled = false;
    return 0;
}

static int
rtwn8723be_netbsd_intr(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint32_t rawa, rawb, inta, intb;

    if (!sc->sc_irq_enabled)
        return 0;

    /*
     * Linux _rtl_pci_interrupt(): mask first, then recognize/ACK.
     * Keep the hardware quiet until SOFTINT_NET finishes processing.
     */
    (void)rtwn8723be_netbsd_disable_interrupt(sc);

    rawa = rtwn8723be_read_4(sc, R23BE_REG_HISR);
    rawb = rtwn8723be_read_4(sc, R23BE_REG_HISRE);

    if (rawa == 0xffffffffU || rawb == 0xffffffffU) {
        (void)rtwn8723be_netbsd_enable_interrupt(sc);
        return 0;
    }

    inta = rawa & sc->sc_irq_mask[0];
    intb = rawb & sc->sc_irq_mask[1];

    if (inta != 0)
        rtwn8723be_write_4(sc, R23BE_REG_HISR, inta);
    if (intb != 0)
        rtwn8723be_write_4(sc, R23BE_REG_HISRE, intb);

    /* Linux treats an empty INTA as a shared/non-device IRQ. */
    if (inta == 0 || inta == 0xffffU) {
        (void)rtwn8723be_netbsd_enable_interrupt(sc);
        return 0;
    }

    sc->sc_irq_pending[0] |= inta;
    sc->sc_irq_pending[1] |= intb;
    softint_schedule(sc->sc_soft_ih);
    return 1;
}

static void
rtwn8723be_netbsd_softintr(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint32_t inta, intb;
    uint8_t hsisr;

    /*
     * Device IRQs remain masked while this snapshot is consumed, so no
     * additional device interrupt can race these pending words.
     */
    inta = sc->sc_irq_pending[0];
    intb = sc->sc_irq_pending[1];
    sc->sc_irq_pending[0] = 0;
    sc->sc_irq_pending[1] = 0;

    if ((inta & (R23BE_IMR_ROK | R23BE_IMR_RDU)) != 0 ||
        (intb & R23BE_IMR_RXFOVW) != 0)
        sc->sc_irq_dispatch.rx(sc->sc_irq_arg);

    if ((inta & R23BE_IMR_MGNTDOK) != 0)
        sc->sc_irq_dispatch.tx_done(sc->sc_irq_arg,
            RTWN8723BE_MGNT_QUEUE);
    if ((inta & R23BE_IMR_HIGHDOK) != 0)
        sc->sc_irq_dispatch.tx_done(sc->sc_irq_arg,
            RTWN8723BE_HIGH_QUEUE);
    if ((inta & R23BE_IMR_BKDOK) != 0)
        sc->sc_irq_dispatch.tx_done(sc->sc_irq_arg,
            RTWN8723BE_BK_QUEUE);
    if ((inta & R23BE_IMR_BEDOK) != 0)
        sc->sc_irq_dispatch.tx_done(sc->sc_irq_arg,
            RTWN8723BE_BE_QUEUE);
    if ((inta & R23BE_IMR_VIDOK) != 0)
        sc->sc_irq_dispatch.tx_done(sc->sc_irq_arg,
            RTWN8723BE_VI_QUEUE);
    if ((inta & R23BE_IMR_VODOK) != 0)
        sc->sc_irq_dispatch.tx_done(sc->sc_irq_arg,
            RTWN8723BE_VO_QUEUE);

    /*
     * Linux _rtl_pci_hs_interrupt() handles this only for 8188EE/8723BE:
     * write HSISR with (current status | sys_irq_mask) to clear W1C bits.
     */
    if ((inta & R23BE_IMR_HSISR_IND_ON_INT) != 0) {
        hsisr = rtwn8723be_read_1(sc, R23BE_REG_HSISR);
        rtwn8723be_write_1(sc, R23BE_REG_HSISR,
            hsisr | (uint8_t)sc->sc_sys_irq_mask);
        if (sc->sc_irq_dispatch.power_event != NULL)
            sc->sc_irq_dispatch.power_event(sc->sc_irq_arg);
    }

    /*
     * C2HCMD is present in the RTL8723BE mask, but pinned Linux pci.c
     * dispatches its firmware workqueue only for RTL8723AE.  Do not invent
     * a 8723BE C2H callback here.
     */

    (void)rtwn8723be_netbsd_enable_interrupt(sc);
}

static int
rtwn8723be_netbsd_pcie_lcsr(struct rtwn8723be_softc *sc, uint32_t *value)
{
    if (!sc->sc_pcie_cap_valid) {
        if (!pci_get_capability(sc->sc_pc, sc->sc_tag,
            PCI_CAP_PCIEXPRESS, &sc->sc_pcie_cap_off, NULL))
            return ENODEV;
        sc->sc_pcie_cap_valid = true;
    }

    *value = pci_conf_read(sc->sc_pc, sc->sc_tag,
        sc->sc_pcie_cap_off + PCIE_LCSR);
    return 0;
}

int
rtwn8723be_netbsd_init_aspm(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint32_t lcsr;
    int error;

    error = rtwn8723be_netbsd_pcie_lcsr(sc, &lcsr);
    if (error != 0)
        return error;

    /*
     * Pinned Linux rtl8723be_init_aspm_vars() selects const_pci_aspm=3:
     * ASPM is kept enabled from initialization to halt, with Clock Request.
     * Preserve the complete original LCSR for audit/recovery while changing
     * only the device Link Control bits used by rtlwifi.
     */
    sc->sc_pcie_lcsr_initial = lcsr;
    lcsr |= PCIE_LCSR_ASPM_L0S | PCIE_LCSR_ASPM_L1 |
        PCIE_LCSR_COMCLKCFG | PCIE_LCSR_ENCLKPM;
    pci_conf_write(sc->sc_pc, sc->sc_tag,
        sc->sc_pcie_cap_off + PCIE_LCSR, lcsr);
    return 0;
}

int
rtwn8723be_netbsd_disable_aspm(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint32_t lcsr;
    int error;

    error = rtwn8723be_netbsd_pcie_lcsr(sc, &lcsr);
    if (error != 0)
        return error;

    /*
     * Linux __rtl_pci_disable_aspm(): clear Clock Request first, then L0s/L1.
     * The 8723BE path keeps Common Clock Configuration asserted.
     */
    lcsr &= ~PCIE_LCSR_ENCLKPM;
    pci_conf_write(sc->sc_pc, sc->sc_tag,
        sc->sc_pcie_cap_off + PCIE_LCSR, lcsr);

    lcsr &= ~(PCIE_LCSR_ASPM_L0S | PCIE_LCSR_ASPM_L1);
    lcsr |= PCIE_LCSR_COMCLKCFG;
    pci_conf_write(sc->sc_pc, sc->sc_tag,
        sc->sc_pcie_cap_off + PCIE_LCSR, lcsr);
    return 0;
}

int
rtwn8723be_netbsd_enable_aspm(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint32_t lcsr;
    int error;

    error = rtwn8723be_netbsd_pcie_lcsr(sc, &lcsr);
    if (error != 0)
        return error;

    /*
     * Linux rtl_pci_enable_aspm(): device ASPM L0s/L1 + Common Clock,
     * followed by Clock Request for the const_pci_aspm=3 policy.
     */
    lcsr |= PCIE_LCSR_ASPM_L0S | PCIE_LCSR_ASPM_L1 |
        PCIE_LCSR_COMCLKCFG;
    pci_conf_write(sc->sc_pc, sc->sc_tag,
        sc->sc_pcie_cap_off + PCIE_LCSR, lcsr);

    lcsr |= PCIE_LCSR_ENCLKPM;
    pci_conf_write(sc->sc_pc, sc->sc_tag,
        sc->sc_pcie_cap_off + PCIE_LCSR, lcsr);
    delay(100);
    return 0;
}

static void
rtwn8723be_netbsd_led0_on(struct rtwn8723be_softc *sc)
{
    uint8_t ledcfg;

    ledcfg = rtwn8723be_read_1(sc, R23BE_REG_LEDCFG2);
    ledcfg &= ~(1U << 6);
    rtwn8723be_write_1(sc, R23BE_REG_LEDCFG2,
        (ledcfg & 0xf0) | (1U << 5));
}

static void
rtwn8723be_netbsd_led0_off(struct rtwn8723be_softc *sc)
{
    uint8_t ledcfg;

    ledcfg = rtwn8723be_read_1(sc, R23BE_REG_LEDCFG2);
    ledcfg &= 0xf0;

    if (sc->sc_led_opendrain) {
        ledcfg &= 0x90;
        rtwn8723be_write_1(sc, R23BE_REG_LEDCFG2,
            ledcfg | (1U << 3));
        ledcfg = rtwn8723be_read_1(sc, R23BE_REG_MAC_PINMUX_CFG);
        rtwn8723be_write_1(sc, R23BE_REG_MAC_PINMUX_CFG,
            ledcfg & 0xfe);
    } else {
        ledcfg &= ~(1U << 6);
        rtwn8723be_write_1(sc, R23BE_REG_LEDCFG2,
            ledcfg | (1U << 3) | (1U << 5));
    }
}

static void
rtwn8723be_netbsd_refresh_led_state(struct rtwn8723be_softc *sc)
{
    if (sc->sc_up_first_time)
        return;

    /* Linux: RF_CHANGE_BY_INIT==0, RF_CHANGE_BY_IPS==BIT(28). */
    if (sc->sc_rfoff_reason == 0 ||
        sc->sc_rfoff_reason == (1U << 28))
        rtwn8723be_netbsd_led0_on(sc);
    else
        rtwn8723be_netbsd_led0_off(sc);
}

int
rtwn8723be_netbsd_bt_power_on_setting(struct rtwn8723be_softc *sc)
{
    uint16_t value16;
    uint8_t local = 0;

    if (!sc->sc_btcoexist)
        return 0;
    if (!sc->sc_bt_ant_valid)
        return ENXIO;
    if (sc->sc_btdm_ant_num != RTWN8723BE_ANT_X1 &&
        sc->sc_btdm_ant_num != RTWN8723BE_ANT_X2)
        return EINVAL;
    if (sc->sc_single_ant_path > 1)
        return EINVAL;

    /*
     * Pinned Linux 8723B coexistence power-on common prefix.
     */
    rtwn8723be_write_1(sc, 0x0067, 0x20);
    value16 = rtwn8723be_read_2(sc, R23BE_REG_SYS_FUNC_EN);
    rtwn8723be_write_2(sc, R23BE_REG_SYS_FUNC_EN, value16 | 0x0003);

    if (sc->sc_btdm_ant_num == RTWN8723BE_ANT_X1) {
        sc->sc_bt_stop_coex_dm = true;

        /* GRANT_BT=1 and WLAN_ACT=0 from ex_btc8723b1ant_power_on_setting. */
        rtwn8723be_write_1(sc, 0x0765, 0x18);
        rtwn8723be_write_1(sc, 0x076e, 0x04);

        if (sc->sc_single_ant_path == 0) {
            rtwn8723be_write_4(sc, 0x0948, 0x00000280U);
            sc->sc_btdm_ant_pos = RTWN8723BE_ANT_MAIN;
            sc->sc_ant_pos_registry_ctrl = 1;
        } else {
            rtwn8723be_write_4(sc, 0x0948, 0x00000000U);
            local |= 0x01;
            sc->sc_btdm_ant_pos = RTWN8723BE_ANT_AUX;
            sc->sc_ant_pos_registry_ctrl = 0;
        }

        /* PCI local register write in Linux maps to normal MMIO byte access. */
        rtwn8723be_write_1(sc, 0x0384, local);
        return 0;
    }

    /*
     * Two-antenna power-on uses S0 here; the antenna-count/local-register
     * byte is completed by ex_btc8723b2ant_pre_load_firmware().
     */
    rtwn8723be_write_4(sc, 0x0948, 0x00000000U);
    sc->sc_btdm_ant_pos = sc->sc_single_ant_path == 0 ?
        RTWN8723BE_ANT_MAIN : RTWN8723BE_ANT_AUX;
    sc->sc_ant_pos_registry_ctrl = 0;
    return 0;
}

int
rtwn8723be_netbsd_bt_preload_firmware(struct rtwn8723be_softc *sc)
{
    uint8_t local;

    if (!sc->sc_btcoexist ||
        sc->sc_btdm_ant_num != RTWN8723BE_ANT_X2)
        return 0;
    if (!sc->sc_bt_ant_valid || sc->sc_single_ant_path > 1)
        return ENXIO;

    /*
     * Pinned Linux ex_btc8723b2ant_pre_load_firmware(), PCI branch.
     * BIT2 advertises two antennas; BIT0 selects the inverse/S0 path.
     */
    local = 0x04;
    if (sc->sc_single_ant_path == 1)
        local |= 0x01;
    rtwn8723be_write_1(sc, 0x0384, local);
    return 0;
}

static int
rtwn8723be_netbsd_llt_write(struct rtwn8723be_softc *sc,
    uint8_t address, uint8_t data)
{
    uint32_t value;
    unsigned int n;

    value = (uint32_t)data |
        ((uint32_t)address << 8) |
        ((uint32_t)R23BE_LLT_WRITE_ACCESS << 30);
    rtwn8723be_write_4(sc, R23BE_REG_LLT_INIT, value);

    for (n = 0; n <= R23BE_LLT_POLL_MAX; n++) {
        value = rtwn8723be_read_4(sc, R23BE_REG_LLT_INIT);
        if (((value >> 30) & 0x3U) == R23BE_LLT_NO_ACTIVE)
            return 0;
    }

    return ETIMEDOUT;
}

static int
rtwn8723be_netbsd_llt_table_init(struct rtwn8723be_softc *sc)
{
    const uint8_t txpktbuf_bndy = 245;
    const uint8_t maxpage = 255;
    unsigned int i;
    int error;

    /*
     * Exact pinned-Linux _rtl8723be_llt_table_init() register order.
     */
    rtwn8723be_write_4(sc, R23BE_REG_TRXFF_BNDY,
        0x27ff0000U | txpktbuf_bndy);
    rtwn8723be_write_1(sc, R23BE_REG_TDECTRL + 1, txpktbuf_bndy);
    rtwn8723be_write_1(sc, R23BE_REG_TXPKTBUF_BCNQ_BDNY, txpktbuf_bndy);
    rtwn8723be_write_1(sc, R23BE_REG_TXPKTBUF_MGQ_BDNY, txpktbuf_bndy);
    rtwn8723be_write_1(sc, R23BE_REG_TXPKTBUF_WMAC_LBK_BF_HD,
        txpktbuf_bndy);
    rtwn8723be_write_1(sc, R23BE_REG_PBP, 0x31);
    rtwn8723be_write_1(sc, R23BE_REG_RX_DRVINFO_SZ, 0x04);

    for (i = 0; i < (unsigned int)txpktbuf_bndy - 1; i++) {
        error = rtwn8723be_netbsd_llt_write(sc, (uint8_t)i,
            (uint8_t)(i + 1));
        if (error != 0)
            return error;
    }

    error = rtwn8723be_netbsd_llt_write(sc,
        (uint8_t)(txpktbuf_bndy - 1), 0xff);
    if (error != 0)
        return error;

    for (i = txpktbuf_bndy; i < maxpage; i++) {
        error = rtwn8723be_netbsd_llt_write(sc, (uint8_t)i,
            (uint8_t)(i + 1));
        if (error != 0)
            return error;
    }

    error = rtwn8723be_netbsd_llt_write(sc, maxpage, txpktbuf_bndy);
    if (error != 0)
        return error;

    rtwn8723be_write_4(sc, R23BE_REG_RQPN, 0x80e40808U);
    rtwn8723be_write_1(sc, R23BE_REG_RQPN_NPQ, 0x00);
    return 0;
}

static int
rtwn8723be_netbsd_program_ring_bases(struct rtwn8723be_softc *sc)
{
    if (!sc->sc_rings_allocated)
        return ENXIO;

#define R23BE_RING_ADDR(_addr) do { \
    if ((_addr) > (bus_addr_t)RTWN8723BE_DMA_MAXADDR) \
        return EFBIG; \
} while (0)

    R23BE_RING_ADDR(sc->sc_tx_ring[RTWN8723BE_BEACON_QUEUE].desc_dma.paddr);
    R23BE_RING_ADDR(sc->sc_tx_ring[RTWN8723BE_MGNT_QUEUE].desc_dma.paddr);
    R23BE_RING_ADDR(sc->sc_tx_ring[RTWN8723BE_VO_QUEUE].desc_dma.paddr);
    R23BE_RING_ADDR(sc->sc_tx_ring[RTWN8723BE_VI_QUEUE].desc_dma.paddr);
    R23BE_RING_ADDR(sc->sc_tx_ring[RTWN8723BE_BE_QUEUE].desc_dma.paddr);
    R23BE_RING_ADDR(sc->sc_tx_ring[RTWN8723BE_BK_QUEUE].desc_dma.paddr);
    R23BE_RING_ADDR(sc->sc_tx_ring[RTWN8723BE_HIGH_QUEUE].desc_dma.paddr);
    R23BE_RING_ADDR(sc->sc_rx_ring[RTWN8723BE_RX_MPDU_QUEUE].desc_dma.paddr);

    rtwn8723be_write_4(sc, R23BE_REG_BCNQ_DESA,
        (uint32_t)sc->sc_tx_ring[RTWN8723BE_BEACON_QUEUE].desc_dma.paddr);
    rtwn8723be_write_4(sc, R23BE_REG_MGQ_DESA,
        (uint32_t)sc->sc_tx_ring[RTWN8723BE_MGNT_QUEUE].desc_dma.paddr);
    rtwn8723be_write_4(sc, R23BE_REG_VOQ_DESA,
        (uint32_t)sc->sc_tx_ring[RTWN8723BE_VO_QUEUE].desc_dma.paddr);
    rtwn8723be_write_4(sc, R23BE_REG_VIQ_DESA,
        (uint32_t)sc->sc_tx_ring[RTWN8723BE_VI_QUEUE].desc_dma.paddr);
    rtwn8723be_write_4(sc, R23BE_REG_BEQ_DESA,
        (uint32_t)sc->sc_tx_ring[RTWN8723BE_BE_QUEUE].desc_dma.paddr);
    rtwn8723be_write_4(sc, R23BE_REG_BKQ_DESA,
        (uint32_t)sc->sc_tx_ring[RTWN8723BE_BK_QUEUE].desc_dma.paddr);
    rtwn8723be_write_4(sc, R23BE_REG_HQ_DESA,
        (uint32_t)sc->sc_tx_ring[RTWN8723BE_HIGH_QUEUE].desc_dma.paddr);
    rtwn8723be_write_4(sc, R23BE_REG_RX_DESA,
        (uint32_t)sc->sc_rx_ring[RTWN8723BE_RX_MPDU_QUEUE].desc_dma.paddr);

#undef R23BE_RING_ADDR
    return 0;
}

int
rtwn8723be_netbsd_init_mac(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint16_t wordtmp;
    uint8_t bytetmp;
    int error;

    /*
     * Preflight before the first hardware mutation.  Linux has already
     * populated coexistence/EFUSE and PCI rings by this point.
     */
    if (!sc->sc_mapped || !sc->sc_rings_allocated)
        return ENXIO;
    if (sc->sc_btcoexist && !sc->sc_bt_ant_valid)
        return ENXIO;

    rtwn8723be_write_1(sc, R23BE_REG_RSV_CTRL, 0x00);

    bytetmp = rtwn8723be_read_1(sc, R23BE_REG_APS_FSMCO + 1);
    rtwn8723be_write_1(sc, R23BE_REG_APS_FSMCO + 1,
        bytetmp & ~(1U << 7));

    /*
     * _rtl8723be_init_mac() uses RTL8723_NIC_ENABLE_FLOW:
     * CARDDIS -> CARDEMU -> ACT, not the shorter power-on flow.
     */
    error = rtwn8723be_pwrseq_flow_exec(sc->sc_st, sc->sc_sh,
        RTWN8723BE_PWR_FLOW_CARD_ENABLE, RTWN8723BE_PWR_CUT_ALL,
        RTWN8723BE_PWR_FAB_ALL, RTWN8723BE_PWR_INTF_PCI);
    if (error != 0)
        return error;

    error = rtwn8723be_netbsd_bt_power_on_setting(sc);
    if (error != 0)
        return error;

    bytetmp = rtwn8723be_read_1(sc, R23BE_REG_MULTI_FUNC_CTRL);
    rtwn8723be_write_1(sc, R23BE_REG_MULTI_FUNC_CTRL,
        bytetmp | (1U << 3));

    bytetmp = rtwn8723be_read_1(sc, R23BE_REG_APS_FSMCO);
    rtwn8723be_write_1(sc, R23BE_REG_APS_FSMCO,
        bytetmp | (1U << 4));

    rtwn8723be_write_1(sc, R23BE_REG_CR, 0xff);
    delay(2000);

    bytetmp = rtwn8723be_read_1(sc, R23BE_REG_HWSEQ_CTRL);
    rtwn8723be_write_1(sc, R23BE_REG_HWSEQ_CTRL,
        bytetmp | 0x7f);
    delay(2000);

    bytetmp = rtwn8723be_read_1(sc, R23BE_REG_SYS_CFG + 3);
    if ((bytetmp & (1U << 0)) != 0) {
        bytetmp = rtwn8723be_read_1(sc, R23BE_REG_XCK_OUT_CTRL);
        rtwn8723be_write_1(sc, R23BE_REG_XCK_OUT_CTRL,
            bytetmp | (1U << 6));
    }

    bytetmp = rtwn8723be_read_1(sc, R23BE_REG_SYS_CLKR);
    rtwn8723be_write_1(sc, R23BE_REG_SYS_CLKR,
        bytetmp | (1U << 3));

    bytetmp = rtwn8723be_read_1(sc, R23BE_REG_GPIO_MUXCFG + 1);
    rtwn8723be_write_1(sc, R23BE_REG_GPIO_MUXCFG + 1,
        bytetmp & ~(1U << 4));

    rtwn8723be_write_2(sc, R23BE_REG_CR, 0x02ff);

    if (!sc->sc_linux.mac_func_enable) {
        error = rtwn8723be_netbsd_llt_table_init(sc);
        if (error != 0)
            return error;
    }

    rtwn8723be_write_4(sc, R23BE_REG_HISR, 0xffffffffU);
    rtwn8723be_write_4(sc, R23BE_REG_HISRE, 0xffffffffU);

    bytetmp = rtwn8723be_read_1(sc, R23BE_REG_FWIMR + 3);
    rtwn8723be_write_1(sc, R23BE_REG_FWIMR + 3,
        bytetmp | (1U << 6));

    wordtmp = rtwn8723be_read_2(sc, R23BE_REG_TRXDMA_CTRL);
    wordtmp &= 0x000f;
    wordtmp |= 0xf5b1;
    rtwn8723be_write_2(sc, R23BE_REG_TRXDMA_CTRL, wordtmp);

    rtwn8723be_write_1(sc, R23BE_REG_FWHW_TXQ_CTRL + 1, 0x1f);
    rtwn8723be_write_4(sc, R23BE_REG_RCR, sc->sc_receive_config);
    rtwn8723be_write_2(sc, R23BE_REG_RXFLTMAP2, 0xffff);
    rtwn8723be_write_4(sc, R23BE_REG_TCR, sc->sc_transmit_config);

    error = rtwn8723be_netbsd_program_ring_bases(sc);
    if (error != 0)
        return error;

    bytetmp = rtwn8723be_read_1(sc, R23BE_REG_PCIE_CTRL_REG + 3);
    rtwn8723be_write_1(sc, R23BE_REG_PCIE_CTRL_REG + 3,
        bytetmp | 0x77);

    rtwn8723be_write_4(sc, R23BE_REG_INT_MIG, 0);
    rtwn8723be_write_4(sc, R23BE_REG_MCUTST_1, 0);
    rtwn8723be_write_1(sc, R23BE_REG_SECONDARY_CCA_CTRL, 0x03);

    /*
     * DPDT/fixed-board BB settings copied verbatim from pinned Linux.
     */
    rtwn8723be_netbsd_set_bbreg(sc, 0x0064, (1U << 20), 0);
    rtwn8723be_netbsd_set_bbreg(sc, 0x0064, (1U << 24), 0);
    rtwn8723be_netbsd_set_bbreg(sc, 0x0040, (1U << 4), 0);
    rtwn8723be_netbsd_set_bbreg(sc, 0x0040, (1U << 3), 1);
    rtwn8723be_netbsd_set_bbreg(sc, 0x004c,
        (1U << 24) | (1U << 23), 2);
    rtwn8723be_netbsd_set_bbreg(sc, 0x0944,
        (1U << 1) | (1U << 0), 3);
    rtwn8723be_netbsd_set_bbreg(sc, 0x0930, 0x000000ffU, 0x77);
    rtwn8723be_netbsd_set_bbreg(sc, 0x0038, (1U << 11), 1);

    bytetmp = rtwn8723be_read_1(sc, R23BE_REG_RXDMA_CONTROL);
    rtwn8723be_write_1(sc, R23BE_REG_RXDMA_CONTROL,
        bytetmp & ~R23BE_RXDMA_PAUSE);

    rtwn8723be_netbsd_refresh_led_state(sc);
    return 0;
}

int
rtwn8723be_netbsd_poweroff_adapter(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint8_t tmp;
    int error;

    if (!sc->sc_mapped)
        return ENXIO;
    sc->sc_linux.mac_func_enable = false;

    /*
     * Pinned Linux _rtl8723be_poweroff_adapter():
     * first enter the RTL8723B LPS/RF-off flow.
     */
    error = rtwn8723be_pwrseq_flow_exec(sc->sc_st, sc->sc_sh,
        RTWN8723BE_PWR_FLOW_ENTER_LPS, RTWN8723BE_PWR_CUT_ALL,
        RTWN8723BE_PWR_FAB_ALL, RTWN8723BE_PWR_INTF_PCI);
    if (error != 0)
        return error;

    /*
     * Linux self-resets firmware only when RAM firmware is selected and
     * firmware had reached the ready state.
     */
    if ((rtwn8723be_read_1(sc, R23BE_REG_MCUFWDL) &
        R23BE_MCUFWDL_RAM_DL_SEL) != 0 && sc->sc_linux.fw_ready)
        rtwn8723be_fw_selfreset(sc->sc_st, sc->sc_sh);

    /* Reset MCU and clear the firmware-ready state. */
    tmp = rtwn8723be_read_1(sc, R23BE_REG_SYS_FUNC_EN + 1);
    rtwn8723be_write_1(sc, R23BE_REG_SYS_FUNC_EN + 1,
        tmp & ~(1U << 2));
    rtwn8723be_write_1(sc, R23BE_REG_MCUFWDL, 0);
    sc->sc_linux.fw_ready = false;

    /* Hardware card-disable power flow: ACT -> CARDEMU -> CARDDIS. */
    error = rtwn8723be_pwrseq_flow_exec(sc->sc_st, sc->sc_sh,
        RTWN8723BE_PWR_FLOW_CARD_DISABLE, RTWN8723BE_PWR_CUT_ALL,
        RTWN8723BE_PWR_FAB_ALL, RTWN8723BE_PWR_INTF_PCI);
    if (error != 0)
        return error;

    /* Reset MCU I/O wrapper, then lock ISO/CLK/power control. */
    tmp = rtwn8723be_read_1(sc, R23BE_REG_RSV_CTRL + 1);
    rtwn8723be_write_1(sc, R23BE_REG_RSV_CTRL + 1,
        tmp & ~(1U << 0));
    tmp = rtwn8723be_read_1(sc, R23BE_REG_RSV_CTRL + 1);
    rtwn8723be_write_1(sc, R23BE_REG_RSV_CTRL + 1,
        tmp | (1U << 0));
    rtwn8723be_write_1(sc, R23BE_REG_RSV_CTRL, 0x0e);

    return 0;
}

int
rtwn8723be_netbsd_sys_cfg_clear_bit7(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint8_t value;

    if (!sc->sc_mapped)
        return ENXIO;

    /*
     * Pinned Linux rtl8723be_hw_init(): immediately after _init_mac(),
     * clear SYS_CFG bit 7 before the firmware transfer starts.
     */
    value = rtwn8723be_read_1(sc, R23BE_REG_SYS_CFG);
    rtwn8723be_write_1(sc, R23BE_REG_SYS_CFG, value & 0x7f);
    return 0;
}

int
rtwn8723be_netbsd_download_firmware(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    firmware_handle_t fwh = NULL;
    uint8_t hdr[R23BE_FW_HEADER_SIZE];
    uint8_t *payload = NULL;
    off_t fwsize;
    size_t payload_len;
    uint16_t signature, ramcodesize;
    int error;

    if (!sc->sc_mapped)
        return ENXIO;

    error = firmware_open(RTWN8723BE_FIRMWARE_DRIVER,
        RTWN8723BE_FIRMWARE_FILE, &fwh);
    if (error != 0)
        return error;

    fwsize = firmware_get_size(fwh);
    if (fwsize < (off_t)R23BE_FW_HEADER_SIZE) {
        error = EINVAL;
        goto out;
    }

    payload_len = (size_t)fwsize - R23BE_FW_HEADER_SIZE;
    if (payload_len == 0 ||
        payload_len > (size_t)R23BE_FW_MAX_PAGES * R23BE_FW_PAGE_SIZE) {
        error = EFBIG;
        goto out;
    }

    error = firmware_read(fwh, 0, hdr, sizeof(hdr));
    if (error != 0)
        goto out;

    signature = (uint16_t)hdr[0] | ((uint16_t)hdr[1] << 8);
    ramcodesize = (uint16_t)hdr[12] | ((uint16_t)hdr[13] << 8);
    if ((signature & 0xfff0U) != 0x5300U ||
        (size_t)ramcodesize != payload_len) {
        error = EINVAL;
        goto out;
    }

    payload = kmem_alloc(payload_len, KM_SLEEP);
    error = firmware_read(fwh, R23BE_FW_HEADER_SIZE, payload, payload_len);
    if (error != 0)
        goto out;

    error = rtwn8723be_netbsd_bt_preload_firmware(sc);
    if (error != 0)
        goto out;

    /*
     * rtwn8723be_fw_download() preserves the pinned Linux transfer
     * semantics: RAM_DL_SEL recovery, page upload, checksum polling,
     * MCUFWDL_RDY, MCU self-reset and WINTINI_RDY handshake.
     */
    error = rtwn8723be_fw_download(sc->sc_st, sc->sc_sh,
        payload, payload_len);

out:
    if (payload != NULL)
        kmem_free(payload, payload_len);
    if (fwh != NULL)
        firmware_close(fwh);
    return error;
}

int
rtwn8723be_netbsd_read_cr(void *arg, uint8_t *value)
{
    struct rtwn8723be_softc *sc = arg;

    if (value == NULL || !sc->sc_mapped)
        return EINVAL;

    *value = rtwn8723be_read_1(sc, R23BE_REG_CR);
    return 0;
}

int
rtwn8723be_netbsd_check_pcie_dma_hang(void *arg, bool *hung)
{
    struct rtwn8723be_softc *sc = arg;
    uint8_t tmp;

    if (hung == NULL || !sc->sc_mapped)
        return EINVAL;

    /*
     * Pinned Linux _rtl8723be_check_pcie_dma_hang():
     * DBI_CTRL+3 bit 2 enables the debug port.  After the required 100 ms
     * settle delay, bits 0/1 report RX/TX PCIe DMA hang respectively.
     */
    tmp = rtwn8723be_read_1(sc, R23BE_REG_DBI_CTRL + 3);
    if ((tmp & (1U << 2)) == 0) {
        rtwn8723be_write_1(sc, R23BE_REG_DBI_CTRL + 3,
            tmp | (1U << 2));
        delay(100000);
    }

    tmp = rtwn8723be_read_1(sc, R23BE_REG_DBI_CTRL + 3);
    *hung = (tmp & ((1U << 0) | (1U << 1))) != 0;
    return 0;
}

int
rtwn8723be_netbsd_reset_pcie_interface_dma(void *arg, bool mac_power_on)
{
    struct rtwn8723be_softc *sc = arg;
    bool release_mac_rx_pause;
    uint8_t backup_pcie_dma_pause;
    uint8_t tmp;

    if (!sc->sc_mapped)
        return ENXIO;

    /* 1. Disable the RTL8723BE system-register write lock. */
    tmp = rtwn8723be_read_1(sc, R23BE_REG_RSV_CTRL);
    tmp &= ~((1U << 1) | (1U << 0));
    rtwn8723be_write_1(sc, R23BE_REG_RSV_CTRL, tmp);

    tmp = rtwn8723be_read_1(sc, R23BE_REG_PMC_DBG_CTRL2);
    tmp |= (1U << 2);
    rtwn8723be_write_1(sc, R23BE_REG_PMC_DBG_CTRL2, tmp);

    /* 2. Pause RX and PCIe TRX DMA, preserving the pre-existing state. */
    tmp = rtwn8723be_read_1(sc, R23BE_REG_RXDMA_CONTROL);
    if ((tmp & R23BE_RXDMA_PAUSE) != 0) {
        release_mac_rx_pause = false;
    } else {
        rtwn8723be_write_1(sc, R23BE_REG_RXDMA_CONTROL,
            tmp | R23BE_RXDMA_PAUSE);
        release_mac_rx_pause = true;
    }

    backup_pcie_dma_pause =
        rtwn8723be_read_1(sc, R23BE_REG_PCIE_CTRL_REG + 1);
    if (backup_pcie_dma_pause != 0xff)
        rtwn8723be_write_1(sc, R23BE_REG_PCIE_CTRL_REG + 1, 0xff);

    /* 3. If MAC is live, stop TRX before toggling the PCIe DMA block. */
    if (mac_power_on)
        rtwn8723be_write_1(sc, R23BE_REG_CR, 0);

    /* 4/5. Reset then re-enable PCIe DMA through SYS_FUNC_EN+1 bit 0. */
    tmp = rtwn8723be_read_1(sc, R23BE_REG_SYS_FUNC_EN + 1);
    rtwn8723be_write_1(sc, R23BE_REG_SYS_FUNC_EN + 1,
        tmp & ~(1U << 0));
    tmp = rtwn8723be_read_1(sc, R23BE_REG_SYS_FUNC_EN + 1);
    rtwn8723be_write_1(sc, R23BE_REG_SYS_FUNC_EN + 1,
        tmp | (1U << 0));

    /* 6. Restore TRX only when it was live on entry. */
    if (mac_power_on)
        rtwn8723be_write_1(sc, R23BE_REG_CR, 0xff);

    /* 7. Restore PCIe autoload-down state: MAC_PHY_CTRL_NORMAL bit 17. */
    tmp = rtwn8723be_read_1(sc, R23BE_REG_MAC_PHY_CTRL_NORMAL + 2);
    rtwn8723be_write_1(sc, R23BE_REG_MAC_PHY_CTRL_NORMAL + 2,
        tmp | (1U << 1));

    /*
     * 8. Linux deliberately keeps DMA paused when MAC was powered on;
     * _rtl8723be_init_mac() must rebuild LLT/RQPN/descriptor addresses first.
     */
    if (!mac_power_on) {
        if (release_mac_rx_pause) {
            tmp = rtwn8723be_read_1(sc, R23BE_REG_RXDMA_CONTROL);
            rtwn8723be_write_1(sc, R23BE_REG_RXDMA_CONTROL,
                tmp & ~R23BE_RXDMA_PAUSE);
        }
        rtwn8723be_write_1(sc, R23BE_REG_PCIE_CTRL_REG + 1,
            backup_pcie_dma_pause);
    }

    /* 9. Re-lock the system register. */
    tmp = rtwn8723be_read_1(sc, R23BE_REG_PMC_DBG_CTRL2);
    rtwn8723be_write_1(sc, R23BE_REG_PMC_DBG_CTRL2,
        tmp & ~(1U << 2));

    return 0;
}

/*
 * Linux rtl8723be_phy_mac_config(): program every unconditional entry of
 * the frozen RTL8723BEMAC_1T_ARRAY in source order, then write 04ca=0b.
 * RCR postprocessing must follow this callback, never precede the table.
 */
int
rtwn8723be_netbsd_phy_mac_config(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    size_t i;

    if (!sc->sc_mapped)
        return ENXIO;
    for (i = 0; i < RTWN8723BE_MAC_TABLE_COUNT; i++)
        rtwn8723be_write_1(sc, rtwn8723be_mac_table[i].reg,
            rtwn8723be_mac_table[i].value);
    rtwn8723be_write_1(sc, 0x04ca, 0x0b);
    return 0;
}

/*
 * rtlwifi/cam.c:rtl_cam_reset_all_entry() via
 * rtl8723be/sw.c .maps[RWCAM] = REG_CAMCMD (0x0670).
 * Bits 31/30 request a full on-device CAM clear.
 */
int
rtwn8723be_netbsd_cam_reset_all(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    if (!sc->sc_mapped)
        return ENXIO;
    rtwn8723be_write_4(sc, R23BE_REG_CAMCMD, (1U << 31) | (1U << 30));
    return 0;
}

/*
 * rtl8723be/hw.c:HW_VAR_ETHER_ADDR writes all ETH_ALEN bytes to
 * REG_MACID + index in increasing order using the EFUSE-derived address.
 */
int
rtwn8723be_netbsd_set_mac_address(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    size_t i;

    if (!sc->sc_mapped || !sc->sc_efuse_autoload_ok)
        return ENXIO;
    for (i = 0; i < sizeof(sc->sc_macaddr); i++)
        rtwn8723be_write_1(sc, R23BE_REG_MACID + i, sc->sc_macaddr[i]);
    return 0;
}

/* Linux rtl8723be_hw_init: update RCR after phy_mac_config(). */
int
rtwn8723be_netbsd_rcr_postprocess(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    if (!sc->sc_mapped)
        return ENXIO;
    sc->sc_receive_config = rtwn8723be_read_4(sc, R23BE_REG_RCR);
    /* Pinned Linux rtl8723be/reg.h: RCR_ACRC32=BIT(8), RCR_AICV=BIT(9). */
    sc->sc_receive_config &= ~((1U << 8) | (1U << 9));
    rtwn8723be_write_4(sc, R23BE_REG_RCR, sc->sc_receive_config);
    return 0;
}

/* Linux rtl8723be_hw_init: ((30000 + 127) / 128) == 235. */
int
rtwn8723be_netbsd_set_nav_upper_235(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    if (!sc->sc_mapped)
        return ENXIO;
    rtwn8723be_write_1(sc, R23BE_REG_NAV_UPPER, 235);
    return 0;
}

/* Release RX DMA only after initialization and calibration have succeeded. */
int
rtwn8723be_netbsd_release_rx_dma(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint8_t value;

    if (!sc->sc_mapped)
        return ENXIO;
    value = rtwn8723be_read_1(sc, R23BE_REG_RXDMA_CONTROL);
    if (value & (1U << 2))
        rtwn8723be_write_1(sc, R23BE_REG_RXDMA_CONTROL,
            value & ~(1U << 2));
    return 0;
}

/* Pinned Linux rtl8723be_hw_init: release PCIe TX/RX DMA after RX DMA. */
int
rtwn8723be_netbsd_release_pcie_dma(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    if (!sc->sc_mapped)
        return ENXIO;
    rtwn8723be_write_1(sc, R23BE_REG_PCIE_CTRL_REG + 1, 0);
    return 0;
}

/* Linux HW_VAR_RETRY_LIMIT: short/long retries share the PCI default. */
int
rtwn8723be_netbsd_set_retry_limit(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint16_t value;

    if (!sc->sc_mapped)
        return ENXIO;
    value = ((uint16_t)sc->sc_retry_limit << 8) |
        sc->sc_retry_limit;
    rtwn8723be_write_2(sc, R23BE_REG_RETRY_LIMIT, value);
    return 0;
}

/*
 * rtlwifi/base.c:rtl_init_rx_config() reads HW_VAR_RCR, which
 * rtl8723be_get_hw_reg() supplies from rtlpci->receive_config.
 * Keep a distinct MAC copy as in Linux instead of rereading RCR MMIO.
 */
int
rtwn8723be_netbsd_init_rx_config(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    if (!sc->sc_core_initialized || !sc->sc_mapped)
        return ENXIO;
    sc->sc_mac_rx_conf = sc->sc_receive_config;
    return 0;
}

/*
 * Foundation of the full Linux probe/start state machine.  Unspecified
 * callbacks remain NULL until their exact Linux hardware semantics have been
 * ported; rtwn8723be_linux_state.c will reject such an incomplete transition
 * with ENOSYS rather than touching hardware out of order.
 */
const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops = {
    .pci_enable = rtwn8723be_netbsd_pci_enable,
    .dma_configure = rtwn8723be_netbsd_dma_configure,
    .pci_set_master = rtwn8723be_netbsd_pci_set_master,
    .alloc_softc = rtwn8723be_netbsd_alloc_softc,
    .map_bar = rtwn8723be_netbsd_map_bar,
    .pci_prepare_d0 = rtwn8723be_netbsd_pci_prepare_d0,
    .find_adapter = rtwn8723be_netbsd_find_adapter,
    .init_io = rtwn8723be_netbsd_init_io,
    .read_eeprom_info = rtwn8723be_netbsd_read_eeprom_info,
    .init_sw_vars = rtwn8723be_netbsd_init_sw_vars,
    .init_leds = rtwn8723be_netbsd_init_leds,
    .init_aspm = rtwn8723be_netbsd_init_aspm,
    .init_core = rtwn8723be_netbsd_init_core,
    .init_pci_rings = rtwn8723be_netbsd_init_pci_rings,
    .reset_trx_ring = rtwn8723be_netbsd_reset_trx_ring,
    .disable_aspm = rtwn8723be_netbsd_disable_aspm,
    .read_cr = rtwn8723be_netbsd_read_cr,
    .check_pcie_dma_hang = rtwn8723be_netbsd_check_pcie_dma_hang,
    .reset_pcie_interface_dma =
        rtwn8723be_netbsd_reset_pcie_interface_dma,
    .poweroff_adapter = rtwn8723be_netbsd_poweroff_adapter,
    .init_mac = rtwn8723be_netbsd_init_mac,
    .sys_cfg_clear_bit7 = rtwn8723be_netbsd_sys_cfg_clear_bit7,
    .download_firmware = rtwn8723be_netbsd_download_firmware,
    .phy_mac_config = rtwn8723be_netbsd_phy_mac_config,
    .rcr_postprocess = rtwn8723be_netbsd_rcr_postprocess,
    .cam_reset_all = rtwn8723be_netbsd_cam_reset_all,
    .set_mac_address = rtwn8723be_netbsd_set_mac_address,
    .set_nav_upper_235 = rtwn8723be_netbsd_set_nav_upper_235,
    .set_retry_limit = rtwn8723be_netbsd_set_retry_limit,
    .release_rx_dma = rtwn8723be_netbsd_release_rx_dma,
    .release_pcie_dma = rtwn8723be_netbsd_release_pcie_dma,
    .enable_aspm = rtwn8723be_netbsd_enable_aspm,
    .establish_irq = rtwn8723be_netbsd_establish_irq,
    .enable_interrupt = rtwn8723be_netbsd_enable_interrupt,
    .init_rx_config = rtwn8723be_netbsd_init_rx_config,
    .disable_interrupt = rtwn8723be_netbsd_disable_interrupt,
};
