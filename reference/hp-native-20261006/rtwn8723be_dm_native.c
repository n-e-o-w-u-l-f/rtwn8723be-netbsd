/* SPDX-License-Identifier: GPL-2.0 */
/* Copyright(c) 2009-2014 Realtek Corporation. */
/*
 * Native, per-device RTL8723BE DM. Source: Linux
 * fd179f8a05be3ccae366b9b96e176b51fbe54aab rtl8723be/dm.c, core.c,
 * rtl8723com/dm_common.c, rtl8723be/hw.c, trx.c and stats.c.
 * The caller supplies real lifecycle/MMIO/RF exclusion. No MMIO occurs
 * in the RX producer: its statistics are snapshotted into the watchdog.
 */
#include "rtwn8723be_dm_native.h"
#include "rtwn8723be_netbsd.h"

/* Runtime serial RF access under the same already held adaptive io mutex. */
int rtwn8723be_runtime_write_rf(struct rtwn8723be_softc *, unsigned int,
    uint32_t, uint32_t, uint32_t);

#define BIT(n) (UINT32_C(1) << (n))
#define MASKDWORD UINT32_MAX
#define MASKBYTE0 0x000000ffU
#define MASKBYTE2 0x00ff0000U
#define MASKBYTE3 0xff000000U
#define DM_DIG_MIN 0x1eU
#define DM_DIG_MAX_AP 0x32U
#define DM_DIG_FA_TH0 0x200U
#define DM_DIG_FA_TH1 0x300U
#define DM_DIG_FA_TH2 0x400U
#define ROFDM0_XAAGCCORE1 0xc50U
#define ROFDM0_XBAGCCORE1 0xc58U
#define ROFDM0_ECCATHRESHOLD 0xc4cU
#define ROFDM1_CFOTRACKING 0xd2cU
#define RCCK0_CCA 0xa08U
#define REG_MAC_PHY_CTRL 0x2cU
#define REG_EDCA_BE_PARAM 0x508U
#define REG_BCN_CTRL 0x550U
#define DM_REG_OFDM_FA_HOLDC_11N 0xc00U
#define DM_REG_OFDM_FA_RSTD_11N 0xd00U
#define DM_REG_OFDM_FA_RSTC_11N 0xc0cU
#define DM_REG_OFDM_FA_TYPE1_11N 0xcf0U
#define DM_REG_OFDM_FA_TYPE2_11N 0xda0U
#define DM_REG_OFDM_FA_TYPE3_11N 0xda4U
#define DM_REG_OFDM_FA_TYPE4_11N 0xda8U
#define DM_REG_CCK_FA_RST_11N 0xa2cU
#define DM_REG_CCK_FA_MSB_11N 0xa58U
#define DM_REG_CCK_CCA_CNT_11N 0xa60U
#define ATC_STATUS_OFF 0U
#define ATC_STATUS_ON 1U
#define CFO_THRESHOLD_XTAL 10
#define CFO_THRESHOLD_ATC 80
#define WIRELESS_MODE_B RTWN8723BE_DM_MODE_B
#define WIRELESS_MODE_N_24G RTWN8723BE_DM_MODE_N24
#define PEER_RAL RTWN8723BE_DM_PEER_RAL
#define PEER_ATH RTWN8723BE_DM_PEER_ATH
#define PEER_CISCO RTWN8723BE_DM_PEER_CISCO
#define H2C_8723B_RA_MASK 0x40U
#define H2C_RSSIBE_REPORT 0x42U
#define RX_SMOOTH_FACTOR 20U
#define dm_min(a, b) ((a) < (b) ? (a) : (b))

static const uint32_t edca_setting_dl[8] = {
    0xa44f, 0x5ea44f, 0x5e4322, 0x5ea42b,
    0xa44f, 0xa630, 0x5ea630, 0x5ea42b
};
static const uint32_t edca_setting_ul[8] = {
    0x5e4322, 0xa44f, 0x5ea44f, 0x5ea32b,
    0x5ea422, 0x5ea322, 0x3ea430, 0x5ea44f
};

