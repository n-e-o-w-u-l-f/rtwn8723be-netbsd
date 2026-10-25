/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Fail-closed, side-effect-free admission for the RTL8723BE PCI probe.
 *
 * A Linux-order callback sequence returning zero alone is not evidence that
 * NetBSD resources have actual owners. The native PCI attachment must verify
 * its real net80211, RFKill, DMA and IRQ state before reporting success.
 * This predicate does not initialize, publish, stop or release hardware.
 */
#ifndef _RTWN8723BE_PROBE_ADMISSION_H_
#define _RTWN8723BE_PROBE_ADMISSION_H_

#include "rtwn8723be_os_compat.h"

struct rtwn8723be_probe_admission {
    bool phase_probed;
    bool quiescent;               /* Not started, not initializing, no FW ready */
    bool pci_snapshot;
    bool bar_mapped;
    bool core_initialized;
    bool dma32_configured;
    bool rings_allocated;
    bool net80211_registered;
    bool net80211_owned;          /* Registration owner points to this softc */
    bool net80211_methods_ready;  /* All three hardware methods are nonnull */
    bool rfkill_initialized;
    bool rfkill_active;
    bool irq_dispatch_ready;
    bool irq_handlers_owned;      /* PCI hard + soft + interrupt handles */
    bool irq_disabled;            /* Probe must not enable operational IRQs */
};

static inline bool
rtwn8723be_probe_admission_ok(const struct rtwn8723be_probe_admission *a)
{
    return a != NULL &&
        a->phase_probed && a->quiescent && a->pci_snapshot &&
        a->bar_mapped && a->core_initialized && a->dma32_configured &&
        a->rings_allocated &&
        a->net80211_registered && a->net80211_owned &&
        a->net80211_methods_ready &&
        a->rfkill_initialized && a->rfkill_active &&
        a->irq_dispatch_ready && a->irq_handlers_owned && a->irq_disabled;
}
#endif /* _RTWN8723BE_PROBE_ADMISSION_H_ */
