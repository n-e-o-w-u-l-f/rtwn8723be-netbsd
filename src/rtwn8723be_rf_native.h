/* SPDX-License-Identifier: GPL-2.0 */
/*
 * NetBSD bus_space adapter for frozen Linux RTL8723BE RF6052 bring-up.
 * The adapter runs only in the exclusive, IRQ-disabled PHY_RF and
 * RF_CHANNEL_STATE init phases; each callback enforces its own phase.
 * Hardware-derived cut/board/package/path identity must be validated first.
 */
#ifndef _RTWN8723BE_RF_NATIVE_H_
#define _RTWN8723BE_RF_NATIVE_H_

/* Linux-order phy_rf_config callback; no MMIO on an invalid preflight. */
int rtwn8723be_netbsd_phy_rf_config(void *);
int rtwn8723be_netbsd_rf_channel_state_init(void *);

#endif /* _RTWN8723BE_RF_NATIVE_H_ */
