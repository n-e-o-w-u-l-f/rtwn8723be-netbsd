/* SPDX-License-Identifier: GPL-2.0 */
/* Real NetBSD providers for frozen halbtcoutsrc.c, not algorithm mocks. */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_btc_provider_native.h"

static struct rtwn8723be_softc *
btc_sc(void *arg)
{
    return ((struct btc_coexist *)arg)->adapter;
}

static bool
btc_reg(void *arg, uint32_t reg, unsigned int width)
{
    struct rtwn8723be_softc *sc = btc_sc(arg);
    if (!rtwn8723be_btc_native_provider_ready(sc))
        return false;
    if ((reg & (width - 1U)) != 0 || reg > sc->sc_mapsize ||
        sc->sc_mapsize - reg < width) {
        rtwn8723be_btc_native_provider_error(sc, EINVAL);
        return false;
    }
    return true;
}

static u8 btc_read1(void *b, u32 r)
{
    return btc_reg(b, r, 1) ? rtwn8723be_read_1(btc_sc(b), r) : 0;
}
static u16 btc_read2(void *b, u32 r)
{
    return btc_reg(b, r, 2) ? rtwn8723be_read_2(btc_sc(b), r) : 0;
}
static u32 btc_read4(void *b, u32 r)
{
    return btc_reg(b, r, 4) ? rtwn8723be_read_4(btc_sc(b), r) : 0;
}
static void btc_write1(void *b, u32 r, u32 v)
{
    if (btc_reg(b, r, 1)) rtwn8723be_write_1(btc_sc(b), r, (u8)v);
}
static void btc_write2(void *b, u32 r, u16 v)
{
    if (btc_reg(b, r, 2)) rtwn8723be_write_2(btc_sc(b), r, v);
}
static void btc_write4(void *b, u32 r, u32 v)
{
    if (btc_reg(b, r, 4)) rtwn8723be_write_4(btc_sc(b), r, v);
}
static void btc_local(void *b, u32 r, u8 v)
{
    /* Frozen PCI local registers are in the same MMIO BAR. */
    btc_write1(b, r, v);
}
static void btc_mask1(void *b, u32 r, u32 mask, u8 v)
{
    u8 old;
    unsigned int shift = 0;
    if (!btc_reg(b, r, 1)) return;
    mask &= 0xffU;
    if (mask == 0) {
        rtwn8723be_btc_native_provider_error(btc_sc(b), EINVAL);
        return;
    }
    if (mask != 0xffU) {
        old = rtwn8723be_read_1(btc_sc(b), r);
        for (shift = 0; shift < 8 && !(mask & (1U << shift)); shift++)
            ;
        v = (u8)((old & ~mask) | (v << shift));
    }
    rtwn8723be_write_1(btc_sc(b), r, v);
}
static void btc_setbb(void *b, u32 r, u32 mask, u32 v)
{
    if (!btc_reg(b, r, 4)) return;
    if (mask == 0) {
        rtwn8723be_btc_native_provider_error(btc_sc(b), EINVAL);
        return;
    }
    rtwn8723be_netbsd_set_bbreg(btc_sc(b), r, mask, v);
}
static u32 btc_getbb(void *b, u32 r, u32 mask)
{
    if (!btc_reg(b, r, 4)) return 0;
    if (mask == 0) {
        rtwn8723be_btc_native_provider_error(btc_sc(b), EINVAL);
        return 0;
    }
    return rtwn8723be_netbsd_get_bbreg(btc_sc(b), r, mask);
}
static void btc_setrf(void *b, u8 path, u32 r, u32 mask, u32 v)
{
    struct rtwn8723be_softc *sc = btc_sc(b);
    if (rtwn8723be_btc_native_provider_ready(sc))
        rtwn8723be_btc_native_provider_error(sc,
            rtwn8723be_runtime_write_rf(sc, path, r, mask, v));
}
static u32 btc_getrf(void *b, u8 path, u32 r, u32 mask)
{
    struct rtwn8723be_softc *sc = btc_sc(b);
    u32 value = 0;
    if (rtwn8723be_btc_native_provider_ready(sc))
        rtwn8723be_btc_native_provider_error(sc,
            rtwn8723be_runtime_read_rf(sc, path, r, mask, &value));
    return value;
}
static void btc_h2c(void *b, u8 id, u32 len, u8 *data)
{
    struct rtwn8723be_softc *sc = btc_sc(b);
    if (rtwn8723be_btc_native_provider_ready(sc))
        rtwn8723be_btc_native_provider_error(sc,
            rtwn8723be_h2c_native_send(sc, id, data, len));
}
static void btc_delay(void *b, unsigned int ms)
{
    struct rtwn8723be_softc *sc = btc_sc(b);
    if (!rtwn8723be_btc_native_provider_ready(sc)) return;
    /* Owner holds an adaptive IPL_NONE mutex; no spin lock crosses delay. */
    while (ms-- != 0) delay(1000);
}

