#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/intr.h>
#include <sys/mbuf.h>
#include <sys/endian.h>

#include <dev/pci/pcireg.h>
#include <dev/pci/pcivar.h>
#include <dev/pci/pcidevs.h>

#include "rtwn8723be_netbsd.h"

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
    .init_pci_rings = rtwn8723be_netbsd_init_pci_rings,
    .reset_trx_ring = rtwn8723be_netbsd_reset_trx_ring,
    .establish_irq = rtwn8723be_netbsd_establish_irq,
    .enable_interrupt = rtwn8723be_netbsd_enable_interrupt,
    .disable_interrupt = rtwn8723be_netbsd_disable_interrupt,
};
