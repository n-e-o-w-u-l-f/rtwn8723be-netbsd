#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/intr.h>

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
    sc->sc_dmat = pa->pa_dmat;

    /*
     * Linux rtl8723be_mod_params leaves dma64 false, so rtl_pci_probe()
     * selects the 32-bit DMA mask/coherent mask path.
     */
    sc->sc_dma_32bit = true;

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

    if (sc->sc_dmat == NULL)
        return ENXIO;

    /*
     * NetBSD does not expose Linux dma_set_mask() on a PCI bus_dma_tag.
     * Keep the Linux 32-bit RTL8723BE contract explicit and reject any
     * descriptor/buffer mapping above 0xffffffff in the DMA layer.
     */
    sc->sc_dma_32bit = true;
    return 0;
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
    pci_set_powerstate(sc->sc_pc, sc->sc_tag, PCI_PMCSR_STATE_D0);
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
    .establish_irq = rtwn8723be_netbsd_establish_irq,
    .enable_interrupt = rtwn8723be_netbsd_enable_interrupt,
    .disable_interrupt = rtwn8723be_netbsd_disable_interrupt,
};