struct dm_work {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_dm_native *dm;
    const struct rtwn8723be_dm_watchdog_inputs *input;
};

static uint32_t
dm_get_bb(struct dm_work *hw, uint32_t reg, uint32_t mask)
{
    return rtwn8723be_netbsd_get_bbreg(hw->sc, reg, mask);
}

static void
dm_set_bb(struct dm_work *hw, uint32_t reg, uint32_t mask, uint32_t value)
{
    rtwn8723be_netbsd_set_bbreg(hw->sc, reg, mask, value);
}

static void
dm_write8(struct dm_work *hw, uint32_t reg, uint8_t value)
{
    rtwn8723be_write_1(hw->sc, reg, value);
}

static void
dm_write32(struct dm_work *hw, uint32_t reg, uint32_t value)
{
    rtwn8723be_write_4(hw->sc, reg, value);
}

/* Frozen HW_VAR_AC_PARAM/ACM_CTRL path used when EDCA turbo is withdrawn. */
static void
dm_set_ac_param(struct dm_work *hw)
{
    uint8_t acm_ctrl;
    hw->dm->current_turbo_edca = false;
    hw->dm->is_any_nonbepkts = false;
    hw->dm->is_cur_rdlstate = false;
    if (hw->input->acm_method == 2U)
        return;
    acm_ctrl = rtwn8723be_read_1(hw->sc, 0x5c0U);
    acm_ctrl |= hw->input->acm_method == 2U ? 0U : 1U;
    if (hw->input->be_acm)
        acm_ctrl |= BIT(1);
    else
        acm_ctrl &= (uint8_t)~BIT(1);
    dm_write8(hw, 0x5c0U, acm_ctrl);
}

#include "rtwn8723be_dm_linux.inc"

void
rtwn8723be_dm_native_rx_init(struct rtwn8723be_dm_rx_state *rx)
{
    if (rx != NULL)
        memset(rx, 0, sizeof(*rx));
}

void
rtwn8723be_dm_native_preinit(struct rtwn8723be_dm_native *dm)
{
    if (dm == NULL)
        return;
    memset(dm, 0, sizeof(*dm));
    dm->software_initialized = true;
}

void
rtwn8723be_dm_native_fini(struct rtwn8723be_dm_native *dm)
{
    if (dm != NULL)
        memset(dm, 0, sizeof(*dm));
}

