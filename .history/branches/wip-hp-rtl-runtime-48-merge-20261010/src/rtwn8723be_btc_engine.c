/* SPDX-License-Identifier: GPL-2.0 */
/* Source-level dispatch. Native and full rtlwifi owners remain distinct. */
#include "rtwn8723be_btc_engine.h"

int
rtwn8723be_btc_callbacks_ready(const struct btc_coexist *b)
{
    if (b == NULL) return EINVAL;
    if (b->btc_read_1byte == NULL || b->btc_write_1byte == NULL ||
        b->btc_write_1byte_bitmask == NULL || b->btc_read_2byte == NULL ||
        b->btc_write_2byte == NULL || b->btc_read_4byte == NULL ||
        b->btc_write_4byte == NULL || b->btc_write_local_reg_1byte == NULL ||
        b->btc_set_bb_reg == NULL || b->btc_get_bb_reg == NULL ||
        b->btc_set_rf_reg == NULL || b->btc_get_rf_reg == NULL ||
        b->btc_fill_h2c == NULL || b->btc_disp_dbg_msg == NULL ||
        b->btc_get == NULL || b->btc_set == NULL ||
        b->btc_set_bt_reg == NULL || b->btc_get_bt_reg == NULL ||
        b->btc_get_bt_coex_supported_feature == NULL ||
        b->btc_get_bt_coex_supported_version == NULL ||
        b->btc_get_bt_phydm_version == NULL ||
        b->btc_phydm_modify_ra_pcr_threshold == NULL ||
        b->btc_phydm_query_phy_counter == NULL ||
        b->btc_get_ant_det_val_from_bt == NULL ||
        b->btc_get_ble_scan_type_from_bt == NULL ||
        b->btc_get_ble_scan_para_from_bt == NULL ||
        b->btc_get_bt_afh_map_from_bt == NULL ||
        b->r23be_delay_ms == NULL)
        return ENOSYS;
    return 0;
}

int
rtwn8723be_btc_engine_init(struct rtwn8723be_btc_state *s,
    const struct btc_coexist *input)
{
    struct btc_coexist copy;
    int error;
    if (s == NULL || input == NULL) return EINVAL;
    if (s->prepared) return EALREADY;
    error = rtwn8723be_btc_callbacks_ready(input);
    if (error != 0) return error;
    if (!input->binded || input->adapter == NULL ||
        input->chip_interface != BTC_INTF_PCI ||
        (input->board_info.btdm_ant_num != 1 &&
         input->board_info.btdm_ant_num != 2) ||
        input->board_info.single_ant_path > 1)
        return EINVAL;
    copy = *input;
    memset(s, 0, sizeof(*s));
    s->btc = copy;
    s->btc.r23be_state = s;
    /*
     * Frozen rtl_btc_init_variables() kzallocs btc_coexist.  A copied
     * caller context must not claim exhalbtc_init_coex_dm() has already
     * completed before the native hardware/DM initialization callbacks.
     */
    s->btc.initialized = false;
    s->prepared = true;
    return 0;
}

int
rtwn8723be_btc_event_validate(const struct rtwn8723be_btc_state *s,
    const struct rtwn8723be_btc_event *e)
{
    if (s == NULL || !s->prepared) return ENXIO;
    if (e == NULL || (unsigned int)e->kind >= R23BE_BTC_EVENT_COUNT)
        return EINVAL;
    if (e->kind == R23BE_BTC_INFO &&
        (e->length == 0 || e->length > R23BE_BTC_INFO_MAX))
        return EINVAL;
    if (e->kind == R23BE_BTC_DISPLAY &&
        (e->diagnostic == NULL || e->diagnostic->vprintf == NULL))
        return EINVAL;
    /* The frozen two-antenna source has no RF-status notification entry. */
    if (e->kind == R23BE_BTC_RF_STATUS &&
        s->btc.board_info.btdm_ant_num == 2)
        return ENOTSUP;
    return rtwn8723be_btc_callbacks_ready(&s->btc);
}

int
rtwn8723be_btc_engine_execute(struct rtwn8723be_btc_state *s,
    const struct rtwn8723be_btc_event *e)
{
    struct btc_coexist *b;
    u8 copied[R23BE_BTC_INFO_MAX];
    int error = rtwn8723be_btc_event_validate(s, e);
    bool one;
    if (error != 0) return error;
    b = &s->btc;
    one = b->board_info.btdm_ant_num == 1;
#define BOTH(suffix, ...) do { \
    if (one) ex_btc8723b1ant_##suffix(b, ##__VA_ARGS__); \
    else ex_btc8723b2ant_##suffix(b, ##__VA_ARGS__); \
} while (0)
    switch (e->kind) {
    case R23BE_BTC_POWER_ON: BOTH(power_on_setting); break;
    case R23BE_BTC_PRELOAD:
        /* Exact exhalbtc_pre_load_firmware: one antenna has no hook. */
        if (!one) ex_btc8723b2ant_pre_load_firmware(b);
        break;
    case R23BE_BTC_INIT_HW:
        if (one) ex_btc8723b1ant_init_hwconfig(b, e->value != 0);
        else ex_btc8723b2ant_init_hwconfig(b);
        break;
    case R23BE_BTC_INIT_DM: BOTH(init_coex_dm); break;
    case R23BE_BTC_IPS: BOTH(ips_notify, e->value); break;
    case R23BE_BTC_LPS: BOTH(lps_notify, e->value); break;
    case R23BE_BTC_SCAN: BOTH(scan_notify, e->value); break;
    case R23BE_BTC_CONNECT: BOTH(connect_notify, e->value); break;
    case R23BE_BTC_MEDIA: BOTH(media_status_notify, e->value); break;
    case R23BE_BTC_SPECIAL_PACKET: BOTH(special_packet_notify, e->value); break;
    case R23BE_BTC_INFO:
        memcpy(copied, e->info, e->length);
        BOTH(bt_info_notify, copied, e->length);
        break;
    case R23BE_BTC_RF_STATUS: ex_btc8723b1ant_rf_status_notify(b, e->value); break;
    case R23BE_BTC_HALT: BOTH(halt_notify); break;
    case R23BE_BTC_PNP: BOTH(pnp_notify, e->value); break;
    case R23BE_BTC_PERIODIC: BOTH(periodical); break;
    case R23BE_BTC_DISPLAY: BOTH(display_coex_info, e->diagnostic); break;
    default: return EINVAL;
    }
#undef BOTH
    /* Source dispatch returns no fallible IO result. Native providers must
     * record and surface the first failure and quarantine partial state.
     */
    return 0;
}
