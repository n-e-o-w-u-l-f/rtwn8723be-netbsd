/* SPDX-License-Identifier: GPL-2.0 */
/* Frozen Linux rtlwifi DM, fd179f8a05be3ccae366b9b96e176b51fbe54aab. */
#ifndef _RTWN8723BE_DM_NATIVE_H_
#define _RTWN8723BE_DM_NATIVE_H_
#include "rtwn8723be_thermal.h"

struct rtwn8723be_softc;

/* Values are the frozen Linux enum wireless_mode and peer enumeration. */
#define RTWN8723BE_DM_MODE_B 0x02U
#define RTWN8723BE_DM_MODE_G 0x04U
#define RTWN8723BE_DM_MODE_N24 0x10U
#define RTWN8723BE_DM_MODE_N5 0x20U
#define RTWN8723BE_DM_PEER_UNKNOWN 0U
#define RTWN8723BE_DM_PEER_RAL 4U
#define RTWN8723BE_DM_PEER_ATH 5U
#define RTWN8723BE_DM_PEER_CISCO 6U
#define RTWN8723BE_DM_PEER_MAX 8U
#define RTWN8723BE_DM_RA_INIT 0U
#define RTWN8723BE_DM_RA_HIGH 1U
#define RTWN8723BE_DM_RA_MIDDLE 2U
#define RTWN8723BE_DM_RA_LOW 3U

/* Exact field types of dig_t, rate_adaptive, ps_t and false_alarm_statistics. */
struct rtwn8723be_dm_dig {
    uint32_t rssi_lowthresh, rssi_highthresh, fa_lowthresh, fa_highthresh;
    long last_min_undec_pwdb_for_dm, rssi_highpower_lowthresh;
    long rssi_highpower_highthresh;
    uint32_t recover_cnt, pre_igvalue, cur_igvalue;
    long rssi_val;
    uint8_t dig_enable_flag, dig_ext_port_stage, dig_algorithm;
    uint8_t dig_twoport_algorithm, dig_dbgmode, dig_slgorithm_switch;
    uint8_t cursta_cstate, presta_cstate, curmultista_cstate, stop_dig;
    int8_t back_val, back_range_max, back_range_min;
    uint8_t rx_gain_max, rx_gain_min, min_undec_pwdb_for_dm, rssi_val_min;
    uint8_t pre_cck_cca_thres, cur_cck_cca_thres, pre_cck_pd_state;
    uint8_t cur_cck_pd_state, pre_cck_fa_state, cur_cck_fa_state;
    uint8_t pre_ccastate, cur_ccasate, large_fa_hit, forbidden_igi;
    uint8_t dig_state, dig_highpwrstate, cur_sta_cstate, pre_sta_cstate;
    uint8_t cur_ap_cstate, pre_ap_cstate, cur_pd_thstate, pre_pd_thstate;
    uint8_t cur_cs_ratiostate, pre_cs_ratiostate, backoff_enable_flag;
    int8_t backoffval_range_max, backoffval_range_min;
    uint8_t dig_min_0, dig_min_1, bt30_cur_igi;
    bool media_connect_0, media_connect_1;
    uint32_t antdiv_rssi_max, rssi_max;
};

struct rtwn8723be_dm_ra {
    uint8_t rate_adaptive_disabled, ratr_state;
    uint16_t reserve;
    uint32_t high_rssi_thresh_for_ra, high2low_rssi_thresh_for_ra;
    uint8_t low2high_rssi_thresh_for_ra40m;
    uint32_t low_rssi_thresh_for_ra40m;
    uint8_t low2high_rssi_thresh_for_ra20m;
    uint32_t low_rssi_thresh_for_ra20m, upper_rssi_threshold_ratr;
    uint32_t middleupper_rssi_threshold_ratr, middle_rssi_threshold_ratr;
    uint32_t middlelow_rssi_threshold_ratr, low_rssi_threshold_ratr;
    uint32_t ultralow_rssi_threshold_ratr, low_rssi_threshold_ratr_40m;
    uint32_t low_rssi_threshold_ratr_20m;
    uint8_t ping_rssi_enable;
    uint32_t ping_rssi_ratr, ping_rssi_thresh_for_ra, last_ratr;
    uint8_t pre_ratr_state, ldpc_thres;
    bool use_ldpc, lower_rts_rate, is_special_data;
};

struct rtwn8723be_dm_bb_ps {
    uint8_t pre_ccastate, cur_ccasate, pre_rfstate, cur_rfstate, initialize;
    long rssi_val_min;
};

struct rtwn8723be_dm_false_alarm {
    uint32_t cnt_parity_fail, cnt_rate_illegal, cnt_crc8_fail, cnt_mcs_fail;
    uint32_t cnt_fast_fsync_fail, cnt_sb_search_fail, cnt_ofdm_fail;
    uint32_t cnt_cck_fail, cnt_all, cnt_ofdm_cca, cnt_cck_cca, cnt_cca_all;
    uint32_t cnt_bw_usc, cnt_bw_lsc;
};

struct rtwn8723be_dm_smooth {
    uint32_t elements[100], index, total_num, total_val;
};

/* RX-owned state: initialize once, accumulate under the caller's stats lock. */
struct rtwn8723be_dm_rx_state {
    long undec_sm_pwdb, recv_signal_power, signal_strength, signal_quality;
    long last_sigstrength_inpercent;
    uint32_t pwdb_all_cnt, rssi_calculate_cnt, packet_count, num_beacons;
    int cfo_tail[2];
    uint8_t rx_rssi_percentage[2], rx_evm_percentage[2];
    struct rtwn8723be_dm_smooth ui_rssi, ui_link_quality;
    bool pwdb_measured, cfo_measured;
};

