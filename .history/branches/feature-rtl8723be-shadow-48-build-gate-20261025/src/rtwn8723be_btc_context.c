/* SPDX-License-Identifier: GPL-2.0 */
/* Pure, atomic construction of a Linux-shaped BTC coexistence context. */
#include "rtwn8723be_btc_context.h"
#include "rtwn8723be_btc_engine.h"

static int
btc_context_antenna_count(const struct rtwn8723be_btc_context_identity *identity,
    u8 *count)
{
    if (identity == NULL || count == NULL)
        return EINVAL;
    switch (identity->raw_ant_num) {
    case R23BE_BTC_RAW_ANT_X2:
        *count = 2;
        return 0;
    case R23BE_BTC_RAW_ANT_X1:
        *count = 1;
        return 0;
    default:
        return EINVAL;
    }
}

static int
btc_context_identity_check(const struct rtwn8723be_btc_context_identity *identity,
    u8 *antenna_count)
{
    int error;

    if (identity == NULL || antenna_count == NULL || identity->adapter == NULL)
        return EINVAL;
    if (!identity->identity_valid)
        return ENXIO;
    if (identity->single_ant_path > 1)
        return EINVAL;
    error = btc_context_antenna_count(identity, antenna_count);
    if (error != 0)
        return error;
    return 0;
}

static bool
btc_context_identity_equal(const struct rtwn8723be_btc_context_identity *left,
    const struct rtwn8723be_btc_context_identity *right)
{
    return left->adapter == right->adapter &&
        left->identity_valid == right->identity_valid &&
        left->hwpg_bt_present == right->hwpg_bt_present &&
        left->raw_ant_num == right->raw_ant_num &&
        left->single_ant_path == right->single_ant_path &&
        left->package_type == right->package_type;
}

static void
btc_context_defaults(struct btc_coexist *btc,
    const struct rtwn8723be_btc_context_identity *identity, u8 antenna_count)
{
    memset(btc, 0, sizeof(*btc));
    btc->adapter = identity->adapter;
    btc->binded = true;
    btc->chip_interface = BTC_INTF_PCI;
    btc->statistics.cnt_bind = 1;
    btc->board_info.bt_chip_type = BTC_CHIP_RTL8723B;
    btc->board_info.pg_ant_num = antenna_count;
    btc->board_info.btdm_ant_num = antenna_count;
    btc->board_info.single_ant_path = identity->single_ant_path;
    btc->board_info.btdm_ant_pos = BTC_ANTENNA_AT_MAIN_PORT;
    btc->board_info.tfbga_package = identity->package_type > 1;
    /* Frozen exhalbtc_initlize_variables(): aggregate size starts at five. */
    btc->bt_info.agg_buf_size = 5;
}

static bool
btc_context_invariants(const struct btc_coexist *btc,
    const struct rtwn8723be_btc_context_identity *identity, u8 antenna_count)
{
    return btc->adapter == identity->adapter && btc->binded &&
        btc->chip_interface == BTC_INTF_PCI &&
        btc->statistics.cnt_bind == 1 &&
        btc->board_info.bt_chip_type == BTC_CHIP_RTL8723B &&
        btc->board_info.pg_ant_num == antenna_count &&
        btc->board_info.btdm_ant_num == antenna_count &&
        btc->board_info.single_ant_path == identity->single_ant_path &&
        btc->board_info.btdm_ant_pos == BTC_ANTENNA_AT_MAIN_PORT &&
        btc->board_info.tfbga_package == (identity->package_type > 1) &&
        btc->board_info.rfe_type == 0 && btc->board_info.ant_div_cfg == 0 &&
        btc->board_info.customer_id == 0 &&
        !btc->stack_info.profile_notified &&
        !btc->bt_info.bt_ctrl_buf_size && btc->bt_info.agg_buf_size == 5 &&
        !btc->bt_info.increase_scan_dev_num &&
        !btc->bt_info.miracast_plus_bt && !btc->bt_info.bt_ctrl_agg_buf_size &&
        !btc->initialized && btc->r23be_state == NULL;
}

/* The low-level binder receives a zero/default context.  It may fill only
 * the source's hardware-facing provider slots and delay hook; every other
 * byte must remain exactly at the prepared baseline. */
