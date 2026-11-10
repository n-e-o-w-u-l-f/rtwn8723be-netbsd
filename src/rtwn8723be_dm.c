/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Full RTL8723BE DM initialization, frozen Linux reference:
 * fd179f8a05be3ccae366b9b96e176b51fbe54aab
 * drivers/net/wireless/realtek/rtlwifi/
 *   rtl8723be/dm.c: rtl8723be_dm_init,
 *     rtl8723be_dm_init_rate_adaptive_mask,
 *     rtl8723be_dm_init_txpower_tracking,
 *     rtl8723be_dm_init_dynamic_atc_switch
 *   core.c: rtl_dm_diginit; core.h: DIG thresholds/enumerations
 *   rtl8723com/dm_common.c: rtl8723_dm_init_edca_turbo,
 *     rtl8723_dm_init_dynamic_bb_powersaving,
 *     rtl8723_dm_init_dynamic_txpower
 *   rtl8723be/sw.c: rtl8723be_init_sw_vars
 *   wifi.h: logical state field types
 *   rtl8723be/reg.h: ROFDM0_XAAGCCORE1 and ROFDM1_CFOTRACKING
 *
 * The native caller supplies genuine fallible BB reads under its real
 * exclusion. Initialization publishes only after both reads and final
 * readiness succeed. No MMIO write, provider lease or periodic worker is
 * supplied by this portable initializer.
 */
#include "rtwn8723be_dm.h"

enum {
    R23BE_DM_TYPE_BYDRIVER = 1,
    R23BE_DM_RATR_STA_INIT = 0,
    R23BE_DM_DIG_STA_DISCONNECT = 0,
    R23BE_DM_DIG_MULTISTA_DISCONNECT = 3,
    R23BE_DM_DIG_EXT_PORT_STAGE_MAX = 4,
    R23BE_DM_CCK_PD_STAGE_LOWRSSI = 0,
    R23BE_DM_CCK_PD_STAGE_MAX = 4,
    R23BE_DM_CCA_MAX = 2,
    R23BE_DM_RF_MAX = 2,
    R23BE_DM_TXHIGHPWRLEVEL_NORMAL = 0,
    R23BE_DM_CFO_THRESHOLD_XTAL = 10
};

void
rtwn8723be_dm_construct(struct rtwn8723be_dm_state *state)
{
    if (state == NULL)
        return;
    /* rtl_priv cold allocation is zeroed before init_sw_vars defaults. */
    memset(state, 0, sizeof(*state));
    state->dm_initialgain_enable = true;
    state->dm_flag = 0;
    state->disable_framebursting = false;
    state->thermal.thermalvalue = 0;
}

static void
dm_dig_init(struct rtwn8723be_dm_state *state, uint32_t current_igi)
{
    struct rtwn8723be_dm_dig *dig = &state->dig;

    dig->dig_enable_flag = true;
    dig->dig_ext_port_stage = R23BE_DM_DIG_EXT_PORT_STAGE_MAX;
    dig->cur_igvalue = current_igi;
    dig->pre_igvalue = 0;
    dig->cur_sta_cstate = R23BE_DM_DIG_STA_DISCONNECT;
    dig->presta_cstate = R23BE_DM_DIG_STA_DISCONNECT;
    dig->curmultista_cstate = R23BE_DM_DIG_MULTISTA_DISCONNECT;
    dig->rssi_lowthresh = 35;
    dig->rssi_highthresh = 40;
    dig->fa_lowthresh = 400;
    dig->fa_highthresh = 1000;
    dig->rx_gain_max = 0x3e;
    dig->rx_gain_min = 0x1e;
    dig->back_val = 10;
    dig->back_range_max = 12;
    dig->back_range_min = -4;
    dig->pre_cck_cca_thres = 0xff;
    dig->cur_cck_cca_thres = 0x83;
    dig->forbidden_igi = 0x1e;
    dig->large_fa_hit = 0;
    dig->recover_cnt = 0;
    dig->dig_min_0 = 0x25;
    dig->dig_min_1 = 0x25;
    dig->media_connect_0 = false;
    dig->media_connect_1 = false;
    state->dm_initialgain_enable = true;
    dig->bt30_cur_igi = 0x32;
    dig->pre_cck_pd_state = R23BE_DM_CCK_PD_STAGE_MAX;
    dig->cur_cck_pd_state = R23BE_DM_CCK_PD_STAGE_LOWRSSI;
    dig->pre_cck_fa_state = 0;
    dig->cur_cck_fa_state = 0;
}