int
rtwn8723be_dm_native_init(struct rtwn8723be_softc *sc,
    struct rtwn8723be_dm_native *dm,
    const struct rtwn8723be_dm_init_inputs *input)
{
    struct rtwn8723be_dm_native next;
    struct rtwn8723be_dm_dig *dig;
    if (sc == NULL || dm == NULL || input == NULL)
        return EINVAL;
    if (!dm->software_initialized || !input->hardware_ready ||
        !input->rf_identity_valid || !input->crystal_cap_valid ||
        !sc->sc_mapped || !sc->sc_bb_valid)
        return ENXIO;
    if ((input->rf_path_count != 1U && input->rf_path_count != 2U) ||
        input->crystal_cap > 0x3fU || input->current_channel < 1U ||
        input->current_channel > 14U)
        return EINVAL;
    next = *dm;
    dig = &next.dig;
    next.dm_type = 1; /* DM_TYPE_BYDRIVER */
    dig->dig_enable_flag = true;
    dig->dig_ext_port_stage = 4; /* DIG_EXT_PORT_STAGE_MAX */
    dig->cur_igvalue = rtwn8723be_netbsd_get_bbreg(sc,
        ROFDM0_XAAGCCORE1, 0x7fU);
    dig->pre_igvalue = 0;
    dig->cur_sta_cstate = dig->presta_cstate = 0;
    dig->curmultista_cstate = 3; /* DIG_MULTISTA_DISCONNECT */
    dig->rssi_lowthresh = 35;
    dig->rssi_highthresh = 40;
    dig->fa_lowthresh = 400;
    dig->fa_highthresh = 1000;
    dig->rx_gain_max = 0x3e;
    dig->rx_gain_min = DM_DIG_MIN;
    dig->back_val = 10;
    dig->back_range_max = 12;
    dig->back_range_min = -4;
    dig->pre_cck_cca_thres = 0xff;
    dig->cur_cck_cca_thres = 0x83;
    dig->forbidden_igi = DM_DIG_MIN;
    dig->large_fa_hit = 0;
    dig->recover_cnt = 0;
    dig->dig_min_0 = dig->dig_min_1 = 0x25;
    dig->media_connect_0 = dig->media_connect_1 = false;
    next.dm_initialgain_enable = true;
    dig->bt30_cur_igi = 0x32;
    dig->pre_cck_pd_state = 4;
    dig->cur_cck_pd_state = 0;
    dig->pre_cck_fa_state = dig->cur_cck_fa_state = 0;
    next.ra.ratr_state = next.ra.pre_ratr_state = RTWN8723BE_DM_RA_INIT;
    next.useramask = next.dm_type == 1;
    next.ra.high_rssi_thresh_for_ra = 50;
    next.ra.low_rssi_thresh_for_ra40m = 20;
    /* The source leaves low2high_rssi_thresh_for_ra40m untouched. */
    next.current_turbo_edca = next.is_any_nonbepkts = next.is_cur_rdlstate = false;
    next.bb_ps.pre_ccastate = next.bb_ps.cur_ccasate = 2;
    next.bb_ps.pre_rfstate = next.bb_ps.cur_rfstate = 2;
    next.bb_ps.rssi_val_min = 0;
    next.bb_ps.initialize = 0;
    next.dynamic_txpower_enable = false;
    next.last_dtp_lvl = next.dynamic_txhighpower_lvl = 0;
    rtwn8723be_thermal_txpower_init(&next.thermal);
    next.thermal.cck_inch14 = input->current_channel == 14U;
    next.crystal_cap = next.eeprom_crystal_cap = input->crystal_cap;
    next.atc_status = rtwn8723be_netbsd_get_bbreg(sc,
        ROFDM1_CFOTRACKING, BIT(11)) != 0;
    next.cfo_threshold = CFO_THRESHOLD_XTAL;
    next.rf_path_count = input->rf_path_count;
    next.rfpath_rxenable[0] = true;
    next.rfpath_rxenable[1] = input->rf_path_count == 2U;
    next.initialized = true;
    next.last_error = 0;
    *dm = next;
    return 0;
}

