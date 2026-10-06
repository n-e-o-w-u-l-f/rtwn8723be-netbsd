/* $NetBSD$ */
/*
 * Experimental native RTL8723BE PCIe entry for the full NetBSD driver.
 *
 * This is a SEPARATE opt-in attachment from the historical hardware-passive
 * F8 rtwn8723be.c entry. It selects the real NetBSD softc, callback table
 * and Linux-order lifecycle. Do not add it to GENERIC or a recovery kernel
 * until full prerequisite, rollback, detach and hardware gates are closed.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/device.h>
#include <sys/errno.h>
#include <sys/systm.h>

#include <dev/pci/pcireg.h>
#include <dev/pci/pcivar.h>
#include <dev/pci/pcidevs.h>

#include "rtwn8723be_netbsd.h"

static int
rtwn8723be_native_match(device_t parent, cfdata_t cf, void *aux)
{
    const struct pci_attach_args *pa = aux;

    (void)parent;
    (void)cf;
    return PCI_VENDOR(pa->pa_id) == PCI_VENDOR_REALTEK &&
        PCI_PRODUCT(pa->pa_id) == 0xb723;
}

/*
 * Restore a single PCI config byte without touching neighboring fields.
 * This helper is for the two config bytes the pinned rtlwifi PCI D0 path
 * overwrites (0x44 and 0x81).
 */
static void
rtwn8723be_native_restore_byte(struct rtwn8723be_softc *sc,
    int reg, uint8_t original)
{
    const int aligned = reg & ~3;
    const unsigned int shift = (unsigned int)(reg & 3) * 8;
    pcireg_t word;

    word = pci_conf_read(sc->sc_pc, sc->sc_tag, aligned);
    word &= ~((pcireg_t)0xffU << shift);
    word |= (pcireg_t)original << shift;
    pci_conf_write(sc->sc_pc, sc->sc_tag, aligned, word);
}

/*
 * Reverse the resource mutations of the CURRENT, pre-registration probe.
 * The full net80211/PHY/runtime teardown must be added BEFORE either
 * register_ieee80211 or init_rfkill may be bound to a live probe.
 *
 * In the current canonical ops table preflight returns ENOSYS at IDLE,
 * causing ZERO PCI/MMIO changes and hence no cleanup operations.
 */
static void
rtwn8723be_native_probe_cleanup(struct rtwn8723be_softc *sc)
{
    enum rtwn8723be_linux_stage stage = sc->sc_linux.stage;

    if (!sc->sc_initial_pci_saved || stage == R23BE_STAGE_IDLE)
        return;

    /*
     * A registered net80211 interface cannot be freed using the present
     * pre-registration rollback. Never quietly release resources under it.
     */
    if (stage >= R23BE_STAGE_IEEE80211_REGISTER) {
        aprint_error_dev(sc->sc_dev,
            "refusing incomplete post-registration teardown; "
            "native driver must remain disabled\n");
        return;
    }

    if (sc->sc_irq_enabled || sc->sc_ih != NULL ||
        sc->sc_soft_ih != NULL || sc->sc_pihp != NULL)
        rtwn8723be_netbsd_disestablish_irq(sc);

    /* Probe has no external entrants; IRQ callbacks are already quiesced. */
    if (rtwn8723be_btc_mp_native_fini(sc) != 0) {
        aprint_error_dev(sc->sc_dev, "cannot drain BT MP; retaining resources\n");
        return;
    }

    /* No mailbox users remain once IRQ and the owner are quiesced. */
    rtwn8723be_h2c_native_fini(sc);

    /* Ring maps own buffers; they must die BEFORE the 32-bit DMA tag. */
    if (sc->sc_rings_allocated)
        rtwn8723be_netbsd_free_pci_rings(sc);
    rtwn8723be_netbsd_dma_release(sc);

    /* init_aspm completed before CORE_INIT; restore original LCSR only then. */
    if (stage >= R23BE_STAGE_CORE_INIT && sc->sc_pcie_cap_valid)
        pci_conf_write(sc->sc_pc, sc->sc_tag,
            sc->sc_pcie_cap_off + PCIE_LCSR,
            sc->sc_pcie_lcsr_initial);

    if (sc->sc_mapped) {
        bus_space_unmap(sc->sc_st, sc->sc_sh, sc->sc_mapsize);
        sc->sc_mapped = false;
    }

    if (stage >= R23BE_STAGE_PCI_D0) {
        rtwn8723be_native_restore_byte(sc, 0x81,
            sc->sc_pci_clockreg_initial);
        rtwn8723be_native_restore_byte(sc, 0x44,
            sc->sc_pci_pmreg_initial);
    }

    /* Only restore COMMAND[15:0]: status bits [31:16] are W1C. */
    pci_conf_write(sc->sc_pc, sc->sc_tag, PCI_COMMAND_STATUS_REG,
        sc->sc_pci_command_initial & (pcireg_t)0xffffU);
    (void)pci_set_powerstate(sc->sc_pc, sc->sc_tag,
        sc->sc_pci_powerstate_initial);

    sc->sc_core_initialized = false;
    sc->sc_pcie_cap_valid = false;
    sc->sc_linux.stage = R23BE_STAGE_IDLE;
    sc->sc_linux.fw_ready = false;
    sc->sc_linux.mac_func_enable = false;
    sc->sc_linux.started = false;
    sc->sc_initial_pci_saved = false;
}

