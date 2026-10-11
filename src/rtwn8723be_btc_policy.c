/* SPDX-License-Identifier: GPL-2.0 */
/* Portable Linux halbtc_get()/halbtc_set() policy translation. */
#include "rtwn8723be_btc_policy.h"

#define R23BE_BTC_AGGREGATE_INTERVAL_MSEC UINT64_C(8000)

static int
btc_policy_fail(struct rtwn8723be_btc_policy *policy, bool *result,
    int error)
{
    if (result != NULL)
        *result = false;
    if (policy != NULL && policy->initialized && policy->ops != NULL &&
        policy->ops->fault != NULL)
        policy->ops->fault(policy->arg, error);
    return error;
}

static int
btc_policy_check(struct rtwn8723be_btc_policy *policy,
    struct btc_coexist *btc, bool *result)
{
    if (result == NULL)
        return EINVAL;
    *result = false;
    if (policy == NULL || btc == NULL)
        return EINVAL;
    if (!policy->initialized || policy->ops == NULL)
        return ENXIO;
    return 0;
}

static int
btc_policy_snapshot(struct rtwn8723be_btc_policy *policy,
    struct rtwn8723be_btc_wifi_snapshot *snapshot, bool *result)
{
    int error;

    error = policy->ops->snapshot(policy->arg, snapshot);
    if (error != 0)
        return btc_policy_fail(policy, result, error);
    return 0;
}

static int
btc_policy_bt_query(struct rtwn8723be_btc_policy *policy,
    struct btc_coexist *btc, enum rtwn8723be_btc_policy_bt_query query,
    uint32_t *value, bool *result)
{
    int error;

    error = policy->ops->bt_query(policy->arg, btc, query, value);
    if (error != 0)
        return btc_policy_fail(policy, result, error);
    return 0;
}

static int
btc_policy_aggregate(struct rtwn8723be_btc_policy *policy,
    struct btc_coexist *btc, bool *result)
{
    struct btc_bt_info *info = &btc->bt_info;
    uint64_t now;
    bool need_to_act = false;
    int error;

    error = policy->ops->clock_msec(policy->arg, &now);
    if (error != 0)
        return btc_policy_fail(policy, result, error);
    if (now - policy->aggregate_last_msec <= R23BE_BTC_AGGREGATE_INTERVAL_MSEC)
        return 0;
    policy->aggregate_last_msec = now;

    if (info->reject_agg_pkt) {
        need_to_act = true;
        info->pre_reject_agg_pkt = info->reject_agg_pkt;
    } else {
        if (info->pre_reject_agg_pkt) {
            need_to_act = true;
            info->pre_reject_agg_pkt = info->reject_agg_pkt;
        }
        if (info->pre_bt_ctrl_agg_buf_size != info->bt_ctrl_agg_buf_size) {
            need_to_act = true;
            info->pre_bt_ctrl_agg_buf_size = info->bt_ctrl_agg_buf_size;
        }
        if (info->bt_ctrl_agg_buf_size) {
            if (info->pre_agg_buf_size != info->agg_buf_size)
                need_to_act = true;
            info->pre_agg_buf_size = info->agg_buf_size;
        }
        if (need_to_act) {
            error = policy->ops->aggregate_apply(policy->arg, info);
            if (error != 0)
                return btc_policy_fail(policy, result, error);
        }
    }
    return 0;
}

static int
btc_policy_lps(struct rtwn8723be_btc_policy *policy,
    struct btc_coexist *btc, bool enter, bool *result)
{
    struct rtwn8723be_btc_wifi_snapshot snapshot;
    int error;

    error = btc_policy_snapshot(policy, &snapshot, result);
    if (error != 0)
        return error;
    if (snapshot.ap_mode)
        return 0;

    btc->bt_info.bt_ctrl_lps = true;
    btc->bt_info.bt_lps_on = enter;
    error = enter ? policy->ops->lps_enter(policy->arg) :
        policy->ops->lps_leave(policy->arg);
    if (error != 0)
        return btc_policy_fail(policy, result, error);
    return 0;
}

static int
btc_policy_normal_lps(struct rtwn8723be_btc_policy *policy,
    struct btc_coexist *btc, bool post, bool *result)
{
    int error;