int
rtwn8723be_dm_native_rate_mask(const struct rtwn8723be_dm_rate_inputs *input,
    uint8_t rssi_level, uint8_t output[7], uint8_t *ratr_index)
{
    uint32_t bitmap, select;
    uint8_t index, arfr;
    bool shortgi = false;
    if (input == NULL || output == NULL || ratr_index == NULL)
        return EINVAL;
    if (input->rf_path_count != 1U && input->rf_path_count != 2U)
        return EINVAL;
    if ((input->legacy_rates & ~0xfffU) != 0 || input->macid > 127U ||
        rssi_level > RTWN8723BE_DM_RA_LOW)
        return EINVAL;
    bitmap = input->legacy_rates | ((uint32_t)input->mcs_rx_mask[0] << 12) |
        ((uint32_t)input->mcs_rx_mask[1] << 20);
    switch (input->wireless_mode) {
    case RTWN8723BE_DM_MODE_B:
        index = 6; /* RATR_INX_WIRELESS_B */
        arfr = 8;
        bitmap &= (bitmap & 0x0cU) ? 0x0dU : 0x0fU;
        break;
    case RTWN8723BE_DM_MODE_G:
        index = 4; /* RATR_INX_WIRELESS_GB */
        arfr = 6;
        bitmap &= rssi_level == 1U ? 0xf00U :
            rssi_level == 2U ? 0xff0U : 0xff5U;
        break;
    case RTWN8723BE_DM_MODE_N24:
    case RTWN8723BE_DM_MODE_N5:
        index = 0; /* RATR_INX_WIRELESS_NGB */
        arfr = 1;
        if (input->rf_path_count == 1U)
            select = rssi_level == 1U ? 0x000f0000U :
                rssi_level == 2U ? 0x000ff000U :
                input->bw40 ? 0x000ff015U : 0x000ff005U;
        else
            select = rssi_level == 1U ? 0x0f8f0000U :
                rssi_level == 2U ? 0x0f8ff000U :
                input->bw40 ? 0x0f8ff015U : 0x0f8ff005U;
        bitmap &= select;
        shortgi = input->macid == 0U &&
            ((input->bw40 && input->sgi40) || (!input->bw40 && input->sgi20));
        break;
    default:
        return EOPNOTSUPP;
    }
    output[0] = input->macid;
    output[1] = arfr | (shortgi ? 0x80U : 0U);
    output[2] = (input->bw40 ? 1U : 0U) | (input->update_bw ? 0U : 8U);
    output[3] = (uint8_t)bitmap;
    output[4] = (uint8_t)(bitmap >> 8);
    output[5] = (uint8_t)(bitmap >> 16);
    output[6] = (uint8_t)(bitmap >> 24);
    *ratr_index = index;
    return 0;
}

int
rtwn8723be_dm_native_update_rate(struct rtwn8723be_softc *sc,
    struct rtwn8723be_dm_native *dm,
    const struct rtwn8723be_dm_rate_inputs *input, uint8_t rssi_level)
{
    uint8_t mask[7], index;
    int error;
    if (sc == NULL || dm == NULL || !dm->initialized)
        return ENXIO;
    error = rtwn8723be_dm_native_rate_mask(input, rssi_level, mask, &index);
    if (error != 0)
        return error;
    error = rtwn8723be_h2c_native_send(sc, H2C_8723B_RA_MASK, mask, sizeof(mask));
    if (error != 0)
        return error;
    sc->sc_bcn_ctrl_val |= BIT(3);
    rtwn8723be_write_1(sc, REG_BCN_CTRL, sc->sc_bcn_ctrl_val);
    dm->ratr_index = index;
    memcpy(dm->rate_mask, mask, sizeof(dm->rate_mask));
    dm->rate_mask_valid = true;
    return 0;
}

static int
dm_rssi_monitor(struct dm_work *hw)
{
    struct rtwn8723be_dm_native *dm = hw->dm;
    uint8_t report[3] = {0, 0x20, (uint8_t)dm->undec_sm_pwdb};
    int error;
    /* Native station mode has no AP/adhoc station-entry list. */
    dm->entry_min_undec_sm_pwdb = dm->entry_max_undec_sm_pwdb = 0;
    if (dm->useramask) {
        error = rtwn8723be_h2c_native_send(hw->sc, H2C_RSSIBE_REPORT,
            report, sizeof(report));
        if (error != 0)
            return error;
    } else
        dm_write8(hw, 0x4feU, (uint8_t)dm->undec_sm_pwdb);
    dm->dig.min_undec_pwdb_for_dm = hw->input->linked ?
        (uint8_t)dm->undec_sm_pwdb : (uint8_t)dm->entry_min_undec_sm_pwdb;
    dm->dig.rssi_val_min = dm->dig.min_undec_pwdb_for_dm;
    return 0;
}