struct rtwn8723be_dm_native {
    struct rtwn8723be_dm_dig dig;
    struct rtwn8723be_dm_ra ra;
    struct rtwn8723be_dm_bb_ps bb_ps;
    struct rtwn8723be_dm_false_alarm false_alarm;
    struct rtwn8723be_thermal_state thermal;
    struct rtwn8723be_dm_rx_state rx;
    long entry_min_undec_sm_pwdb, undec_sm_cck, undec_sm_pwdb;
    long entry_max_undec_sm_pwdb;
    int32_t ofdm_pkt_cnt;
    bool dm_initialgain_enable, dynamic_txpower_enable, current_turbo_edca;
    bool is_any_nonbepkts, is_cur_rdlstate, disable_framebursting, useramask;
    bool rfpath_rxenable[4], one_entry_only;
    uint8_t last_dtp_lvl, dynamic_txhighpower_lvl, dm_type;
    bool atc_status, large_cfo_hit, is_freeze;
    int cfo_tail[2], cfo_ave_pre, crystal_cap;
    uint8_t cfo_threshold, eeprom_crystal_cap;
    uint32_t packet_count, packet_count_pre, num_qry_beacon_pkt;
    uint64_t last_txok_cnt, last_rxok_cnt;
    uint8_t rf_path_count;
    uint8_t ratr_index, rate_mask[7];
    bool rate_mask_valid;
    bool pre_edcca_enable, software_initialized, initialized;
    int last_error;
};

struct rtwn8723be_dm_init_inputs {
    bool hardware_ready, rf_identity_valid, crystal_cap_valid;
    uint8_t rf_path_count, crystal_cap, current_channel;
};

struct rtwn8723be_dm_rate_inputs {
    uint32_t legacy_rates; /* Frozen supp_rates bits: 1M..54M, low 12 bits. */
    uint8_t mcs_rx_mask[2];
    uint8_t wireless_mode, rf_path_count, macid;
    bool bw40, sgi20, sgi40, update_bw;
};

struct rtwn8723be_dm_watchdog_inputs {
    bool hardware_ready, hal_started, rf_on, fw_in_ps, fw_awake;
    bool p2p_ps, rfchange_inprogress, scanning, linked, station;
    bool btc_active, bt_disabled;
    uint8_t peer_vendor, wireless_mode;
    uint64_t txbytesunicast, rxbytesunicast;
    bool is_any_nonbepkts, disable_framebursting;
    uint8_t acm_method; /* Frozen rtl_pci_init defaults to EACMWAY2_SW (2). */
    bool be_acm; /* Actual ac[0].aifs ACM bit, for HW_VAR_AC_PARAM. */
    bool rates_valid;
    struct rtwn8723be_dm_rate_inputs rates;
    struct rtwn8723be_thermal_inputs thermal;
    /* A caller-owned, locked snapshot; NULL preserves the last snapshot. */
    const struct rtwn8723be_dm_rx_state *rx_snapshot;
};

struct rtwn8723be_dm_rx_inputs {
    const uint8_t *frame, *phy;
    size_t frame_length, phy_length;
    uint8_t bssid[6], macaddr[6], rate, rf_path_count;
    bool phy_present, crc_error, icv_error, hw_error;
};

struct rtwn8723be_dm_rx_observation {
    bool measured, is_cck, packet_matchbssid, packet_toself, packet_beacon;
    int8_t recvsignalpower, rx_pwr[2], cfo_tail[2];
    uint8_t rx_pwdb_all, signalstrength, signalquality;
    uint8_t rx_mimo_signalstrength[2], rf_path_count;
    int8_t rx_mimo_signalquality[2];
    bool quality_measured, cfo_measured, path_power_measured;
};

/* swvars/cold calibration context exists before MMIO dm_init: tracking is off. */
void rtwn8723be_dm_native_preinit(struct rtwn8723be_dm_native *);
/* All MMIO/thermal functions require the caller's real lifecycle/io mutex. */
int rtwn8723be_dm_native_init(struct rtwn8723be_softc *,
    struct rtwn8723be_dm_native *, const struct rtwn8723be_dm_init_inputs *);
void rtwn8723be_dm_native_fini(struct rtwn8723be_dm_native *);
int rtwn8723be_dm_native_watchdog(struct rtwn8723be_softc *,
    struct rtwn8723be_dm_native *, const struct rtwn8723be_dm_watchdog_inputs *,
    const struct rtwn8723be_calibration_context *,
    struct rtwn8723be_calibration_state *);
int rtwn8723be_dm_native_rate_mask(const struct rtwn8723be_dm_rate_inputs *,
    uint8_t, uint8_t[7], uint8_t *);
int rtwn8723be_dm_native_update_rate(struct rtwn8723be_softc *,
    struct rtwn8723be_dm_native *, const struct rtwn8723be_dm_rate_inputs *,
    uint8_t);
/* Parse is pure; no DM mutation in softint and no fabricated absent PHY data. */
int rtwn8723be_dm_native_rx_parse(const struct rtwn8723be_dm_rx_inputs *,
    struct rtwn8723be_dm_rx_observation *);
void rtwn8723be_dm_native_rx_init(struct rtwn8723be_dm_rx_state *);
int rtwn8723be_dm_native_rx_accumulate(struct rtwn8723be_dm_rx_state *,
    const struct rtwn8723be_dm_rx_observation *);

#endif