/* Copy-reply/native generation lifetime, exact frozen cache updates. */
static bool
btc_mp(struct btc_coexist *b, u8 opcode, const u8 *command, size_t length)
{
    struct rtwn8723be_softc *sc = btc_sc(b);
    struct rtwn8723be_btc_mp_reply reply;
    int error;
    if (!rtwn8723be_btc_native_provider_ready(sc)) return false;
    error = rtwn8723be_btc_mp_native_request(sc, opcode, command, length,
        true, &reply);
    if (error != 0) {
        rtwn8723be_btc_native_provider_error(sc, error);
        return false;
    }
    switch (reply.field) {
    case R23BE_BT_MP_VERSION:
        b->bt_info.bt_real_fw_ver = (u16)reply.value;
        b->bt_info.bt_fw_ver = reply.firmware_subversion;
        break;
    case R23BE_BT_MP_AFH_L: b->bt_info.afh_map_l = reply.value; break;
    case R23BE_BT_MP_AFH_M: b->bt_info.afh_map_m = reply.value; break;
    case R23BE_BT_MP_AFH_H: b->bt_info.afh_map_h = (u16)reply.value; break;
    case R23BE_BT_MP_FEATURE: b->bt_info.bt_supported_feature = reply.value; break;
    case R23BE_BT_MP_SUPPORTED_VERSION:
        b->bt_info.bt_supported_version = reply.value; break;
    case R23BE_BT_MP_ANT_DETECTION:
        b->bt_info.bt_ant_det_val = (u8)reply.value; break;
    case R23BE_BT_MP_BLE_SCAN_PARAMETERS:
        b->bt_info.bt_ble_scan_para = reply.value; break;
    case R23BE_BT_MP_BLE_SCAN_TYPE:
        b->bt_info.bt_ble_scan_type = (u8)reply.value; break;
    case R23BE_BT_MP_DEVICE_INFO: b->bt_info.bt_device_info = reply.value; break;
    case R23BE_BT_MP_NONE: break;
    }
    /* Frozen sequence0xb does not update forbidden-slot: source uses opcode49.
     * Native matching does not invent a wire nonce or repair that source bug. */
    return true;
}

static u32 btc_version(void *arg)
{
    struct btc_coexist *b = arg;
    const u8 command[4] = {0};
    if (!b->bt_info.bt_real_fw_ver)
        (void)btc_mp(b, BT_OP_GET_BT_VERSION, command, sizeof(command));
    return b->bt_info.bt_real_fw_ver;
}
static u32 btc_feature(void *arg)
{
    struct btc_coexist *b = arg;
    const u8 command[4] = {0};
    if (!b->bt_info.bt_supported_feature)
        (void)btc_mp(b, BT_OP_GET_BT_COEX_SUPPORTED_FEATURE,
            command, sizeof(command));
    return b->bt_info.bt_supported_feature;
}
static u32 btc_supported_version(void *arg)
{
    struct btc_coexist *b = arg;
    const u8 command[4] = {0};
    if (!b->bt_info.bt_supported_version)
        (void)btc_mp(b, BT_OP_GET_BT_COEX_SUPPORTED_VERSION,
            command, sizeof(command));
    return b->bt_info.bt_supported_version;
}
static u32 btc_device_info(void *arg)
{
    struct btc_coexist *b = arg;
    const u8 command[4] = {0};
    (void)btc_mp(b, BT_OP_GET_BT_DEVICE_INFO, command, sizeof(command));
    return b->bt_info.bt_device_info;
}
static u32 btc_forbidden(void *arg)
{
    struct btc_coexist *b = arg;
    const u8 command[4] = {0};
    (void)btc_mp(b, BT_OP_GET_BT_FORBIDDEN_SLOT_VAL, command, sizeof(command));
    return b->bt_info.bt_forb_slot_val;
}
static void btc_setbt(void *arg, u8 type, u32 offset, u32 value)
{
    struct btc_coexist *b = arg;
    const u8 data[4] = {0, 0, (u8)value, (u8)(value >> 8)};
    const u8 address[4] = {0, 0, type, (u8)offset};
    if (btc_mp(b, BT_OP_WRITE_REG_VALUE, data, sizeof(data)))
        (void)btc_mp(b, BT_OP_WRITE_REG_ADDR, address, sizeof(address));
}

