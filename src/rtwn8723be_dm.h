/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_DM_H_
#define _RTWN8723BE_DM_H_

#include "rtwn8723be_os_compat.h"
#include "rtwn8723be_thermal.h"

#define R23BE_DM_AGC_REG  0xc50U
#define R23BE_DM_AGC_MASK 0x7fU
#define R23BE_DM_ATC_REG  0xd2cU
#define R23BE_DM_ATC_MASK 0x800U

/*
 * Logical per-device tables from frozen rtlwifi/wifi.h. Retain unassigned
 * fields across warm initialization; this is not a Linux binary ABI.
 */
struct rtwn8723be_dm_dig {
    uint32_t rssi_lowthresh, rssi_highthresh;
    uint32_t fa_lowthresh, fa_highthresh;
    long last_min_undec_pwdb_for_dm;
    long rssi_highpower_lowthresh, rssi_highpower_highthresh;
    uint32_t recover_cnt, pre_igvalue, cur_igvalue;
    long rssi_val;
    uint8_t dig_enable_flag, dig_ext_port_stage;
    uint8_t dig_algorithm, dig_twoport_algorithm, dig_dbgmode;
    uint8_t dig_slgorithm_switch;
    uint8_t cursta_cstate, presta_cstate, curmultista_cstate, stop_dig;
    int8_t back_val, back_range_max, back_range_min;
    uint8_t rx_gain_max, rx_gain_min, min_undec_pwdb_for_dm, rssi_val_min;
    uint8_t pre_cck_cca_thres, cur_cck_cca_thres;
    uint8_t pre_cck_pd_state, cur_cck_pd_state;
    uint8_t pre_cck_fa_state, cur_cck_fa_state;
    uint8_t pre_ccastate, cur_ccasate, large_fa_hit, forbidden_igi;
    uint8_t dig_state, dig_highpwrstate;
    uint8_t cur_sta_cstate, pre_sta_cstate, cur_ap_cstate, pre_ap_cstate;
    uint8_t cur_pd_thstate, pre_pd_thstate, cur_cs_ratiostate;
    uint8_t pre_cs_ratiostate, backoff_enable_flag;
    int8_t backoffval_range_max, backoffval_range_min;
    uint8_t dig_min_0, dig_min_1, bt30_cur_igi;
    bool media_connect_0, media_connect_1;
    uint32_t antdiv_rssi_max, rssi_max;
};

struct rtwn8723be_dm_rate_adaptive {
    uint8_t rate_adaptive_disabled, ratr_state;
    uint16_t reserve;
    uint32_t high_rssi_thresh_for_ra, high2low_rssi_thresh_for_ra;
    uint8_t low2high_rssi_thresh_for_ra40m;
    uint32_t low_rssi_thresh_for_ra40m;
    uint8_t low2high_rssi_thresh_for_ra20m;
    uint32_t low_rssi_thresh_for_ra20m;
    uint32_t upper_rssi_threshold_ratr, middleupper_rssi_threshold_ratr;
    uint32_t middle_rssi_threshold_ratr, middlelow_rssi_threshold_ratr;
    uint32_t low_rssi_threshold_ratr, ultralow_rssi_threshold_ratr;
    uint32_t low_rssi_threshold_ratr_40m, low_rssi_threshold_ratr_20m;
    uint8_t ping_rssi_enable;
    uint32_t ping_rssi_ratr, ping_rssi_thresh_for_ra, last_ratr;
    uint8_t pre_ratr_state, ldpc_thres;
    bool use_ldpc, lower_rts_rate, is_special_data;
};

struct rtwn8723be_dm_powersaving {
    uint8_t pre_ccastate, cur_ccasate, pre_rfstate, cur_rfstate, initialize;
    long rssi_val_min;
};

struct rtwn8723be_dm_state {
    struct rtwn8723be_dm_dig dig;
    struct rtwn8723be_dm_rate_adaptive ra;
    struct rtwn8723be_dm_powersaving powersaving;
    struct rtwn8723be_thermal_state thermal;
    bool dm_initialgain_enable, dynamic_txpower_enable, current_turbo_edca;
    bool is_any_nonbepkts, is_cur_rdlstate, disable_framebursting, useramask;
    uint8_t last_dtp_lvl, dynamic_txhighpower_lvl, dm_flag, dm_type;
    bool atc_status;
    int crystal_cap;
    uint8_t cfo_threshold;
};

/*
 * The real native caller owns MMIO/power/RF/DM exclusion throughout.
 * read_bb returns the masked, right-aligned value, matching rtl_get_bbreg.
 * No acquisition, scheduling, lease or hardware-ready state is invented here.
 */
struct rtwn8723be_dm_io {
    bool (*ready)(void *);
    int (*read_bb)(void *, uint32_t, uint32_t, uint32_t *);
};

/* Once for real cold storage, not at each STOP/START. No IO. */
void rtwn8723be_dm_construct(struct rtwn8723be_dm_state *);
/*
 * Full frozen rtl8723be_dm_init, not watchdog or periodic DM execution.
 * AGC is read first and ATC last. On any error state is unchanged.
 * Warm thermal/DIG/RA history not assigned by the frozen initializer survives.
 */
int rtwn8723be_dm_init(struct rtwn8723be_dm_state *,
    const struct rtwn8723be_dm_io *, void *, uint8_t crystal_cap);

#endif
