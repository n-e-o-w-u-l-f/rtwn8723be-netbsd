/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Source-shared, fail-closed rollback broker for an UNSTARTED PCI probe.
 * Only the four post-registration probe checkpoints are eligible.
 * Running, failed-start, STOPPING and STOPPED require distinct owners.
 */
#ifndef _RTWN8723BE_PROBE_UNWIND_H_
#define _RTWN8723BE_PROBE_UNWIND_H_

#include "rtwn8723be_linux_state.h"

/* Persist completion across failed subsequent compensators. Never infer
 * completion solely from absent handles: only a zero-returning real owner
 * callback advances this journal. Values are strictly monotonic until IDLE.
 */
enum rtwn8723be_probe_unwind_progress {
    R23BE_PROBE_UNWIND_NONE = 0,
    R23BE_PROBE_UNWIND_IRQ,
    R23BE_PROBE_UNWIND_DATAPATH,
    R23BE_PROBE_UNWIND_RX_BINDING,
    R23BE_PROBE_UNWIND_RFKILL,
    R23BE_PROBE_UNWIND_NET80211,
};

struct rtwn8723be_probe_unwind_snapshot {
    enum rtwn8723be_linux_stage stage;
    enum rtwn8723be_probe_unwind_progress progress;
    bool pci_snapshot;
    bool bar_mapped;
    bool started;
    bool being_init_adapter;
    bool fw_ready;
    bool hal_started;
    bool datapath_bound;          /* Prepared TX lock/IRQ dispatch still owned */
    bool datapath_owner_valid;    /* IRQ callbacks and owner pointer agree */
    bool datapath_tx_enabled;     /* Unprepare requires TX quiescence */
    bool rx_binding_owned;        /* Same net80211/device callback context */
    bool rx_binding_present;      /* Owner has not yet retired its storage */
    bool irq_requested;
    bool irq_enabled;
    bool irq_handles_coherent;
    bool irq_handles_present;
    bool net80211_registered;
    bool net80211_owned;
    bool rfkill_initialized;
    bool rfkill_queue_present;
    bool rfkill_active;
};

struct rtwn8723be_probe_unwind_ops {
    int (*disestablish_irq)(void *);
    int (*unprepare_datapath)(void *);
    int (*unbind_rx)(void *);
    int (*drain_rfkill)(void *);
    int (*unregister_net80211)(void *);
};

/*
 * Validate the acquisition order and the explicit rollback journal.
 * A resource missing before its acknowledged release is NOT safe to skip.
 */
static inline bool
rtwn8723be_probe_unwind_eligible(
    const struct rtwn8723be_probe_unwind_snapshot *s)
{
    if (s == NULL || !s->pci_snapshot || !s->bar_mapped ||
        s->stage < R23BE_STAGE_IEEE80211_REGISTER ||
        s->stage > R23BE_STAGE_PROBED ||
        (unsigned int)s->progress > R23BE_PROBE_UNWIND_NET80211 ||
        s->started || s->being_init_adapter || s->fw_ready ||
        s->hal_started || !s->datapath_owner_valid ||
        s->datapath_tx_enabled || s->irq_requested || s->irq_enabled ||
        !s->irq_handles_coherent)
        return false;

    if (s->rx_binding_present != s->rx_binding_owned ||
        (s->progress >= R23BE_PROBE_UNWIND_RX_BINDING &&
         s->rx_binding_present))
        return false;

    if (s->net80211_registered != s->net80211_owned ||
        (s->progress < R23BE_PROBE_UNWIND_NET80211 &&
         s->stage > R23BE_STAGE_IEEE80211_REGISTER &&
         !s->net80211_registered) ||
        (s->progress >= R23BE_PROBE_UNWIND_NET80211 &&
         s->net80211_registered))
        return false;

    if (s->rfkill_initialized != s->rfkill_queue_present ||
        (s->rfkill_active && !s->rfkill_initialized) ||
        (s->progress < R23BE_PROBE_UNWIND_RFKILL &&
         s->stage > R23BE_STAGE_RFKILL &&
         !s->rfkill_initialized) ||
        (s->progress >= R23BE_PROBE_UNWIND_RFKILL &&
         s->rfkill_initialized))
        return false;

    if ((s->progress >= R23BE_PROBE_UNWIND_DATAPATH &&
         s->datapath_bound) ||
        (s->progress >= R23BE_PROBE_UNWIND_IRQ &&
         s->irq_handles_present) ||
        (s->progress < R23BE_PROBE_UNWIND_IRQ &&
         s->stage == R23BE_STAGE_PROBED &&
         !s->irq_handles_present))
        return false;

    /* Later owners cannot appear before their Linux probe callback. */
    if ((s->stage == R23BE_STAGE_IEEE80211_REGISTER &&
         (s->rfkill_initialized || s->irq_handles_present)) ||
        (s->stage == R23BE_STAGE_RFKILL && s->irq_handles_present))
        return false;
    return true;
}

/*
 * All callbacks are real NetBSD owners and must be idempotent if absent.
 * Check callback availability BEFORE any effect; advance the persistent
 * journal ONLY after success. On failure retain PCI/MMIO and remaining
 * owners, allowing a later, explicitly serialized retry.
 */
static inline int
rtwn8723be_probe_unwind_post_registration(
    const struct rtwn8723be_probe_unwind_snapshot *s,
    enum rtwn8723be_probe_unwind_progress *progress,
    const struct rtwn8723be_probe_unwind_ops *ops, void *owner)
{
    int error;

    if (progress == NULL || s == NULL || s->progress != *progress ||
        !rtwn8723be_probe_unwind_eligible(s))
        return EBUSY;
    if (ops == NULL || ops->disestablish_irq == NULL ||
        ops->unprepare_datapath == NULL || ops->unbind_rx == NULL ||
        ops->drain_rfkill == NULL || ops->unregister_net80211 == NULL)
        return ENOSYS;

    if (*progress < R23BE_PROBE_UNWIND_IRQ) {
        error = ops->disestablish_irq(owner);
        if (error != 0)
            return error;
        *progress = R23BE_PROBE_UNWIND_IRQ;
    }
    if (*progress < R23BE_PROBE_UNWIND_DATAPATH) {
        error = ops->unprepare_datapath(owner);
        if (error != 0)
            return error;
        *progress = R23BE_PROBE_UNWIND_DATAPATH;
    }
    if (*progress < R23BE_PROBE_UNWIND_RX_BINDING) {
        error = ops->unbind_rx(owner);
        if (error != 0)
            return error;
        *progress = R23BE_PROBE_UNWIND_RX_BINDING;
    }
    if (*progress < R23BE_PROBE_UNWIND_RFKILL) {
        error = ops->drain_rfkill(owner);
        if (error != 0)
            return error;
        *progress = R23BE_PROBE_UNWIND_RFKILL;
    }
    if (*progress < R23BE_PROBE_UNWIND_NET80211) {
        error = ops->unregister_net80211(owner);
        if (error != 0)
            return error;
        *progress = R23BE_PROBE_UNWIND_NET80211;
    }
    return 0;
}
#endif /* _RTWN8723BE_PROBE_UNWIND_H_ */