/* These four providers are truly constant/no-op in the frozen reference:
 * halbtcoutsrc.c:1086-1126, not substitutes for a missing native DM engine. */
static u32 btc_getbt(void *arg, u8 type, u32 offset)
{
    (void)arg; (void)type; (void)offset;
    return 0;
}
static u32 btc_phydm_version(void *arg)
{
    (void)arg;
    return 0;
}
static void btc_phydm_threshold(void *arg, u8 direction, u8 offset)
{
    (void)arg; (void)direction; (void)offset;
}
static u32 btc_phydm_counter(void *arg, enum dm_info_query id)
{
    (void)arg; (void)id;
    return 0;
}
static u8 btc_ant(void *arg)
{
    struct btc_coexist *b = arg;
    const u8 command[4] = {0};
    (void)btc_mp(b, BT_OP_GET_BT_ANT_DET_VAL, command, sizeof(command));
    return b->bt_info.bt_ant_det_val;
}
static u8 btc_ble_type(void *arg)
{
    struct btc_coexist *b = arg;
    const u8 command[4] = {0};
    (void)btc_mp(b, BT_OP_GET_BT_BLE_SCAN_TYPE, command, sizeof(command));
    return b->bt_info.bt_ble_scan_type;
}
static u32 btc_ble_parameters(void *arg, u8 type)
{
    struct btc_coexist *b = arg;
    const u8 command[4] = {0};
    /* Frozen source ignores scan_type. Preserve its command bytes. */
    (void)type;
    (void)btc_mp(b, BT_OP_GET_BT_BLE_SCAN_PARA, command, sizeof(command));
    return b->bt_info.bt_ble_scan_para;
}
static bool btc_afh(void *arg, u8 type, u8 *out)
{
    struct btc_coexist *b = arg;
    const u8 command[2] = {0};
    (void)type;
    if (out == NULL) return false;
    if (!btc_mp(b, BT_OP_GET_AFH_MAP_L, command, sizeof(command))) return false;
    /* Reference stores native host scalars; use aligned-safe copies. */
    memcpy(out, &b->bt_info.afh_map_l, 4);
    if (!btc_mp(b, BT_OP_GET_AFH_MAP_M, command, sizeof(command))) return false;
    memcpy(out + 4, &b->bt_info.afh_map_m, 4);
    if (!btc_mp(b, BT_OP_GET_AFH_MAP_H, command, sizeof(command))) return false;
    memcpy(out + 8, &b->bt_info.afh_map_h, 2);
    return true;
}