static int
dm_refresh_rate(struct dm_work *hw)
{
    struct rtwn8723be_dm_ra *ra = &hw->dm->ra;
    uint32_t high = ra->high_rssi_thresh_for_ra;
    uint32_t low = ra->low2high_rssi_thresh_for_ra40m;
    uint8_t next;
    int error;
    if (!hw->input->hal_started || !hw->dm->useramask ||
        !hw->input->linked || !hw->input->station)
        return 0;
    if (ra->pre_ratr_state == RTWN8723BE_DM_RA_MIDDLE)
        high += 5;
    else if (ra->pre_ratr_state == RTWN8723BE_DM_RA_LOW) {
        high += 5;
        low += 5;
    }
    next = hw->dm->undec_sm_pwdb > (long)high ? RTWN8723BE_DM_RA_HIGH :
        hw->dm->undec_sm_pwdb > (long)low ? RTWN8723BE_DM_RA_MIDDLE :
        RTWN8723BE_DM_RA_LOW;
    ra->ratr_state = next;
    if (next != ra->pre_ratr_state) {
        /* A missing real associated station matches rtl_find_sta returning NULL. */
        if (hw->input->rates_valid) {
            error = rtwn8723be_dm_native_update_rate(hw->sc, hw->dm,
                &hw->input->rates, next);
            if (error != 0)
                return error;
        }
        ra->pre_ratr_state = next;
    }
    return 0;
}

int
rtwn8723be_dm_native_watchdog(struct rtwn8723be_softc *sc,
    struct rtwn8723be_dm_native *dm,
    const struct rtwn8723be_dm_watchdog_inputs *input,
    const struct rtwn8723be_calibration_context *calctx,
    struct rtwn8723be_calibration_state *calibration)
{
    struct dm_work hw;
    int error = 0;
    if (sc == NULL || dm == NULL || input == NULL)
        return EINVAL;
    if (!dm->initialized || !input->hardware_ready || !sc->sc_mapped ||
        !sc->sc_bb_valid)
        return ENXIO;
    if (!input->station || input->peer_vendor >= RTWN8723BE_DM_PEER_MAX)
        return EOPNOTSUPP;
    if (input->rx_snapshot != NULL) {
        dm->rx = *input->rx_snapshot;
        dm->undec_sm_pwdb = dm->rx.undec_sm_pwdb;
        dm->cfo_tail[0] = dm->rx.cfo_tail[0];
        dm->cfo_tail[1] = dm->rx.cfo_tail[1];
        dm->packet_count = dm->rx.packet_count;
        dm->num_qry_beacon_pkt = dm->rx.num_beacons;
    }
    dm->is_any_nonbepkts |= input->is_any_nonbepkts;
    dm->disable_framebursting = input->disable_framebursting;
    if (!input->rf_on || input->fw_in_ps || !input->fw_awake ||
        input->p2p_ps || input->rfchange_inprogress)
        goto out;
    hw.sc = sc;
    hw.dm = dm;
    hw.input = input;
    dm->one_entry_only = input->linked && input->station;
    dm_false_alarm_counter_statistics(&hw);
    error = dm_rssi_monitor(&hw);
    if (error != 0)
        goto out;
    dm_dig(&hw);
    dm_dynamic_edcca(&hw);
    dm_cck_packet_detection_thresh(&hw);
    error = dm_refresh_rate(&hw);
    if (error != 0)
        goto out;
    dm_check_edca_turbo(&hw);
    dm_dynamic_atc_switch(&hw);
    if (dm->thermal.txpower_tracking) {
        if (!dm->thermal.tm_trigger) {
            error = rtwn8723be_runtime_write_rf(sc, 0, 0x42U,
                BIT(17) | BIT(16), 3);
            if (error == 0) {
                dm->thermal.tm_trigger = 1;
                if (calibration != NULL)
                    calibration->tm_trigger = true;
            }
        } else {
            if (calctx == NULL || calibration == NULL) {
                error = ENXIO;
                goto out;
            }
            dm->thermal.cck_inch14 = input->thermal.current_channel == 14U;
            error = rtwn8723be_thermal_callback(calctx, calibration,
                &dm->thermal, &input->thermal);
            if (error == 0) {
                dm->thermal.tm_trigger = 0;
                calibration->tm_trigger = false;
            }
        }
    }
    /* Frozen dynamic_txpower is exactly a no-op on RTL8723BE. */
out:
    dm->num_qry_beacon_pkt = 0;
    dm->last_error = error;
    return error;
}

