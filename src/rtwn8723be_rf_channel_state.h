/* SPDX-License-Identifier: GPL-2.0
 * Frozen Linux rtl8723be/hw.c RF_CHNLBW state after phy_rf_config().
 * Portable stage: the caller owns RF locking, phase, MMIO and recovery.
 */
#ifndef _RTWN8723BE_RF_CHANNEL_STATE_H_
#define _RTWN8723BE_RF_CHANNEL_STATE_H_

#include "rtwn8723be_rf_serial.h"

/* Read A and B as Linux does; only publish both values after both succeed. */
int rtwn8723be_rf_channel_state_read(
    const struct rtwn8723be_rf_serial_ctx *, uint32_t values[2]);

#endif /* _RTWN8723BE_RF_CHANNEL_STATE_H_ */
