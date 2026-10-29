/* SPDX-License-Identifier: GPL-2.0 */
/* Frozen Linux RTL8723BE IQK/LCK, fd179f8a05be3ccae366b9b96e176b51fbe54aab. */
#ifndef _RTWN8723BE_CALIBRATION_H_
#define _RTWN8723BE_CALIBRATION_H_
#include "rtwn8723be_os_compat.h"

struct rtwn8723be_calibration_state {
    bool iqk_initialized;
    bool iqk_recovery_valid;
    bool lck_inprogress;
    bool iqk_matrix_done;
    bool tm_trigger;
    bool tracking_changed;
    uint8_t final_candidate;
    int32_t reg_e94, reg_e9c, reg_eb4, reg_ebc;
    /* The 2.4 GHz channel mapping in the pin always selects matrix[0]. */
    int32_t iqk_matrix[8];
    uint32_t recovery[9];
    int last_error;
    int last_restore_error;
};

/* Published under the owning lifecycle/RF exclusion, never from EFUSE alone. */
struct rtwn8723be_calibration_inputs {
    bool rf_state_valid;
    bool rf_on;
    bool btc_bound;
    bool btc_initialized;
    /* Linux enum bt_ant_num: ANT_X2=0, ANT_X1=1. */
    uint8_t btc_ant_num;
    bool dm_state_valid;
    bool txpower_tracking;
    bool tm_trigger;
    uint8_t current_channel;
};

struct rtwn8723be_calibration_context;
struct rtwn8723be_calibration_io {
    bool (*ready)(void *);
    int (*read_bb)(void *, uint32_t, uint32_t, uint32_t *);
    int (*write_bb)(void *, uint32_t, uint32_t, uint32_t);
    int (*read_rf)(void *, unsigned int, uint32_t, uint32_t, uint32_t *);
    int (*write_rf)(void *, unsigned int, uint32_t, uint32_t, uint32_t);
    int (*read_mac)(void *, uint32_t, unsigned int, uint32_t *);
    int (*write_mac)(void *, uint32_t, unsigned int, uint32_t);
    int (*delay_us)(void *, unsigned int);
    int (*scan_active)(void *, bool *);
    /*
     * Required only for an enabled, previously triggered DM meter.
     * Must be the real port of the pinned thermal callback, under this
     * same owner's exclusion. It may use iqk/lck below without reacquiring
     * the owner. It must not stand in for a missing DM implementation.
     */
    int (*thermal_track)(void *, const struct rtwn8723be_calibration_context *,
        struct rtwn8723be_calibration_state *);
};

struct rtwn8723be_calibration_context {
    const struct rtwn8723be_calibration_io *io;
    void *arg;
};

/*
 * Caller holds lifecycle, MMIO/power lifetime and RF/calibration exclusion.
 * No spin lock may be held across the 10 ms IQK / 50 ms LCK delays.
 * These functions do not acquire or invent those owners.
 */
int rtwn8723be_calibration_iqk(const struct rtwn8723be_calibration_context *,
    struct rtwn8723be_calibration_state *, bool);
int rtwn8723be_calibration_lck(const struct rtwn8723be_calibration_context *,
    struct rtwn8723be_calibration_state *);
int rtwn8723be_calibration_run(const struct rtwn8723be_calibration_context *,
    struct rtwn8723be_calibration_state *,
    const struct rtwn8723be_calibration_inputs *);
#endif