    if (!btc->bt_info.bt_ctrl_lps)
        return 0;
    if (post) {
        btc->bt_info.bt_ctrl_lps = false;
        return 0;
    }
    btc->bt_info.bt_lps_on = false;
    error = policy->ops->lps_leave(policy->arg);
    btc->bt_info.bt_ctrl_lps = false;
    if (error != 0)
        return btc_policy_fail(policy, result, error);
    return 0;
}

int
rtwn8723be_btc_policy_init(struct rtwn8723be_btc_policy *policy,
    const struct rtwn8723be_btc_policy_ops *ops, void *arg)
{
    if (policy == NULL || ops == NULL)
        return EINVAL;
    if (policy->initialized)
        return EALREADY;
    if (ops->snapshot == NULL || ops->clock_msec == NULL ||
        ops->aggregate_apply == NULL || ops->lps_enter == NULL ||
        ops->lps_leave == NULL || ops->bt_query == NULL || ops->fault == NULL)
        return ENOSYS;
    memset(policy, 0, sizeof(*policy));
    policy->ops = ops;
    policy->arg = arg;
    policy->initialized = true;
    return 0;
}

void
rtwn8723be_btc_policy_fini(struct rtwn8723be_btc_policy *policy)
{
    if (policy != NULL)
        memset(policy, 0, sizeof(*policy));
}

int
rtwn8723be_btc_policy_get(struct rtwn8723be_btc_policy *policy,
    struct btc_coexist *btc, u8 type, void *out, bool *result)
{
    struct rtwn8723be_btc_wifi_snapshot snapshot;
    bool *bool_out = out;
    int32_t *s32_out = out;
    uint32_t *u32_out = out;
    uint8_t *u8_out = out;
    uint32_t value;
    int error;

    error = btc_policy_check(policy, btc, result);
    if (error != 0)
        return btc_policy_fail(policy, result, error);
    if (out == NULL)
        return btc_policy_fail(policy, result, EINVAL);

    switch (type) {
    case BTC_GET_BL_HS_OPERATION:
    case BTC_GET_BL_HS_CONNECTING:
        *bool_out = false;
        return 0;
    case BTC_GET_BL_WIFI_CONNECTED:
    case BTC_GET_BL_WIFI_BUSY:
    case BTC_GET_BL_WIFI_SCAN:
    case BTC_GET_BL_WIFI_LINK:
    case BTC_GET_BL_WIFI_ROAM:
    case BTC_GET_BL_WIFI_4_WAY_PROGRESS:
    case BTC_GET_BL_WIFI_UNDER_5G:
    case BTC_GET_BL_WIFI_AP_MODE_ENABLE:
    case BTC_GET_BL_WIFI_ENABLE_ENCRYPTION:
    case BTC_GET_BL_WIFI_UNDER_B_MODE:
    case BTC_GET_S4_WIFI_RSSI:
    case BTC_GET_U4_WIFI_BW:
    case BTC_GET_U4_WIFI_TRAFFIC_DIRECTION:
    case BTC_GET_U4_WIFI_FW_VER:
    case BTC_GET_U4_WIFI_LINK_STATUS:
    case BTC_GET_U1_WIFI_DOT11_CHNL:
    case BTC_GET_U1_WIFI_CENTRAL_CHNL:
    case BTC_GET_U1_AP_NUM:
        error = btc_policy_snapshot(policy, &snapshot, result);
        if (error != 0)
            return error;
        break;
    default:
        break;
    }

