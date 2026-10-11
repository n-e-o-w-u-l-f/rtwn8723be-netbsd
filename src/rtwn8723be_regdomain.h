/* SPDX-License-Identifier: GPL-2.0 */
/* Portable RTL8723BE world-regdomain baseline. */
#ifndef _RTWN8723BE_REGDOMAIN_H_
#define _RTWN8723BE_REGDOMAIN_H_

#include "rtwn8723be_os_compat.h"

/*
 * This is the unprivileged world baseline from pinned rtlwifi/regd.c.
 * A later EFUSE-country/notifier owner may only relax it after it proves
 * authority for the board and country; this helper never authorizes that.
 */
enum rtwn8723be_regdomain_channel_mode {
    R23BE_REGDOMAIN_ACTIVE_CCK_OFDM,
    R23BE_REGDOMAIN_PASSIVE_CCK_OFDM,
    R23BE_REGDOMAIN_PASSIVE_CCK_ONLY,
};

int rtwn8723be_regdomain_world_channel_mode(unsigned int,
    enum rtwn8723be_regdomain_channel_mode *);

#endif
