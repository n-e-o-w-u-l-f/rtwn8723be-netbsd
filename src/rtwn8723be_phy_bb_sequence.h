/* SPDX-License-Identifier: GPL-2.0
 * Ordered Linux RTL8723BE BB/AGC/PG phase adapter.  No native MMIO or
 * hardware-start callback is exposed by this standalone component.
 */
#ifndef _RTWN8723BE_PHY_BB_SEQUENCE_H_
#define _RTWN8723BE_PHY_BB_SEQUENCE_H_
#include "rtwn8723be_os_compat.h"
#include "rtwn8723be_phy_exec.h"

struct rtwn8723be_bb_sequence_ops {
    int (*select_antenna)(void *);
    rtwn8723be_phy_write_fn write_bb;
    int (*init_txpower)(void *);
    /* Linux clears rtlphy->pwrgroup_cnt before each autoload-valid PG run. */
    int (*reset_pwrgroup)(void *);
    rtwn8723be_phy_pg_fn store_pg;
    int (*convert_txpower)(void *);
    rtwn8723be_phy_write_fn write_agc;
    int (*read_cck_high_power)(void *, bool *);
};

/*
 * Frozen Linux rtl8723be/phy.c:
 * _rtl8723be_phy_bb8723b_config_parafile() selects the antenna, applies BB,
 * initializes TX power, conditionally resets the group count and applies PG, converts TX power, applies
 * AGC, and captures CCK-high-power.  The enclosing phy_bb_config() handles
 * preceding SYS_FUNC_EN/RF_CTRL setup and subsequent crystal-cap programming.
 * Those hardware phases and the PG numerical conversion are NOT implemented
 * here; the caller must provide source-derived validated callbacks.
 */
int rtwn8723be_phy_bb_sequence(void *,
    const struct rtwn8723be_bb_sequence_ops *,
    bool efuse_autoload_ok, bool *cck_high_power);
#endif