    switch (type) {
    case BTC_GET_BL_WIFI_CONNECTED:
        *bool_out = snapshot.station_linked || snapshot.any_client_connected;
        break;
    case BTC_GET_BL_WIFI_DUAL_BAND_CONNECTED:
        *u8_out = BTC_MULTIPORT_SCC;
        break;
    case BTC_GET_BL_WIFI_BUSY:
        *bool_out = snapshot.busy;
        break;
    case BTC_GET_BL_WIFI_SCAN:
        *bool_out = snapshot.scanning;
        break;
    case BTC_GET_BL_WIFI_LINK:
    case BTC_GET_BL_WIFI_ROAM:
        *bool_out = snapshot.linking;
        break;
    case BTC_GET_BL_WIFI_4_WAY_PROGRESS:
        *bool_out = snapshot.in_4way;
        break;
    case BTC_GET_BL_WIFI_UNDER_5G:
        *bool_out = snapshot.under_5g;
        break;
    case BTC_GET_BL_WIFI_AP_MODE_ENABLE:
        *bool_out = snapshot.ap_mode;
        break;
    case BTC_GET_BL_WIFI_ENABLE_ENCRYPTION:
        *bool_out = snapshot.encryption_enabled;
        break;
    case BTC_GET_BL_WIFI_UNDER_B_MODE:
        *bool_out = snapshot.under_b_mode;
        break;
    case BTC_GET_BL_EXT_SWITCH:
    case BTC_GET_BL_WIFI_IS_IN_MP_MODE:
    case BTC_GET_BL_IS_ASUS_8723B:
    case BTC_GET_BL_RF4CE_CONNECTED:
        *bool_out = false;
        break;
    case BTC_GET_S4_WIFI_RSSI:
        *s32_out = snapshot.rssi;
        break;
    case BTC_GET_S4_HS_RSSI:
        *s32_out = 0;
        return 0;
    case BTC_GET_U4_WIFI_BW:
        *u32_out = snapshot.bandwidth;
        break;
    case BTC_GET_U4_WIFI_TRAFFIC_DIRECTION:
        *u32_out = snapshot.traffic_direction;
        break;
    case BTC_GET_U4_WIFI_FW_VER:
        *u32_out = snapshot.firmware_version;
        break;
    case BTC_GET_U4_WIFI_LINK_STATUS:
        value = 0;
        if (snapshot.station_linked)
            value |= WIFI_STA_CONNECTED;
        if (snapshot.any_client_connected)
            value |= WIFI_AP_CONNECTED;
        if (snapshot.station_linked)
            value += UINT32_C(1) << 16;
        if (snapshot.any_client_connected)
            value += UINT32_C(1) << 16;
        *u32_out = value;
        break;
    case BTC_GET_U4_BT_PATCH_VER:
        if (btc->bt_info.bt_real_fw_ver == 0) {
            error = btc_policy_bt_query(policy, btc,
                R23BE_BTC_POLICY_BT_PATCH_VERSION, &value, result);
            if (error != 0)
                return error;
            btc->bt_info.bt_real_fw_ver = (u16)value;
        }
        *u32_out = btc->bt_info.bt_real_fw_ver;
        break;
    case BTC_GET_U4_VENDOR:
        *u32_out = BTC_VENDOR_OTHER;
        break;
    case BTC_GET_U4_SUPPORTED_VERSION:
        if (btc->btc_get_bt_coex_supported_version == NULL)
            return btc_policy_fail(policy, result, ENOSYS);
        *u32_out = btc->btc_get_bt_coex_supported_version(btc);
        break;
    case BTC_GET_U4_SUPPORTED_FEATURE:
        if (btc->btc_get_bt_coex_supported_feature == NULL)
            return btc_policy_fail(policy, result, ENOSYS);
        *u32_out = btc->btc_get_bt_coex_supported_feature(btc);
        break;
    case BTC_GET_U4_BT_DEVICE_INFO:
        error = btc_policy_bt_query(policy, btc,
            R23BE_BTC_POLICY_BT_DEVICE_INFO, &value, result);
        if (error != 0)
            return error;
        btc->bt_info.bt_device_info = value;
        *u32_out = value;
        break;
    case BTC_GET_U4_BT_FORBIDDEN_SLOT_VAL:
        error = btc_policy_bt_query(policy, btc,
            R23BE_BTC_POLICY_BT_FORBIDDEN_SLOT, &value, result);
        if (error != 0)
            return error;
        btc->bt_info.bt_forb_slot_val = value;
        *u32_out = value;
        break;
    case BTC_GET_U4_WIFI_IQK_TOTAL:
    case BTC_GET_U4_WIFI_IQK_OK:
    case BTC_GET_U4_WIFI_IQK_FAIL:
        if (btc->btc_phydm_query_phy_counter == NULL)
            return btc_policy_fail(policy, result, ENOSYS);
        *u32_out = btc->btc_phydm_query_phy_counter(btc,
            type == BTC_GET_U4_WIFI_IQK_TOTAL ? DM_INFO_IQK_ALL :
            type == BTC_GET_U4_WIFI_IQK_OK ? DM_INFO_IQK_OK : DM_INFO_IQK_NG);
        break;
    case BTC_GET_U1_WIFI_DOT11_CHNL:
        *u8_out = snapshot.dot11_channel;
        break;
    case BTC_GET_U1_WIFI_CENTRAL_CHNL:
        *u8_out = snapshot.dot11_channel == 0 ? 1 : snapshot.dot11_channel;
        break;
    case BTC_GET_U1_WIFI_HS_CHNL:
        *u8_out = 0;
        return 0;
    case BTC_GET_U1_AP_NUM:
        *u8_out = snapshot.ap_count;
        break;
    case BTC_GET_U1_ANT_TYPE:
        *u8_out = BTC_ANT_TYPE_0;
        break;
    case BTC_GET_U1_IOT_PEER:
        *u8_out = 0;
        break;
    case BTC_GET_U1_LPS_MODE:
        *u8_out = btc->pwr_mode_val[0];
        break;
    default:
        return 0;
    }
    *result = true;
    return 0;
}