static uint8_t
dm_rxpwr_percentage(int8_t antpower)
{
    if (antpower <= -100 || antpower >= 20)
        return 0;
    if (antpower >= 0)
        return 100;
    return (uint8_t)(100 + antpower);
}

static uint8_t
dm_evm_percentage(int8_t value)
{
    int evm = -value;
    if (evm < 0)
        evm = 0;
    if (evm > 33)
        evm = 33;
    evm *= 3;
    return (uint8_t)(evm == 99 ? 100 : evm);
}

static uint8_t
dm_signal_scale(unsigned int signal)
{
    if (signal >= 61U && signal <= 100U)
        return (uint8_t)(90U + (signal - 60U) / 4U);
    if (signal >= 41U && signal <= 60U)
        return (uint8_t)(78U + (signal - 40U) / 2U);
    if (signal >= 31U && signal <= 40U)
        return (uint8_t)(66U + signal - 30U);
    if (signal >= 21U && signal <= 30U)
        return (uint8_t)(54U + signal - 20U);
    if (signal >= 5U && signal <= 20U)
        return (uint8_t)(42U + ((signal - 5U) * 2U) / 3U);
    if (signal == 4U)
        return 36;
    if (signal == 3U)
        return 27;
    if (signal == 2U)
        return 18;
    if (signal == 1U)
        return 9;
    return (uint8_t)signal;
}

