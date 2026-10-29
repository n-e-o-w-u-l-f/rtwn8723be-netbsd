/* SPDX-License-Identifier: GPL-2.0 */
/* Copyright(c) 2009-2014 Realtek Corporation. */
/* Frozen DM functions with test-only Linux ABI shims. */
#include "rtwn8723be_thermal.h"
#include "calibration_test_iface.h"
#include <assert.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef int8_t s8;
struct rtl_dm {
    bool txpower_state_valid;
    bool txpower_tracking, txpower_trackinginit, done_txpower, cck_inch14;
    uint8_t txpower_track_control, txpowercount, tm_trigger;
    uint8_t thermalvalue, thermalvalue_lck, thermalvalue_iqk;
    uint8_t thermalvalue_avg[8], thermalvalue_avg_index;
    int8_t ofdm_index[4], cck_index;
    int8_t delta_power_index[4], delta_power_index_last[4], power_index_offset[4];
    uint8_t swing_idx_ofdm[4], swing_idx_ofdm_base[4];
    uint8_t swing_idx_cck, swing_idx_cck_base;
    int last_error, last_restore_error;
};
struct rtl_efuse { u8 eeprom_thermalmeter; };
#define RF90_PATH_A 0
#define RF90_PATH_B 1
#define RF_T_METER 0x42
#define ROFDM0_XATXIQIMBALANCE 0xc80
#define ROFDM0_XCTXAFE 0xc94
#define ROFDM0_ECCATHRESHOLD 0xc4c
#define MASKDWORD 0xffffffffU
#define MASKH4BITS 0xf0000000U
#define BIT(n) (UINT32_C(1) << (n))
#define TXSCALE_TABLE_SIZE 30
#define OFDM_TABLE_SIZE 37
#define CCK_TABLE_SIZE 33
#define AVG_THERMAL_NUM_8723BE 4
#define IQK_THRESHOLD 8
enum pwr_track_control_method { BBSWING, TXAGC };
struct rtl_phy {
    u8 current_channel;
    struct { long value[1][8]; } iqk_matrix[59];
};
struct rtl_priv {
    void *backend;
    struct rtl_dm dm;
    struct rtl_phy phy;
    struct rtl_efuse efuse;
    struct rtwn8723be_calibration_state *calibration;
};
struct ieee80211_hw { struct rtl_priv *priv; };
#define rtl_priv(hw) ((hw)->priv)
#define rtl_efuse(priv) (&(priv)->efuse)
#define rtl_dm(priv) (&(priv)->dm)
#define rtl_dbg(...) ((void)0)
#define rtl_set_bbreg(hw,r,m,v) test_bb_write_raw((hw)->priv->backend,(r),(m),(v))
#define rtl_get_rfreg(hw,p,r,m) test_rf_read_raw((hw)->priv->backend,(p),(r),(m))
#define rtl_write_byte(priv,r,v) test_mac_write_raw((priv)->backend,(r),1U,(v))
#define rtl8723be_phy_set_txpower_level(hw,c) ((void)(hw), (void)(c), assert(false))
static void thermal_oracle_lck(struct ieee80211_hw *hw)
{
    test_oracle_lck(hw->priv->backend, false);
}
static void thermal_oracle_iqk(struct ieee80211_hw *hw, bool recovery)
{
    struct rtwn8723be_calibration_state *cal = hw->priv->calibration;
    struct test_oracle_result out = {0};
    unsigned int i;
    memcpy(out.recovery, cal->recovery, sizeof(out.recovery));
    test_oracle_iqk(hw->priv->backend, recovery, &out);
    memcpy(cal->recovery, out.recovery, sizeof(out.recovery));
    memcpy(cal->iqk_matrix, out.matrix, sizeof(out.matrix));
    cal->reg_e94 = out.reg[0];
    cal->reg_e9c = out.reg[1];
    cal->reg_eb4 = out.reg[2];
    cal->reg_ebc = out.reg[3];
    cal->iqk_matrix_done = out.matrix_done;
    cal->iqk_recovery_valid = true;
    for (i = 0; i < 8; i++)
        hw->priv->phy.iqk_matrix[0].value[0][i] = out.matrix[i];
}
#define rtl8723be_phy_lc_calibrate(hw) thermal_oracle_lck(hw)
#define rtl8723be_phy_iq_calibrate(hw,r) thermal_oracle_iqk(hw,r)
static const u32 ofdmswing_table[] = {
	0x0b40002d, /* 0,  -15.0dB */
	0x0c000030, /* 1,  -14.5dB */
	0x0cc00033, /* 2,  -14.0dB */
	0x0d800036, /* 3,  -13.5dB */
	0x0e400039, /* 4,  -13.0dB */
	0x0f00003c, /* 5,  -12.5dB */
	0x10000040, /* 6,  -12.0dB */
	0x11000044, /* 7,  -11.5dB */
	0x12000048, /* 8,  -11.0dB */
	0x1300004c, /* 9,  -10.5dB */
	0x14400051, /* 10, -10.0dB */
	0x15800056, /* 11, -9.5dB */
	0x16c0005b, /* 12, -9.0dB */
	0x18000060, /* 13, -8.5dB */
	0x19800066, /* 14, -8.0dB */
	0x1b00006c, /* 15, -7.5dB */
	0x1c800072, /* 16, -7.0dB */
	0x1e400079, /* 17, -6.5dB */
	0x20000080, /* 18, -6.0dB */
	0x22000088, /* 19, -5.5dB */
	0x24000090, /* 20, -5.0dB */
	0x26000098, /* 21, -4.5dB */
	0x288000a2, /* 22, -4.0dB */
	0x2ac000ab, /* 23, -3.5dB */
	0x2d4000b5, /* 24, -3.0dB */
	0x300000c0, /* 25, -2.5dB */
	0x32c000cb, /* 26, -2.0dB */
	0x35c000d7, /* 27, -1.5dB */
	0x390000e4, /* 28, -1.0dB */
	0x3c8000f2, /* 29, -0.5dB */
	0x40000100, /* 30, +0dB */
	0x43c0010f, /* 31, +0.5dB */
	0x47c0011f, /* 32, +1.0dB */
	0x4c000130, /* 33, +1.5dB */
	0x50800142, /* 34, +2.0dB */
	0x55400155, /* 35, +2.5dB */
	0x5a400169, /* 36, +3.0dB */
	0x5fc0017f, /* 37, +3.5dB */
	0x65400195, /* 38, +4.0dB */
	0x6b8001ae, /* 39, +4.5dB */
	0x71c001c7, /* 40, +5.0dB */
	0x788001e2, /* 41, +5.5dB */
	0x7f8001fe  /* 42, +6.0dB */
};

