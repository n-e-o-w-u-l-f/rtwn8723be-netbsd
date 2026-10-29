/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_NET80211_STATE_H_
#define _RTWN8723BE_NET80211_STATE_H_

#include "rtwn8723be_linux_state.h"

/*
 * A net80211 registration can complete before RFKill/IRQ probe setup does.
 * Such an interface has no running hardware to stop, but still owns ifnet
 * resources that a caller must be able to release during reverse probe.
 */
static inline bool
rtwn8723be_net80211_unstarted_detach_allowed(
    const struct rtwn8723be_linux_state *state)
{
    if (state == NULL || state->started)
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
