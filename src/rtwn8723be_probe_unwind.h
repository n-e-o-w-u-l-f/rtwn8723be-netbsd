/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Source-shared, fail-closed rollback broker for an UNSTARTED PCI probe.
 * Only the four post-registration probe checkpoints are eligible.
 * Running, failed-start, STOPPING and STOPPED require distinct owners.
 */
#ifndef _RTWN8723BE_PROBE_UNWIND_H_
#define _RTWN8723BE_PROBE_UNWIND_H_

#include "rtwn8723be_linux_state.h"

struct rtwn8723be_probe_unwind_snapshot {
    enum rtwn8723be_linux_stage stage;
    bool pci_snapshot;
    bool bar_mapped;
    bool started;
    bool being_init_adapter;
    bool fw_ready;
    bool hal_started;
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
    int (*drain_rfkill)(void *);
    int (*unregister_net80211)(void *);
};

/* Validate EVERY owner before the first irreversible teardown effect. */
static inline bool
rtwn8723be_probe_unwind_eligible(
    const struct rtwn8723be_probe_unwind_snapshot *s)
{
    if (s == NULL || !s->pci_snapshot || !s->bar_mapped ||
        s->stage < R23BE_STAGE_IEEE80211_REGISTER ||
        s->stage > R23BE_STAGE_PROBED ||
        s->started || s->being_init_adapter || s->fw_ready ||
        s->hal_started || s->irq_requested || s->irq_enabled ||
        !s->irq_handles_coherent)
        return false;

    /* Reached RFKill only after a successful net80211 publication. */
    if (s->net80211_registered != s->net80211_owned ||
        (s->stage > R23BE_STAGE_IEEE80211_REGISTER &&
         !s->net80211_registered))
        return false;

    /* An initialized polling owner must have its actual workqueue. */
    if (s->rfkill_initialized != s->rfkill_queue_present ||
        (s->rfkill_active && !s->rfkill_initialized) ||
        (s->stage > R23BE_STAGE_RFKILL && !s->rfkill_initialized))
        return false;

    /* Later owners must never appear at earlier probe checkpoints. */
    if ((s->stage == R23BE_STAGE_IEEE80211_REGISTER &&
         (s->rfkill_initialized || s->irq_handles_present)) ||
        (s->stage == R23BE_STAGE_RFKILL && s->irq_handles_present) ||
        (s->stage == R23BE_STAGE_PROBED && !s->irq_handles_present))
        return false;
    return true;
}

/*
 * Every effect is a real NetBSD owner, idempotent when its resource is absent.
 * STOP ON FIRST FAILURE: retain remaining resources for explicit recovery.
 * Caller must not release rings/DMA/BAR/PCI unless this returns zero.
 */
static inline int
rtwn8723be_probe_unwind_post_registration(
    const struct rtwn8723be_probe_unwind_snapshot *s,
    const struct rtwn8723be_probe_unwind_ops *ops, void *owner)
{
    int error;

    if (!rtwn8723be_probe_unwind_eligible(s))
        return EBUSY;
    if (ops == NULL || ops->disestablish_irq == NULL ||
        ops->drain_rfkill == NULL || ops->unregister_net80211 == NULL)
        return ENOSYS;

    error = ops->disestablish_irq(owner);
    if (error != 0)
        return error;
    error = ops->drain_rfkill(owner);
    if (error != 0)
        return error;
    return ops->unregister_net80211(owner);
}
#endif /* _RTWN8723BE_PROBE_UNWIND_H_ */