int
rtwn8723be_btc_policy_set(struct rtwn8723be_btc_policy *policy,
    struct btc_coexist *btc, u8 type, void *in, bool *result)
{
    bool *bool_in = in;
    uint8_t *u8_in = in;
    uint32_t *u32_in = in;
    int error;

    error = btc_policy_check(policy, btc, result);
    if (error != 0)
        return btc_policy_fail(policy, result, error);

    switch (type) {
    case BTC_SET_BL_BT_DISABLE:
    case BTC_SET_BL_BT_TRAFFIC_BUSY:
    case BTC_SET_BL_BT_LIMITED_DIG:
    case BTC_SET_BL_FORCE_TO_ROAM:
    case BTC_SET_BL_TO_REJ_AP_AGG_PKT:
    case BTC_SET_BL_BT_CTRL_AGG_SIZE:
    case BTC_SET_BL_INC_SCAN_DEV_NUM:
    case BTC_SET_BL_BT_TX_RX_MASK:
    case BTC_SET_BL_MIRACAST_PLUS_BT:
    case BTC_SET_U1_RSSI_ADJ_VAL_FOR_AGC_TABLE_ON:
    case BTC_SET_U1_AGG_BUF_SIZE:
    case BTC_SET_U1_RSSI_ADJ_VAL_FOR_1ANT_COEX_TYPE:
    case BTC_SET_U1_LPS_VAL:
    case BTC_SET_U1_RPWM_VAL:
    case BTC_SET_ACT_DISABLE_LOW_POWER:
    case BTC_SET_ACT_UPDATE_RAMASK:
        if (in == NULL)
            return btc_policy_fail(policy, result, EINVAL);
        break;
    default:
        break;
    }