static bool
btc_get(void *arg, u8 type, void *out)
{
    struct btc_coexist *b = arg;
    struct rtwn8723be_softc *sc = btc_sc(b);
    struct rtwn8723be_btc_wifi_state s;
    bool *bv = out;
    u8 *u1 = out;
    u32 *u4 = out;
    int32_t *s4 = out;
    int error;
    if (out == NULL || !rtwn8723be_btc_native_provider_ready(sc)) return false;
    error = rtwn8723be_runtime_btc_snapshot(sc, &s);
    if (error != 0) {
        rtwn8723be_btc_native_provider_error(sc, error);
        return false;
    }
    switch (type) {
    case BTC_GET_BL_HS_OPERATION:
    case BTC_GET_BL_HS_CONNECTING: *bv = false; return false;
    case BTC_GET_BL_WIFI_CONNECTED: *bv = s.connected; break;
    case BTC_GET_BL_WIFI_DUAL_BAND_CONNECTED: *u1 = BTC_MULTIPORT_SCC; break;
    case BTC_GET_BL_WIFI_BUSY: *bv = s.busy; break;
    case BTC_GET_BL_WIFI_SCAN: *bv = s.scanning; break;
    case BTC_GET_BL_WIFI_LINK:
    case BTC_GET_BL_WIFI_ROAM: *bv = s.linking; break;
    case BTC_GET_BL_WIFI_4_WAY_PROGRESS: *bv = s.in_4way; break;
    case BTC_GET_BL_WIFI_UNDER_5G: *bv = s.under_5g; break;
    case BTC_GET_BL_WIFI_AP_MODE_ENABLE: *bv = s.ap; break;
    case BTC_GET_BL_WIFI_ENABLE_ENCRYPTION: *bv = s.encrypted; break;
    case BTC_GET_BL_WIFI_UNDER_B_MODE: *bv = s.under_b; break;
    case BTC_GET_BL_EXT_SWITCH:
    case BTC_GET_BL_WIFI_IS_IN_MP_MODE:
    case BTC_GET_BL_IS_ASUS_8723B:
    case BTC_GET_BL_RF4CE_CONNECTED: *bv = false; break;
    case BTC_GET_S4_WIFI_RSSI: *s4 = s.rssi; break;
    case BTC_GET_S4_HS_RSSI: *s4 = 0; return false;
    case BTC_GET_U4_WIFI_BW: *u4 = s.bandwidth; break;
    case BTC_GET_U4_WIFI_TRAFFIC_DIRECTION: *u4 = s.direction; break;
    case BTC_GET_U4_WIFI_FW_VER: *u4 = s.firmware_version; break;
    case BTC_GET_U4_WIFI_LINK_STATUS: *u4 = s.link_status; break;
    case BTC_GET_U4_BT_PATCH_VER: *u4 = btc_version(b); break;
    case BTC_GET_U4_VENDOR: *u4 = BTC_VENDOR_OTHER; break;
    case BTC_GET_U4_SUPPORTED_VERSION: *u4 = btc_supported_version(b); break;
    case BTC_GET_U4_SUPPORTED_FEATURE: *u4 = btc_feature(b); break;
    case BTC_GET_U4_BT_DEVICE_INFO: *u4 = btc_device_info(b); break;
    case BTC_GET_U4_BT_FORBIDDEN_SLOT_VAL: *u4 = btc_forbidden(b); break;
    case BTC_GET_U4_WIFI_IQK_TOTAL:
    case BTC_GET_U4_WIFI_IQK_OK:
    case BTC_GET_U4_WIFI_IQK_FAIL: *u4 = 0; break;
    case BTC_GET_U1_WIFI_DOT11_CHNL: *u1 = s.channel; break;
    case BTC_GET_U1_WIFI_CENTRAL_CHNL: *u1 = s.channel == 0 ? 1 : s.channel; break;
    case BTC_GET_U1_WIFI_HS_CHNL: *u1 = 0; return false;
    case BTC_GET_U1_AP_NUM: *u1 = s.ap_count; break;
    case BTC_GET_U1_ANT_TYPE: *u1 = BTC_ANT_TYPE_0; break;
    case BTC_GET_U1_IOT_PEER: *u1 = 0; break;
    case BTC_GET_U1_LPS_MODE: *u1 = b->pwr_mode_val[0]; break;
    default: return false;
    }
    return rtwn8723be_btc_native_provider_ready(sc);
}