static const u8 cckswing_table_ch1ch13[CCK_TABLE_SIZE][8] = {
	{0x09, 0x08, 0x07, 0x06, 0x04, 0x03, 0x01, 0x01}, /*  0, -16.0dB */
	{0x09, 0x09, 0x08, 0x06, 0x05, 0x03, 0x01, 0x01}, /*  1, -15.5dB */
	{0x0a, 0x09, 0x08, 0x07, 0x05, 0x03, 0x02, 0x01}, /*  2, -15.0dB */
	{0x0a, 0x0a, 0x09, 0x07, 0x05, 0x03, 0x02, 0x01}, /*  3, -14.5dB */
	{0x0b, 0x0a, 0x09, 0x08, 0x06, 0x04, 0x02, 0x01}, /*  4, -14.0dB */
	{0x0b, 0x0b, 0x0a, 0x08, 0x06, 0x04, 0x02, 0x01}, /*  5, -13.5dB */
	{0x0c, 0x0c, 0x0a, 0x09, 0x06, 0x04, 0x02, 0x01}, /*  6, -13.0dB */
	{0x0d, 0x0c, 0x0b, 0x09, 0x07, 0x04, 0x02, 0x01}, /*  7, -12.5dB */
	{0x0d, 0x0d, 0x0c, 0x0a, 0x07, 0x05, 0x02, 0x01}, /*  8, -12.0dB */
	{0x0e, 0x0e, 0x0c, 0x0a, 0x08, 0x05, 0x02, 0x01}, /*  9, -11.5dB */
	{0x0f, 0x0f, 0x0d, 0x0b, 0x08, 0x05, 0x03, 0x01}, /* 10, -11.0dB */
	{0x10, 0x10, 0x0e, 0x0b, 0x08, 0x05, 0x03, 0x01}, /* 11, -10.5dB */
	{0x11, 0x11, 0x0f, 0x0c, 0x09, 0x06, 0x03, 0x01}, /* 12, -10.0dB */
	{0x12, 0x12, 0x0f, 0x0c, 0x09, 0x06, 0x03, 0x01}, /* 13, -9.5dB */
	{0x13, 0x13, 0x10, 0x0d, 0x0a, 0x06, 0x03, 0x01}, /* 14, -9.0dB */
	{0x14, 0x14, 0x11, 0x0e, 0x0b, 0x07, 0x03, 0x02}, /* 15, -8.5dB */
	{0x16, 0x15, 0x12, 0x0f, 0x0b, 0x07, 0x04, 0x01}, /* 16, -8.0dB */
	{0x17, 0x16, 0x13, 0x10, 0x0c, 0x08, 0x04, 0x02}, /* 17, -7.5dB */
	{0x18, 0x17, 0x15, 0x11, 0x0c, 0x08, 0x04, 0x02}, /* 18, -7.0dB */
	{0x1a, 0x19, 0x16, 0x12, 0x0d, 0x09, 0x04, 0x02}, /* 19, -6.5dB */
	{0x1b, 0x1a, 0x17, 0x13, 0x0e, 0x09, 0x04, 0x02}, /* 20, -6.0dB */
	{0x1d, 0x1c, 0x18, 0x14, 0x0f, 0x0a, 0x05, 0x02}, /* 21, -5.5dB */
	{0x1f, 0x1e, 0x1a, 0x15, 0x10, 0x0a, 0x05, 0x02}, /* 22, -5.0dB */
	{0x20, 0x20, 0x1b, 0x16, 0x11, 0x08, 0x05, 0x02}, /* 23, -4.5dB */
	{0x22, 0x21, 0x1d, 0x18, 0x11, 0x0b, 0x06, 0x02}, /* 24, -4.0dB */
	{0x24, 0x23, 0x1f, 0x19, 0x13, 0x0c, 0x06, 0x03}, /* 25, -3.5dB */
	{0x26, 0x25, 0x21, 0x1b, 0x14, 0x0d, 0x06, 0x03}, /* 26, -3.0dB */
	{0x28, 0x28, 0x22, 0x1c, 0x15, 0x0d, 0x07, 0x03}, /* 27, -2.5dB */
	{0x2b, 0x2a, 0x25, 0x1e, 0x16, 0x0e, 0x07, 0x03}, /* 28, -2.0dB */
	{0x2d, 0x2d, 0x27, 0x1f, 0x18, 0x0f, 0x08, 0x03}, /* 29, -1.5dB */
	{0x30, 0x2f, 0x29, 0x21, 0x19, 0x10, 0x08, 0x03}, /* 30, -1.0dB */
	{0x33, 0x32, 0x2b, 0x23, 0x1a, 0x11, 0x08, 0x04}, /* 31, -0.5dB */
	{0x36, 0x35, 0x2e, 0x25, 0x1c, 0x12, 0x09, 0x04}  /* 32, +0dB */
};

