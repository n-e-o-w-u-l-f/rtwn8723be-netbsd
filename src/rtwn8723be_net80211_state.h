/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_NET80211_STATE_H_
#define _RTWN8723BE_NET80211_STATE_H_

#include "rtwn8723be_linux_state.h"

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
