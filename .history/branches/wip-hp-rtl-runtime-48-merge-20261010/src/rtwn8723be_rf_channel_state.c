/* SPDX-License-Identifier: GPL-2.0
 * Frozen Linux fd179f8a rtl8723be/hw.c:rtl8723be_hw_init() snapshots
 * RF_CHNLBW A/B following RF configuration, then adjusts only A.
 * This component does not bind a native MMIO or lifecycle callback.
 */
#include <sys/types.h>
#include "rtwn8723be_os_compat.h"
#include "rtwn8723be_rf_channel_state.h"

#define RTWN8723BE_RF_CHNLBW   0x18U
#define RTWN8723BE_CHNLA_KEEP  0x000fff03ffU
#define RTWN8723BE_CHNLA_SET   ((1U << 10) | (1U << 11))

int
rtwn8723be_rf_channel_state_read(
    const struct rtwn8723be_rf_serial_ctx *ctx, uint32_t values[2])
{
    uint32_t a, b;
    int error;

    if (values == NULL || ctx == NULL)
        return EINVAL;
    error = rtwn8723be_rf_serial_read(ctx, RTWN8723BE_RF_PATH_A,
        RTWN8723BE_RF_CHNLBW, &a);
    if (error != 0)
        return error;
    error = rtwn8723be_rf_serial_read(ctx, RTWN8723BE_RF_PATH_B,
        RTWN8723BE_RF_CHNLBW, &b);
    if (error != 0)
        return error;
    values[0] = (a & RTWN8723BE_CHNLA_KEEP) | RTWN8723BE_CHNLA_SET;
    values[1] = b;
    return 0;
}