static const u8 cckswing_table_ch14[CCK_TABLE_SIZE][8] = {
	{0x09, 0x08, 0x07, 0x04, 0x00, 0x00, 0x00, 0x00}, /*  0, -16.0dB */
	{0x09, 0x09, 0x08, 0x05, 0x00, 0x00, 0x00, 0x00}, /*  1, -15.5dB */
	{0x0a, 0x09, 0x08, 0x05, 0x00, 0x00, 0x00, 0x00}, /*  2, -15.0dB */
	{0x0a, 0x0a, 0x09, 0x05, 0x00, 0x00, 0x00, 0x00}, /*  3, -14.5dB */
	{0x0b, 0x0a, 0x09, 0x05, 0x00, 0x00, 0x00, 0x00}, /*  4, -14.0dB */
	{0x0b, 0x0b, 0x0a, 0x06, 0x00, 0x00, 0x00, 0x00}, /*  5, -13.5dB */
	{0x0c, 0x0c, 0x0a, 0x06, 0x00, 0x00, 0x00, 0x00}, /*  6, -13.0dB */
	{0x0d, 0x0c, 0x0b, 0x06, 0x00, 0x00, 0x00, 0x00}, /*  7, -12.5dB */
	{0x0d, 0x0d, 0x0c, 0x07, 0x00, 0x00, 0x00, 0x00}, /*  8, -12.0dB */
	{0x0e, 0x0e, 0x0c, 0x07, 0x00, 0x00, 0x00, 0x00}, /*  9, -11.5dB */
	{0x0f, 0x0f, 0x0d, 0x08, 0x00, 0x00, 0x00, 0x00}, /* 10, -11.0dB */
	{0x10, 0x10, 0x0e, 0x08, 0x00, 0x00, 0x00, 0x00}, /* 11, -10.5dB */
	{0x11, 0x11, 0x0f, 0x09, 0x00, 0x00, 0x00, 0x00}, /* 12, -10.0dB */
	{0x12, 0x12, 0x0f, 0x09, 0x00, 0x00, 0x00, 0x00}, /* 13, -9.5dB */
	{0x13, 0x13, 0x10, 0x0a, 0x00, 0x00, 0x00, 0x00}, /* 14, -9.0dB */
	{0x14, 0x14, 0x11, 0x0a, 0x00, 0x00, 0x00, 0x00}, /* 15, -8.5dB */
	{0x16, 0x15, 0x12, 0x0b, 0x00, 0x00, 0x00, 0x00}, /* 16, -8.0dB */
	{0x17, 0x16, 0x13, 0x0b, 0x00, 0x00, 0x00, 0x00}, /* 17, -7.5dB */
	{0x18, 0x17, 0x15, 0x0c, 0x00, 0x00, 0x00, 0x00}, /* 18, -7.0dB */
	{0x1a, 0x19, 0x16, 0x0d, 0x00, 0x00, 0x00, 0x00}, /* 19, -6.5dB */
	{0x1b, 0x1a, 0x17, 0x0e, 0x00, 0x00, 0x00, 0x00}, /* 20, -6.0dB */
	{0x1d, 0x1c, 0x18, 0x0e, 0x00, 0x00, 0x00, 0x00}, /* 21, -5.5dB */
	{0x1f, 0x1e, 0x1a, 0x0f, 0x00, 0x00, 0x00, 0x00}, /* 22, -5.0dB */
	{0x20, 0x20, 0x1b, 0x10, 0x00, 0x00, 0x00, 0x00}, /* 23, -4.5dB */
	{0x22, 0x21, 0x1d, 0x11, 0x00, 0x00, 0x00, 0x00}, /* 24, -4.0dB */
	{0x24, 0x23, 0x1f, 0x12, 0x00, 0x00, 0x00, 0x00}, /* 25, -3.5dB */
	{0x26, 0x25, 0x21, 0x13, 0x00, 0x00, 0x00, 0x00}, /* 26, -3.0dB */
	{0x28, 0x28, 0x24, 0x14, 0x00, 0x00, 0x00, 0x00}, /* 27, -2.5dB */
	{0x2b, 0x2a, 0x25, 0x15, 0x00, 0x00, 0x00, 0x00}, /* 28, -2.0dB */
	{0x2d, 0x2d, 0x17, 0x17, 0x00, 0x00, 0x00, 0x00}, /* 29, -1.5dB */
	{0x30, 0x2f, 0x29, 0x18, 0x00, 0x00, 0x00, 0x00}, /* 30, -1.0dB */
	{0x33, 0x32, 0x2b, 0x19, 0x00, 0x00, 0x00, 0x00}, /* 31, -0.5dB */
	{0x36, 0x35, 0x2e, 0x1b, 0x00, 0x00, 0x00, 0x00}  /* 32, +0dB */
};