int
rtwn8723be_dm_native_rx_parse(const struct rtwn8723be_dm_rx_inputs *input,
    struct rtwn8723be_dm_rx_observation *output)
{
    struct rtwn8723be_dm_rx_observation next;
    const uint8_t *bssid;
    uint16_t fc;
    unsigned int i, streams, total_rssi = 0;
    int8_t rx_pwr_all = 0;
    uint8_t lan_idx, vga_idx, sq;
    if (input == NULL || output == NULL)
        return EINVAL;
    if (!input->phy_present)
        return ENODATA;
    /* phy_status_rpt is a frozen packed 28-byte report, not rx_fwinfo's layout. */
    if (input->phy == NULL || input->phy_length < 28U || input->frame == NULL ||
        input->frame_length < 2U || input->rate > 0x1bU ||
        (input->rf_path_count != 1U && input->rf_path_count != 2U))
        return EINVAL;
    memset(&next, 0, sizeof(next));
    next.measured = true;
    next.rf_path_count = input->rf_path_count;
    next.is_cck = input->rate <= 3U;
    next.rx_mimo_signalquality[0] = next.rx_mimo_signalquality[1] = -1;
    fc = (uint16_t)input->frame[0] | ((uint16_t)input->frame[1] << 8);
    if ((fc & 0x000cU) != 0x0004U) {
        if (input->frame_length < 24U)
            return EINVAL;
        bssid = input->frame + ((fc & 0x0100U) ? 4U :
            (fc & 0x0200U) ? 10U : 16U);
        next.packet_matchbssid = memcmp(bssid, input->bssid, 6U) == 0 &&
            !input->hw_error && !input->crc_error && !input->icv_error;
        next.packet_toself = next.packet_matchbssid &&
            memcmp(input->frame + 4U, input->macaddr, 6U) == 0;
        next.packet_beacon = (fc & 0x00fcU) == 0x0080U;
    }
    if (next.is_cck) {
        lan_idx = (input->phy[5] & 0xe0U) >> 5;
        vga_idx = input->phy[5] & 0x1fU;
        switch (lan_idx) {
        case 6:
            rx_pwr_all = (int8_t)(-34 - (2 * vga_idx));
            break;
        case 4:
            rx_pwr_all = (int8_t)(-14 - (2 * vga_idx));
            break;
        case 1:
            rx_pwr_all = (int8_t)(6 - (2 * vga_idx));
            break;
        case 0:
            rx_pwr_all = (int8_t)(16 - (2 * vga_idx));
            break;
        default:
            /* Source starts rx_pwr_all at zero for the other report codes. */
            break;
        }
        next.rx_pwdb_all = dm_rxpwr_percentage(rx_pwr_all);
        if (next.packet_matchbssid) {
            sq = input->phy[4];
            next.signalquality = next.rx_pwdb_all > 40U ? 100U :
                sq > 64U ? 0U : sq < 20U ? 100U :
                (uint8_t)(((64U - sq) * 100U) / 44U);
            next.rx_mimo_signalquality[0] = (int8_t)next.signalquality;
            next.quality_measured = true;
        }
        next.signalstrength = dm_signal_scale(next.rx_pwdb_all);
    } else {
        next.path_power_measured = true;
        for (i = 0; i < 2U; i++) {
            next.rx_pwr[i] = (int8_t)(((input->phy[i] & 0x3f) * 2) - 110);
            next.rx_mimo_signalstrength[i] = dm_rxpwr_percentage(next.rx_pwr[i]);
            total_rssi += next.rx_mimo_signalstrength[i];
        }
        rx_pwr_all = (int8_t)(((input->phy[4] >> 1) & 0x7f) - 110);
        next.rx_pwdb_all = dm_rxpwr_percentage(rx_pwr_all);
        streams = input->rate >= 0x14U && input->rate <= 0x1bU ? 2U : 1U;
        if (next.packet_matchbssid) {
            for (i = 0; i < streams; i++) {
                next.rx_mimo_signalquality[i] = (int8_t)
                    dm_evm_percentage((int8_t)input->phy[13U + i]);
                if (i == 0U)
                    next.signalquality = (uint8_t)next.rx_mimo_signalquality[0];
            }
            /* Source path_cfotail starts at byte 9, not rx_fwinfo byte 9+4. */
            next.cfo_tail[0] = (int8_t)input->phy[9];
            next.cfo_tail[1] = (int8_t)input->phy[10];
            next.cfo_measured = next.quality_measured = true;
        }
        /* Preserve source's sum of both path readings / enabled RF-path count. */
        next.signalstrength = dm_signal_scale(total_rssi / input->rf_path_count);
    }
    next.recvsignalpower = rx_pwr_all;
    *output = next;
    return 0;
}

static uint32_t
dm_smooth_insert(struct rtwn8723be_dm_smooth *smooth, uint32_t value,
    uint32_t window)
{
    if (smooth->total_num++ >= window) {
        smooth->total_num = window;
        smooth->total_val -= smooth->elements[smooth->index];
    }
    smooth->total_val += value;
    smooth->elements[smooth->index++] = value;
    if (smooth->index >= window)
        smooth->index = 0;
    return smooth->total_val / smooth->total_num;
}

