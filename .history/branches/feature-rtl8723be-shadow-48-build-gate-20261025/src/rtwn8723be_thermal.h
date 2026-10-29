/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_THERMAL_H_
#define _RTWN8723BE_THERMAL_H_
#include "rtwn8723be_calibration.h"

/* Exact pinned rtl_dm field types used by its RTL8723BE thermal callback. */
struct rtwn8723be_thermal_state {
    bool txpower_state_valid;
    bool txpower_tracking, txpower_trackinginit, done_txpower, cck_inch14;
    uint8_t txpower_track_control, txpowercount, tm_trigger;
    uint8_t thermalvalue, thermalvalue_lck, thermalvalue_iqk;
    uint8_t thermalvalue_avg[8], thermalvalue_avg_index;
    int8_t ofdm_index[4], cck_index;
    int8_t delta_power_index[4], delta_power_index_last[4], power_index_offset[4];
    uint8_t swing_idx_ofdm[4], swing_idx_ofdm_base[4];
    uint8_t swing_idx_cck, swing_idx_cck_base;
    int last_error, last_restore_error;
};

struct rtwn8723be_thermal_inputs {
    bool eeprom_meter_valid;
    uint8_t eeprom_thermalmeter;
    uint8_t current_channel;
};

/* Only the pinned dm_init_txpower_tracking subsection, not full dm_init. */
void rtwn8723be_thermal_txpower_init(struct rtwn8723be_thermal_state *);
/* Frozen hw.c thermal-meter EFUSE parse, with bounds and atomic outputs. */
int rtwn8723be_thermal_meter_parse(const uint8_t *, size_t, bool,
    uint8_t *, bool *);

/*
 * Real thermal meter read, averaging, delta/swing decisions and LCK/IQK
 * threshold calls under an already acquired calibration/RF/DM owner.
 * Intended for the real owner's thermal_track hook. Does not acquire,
 * invent, or validate a BTC/DM/lifecycle owner. A warm-init caller must
 * publish the actual parsed EFUSE meter and actual channel/CCK state.
 */
int rtwn8723be_thermal_callback(const struct rtwn8723be_calibration_context *,
    struct rtwn8723be_calibration_state *, struct rtwn8723be_thermal_state *,
    const struct rtwn8723be_thermal_inputs *);
#endif