static void rtl8723be_set_iqk_matrix(struct ieee80211_hw *hw, u8 ofdm_index,
				     u8 rfpath, long iqk_result_x,
				     long iqk_result_y)
{
	long ele_a = 0, ele_d, ele_c = 0, value32;

	if (ofdm_index >= 43)
		ofdm_index = 43 - 1;

	ele_d = (ofdmswing_table[ofdm_index] & 0xFFC00000) >> 22;

	if (iqk_result_x != 0) {
		if ((iqk_result_x & 0x00000200) != 0)
			iqk_result_x = iqk_result_x | 0xFFFFFC00;
		ele_a = ((iqk_result_x * ele_d) >> 8) & 0x000003FF;

		if ((iqk_result_y & 0x00000200) != 0)
			iqk_result_y = iqk_result_y | 0xFFFFFC00;
		ele_c = ((iqk_result_y * ele_d) >> 8) & 0x000003FF;

		switch (rfpath) {
		case RF90_PATH_A:
			value32 = (ele_d << 22) |
				((ele_c & 0x3F) << 16) | ele_a;
			rtl_set_bbreg(hw, ROFDM0_XATXIQIMBALANCE, MASKDWORD,
				      value32);
			value32 = (ele_c & 0x000003C0) >> 6;
			rtl_set_bbreg(hw, ROFDM0_XCTXAFE, MASKH4BITS, value32);
			value32 = ((iqk_result_x * ele_d) >> 7) & 0x01;
			rtl_set_bbreg(hw, ROFDM0_ECCATHRESHOLD, BIT(24),
				      value32);
			break;
		default:
			break;
		}
	} else {
		switch (rfpath) {
		case RF90_PATH_A:
			rtl_set_bbreg(hw, ROFDM0_XATXIQIMBALANCE, MASKDWORD,
				      ofdmswing_table[ofdm_index]);
			rtl_set_bbreg(hw, ROFDM0_XCTXAFE, MASKH4BITS, 0x00);
			rtl_set_bbreg(hw, ROFDM0_ECCATHRESHOLD, BIT(24), 0x00);
			break;
		default:
			break;
		}
	}
}