static bool
btc_set(void *arg, u8 type, void *in)
{
    struct btc_coexist *b = arg;
    struct rtwn8723be_softc *sc = btc_sc(b);
    bool *bv = in;
    u8 *u1 = in;
    u32 *u4 = in;
    struct rtwn8723be_btc_wifi_state s;
    int error = 0;
    if (!rtwn8723be_btc_native_provider_ready(sc)) return false;
    /* The frozen algorithms pass NULL to action-only providers. */
    switch (type) {
    case BTC_SET_ACT_AGGREGATE_CTRL:
    case BTC_SET_ACT_GET_BT_RSSI:
    case BTC_SET_ACT_LEAVE_LPS:
    case BTC_SET_ACT_ENTER_LPS:
    case BTC_SET_ACT_NORMAL_LPS:
    case BTC_SET_ACT_PRE_NORMAL_LPS:
    case BTC_SET_ACT_POST_NORMAL_LPS:
    case BTC_SET_UI_SCAN_SIG_COMPENSATION:
    case BTC_SET_ACT_SEND_MIMO_PS:
    case BTC_SET_ACT_CTRL_BT_INFO:
    case BTC_SET_ACT_CTRL_BT_COEX:
    case BTC_SET_ACT_CTRL_8723B_ANT:
        break;
    default:
        if (in == NULL) return false;
        break;
    }
    if (type == BTC_SET_ACT_LEAVE_LPS || type == BTC_SET_ACT_ENTER_LPS) {
        error = rtwn8723be_runtime_btc_snapshot(sc, &s);
        if (error != 0) {
            rtwn8723be_btc_native_provider_error(sc, error);
            return false;
        }
        if (s.ap) return true; /* exact halbtc_*_lps AP exclusion */
    }
    switch (type) {
    case BTC_SET_BL_BT_DISABLE: b->bt_info.bt_disabled = *bv; break;
    case BTC_SET_BL_BT_TRAFFIC_BUSY: b->bt_info.bt_busy = *bv; break;
    case BTC_SET_BL_BT_LIMITED_DIG: b->bt_info.limited_dig = *bv; break;
    case BTC_SET_BL_FORCE_TO_ROAM: b->bt_info.force_to_roam = *bv; break;
    case BTC_SET_BL_TO_REJ_AP_AGG_PKT: b->bt_info.reject_agg_pkt = *bv; break;
    case BTC_SET_BL_BT_CTRL_AGG_SIZE: b->bt_info.bt_ctrl_agg_buf_size = *bv; break;
    case BTC_SET_BL_INC_SCAN_DEV_NUM: b->bt_info.increase_scan_dev_num = *bv; break;
    case BTC_SET_BL_BT_TX_RX_MASK: b->bt_info.bt_tx_rx_mask = *bv; break;
    case BTC_SET_BL_MIRACAST_PLUS_BT: b->bt_info.miracast_plus_bt = *bv; break;
    case BTC_SET_U1_RSSI_ADJ_VAL_FOR_AGC_TABLE_ON:
        b->bt_info.rssi_adjust_for_agc_table_on = *u1; break;
    case BTC_SET_U1_AGG_BUF_SIZE: b->bt_info.agg_buf_size = *u1; break;
    case BTC_SET_ACT_GET_BT_RSSI: return false;
    case BTC_SET_ACT_AGGREGATE_CTRL:
        error = rtwn8723be_runtime_aggregate(sc, &b->bt_info); break;
    case BTC_SET_U1_RSSI_ADJ_VAL_FOR_1ANT_COEX_TYPE:
        b->bt_info.rssi_adjust_for_1ant_coex_type = *u1; break;
    case BTC_SET_U1_LPS_VAL: b->bt_info.lps_val = *u1; break;
    case BTC_SET_U1_RPWM_VAL: b->bt_info.rpwm_val = *u1; break;
    case BTC_SET_ACT_LEAVE_LPS:
    case BTC_SET_ACT_ENTER_LPS:
        if (type == BTC_SET_ACT_ENTER_LPS) {
            b->bt_info.bt_ctrl_lps = true;
            b->bt_info.bt_lps_on = true;
            error = rtwn8723be_runtime_lps(sc, true);
        } else {
            b->bt_info.bt_ctrl_lps = true;
            b->bt_info.bt_lps_on = false;
            error = rtwn8723be_runtime_lps(sc, false);
        }
        break;
    case BTC_SET_ACT_NORMAL_LPS:
    case BTC_SET_ACT_PRE_NORMAL_LPS:
        if (b->bt_info.bt_ctrl_lps) {
            b->bt_info.bt_lps_on = false;
            error = rtwn8723be_runtime_lps(sc, false);
            if (type == BTC_SET_ACT_NORMAL_LPS) b->bt_info.bt_ctrl_lps = false;
        }
        break;
    case BTC_SET_ACT_POST_NORMAL_LPS: b->bt_info.bt_ctrl_lps = false; break;
    case BTC_SET_ACT_DISABLE_LOW_POWER: b->bt_info.bt_disable_low_pwr = *bv; break;
    case BTC_SET_ACT_UPDATE_RAMASK: b->bt_info.ra_mask = *u4; break;
    /* Exact frozen action bodies are empty: halbtcoutsrc.c:751,782-789. */
    case BTC_SET_UI_SCAN_SIG_COMPENSATION:
    case BTC_SET_ACT_SEND_MIMO_PS:
    case BTC_SET_ACT_CTRL_BT_INFO:
    case BTC_SET_ACT_CTRL_BT_COEX:
    case BTC_SET_ACT_CTRL_8723B_ANT:
    default: break;
    }
    rtwn8723be_btc_native_provider_error(sc, error);
    return error == 0;
}