static bool
btc_context_lowlevel_changes_only(const struct btc_coexist *candidate,
    const struct btc_coexist *baseline)
{
    struct btc_coexist check;

    memcpy(&check, candidate, sizeof(check));
    check.btc_read_1byte = baseline->btc_read_1byte;
    check.btc_write_1byte = baseline->btc_write_1byte;
    check.btc_write_1byte_bitmask = baseline->btc_write_1byte_bitmask;
    check.btc_read_2byte = baseline->btc_read_2byte;
    check.btc_write_2byte = baseline->btc_write_2byte;
    check.btc_read_4byte = baseline->btc_read_4byte;
    check.btc_write_4byte = baseline->btc_write_4byte;
    check.btc_write_local_reg_1byte = baseline->btc_write_local_reg_1byte;
    check.btc_set_bb_reg = baseline->btc_set_bb_reg;
    check.btc_get_bb_reg = baseline->btc_get_bb_reg;
    check.btc_set_rf_reg = baseline->btc_set_rf_reg;
    check.btc_get_rf_reg = baseline->btc_get_rf_reg;
    check.btc_fill_h2c = baseline->btc_fill_h2c;
    check.btc_disp_dbg_msg = baseline->btc_disp_dbg_msg;
    check.btc_set_bt_reg = baseline->btc_set_bt_reg;
    check.btc_get_bt_reg = baseline->btc_get_bt_reg;
    check.btc_get_bt_coex_supported_feature =
        baseline->btc_get_bt_coex_supported_feature;
    check.btc_get_bt_coex_supported_version =
        baseline->btc_get_bt_coex_supported_version;
    check.btc_get_bt_phydm_version = baseline->btc_get_bt_phydm_version;
    check.btc_phydm_modify_ra_pcr_threshold =
        baseline->btc_phydm_modify_ra_pcr_threshold;
    check.btc_phydm_query_phy_counter = baseline->btc_phydm_query_phy_counter;
    check.btc_get_ant_det_val_from_bt = baseline->btc_get_ant_det_val_from_bt;
    check.btc_get_ble_scan_type_from_bt =
        baseline->btc_get_ble_scan_type_from_bt;
    check.btc_get_ble_scan_para_from_bt =
        baseline->btc_get_ble_scan_para_from_bt;
    check.btc_get_bt_afh_map_from_bt = baseline->btc_get_bt_afh_map_from_bt;
    check.r23be_delay_ms = baseline->r23be_delay_ms;
    return memcmp(&check, baseline, sizeof(check)) == 0;
}

/* Policy owns precisely its two Linux callback entry points and the policy
 * state pointer.  All low-level providers remain the verified prior snapshot. */
static bool
btc_context_policy_changes_only(const struct btc_coexist *candidate,
    const struct btc_coexist *lowlevel)
{
    struct btc_coexist check;

    memcpy(&check, candidate, sizeof(check));
    check.btc_get = lowlevel->btc_get;
    check.btc_set = lowlevel->btc_set;
    check.r23be_policy = lowlevel->r23be_policy;
    return memcmp(&check, lowlevel, sizeof(check)) == 0;
}

int
rtwn8723be_btc_context_build(struct btc_coexist *out,
    const struct rtwn8723be_btc_context_identity *identity,
    const struct rtwn8723be_btc_context_binders *binders)
{
    struct btc_coexist candidate;
    struct btc_coexist baseline;
    struct btc_coexist lowlevel;
    struct rtwn8723be_btc_context_identity identity_snapshot;
    u8 antenna_count;
    int error;

    if (out == NULL || identity == NULL || binders == NULL)
        return EINVAL;
    if (binders->lowlevel.bind == NULL || binders->policy.bind == NULL)
        return ENOSYS;
    identity_snapshot = *identity;
    error = btc_context_identity_check(&identity_snapshot, &antenna_count);
    if (error != 0)
        return error;

    btc_context_defaults(&candidate, &identity_snapshot, antenna_count);
    memcpy(&baseline, &candidate, sizeof(baseline));
    error = binders->lowlevel.bind(binders->lowlevel.arg, &candidate);
    if (error != 0)
        return error;
    if (!btc_context_identity_equal(identity, &identity_snapshot) ||
        !btc_context_invariants(&candidate, &identity_snapshot, antenna_count) ||
        !btc_context_lowlevel_changes_only(&candidate, &baseline))
        return EINVAL;
    memcpy(&lowlevel, &candidate, sizeof(lowlevel));

    error = binders->policy.bind(binders->policy.arg, &candidate);
    if (error != 0)
        return error;
    if (!btc_context_identity_equal(identity, &identity_snapshot) ||
        !btc_context_invariants(&candidate, &identity_snapshot, antenna_count) ||
        !btc_context_policy_changes_only(&candidate, &lowlevel))
        return EINVAL;
    error = rtwn8723be_btc_callbacks_ready(&candidate);
    if (error != 0)
        return error;

    *out = candidate;
    return 0;
}
