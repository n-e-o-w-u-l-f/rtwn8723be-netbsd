/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_NET80211_STATE_H_
#define _RTWN8723BE_NET80211_STATE_H_

#include "rtwn8723be_linux_state.h"

/*
 * The Linux probe controller publishes the IEEE80211_REGISTER stage before
 * invoking the native ifnet registration callback. Neither a failed
 * firmware start nor a later STOPPED adapter is permission to publish a
 * second NetBSD ifnet. Check this before ANY NetBSD registration effects;
 * the PCI/DMA/IRQ and unique softc storage checks are separate.
 */
static inline bool
rtwn8723be_net80211_registration_checkpoint_ok(
    const struct rtwn8723be_linux_state *state)
{
    return state != NULL &&
        state->stage == R23BE_STAGE_IEEE80211_REGISTER &&
        !state->started && !state->fw_ready &&
        !state->mac_func_enable && !state->being_init_adapter;
}

/*
 * A start retry is admissible only from an entirely quiescent PROBED or
 * STOPPED adapter. A callback returning failure or a false success after
 * partial firmware initialization MUST retain its stage and resources;
 * an ifconfig down/up must not silently overwrite the recovery journal.
 */
static inline bool
rtwn8723be_net80211_start_checkpoint_ok(
    const struct rtwn8723be_linux_state *state)
{
    if (state == NULL || state->started || state->being_init_adapter ||
        state->fw_ready || state->mac_func_enable)
        return false;
    return state->stage == R23BE_STAGE_PROBED ||
        state->stage == R23BE_STAGE_STOPPED;
}

/*
 * An ifnet's IFF_RUNNING flag is not the authority for PCI/MAC lifetime.
 * A false-success start or an incomplete RFKill rollback may leave Linux
 * hardware genuinely RUNNING even after the interface is logically DOWN.
 * A later explicit DOWN must be able to attempt a real hardware STOP.
 *
 * This is an advisory snapshot: begin_stop() revalidates real owners under
 * the native TX mutex. STOPPING and partial-start states are NOT promoted
 * back to RUNNING by this helper.
 */
static inline bool
rtwn8723be_net80211_running_hw_stop_needed(
    const struct rtwn8723be_linux_state *state)
{
    return state != NULL && state->started &&
        state->stage == R23BE_STAGE_RUNNING;
}

/*
 * Fail closed on *every* unfinished Linux MAC/firmware lifetime, not just
 * a normal started+RUNNING adapter or a datapath stop_pending lease.
 * An interrupted STOPPING transition and a partially initialized firmware
 * stage cannot safely be retried via normal hw_stop, but must never cause
 * net80211 media/ENETRESET/DOWN to report successful cleanup either.
 *
 * An unstarted firmware-free pre-PROBED owner and fully clean STOPPED
 * hardware are quiescent for the purpose of these user control paths.
 * The separate probe/PCI resource broker still owns attach rollback.
 */
static inline bool
rtwn8723be_net80211_hw_recovery_required(
    const struct rtwn8723be_linux_state *state)
{
    if (state == NULL)
        return true;
    return state->started || state->fw_ready ||
        state->mac_func_enable || state->being_init_adapter ||
        (state->stage > R23BE_STAGE_PROBED &&
         state->stage != R23BE_STAGE_STOPPED);
}

/*
 * A net80211 registration can complete before RFKill/IRQ probe setup does.
 * Only an UNSTARTED, hardware-quiescent interface may be released by the
 * probe rollback without invoking a normal hardware STOP callback.
 */
static inline bool
rtwn8723be_net80211_unstarted_detach_allowed(
    const struct rtwn8723be_linux_state *state)
{
    if (state == NULL || state->started || state->being_init_adapter ||
        state->fw_ready || state->mac_func_enable)
        return false;

    switch (state->stage) {
    case R23BE_STAGE_IEEE80211_REGISTER:
    case R23BE_STAGE_RFKILL:
    case R23BE_STAGE_IRQ_ESTABLISH:
    case R23BE_STAGE_PROBED:
    case R23BE_STAGE_STOPPED:
        return true;
    default:
        return false;
    }
}

#endif