    switch (type) {
    case BTC_SET_BL_BT_DISABLE:
        btc->bt_info.bt_disabled = *bool_in;
        break;
    case BTC_SET_BL_BT_TRAFFIC_BUSY:
        btc->bt_info.bt_busy = *bool_in;
        break;
    case BTC_SET_BL_BT_LIMITED_DIG:
        btc->bt_info.limited_dig = *bool_in;
        break;
    case BTC_SET_BL_FORCE_TO_ROAM:
        btc->bt_info.force_to_roam = *bool_in;
        break;
    case BTC_SET_BL_TO_REJ_AP_AGG_PKT:
        btc->bt_info.reject_agg_pkt = *bool_in;
        break;
    case BTC_SET_BL_BT_CTRL_AGG_SIZE:
        btc->bt_info.bt_ctrl_agg_buf_size = *bool_in;
        break;
    case BTC_SET_BL_INC_SCAN_DEV_NUM:
        btc->bt_info.increase_scan_dev_num = *bool_in;
        break;
    case BTC_SET_BL_BT_TX_RX_MASK:
        btc->bt_info.bt_tx_rx_mask = *bool_in;
        break;
    case BTC_SET_BL_MIRACAST_PLUS_BT:
        btc->bt_info.miracast_plus_bt = *bool_in;
        break;
    case BTC_SET_U1_RSSI_ADJ_VAL_FOR_AGC_TABLE_ON:
        btc->bt_info.rssi_adjust_for_agc_table_on = *u8_in;
        break;
    case BTC_SET_U1_AGG_BUF_SIZE:
        btc->bt_info.agg_buf_size = *u8_in;
        break;
    case BTC_SET_ACT_GET_BT_RSSI:
        return 0;
    case BTC_SET_ACT_AGGREGATE_CTRL:
        error = btc_policy_aggregate(policy, btc, result);
        if (error != 0)
            return error;
        break;
    case BTC_SET_U1_RSSI_ADJ_VAL_FOR_1ANT_COEX_TYPE:
        btc->bt_info.rssi_adjust_for_1ant_coex_type = *u8_in;
        break;
    case BTC_SET_U1_LPS_VAL:
        btc->bt_info.lps_val = *u8_in;
        break;
    case BTC_SET_U1_RPWM_VAL:
        btc->bt_info.rpwm_val = *u8_in;
        break;
    case BTC_SET_ACT_LEAVE_LPS:
        error = btc_policy_lps(policy, btc, false, result);
        if (error != 0)
            return error;
        break;
    case BTC_SET_ACT_ENTER_LPS:
        error = btc_policy_lps(policy, btc, true, result);
        if (error != 0)
            return error;
        break;
    case BTC_SET_ACT_NORMAL_LPS:
        error = btc_policy_normal_lps(policy, btc, false, result);
        if (error != 0)
            return error;
        break;
    case BTC_SET_ACT_PRE_NORMAL_LPS:
        if (btc->bt_info.bt_ctrl_lps) {
            btc->bt_info.bt_lps_on = false;
            error = policy->ops->lps_leave(policy->arg);
            if (error != 0)
                return btc_policy_fail(policy, result, error);
        }
        break;
    case BTC_SET_ACT_POST_NORMAL_LPS:
        error = btc_policy_normal_lps(policy, btc, true, result);
        if (error != 0)
            return error;
        break;
    case BTC_SET_ACT_DISABLE_LOW_POWER:
        btc->bt_info.bt_disable_low_pwr = *bool_in;
        break;
    case BTC_SET_ACT_UPDATE_RAMASK:
        btc->bt_info.ra_mask = *u32_in;
        break;
    default:
        break;
    }
    *result = true;
    return 0;
}

static bool
btc_policy_get_provider(void *context, u8 type, void *out)
{
    struct btc_coexist *btc = context;
    struct rtwn8723be_btc_policy *policy;
    bool result = false;

    if (btc == NULL || btc->r23be_policy == NULL)
        return false;
    policy = btc->r23be_policy;
    if (rtwn8723be_btc_policy_get(policy, btc, type, out, &result) != 0)
        return false;
    return result;
}

static bool
btc_policy_set_provider(void *context, u8 type, void *in)
{
    struct btc_coexist *btc = context;
    struct rtwn8723be_btc_policy *policy;
    bool result = false;

    if (btc == NULL || btc->r23be_policy == NULL)
        return false;
    policy = btc->r23be_policy;
    if (rtwn8723be_btc_policy_set(policy, btc, type, in, &result) != 0)
        return false;
    return result;
}

int
rtwn8723be_btc_policy_bind(struct btc_coexist *btc,
    struct rtwn8723be_btc_policy *policy)
{
    if (btc == NULL || policy == NULL)
        return EINVAL;
    if (!policy->initialized)
        return ENXIO;
    if ((btc->r23be_policy != NULL && btc->r23be_policy != policy) ||
        (btc->btc_get != NULL && btc->btc_get != btc_policy_get_provider) ||
        (btc->btc_set != NULL && btc->btc_set != btc_policy_set_provider))
        return EBUSY;
    btc->r23be_policy = policy;
    btc->btc_get = btc_policy_get_provider;
    btc->btc_set = btc_policy_set_provider;
    return 0;
}
