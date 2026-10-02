/* SPDX-License-Identifier: GPL-2.0
 * Linux RTL8723BE RF6052 per-path RFENV/HSSI setup and restoration.
 * Frozen Linux: rtl8723be/rf.c:_rtl8723be_phy_rf6052_config_parafile().
 * All platform I/O and locking are supplied by the future NetBSD adapter.
 */
#ifndef _RTWN8723BE_RF_PATH_H_
#define _RTWN8723BE_RF_PATH_H_
#include "rtwn8723be_rf_serial.h"

typedef int (*rtwn8723be_rf_path_init_fn)(void *, unsigned int);
int rtwn8723be_rf_path_configure(
    const struct rtwn8723be_rf_serial_ctx *,
    unsigned int path, rtwn8723be_rf_path_init_fn initialize,
    void *initialize_arg);

#endif /* _RTWN8723BE_RF_PATH_H_ */