static int
rtwn8723be_native_detach(device_t self, int flags)
{
    struct rtwn8723be_softc *sc = device_private(self);

    (void)flags;
    /* Runtime/network teardown has not yet been implemented or validated. */
    if (sc->sc_linux.stage >= R23BE_STAGE_IEEE80211_REGISTER)
        return EBUSY;
    rtwn8723be_native_probe_cleanup(sc);
    if (sc->sc_linux.stage != R23BE_STAGE_IDLE ||
        sc->sc_initial_pci_saved)
        return EBUSY;
    rtwn8723be_netbsd_context_fini(sc);
    return 0;
}

static void
rtwn8723be_native_attach(device_t parent, device_t self, void *aux)
{
    struct rtwn8723be_softc *sc = device_private(self);
    const struct pci_attach_args *pa = aux;
    enum rtwn8723be_linux_stage failed_stage;
    int error;

    (void)parent;
    rtwn8723be_netbsd_context_init(sc, self, pa);
    pci_aprint_devinfo(pa, NULL);

    /*
     * Refuse to enable the device if its pre-probe power state is unknown;
     * no PCI, DMA, BAR or MMIO write has happened at this point.
     */
    if (pci_get_powerstate(sc->sc_pc, sc->sc_tag,
        &sc->sc_pci_powerstate_initial) != 0) {
        aprint_error_dev(self,
            "cannot snapshot original PCI power state; probe aborted\n");
        return;
    }
    sc->sc_pci_command_initial =
        pci_conf_read(sc->sc_pc, sc->sc_tag, PCI_COMMAND_STATUS_REG);
    sc->sc_pci_clockreg_initial = (uint8_t)(
        pci_conf_read(sc->sc_pc, sc->sc_tag, 0x80) >> 8);
    sc->sc_pci_pmreg_initial = (uint8_t)
        pci_conf_read(sc->sc_pc, sc->sc_tag, 0x44);
    sc->sc_initial_pci_saved = true;

    /*
     * rtwn8723be_linux_probe() checks ALL probe callbacks before the first
     * hardware-visible operation. Today it must return ENOSYS because the
     * net80211 registration and rfkill adapters are not yet implemented.
     * There is deliberately no hardware fallback or fake WLAN interface.
     *
     * Before completing the final missing probe callback, implement and
     * verify comprehensive reverse-order rollback of PCI command, BAR,
     * bus_dma, rings, interrupts, net80211 and RF resources plus detach.
     * A partially successful probe may NOT be treated as attach success.
     */
    error = rtwn8723be_linux_probe(sc, &sc->sc_linux,
        &rtwn8723be_netbsd_ops);
    if (error != 0) {
        failed_stage = sc->sc_linux.stage;
        rtwn8723be_native_probe_cleanup(sc);
        aprint_error_dev(self,
            "native RTL8723BE probe failed: %d (stage %d); "
            "WLAN not registered\n", error, (int)failed_stage);
        return;
    }

    /*
     * The last probe callback must not become available before detach and
     * rollback are implemented. This entry cannot be enabled for runtime
     * testing until the parent full-scope contract authorizes it.
     */
    aprint_normal_dev(self, "native RTL8723BE probe completed\n");
}

CFATTACH_DECL_NEW(rtwn8723be_native, sizeof(struct rtwn8723be_softc),
    rtwn8723be_native_match, rtwn8723be_native_attach,
    rtwn8723be_native_detach, NULL);