static void rtl8723be_dm_tx_power_track_set_power(struct ieee80211_hw *hw,
					enum pwr_track_control_method method,
					u8 rfpath, u8 idx)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rtl_phy *rtlphy = &rtlpriv->phy;
	struct rtl_dm *rtldm = rtl_dm(rtl_priv(hw));
	u8 swing_idx_ofdm_limit = 36;

	if (method == TXAGC) {
		rtl8723be_phy_set_txpower_level(hw, rtlphy->current_channel);
	} else if (method == BBSWING) {
		if (rtldm->swing_idx_cck >= CCK_TABLE_SIZE)
			rtldm->swing_idx_cck = CCK_TABLE_SIZE - 1;

		if (!rtldm->cck_inch14) {
			rtl_write_byte(rtlpriv, 0xa22,
			    cckswing_table_ch1ch13[rtldm->swing_idx_cck][0]);
			rtl_write_byte(rtlpriv, 0xa23,
			    cckswing_table_ch1ch13[rtldm->swing_idx_cck][1]);
			rtl_write_byte(rtlpriv, 0xa24,
			    cckswing_table_ch1ch13[rtldm->swing_idx_cck][2]);
			rtl_write_byte(rtlpriv, 0xa25,
			    cckswing_table_ch1ch13[rtldm->swing_idx_cck][3]);
			rtl_write_byte(rtlpriv, 0xa26,
			    cckswing_table_ch1ch13[rtldm->swing_idx_cck][4]);
			rtl_write_byte(rtlpriv, 0xa27,
			    cckswing_table_ch1ch13[rtldm->swing_idx_cck][5]);
			rtl_write_byte(rtlpriv, 0xa28,
			    cckswing_table_ch1ch13[rtldm->swing_idx_cck][6]);
			rtl_write_byte(rtlpriv, 0xa29,
			    cckswing_table_ch1ch13[rtldm->swing_idx_cck][7]);
		} else {
			rtl_write_byte(rtlpriv, 0xa22,
			    cckswing_table_ch14[rtldm->swing_idx_cck][0]);
			rtl_write_byte(rtlpriv, 0xa23,
			    cckswing_table_ch14[rtldm->swing_idx_cck][1]);
			rtl_write_byte(rtlpriv, 0xa24,
			    cckswing_table_ch14[rtldm->swing_idx_cck][2]);
			rtl_write_byte(rtlpriv, 0xa25,
			    cckswing_table_ch14[rtldm->swing_idx_cck][3]);
			rtl_write_byte(rtlpriv, 0xa26,
			    cckswing_table_ch14[rtldm->swing_idx_cck][4]);
			rtl_write_byte(rtlpriv, 0xa27,
			    cckswing_table_ch14[rtldm->swing_idx_cck][5]);
			rtl_write_byte(rtlpriv, 0xa28,
			    cckswing_table_ch14[rtldm->swing_idx_cck][6]);
			rtl_write_byte(rtlpriv, 0xa29,
			    cckswing_table_ch14[rtldm->swing_idx_cck][7]);
		}

		if (rfpath == RF90_PATH_A) {
			if (rtldm->swing_idx_ofdm[RF90_PATH_A] <
			    swing_idx_ofdm_limit)
				swing_idx_ofdm_limit =
					rtldm->swing_idx_ofdm[RF90_PATH_A];

			rtl8723be_set_iqk_matrix(hw,
				rtldm->swing_idx_ofdm[rfpath], rfpath,
				rtlphy->iqk_matrix[idx].value[0][0],
				rtlphy->iqk_matrix[idx].value[0][1]);
		} else if (rfpath == RF90_PATH_B) {
			if (rtldm->swing_idx_ofdm[RF90_PATH_B] <
			    swing_idx_ofdm_limit)
				swing_idx_ofdm_limit =
					rtldm->swing_idx_ofdm[RF90_PATH_B];

			rtl8723be_set_iqk_matrix(hw,
				rtldm->swing_idx_ofdm[rfpath], rfpath,
				rtlphy->iqk_matrix[idx].value[0][4],
				rtlphy->iqk_matrix[idx].value[0][5]);
		}
	} else {
		return;
	}
}