static void
dm_rate_adaptive_init(struct rtwn8723be_dm_state *state)
{
    state->ra.ratr_state = R23BE_DM_RATR_STA_INIT;
    state->ra.pre_ratr_state = R23BE_DM_RATR_STA_INIT;
    state->useramask = state->dm_type == R23BE_DM_TYPE_BYDRIVER;
    state->ra.high_rssi_thresh_for_ra = 50;
    state->ra.low_rssi_thresh_for_ra40m = 20;
}

static void
dm_edca_init(struct rtwn8723be_dm_state *state)
{
    state->current_turbo_edca = false;
    state->is_any_nonbepkts = false;
    state->is_cur_rdlstate = false;
}

static void
dm_powersaving_init(struct rtwn8723be_dm_state *state)
{
    state->powersaving.pre_ccastate = R23BE_DM_CCA_MAX;
    state->powersaving.cur_ccasate = R23BE_DM_CCA_MAX;
    state->powersaving.pre_rfstate = R23BE_DM_RF_MAX;
    state->powersaving.cur_rfstate = R23BE_DM_RF_MAX;
    state->powersaving.rssi_val_min = 0;
    state->powersaving.initialize = 0;
}

static void
dm_dynamic_txpower_init(struct rtwn8723be_dm_state *state)
{
    state->dynamic_txpower_enable = false;
    state->last_dtp_lvl = R23BE_DM_TXHIGHPWRLEVEL_NORMAL;
    state->dynamic_txhighpower_lvl = R23BE_DM_TXHIGHPWRLEVEL_NORMAL;
}

int
rtwn8723be_dm_init(struct rtwn8723be_dm_state *state,
    const struct rtwn8723be_dm_io *io, void *arg, uint8_t crystal_cap)
{
    struct rtwn8723be_dm_state next;
    uint32_t current_igi = UINT32_MAX, atc = UINT32_MAX;
    int error;

    if (state == NULL || io == NULL)
        return EINVAL;
    if (io->ready == NULL || io->read_bb == NULL)
        return ENOSYS;
    if (crystal_cap > 0x3fU)
        return EINVAL;
    if (!io->ready(arg))
        return ENXIO;
    error = io->read_bb(arg, R23BE_DM_AGC_REG, R23BE_DM_AGC_MASK,
        &current_igi);
    if (error != 0)
        return error;
    if (current_igi > R23BE_DM_AGC_MASK)
        return EINVAL;

    next = *state;
    next.dm_type = R23BE_DM_TYPE_BYDRIVER;
    dm_dig_init(&next, current_igi);
    dm_rate_adaptive_init(&next);
    dm_edca_init(&next);
    dm_powersaving_init(&next);
    dm_dynamic_txpower_init(&next);
    rtwn8723be_thermal_txpower_init(&next.thermal);
    next.crystal_cap = crystal_cap;

    if (!io->ready(arg))
        return ENXIO;
    error = io->read_bb(arg, R23BE_DM_ATC_REG, R23BE_DM_ATC_MASK, &atc);
    if (error != 0)
        return error;
    if (atc > 1U)
        return EINVAL;
    next.atc_status = atc != 0;
    next.cfo_threshold = R23BE_DM_CFO_THRESHOLD_XTAL;
    if (!io->ready(arg))
        return ENXIO;

    *state = next;
    return 0;
}
