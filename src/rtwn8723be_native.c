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

static void
rtwn8723be_native_attach(device_t parent, device_t self, void *aux)
{
    struct rtwn8723be_softc *sc = device_private(self);
    const struct pci_attach_args *pa = aux;
    int error;

    (void)parent;
    rtwn8723be_netbsd_context_init(sc, self, pa);
    pci_aprint_devinfo(pa, NULL);

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
        aprint_error_dev(self,
            "native RTL8723BE probe unavailable/failed: %d; "
            "WLAN not registered\n", error);
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
    rtwn8723be_native_match, rtwn8723be_native_attach, NULL, NULL);
