/* SPDX-License-Identifier: GPL-2.0 */
/* Portable RTL8723BE world-regdomain baseline. */
#include "rtwn8723be_regdomain.h"

int
rtwn8723be_regdomain_world_channel_mode(unsigned int channel,
    enum rtwn8723be_regdomain_channel_mode *mode)
{
    if (mode == NULL || channel < 1U || channel > 14U)
        return EINVAL;
    if (channel <= 11U)
        *mode = R23BE_REGDOMAIN_ACTIVE_CCK_OFDM;
    else if (channel <= 13U)
        *mode = R23BE_REGDOMAIN_PASSIVE_CCK_OFDM;
    else
        *mode = R23BE_REGDOMAIN_PASSIVE_CCK_ONLY;
    return 0;
}