static void
btc_display(void *arg, u8 type, struct seq_file *m)
{
    struct rtwn8723be_btc_wifi_state s;
    struct rtwn8723be_softc *sc = btc_sc(arg);
    if (m == NULL || m->vprintf == NULL) return;
    /* Frozen COEX_STATISTICS and BT_LINK_INFO display functions are empty. */
    if (type != BTC_DBG_DISP_WIFI_STATUS) return;
    if (rtwn8723be_runtime_btc_snapshot(sc, &s) != 0) return;
    seq_printf(m, "WiFi connected=%u scan=%u link=%u channel=%u bw=%u "
        "RSSI=%d busy=%u direction=%u\n", s.connected, s.scanning,
        s.linking, s.channel, s.bandwidth, s.rssi, s.busy, s.direction);
}

int
rtwn8723be_btc_provider_native_context(struct rtwn8723be_softc *sc,
    struct btc_coexist *out)
{
    struct btc_coexist b;
    if (sc == NULL || out == NULL) return EINVAL;
    if (!sc->sc_bt_ant_valid || !sc->sc_package_valid ||
        !sc->sc_phy_identity_valid || !sc->sc_core_initialized ||
        !rtwn8723be_runtime_io_ready(sc)) return ENXIO;
    memset(&b, 0, sizeof(b));
    b.adapter = sc;
    b.binded = true;
    b.chip_interface = BTC_INTF_PCI;
    b.statistics.cnt_bind = 1;
    b.board_info.bt_chip_type = BTC_CHIP_RTL8723B;
    b.board_info.pg_ant_num = b.board_info.btdm_ant_num =
        sc->sc_btdm_ant_num == RTWN8723BE_ANT_X2 ? 2 : 1;
    b.board_info.single_ant_path = sc->sc_single_ant_path;
    b.board_info.btdm_ant_pos = BTC_ANTENNA_AT_MAIN_PORT;
    b.board_info.tfbga_package = sc->sc_package_type > 1;
    /* rtl8723be never writes rtl_hal.rfe_type/ant_div_cfg: zero source state. */
    b.bt_info.agg_buf_size = 5;
    b.btc_read_1byte = btc_read1; b.btc_write_1byte = btc_write1;
    b.btc_write_1byte_bitmask = btc_mask1;
    b.btc_read_2byte = btc_read2; b.btc_write_2byte = btc_write2;
    b.btc_read_4byte = btc_read4; b.btc_write_4byte = btc_write4;
    b.btc_write_local_reg_1byte = btc_local;
    b.btc_set_bb_reg = btc_setbb; b.btc_get_bb_reg = btc_getbb;
    b.btc_set_rf_reg = btc_setrf; b.btc_get_rf_reg = btc_getrf;
    b.btc_fill_h2c = btc_h2c; b.btc_disp_dbg_msg = btc_display;
    b.btc_get = btc_get; b.btc_set = btc_set;
    b.btc_set_bt_reg = btc_setbt; b.btc_get_bt_reg = btc_getbt;
    b.btc_get_bt_coex_supported_feature = btc_feature;
    b.btc_get_bt_coex_supported_version = btc_supported_version;
    b.btc_get_bt_phydm_version = btc_phydm_version;
    b.btc_phydm_modify_ra_pcr_threshold = btc_phydm_threshold;
    b.btc_phydm_query_phy_counter = btc_phydm_counter;
    b.btc_get_ant_det_val_from_bt = btc_ant;
    b.btc_get_ble_scan_type_from_bt = btc_ble_type;
    b.btc_get_ble_scan_para_from_bt = btc_ble_parameters;
    b.btc_get_bt_afh_map_from_bt = btc_afh;
    b.r23be_delay_ms = btc_delay;
    *out = b;
    return rtwn8723be_btc_callbacks_ready(out);
}