int
rtwn8723be_dm_native_rx_accumulate(struct rtwn8723be_dm_rx_state *rx,
    const struct rtwn8723be_dm_rx_observation *observation)
{
    long undec_sm_pwdb;
    int weighting = 0;
    unsigned int i;
    uint32_t average;
    if (rx == NULL || observation == NULL)
        return EINVAL;
    if (!observation->measured)
        return ENODATA;
    if (observation->rf_path_count != 1U && observation->rf_path_count != 2U)
        return EINVAL;
    if (rx->ui_rssi.index >= 100U || rx->ui_rssi.total_num > 100U ||
        rx->ui_link_quality.index >= 20U || rx->ui_link_quality.total_num > 20U)
        return EINVAL;
    if (!observation->packet_matchbssid)
        return 0;
    if (observation->packet_beacon)
        rx->num_beacons++;
    if (observation->cfo_measured && !observation->is_cck) {
        rx->cfo_tail[0] = observation->cfo_tail[0];
        rx->cfo_tail[1] = observation->cfo_tail[1];
        rx->packet_count = rx->packet_count == UINT32_MAX ? 0U :
            rx->packet_count + 1U;
        rx->cfo_measured = true;
    }
    if (observation->packet_toself || observation->packet_beacon) {
        rx->pwdb_all_cnt += observation->rx_pwdb_all;
        rx->rssi_calculate_cnt++;
        average = dm_smooth_insert(&rx->ui_rssi, observation->signalstrength, 100U);
        rx->signal_strength = (long)((average + 1U) >> 1) - 95;
        if (!observation->is_cck) {
            for (i = 0; i < observation->rf_path_count; i++) {
                if (rx->rx_rssi_percentage[i] == 0U)
                    rx->rx_rssi_percentage[i] = observation->rx_mimo_signalstrength[i];
                if (observation->rx_mimo_signalstrength[i] > rx->rx_rssi_percentage[i]) {
                    rx->rx_rssi_percentage[i] = (uint8_t)
                        (((rx->rx_rssi_percentage[i] * (RX_SMOOTH_FACTOR - 1U)) +
                        observation->rx_mimo_signalstrength[i]) / RX_SMOOTH_FACTOR);
                    rx->rx_rssi_percentage[i]++;
                } else
                    rx->rx_rssi_percentage[i] = (uint8_t)
                        (((rx->rx_rssi_percentage[i] * (RX_SMOOTH_FACTOR - 1U)) +
                        observation->rx_mimo_signalstrength[i]) / RX_SMOOTH_FACTOR);
            }
        }
    }
    undec_sm_pwdb = rx->undec_sm_pwdb;
    if (undec_sm_pwdb < 0)
        undec_sm_pwdb = observation->rx_pwdb_all;
    if (observation->rx_pwdb_all > (uint32_t)undec_sm_pwdb) {
        undec_sm_pwdb = ((undec_sm_pwdb * (RX_SMOOTH_FACTOR - 1U)) +
            observation->rx_pwdb_all) / RX_SMOOTH_FACTOR;
        undec_sm_pwdb++;
    } else
        undec_sm_pwdb = ((undec_sm_pwdb * (RX_SMOOTH_FACTOR - 1U)) +
            observation->rx_pwdb_all) / RX_SMOOTH_FACTOR;
    rx->undec_sm_pwdb = undec_sm_pwdb;
    rx->pwdb_measured = true;
    if (rx->recv_signal_power == 0)
        rx->recv_signal_power = observation->recvsignalpower;
    if (observation->recvsignalpower > rx->recv_signal_power)
        weighting = 5;
    else if (observation->recvsignalpower < rx->recv_signal_power)
        weighting = -5;
    rx->recv_signal_power = (rx->recv_signal_power * 5 +
        observation->recvsignalpower + weighting) / 6;
    if (observation->quality_measured && observation->signalquality != 0U) {
        rx->signal_quality = dm_smooth_insert(&rx->ui_link_quality,
            observation->signalquality, 20U);
        rx->last_sigstrength_inpercent = rx->signal_quality;
        for (i = 0; i < 2U; i++) {
            /* stats.c reads the separate rx_mimo_sig_qual[] staging field.
             * RTL8723BE trx.c only fills rx_mimo_signalquality[]; the pinned
             * PCI staging field remains its zero initializer. Do not merge
             * those distinct fields or invent a missing PHY measurement. */
            rx->rx_evm_percentage[i] = (uint8_t)
                ((rx->rx_evm_percentage[i] * (RX_SMOOTH_FACTOR - 1U)) /
                RX_SMOOTH_FACTOR);
        }
    }
    return 0;
}
