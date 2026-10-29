/* SPDX-License-Identifier: GPL-2.0 */
/* Generated function-local histories: zero initial state, per device. */
struct rtwn8723be_btc_history1 {
    u32 halbtc8723b1ant_monitor_bt_ctr__num_of_bt_counter_chk;
    u8 halbtc8723b1ant_monitor_wifi_ctr__cck_lock_counter;
    bool btc8723b1ant_is_wifi_status_changed__pre_wifi_busy;
    bool btc8723b1ant_is_wifi_status_changed__pre_under_4way;
    bool btc8723b1ant_is_wifi_status_changed__pre_bt_hs_on;
    bool halbtc8723b1ant_ps_tdma__pre_wifi_busy;
    s32 btc8723b1ant_tdma_dur_adj_for_acl__up;
    s32 btc8723b1ant_tdma_dur_adj_for_acl__dn;
    s32 btc8723b1ant_tdma_dur_adj_for_acl__m;
    s32 btc8723b1ant_tdma_dur_adj_for_acl__n;
    s32 btc8723b1ant_tdma_dur_adj_for_acl__wait_count;
    u32 halbtc8723b1ant_monitor_bt_enable_disable__bt_disable_cnt;
};
struct rtwn8723be_btc_history2 {
    bool btc8723b2ant_is_wifi_status_changed__pre_wifi_busy;
    bool btc8723b2ant_is_wifi_status_changed__pre_under_4way;
    bool btc8723b2ant_is_wifi_status_changed__pre_bt_hs_on;
    s32 btc8723b2ant_tdma_duration_adjust__up;
    s32 btc8723b2ant_tdma_duration_adjust__dn;
    s32 btc8723b2ant_tdma_duration_adjust__m;
    s32 btc8723b2ant_tdma_duration_adjust__n;
    s32 btc8723b2ant_tdma_duration_adjust__wait_count;
};