static void rtl8723be_dm_txpower_tracking_callback_thermalmeter(
							struct ieee80211_hw *hw)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rtl_efuse *rtlefuse = rtl_efuse(rtl_priv(hw));
	struct rtl_dm	*rtldm = rtl_dm(rtl_priv(hw));
	u8 thermalvalue = 0, delta, delta_lck, delta_iqk;
	u8 thermalvalue_avg_count = 0;
	u32 thermalvalue_avg = 0;
	int i = 0;

	u8 ofdm_min_index = 6;
	u8 index_for_channel = 0;

	static const s8 delta_swing_table_idx_tup_a[TXSCALE_TABLE_SIZE] = {
		0, 0, 1, 2, 2, 2, 3, 3, 3, 4,  5,
		5, 6, 6, 7, 7, 8, 8, 9, 9, 9, 10,
		10, 11, 11, 12, 12, 13, 14, 15};
	static const s8 delta_swing_table_idx_tdown_a[TXSCALE_TABLE_SIZE] = {
		0, 0, 1, 2, 2, 2, 3, 3, 3, 4,  5,
		5, 6, 6, 6, 6, 7, 7, 7, 8, 8,  9,
		9, 10, 10, 11, 12, 13, 14, 15};

	/*Initilization ( 7 steps in total )*/
	rtlpriv->dm.txpower_trackinginit = true;
	rtl_dbg(rtlpriv, COMP_POWER_TRACKING, DBG_LOUD,
		"%s\n", __func__);

	thermalvalue = (u8)rtl_get_rfreg(hw,
		RF90_PATH_A, RF_T_METER, 0xfc00);
	if (!rtlpriv->dm.txpower_track_control || thermalvalue == 0 ||
	    rtlefuse->eeprom_thermalmeter == 0xFF)
		return;
	rtl_dbg(rtlpriv, COMP_POWER_TRACKING, DBG_LOUD,
		"Readback Thermal Meter = 0x%x pre thermal meter 0x%x eeprom_thermalmeter 0x%x\n",
		thermalvalue, rtldm->thermalvalue,
		rtlefuse->eeprom_thermalmeter);
	/*3 Initialize ThermalValues of RFCalibrateInfo*/
	if (!rtldm->thermalvalue) {
		rtlpriv->dm.thermalvalue_lck = thermalvalue;
		rtlpriv->dm.thermalvalue_iqk = thermalvalue;
	}

	/*4 Calculate average thermal meter*/
	rtldm->thermalvalue_avg[rtldm->thermalvalue_avg_index] = thermalvalue;
	rtldm->thermalvalue_avg_index++;
	if (rtldm->thermalvalue_avg_index == AVG_THERMAL_NUM_8723BE)
		rtldm->thermalvalue_avg_index = 0;

	for (i = 0; i < AVG_THERMAL_NUM_8723BE; i++) {
		if (rtldm->thermalvalue_avg[i]) {
			thermalvalue_avg += rtldm->thermalvalue_avg[i];
			thermalvalue_avg_count++;
		}
	}

	if (thermalvalue_avg_count)
		thermalvalue = (u8)(thermalvalue_avg / thermalvalue_avg_count);

	/* 5 Calculate delta, delta_LCK, delta_IQK.*/
	delta = (thermalvalue > rtlpriv->dm.thermalvalue) ?
		(thermalvalue - rtlpriv->dm.thermalvalue) :
		(rtlpriv->dm.thermalvalue - thermalvalue);
	delta_lck = (thermalvalue > rtlpriv->dm.thermalvalue_lck) ?
		    (thermalvalue - rtlpriv->dm.thermalvalue_lck) :
		    (rtlpriv->dm.thermalvalue_lck - thermalvalue);
	delta_iqk = (thermalvalue > rtlpriv->dm.thermalvalue_iqk) ?
		    (thermalvalue - rtlpriv->dm.thermalvalue_iqk) :
		    (rtlpriv->dm.thermalvalue_iqk - thermalvalue);

	rtl_dbg(rtlpriv, COMP_POWER_TRACKING, DBG_LOUD,
		"Readback Thermal Meter = 0x%x pre thermal meter 0x%x eeprom_thermalmeter 0x%x delta 0x%x delta_lck 0x%x delta_iqk 0x%x\n",
		thermalvalue, rtlpriv->dm.thermalvalue,
		rtlefuse->eeprom_thermalmeter, delta, delta_lck, delta_iqk);
	/* 6 If necessary, do LCK.*/
	if (delta_lck >= IQK_THRESHOLD) {
		rtlpriv->dm.thermalvalue_lck = thermalvalue;
		rtl8723be_phy_lc_calibrate(hw);
	}

	/* 7 If necessary, move the index of
	 * swing table to adjust Tx power.
	 */
	if (delta > 0 && rtlpriv->dm.txpower_track_control) {
		delta = (thermalvalue > rtlefuse->eeprom_thermalmeter) ?
			(thermalvalue - rtlefuse->eeprom_thermalmeter) :
			(rtlefuse->eeprom_thermalmeter - thermalvalue);

		if (delta >= TXSCALE_TABLE_SIZE)
			delta = TXSCALE_TABLE_SIZE - 1;
		/* 7.1 Get the final CCK_index and
		 * OFDM_index for each swing table.
		 */
		if (thermalvalue > rtlefuse->eeprom_thermalmeter) {
			rtldm->delta_power_index_last[RF90_PATH_A] =
					rtldm->delta_power_index[RF90_PATH_A];
			rtldm->delta_power_index[RF90_PATH_A] =
					delta_swing_table_idx_tup_a[delta];
		} else {
			rtldm->delta_power_index_last[RF90_PATH_A] =
					rtldm->delta_power_index[RF90_PATH_A];
			rtldm->delta_power_index[RF90_PATH_A] =
				-1 * delta_swing_table_idx_tdown_a[delta];
		}

		/* 7.2 Handle boundary conditions of index.*/
		if (rtldm->delta_power_index[RF90_PATH_A] ==
		    rtldm->delta_power_index_last[RF90_PATH_A])
			rtldm->power_index_offset[RF90_PATH_A] = 0;
		else
			rtldm->power_index_offset[RF90_PATH_A] =
				rtldm->delta_power_index[RF90_PATH_A] -
				rtldm->delta_power_index_last[RF90_PATH_A];

		rtldm->ofdm_index[0] =
			rtldm->swing_idx_ofdm_base[RF90_PATH_A] +
			rtldm->power_index_offset[RF90_PATH_A];
		rtldm->cck_index = rtldm->swing_idx_cck_base +
				   rtldm->power_index_offset[RF90_PATH_A];

		rtldm->swing_idx_cck = rtldm->cck_index;
		rtldm->swing_idx_ofdm[0] = rtldm->ofdm_index[0];

		if (rtldm->ofdm_index[0] > OFDM_TABLE_SIZE - 1)
			rtldm->ofdm_index[0] = OFDM_TABLE_SIZE - 1;
		else if (rtldm->ofdm_index[0] < ofdm_min_index)
			rtldm->ofdm_index[0] = ofdm_min_index;

		if (rtldm->cck_index > CCK_TABLE_SIZE - 1)
			rtldm->cck_index = CCK_TABLE_SIZE - 1;
		else if (rtldm->cck_index < 0)
			rtldm->cck_index = 0;
	} else {
		rtldm->power_index_offset[RF90_PATH_A] = 0;
	}

	if ((rtldm->power_index_offset[RF90_PATH_A] != 0) &&
	    (rtldm->txpower_track_control)) {
		rtldm->done_txpower = true;
		rtl8723be_dm_tx_power_track_set_power(hw, BBSWING, 0,
						      index_for_channel);

		rtldm->swing_idx_cck_base = rtldm->swing_idx_cck;
		rtldm->swing_idx_ofdm_base[RF90_PATH_A] =
						rtldm->swing_idx_ofdm[0];
		rtldm->thermalvalue = thermalvalue;
	}

	if (delta_iqk >= IQK_THRESHOLD) {
		rtldm->thermalvalue_iqk = thermalvalue;
		rtl8723be_phy_iq_calibrate(hw, false);
	}

	rtldm->txpowercount = 0;
	rtl_dbg(rtlpriv, COMP_POWER_TRACKING, DBG_LOUD, "end\n");

}
void test_thermal_oracle(void *backend, struct rtwn8723be_thermal_state *dm,
    struct rtwn8723be_calibration_state *calibration, uint8_t eeprom)
{
    struct rtl_priv priv = {0};
    struct ieee80211_hw hw = {&priv};
    unsigned int i;
    priv.backend = backend;
    assert(sizeof(priv.dm) == sizeof(*dm));
    memcpy(&priv.dm, dm, sizeof(*dm));
    priv.efuse.eeprom_thermalmeter = eeprom;
    priv.calibration = calibration;
    for (i = 0; i < 8; i++)
        priv.phy.iqk_matrix[0].value[0][i] = calibration->iqk_matrix[i];
    rtl8723be_dm_txpower_tracking_callback_thermalmeter(&hw);
    memcpy(dm, &priv.dm, sizeof(*dm));
}
