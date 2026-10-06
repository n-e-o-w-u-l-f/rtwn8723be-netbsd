/* SPDX-License-Identifier: GPL-2.0 */
/* Copyright(c) 2009-2014 Realtek Corporation. */
/* Frozen Linux bodies, without Linux headers; HP differential test only. */
#include "calibration_test_iface.h"
#include <stddef.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef int32_t s32;
#define RFPGA0_IQK 0xe28
#define MASKDWORD 0xffffffff
#define RF_WE_LUT 0xEF
#define RFREG_OFFSET_MASK 0xfffff
#define RF_RCK_OS 0x30
#define RF_TXPA_G1 0x31
#define RF_TXPA_G2 0x32
#define RTX_IQK 0xe40
#define RRX_IQK 0xe44
#define RTX_IQK_TONE_A 0xe30
#define RRX_IQK_TONE_A 0xe34
#define RTX_IQK_TONE_B 0xe50
#define RRX_IQK_TONE_B 0xe54
#define RTX_IQK_PI_A 0xe38
#define RRX_IQK_PI_A 0xe3c
#define RTX_IQK_PI_B 0xe58
#define RRX_IQK_PI_B 0xe5c
#define RIQK_AGC_RSP 0xe4c
#define RIQK_AGC_PTS 0xe48
#define RRX_POWER_AFTER_IQK_A_2 0xeac
#define RTX_POWER_BEFORE_IQK_A 0xe94
#define RTX_POWER_AFTER_IQK_A 0xe9c
#define RRX_POWER_BEFORE_IQK_A_2 0xea4
#define ROFDM0_XBTXIQIMBALANCE 0xc88
#define ROFDM0_ECCATHRESHOLD 0xc4c
#define ROFDM0_XDTXAFE 0xc9c
#define ROFDM0_XBRXIQIMBALANCE 0xc1c
#define ROFDM0_TRXPATHENABLE 0xc04
#define ROFDM0_TRMUXPAR 0xc08
#define RFPGA0_XCD_RFINTERFACESW 0x874
#define MASKBYTE0 0xff
#define RFPGA0_XA_HSSIPARAMETER1 0x820
#define ROFDM0_XATXIQIMBALANCE 0xc80
#define ROFDM0_XCTXAFE 0xc94
#define ROFDM0_XARXIQIMBALANCE 0xc14
#define RF_T_METER 0x42
#define MASK12BITS 0xfff
#define REG_TXPAUSE 0x0522
#define RF90_PATH_A 0U
#define ROFDM0_AGCRSSITABLE 0xc78U
#define ROFDM0_RXIQEXTANTA 0xca0U
#define RF90_PATH_B 1U
#define IQK_ADDA_REG_NUM 16
#define IQK_MAC_REG_NUM 4
#define IQK_BB_REG_NUM 9
#define IQK_MATRIX_REG_NUM 8
#define IQK_DELAY_TIME 10
#define MAX_TOLERANCE 5
#define TARGET_CHNL_NUM_2G_5G 59
#define HARDWARE_TYPE_RTL8723AE 8
#define HARDWARE_TYPE_RTL8723BE 11
#define BIT(n) (UINT32_C(1) << (n))
struct rtl_phy {
    u32 adda_backup[16], iqk_mac_backup[4], iqk_bb_backup[9];
    bool lck_inprogress, rfpi_enable;
    u8 current_channel;
    long reg_e94, reg_e9c, reg_eb4, reg_ebc;
    struct { long value[1][8]; bool iqk_done; } iqk_matrix[59];
};
struct rtl_hal { int hw_type, current_bandtype; };
struct rtl_priv {
    void *backend;
    struct rtl_phy phy;
    struct rtl_hal rtlhal;
    struct { int iqk_lock; } locks;
    struct { bool act_scanning; } mac80211;
};
struct ieee80211_hw { void *backend; struct rtl_priv *priv; };
#define rtl_priv(hw) ((hw)->priv)
#define rtl_hal(priv) (&(priv)->rtlhal)
#define rtl_dbg(...) ((void)0)
#define RTPRINT(...) ((void)0)
#define spin_lock(...) ((void)0)
#define spin_unlock(...) ((void)0)
#define mdelay(ms) test_delay_raw(hw->backend, (ms) * 1000U)
#define udelay(us) test_delay_raw(hw->backend, (us))
#define rtl_get_bbreg(hw,r,m) test_bb_read_raw((hw)->backend,(r),(m))
#define rtl_set_bbreg(hw,r,m,v) test_bb_write_raw((hw)->backend,(r),(m),(v))
#define rtl_get_rfreg(hw,p,r,m) test_rf_read_raw((hw)->backend,(p),(r),(m))
#define rtl_set_rfreg(hw,p,r,m,v) test_rf_write_raw((hw)->backend,(p),(r),(m),(v))
#define rtl_read_byte(priv,r) test_mac_read_raw((priv)->backend,(r),1U)
#define rtl_read_dword(priv,r) test_mac_read_raw((priv)->backend,(r),4U)
#define rtl_write_byte(priv,r,v) test_mac_write_raw((priv)->backend,(r),1U,(v))
#define rtl_write_dword(priv,r,v) test_mac_write_raw((priv)->backend,(r),4U,(v))

void rtl8723_phy_path_a_fill_iqk_matrix(struct ieee80211_hw *hw,
					bool iqk_ok,
					long result[][8],
					u8 final_candidate,
					bool btxonly)
{
	u32 oldval_0, x, tx0_a, reg;
	long y, tx0_c;

	if (final_candidate == 0xFF) {
		return;
	} else if (iqk_ok) {
		oldval_0 = (rtl_get_bbreg(hw, ROFDM0_XATXIQIMBALANCE,
					  MASKDWORD) >> 22) & 0x3FF;
		x = result[final_candidate][0];
		if ((x & 0x00000200) != 0)
			x = x | 0xFFFFFC00;
		tx0_a = (x * oldval_0) >> 8;
		rtl_set_bbreg(hw, ROFDM0_XATXIQIMBALANCE, 0x3FF, tx0_a);
		rtl_set_bbreg(hw, ROFDM0_ECCATHRESHOLD, BIT(31),
			      ((x * oldval_0 >> 7) & 0x1));
		y = result[final_candidate][1];
		if ((y & 0x00000200) != 0)
			y = y | 0xFFFFFC00;
		tx0_c = (y * oldval_0) >> 8;
		rtl_set_bbreg(hw, ROFDM0_XCTXAFE, 0xF0000000,
			      ((tx0_c & 0x3C0) >> 6));
		rtl_set_bbreg(hw, ROFDM0_XATXIQIMBALANCE, 0x003F0000,
			      (tx0_c & 0x3F));
		rtl_set_bbreg(hw, ROFDM0_ECCATHRESHOLD, BIT(29),
			      ((y * oldval_0 >> 7) & 0x1));
		if (btxonly)
			return;
		reg = result[final_candidate][2];
		rtl_set_bbreg(hw, ROFDM0_XARXIQIMBALANCE, 0x3FF, reg);
		reg = result[final_candidate][3] & 0x3F;
		rtl_set_bbreg(hw, ROFDM0_XARXIQIMBALANCE, 0xFC00, reg);
		reg = (result[final_candidate][3] >> 6) & 0xF;
		rtl_set_bbreg(hw, 0xca0, 0xF0000000, reg);
	}
}

void rtl8723_save_adda_registers(struct ieee80211_hw *hw, u32 *addareg,
				 u32 *addabackup, u32 registernum)
{
	u32 i;

	for (i = 0; i < registernum; i++)
		addabackup[i] = rtl_get_bbreg(hw, addareg[i], MASKDWORD);
}

void rtl8723_phy_save_mac_registers(struct ieee80211_hw *hw,
				    u32 *macreg, u32 *macbackup)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u32 i;

	for (i = 0; i < (IQK_MAC_REG_NUM - 1); i++)
		macbackup[i] = rtl_read_byte(rtlpriv, macreg[i]);
	macbackup[i] = rtl_read_dword(rtlpriv, macreg[i]);
}

void rtl8723_phy_reload_adda_registers(struct ieee80211_hw *hw,
				       u32 *addareg, u32 *addabackup,
				       u32 regiesternum)
{
	u32 i;

	for (i = 0; i < regiesternum; i++)
		rtl_set_bbreg(hw, addareg[i], MASKDWORD, addabackup[i]);
}

void rtl8723_phy_reload_mac_registers(struct ieee80211_hw *hw,
				      u32 *macreg, u32 *macbackup)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u32 i;

	for (i = 0; i < (IQK_MAC_REG_NUM - 1); i++)
		rtl_write_byte(rtlpriv, macreg[i], (u8) macbackup[i]);
	rtl_write_dword(rtlpriv, macreg[i], macbackup[i]);
}

void rtl8723_phy_path_adda_on(struct ieee80211_hw *hw, u32 *addareg,
			      bool is_patha_on, bool is2t)
{
	struct rtl_hal *rtlhal = rtl_hal(rtl_priv(hw));
	u32 pathon;
	u32 i;

	if (rtlhal->hw_type == HARDWARE_TYPE_RTL8723AE) {
		pathon = is_patha_on ? 0x04db25a4 : 0x0b1b25a4;
		if (!is2t) {
			pathon = 0x0bdb25a0;
			rtl_set_bbreg(hw, addareg[0], MASKDWORD, 0x0b1b25a0);
		} else {
			rtl_set_bbreg(hw, addareg[0], MASKDWORD, pathon);
		}
	} else {
		/* rtl8723be */
		pathon = 0x01c00014;
		rtl_set_bbreg(hw, addareg[0], MASKDWORD, pathon);
	}

	for (i = 1; i < IQK_ADDA_REG_NUM; i++)
		rtl_set_bbreg(hw, addareg[i], MASKDWORD, pathon);
}

void rtl8723_phy_mac_setting_calibration(struct ieee80211_hw *hw,
					 u32 *macreg, u32 *macbackup)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u32 i = 0;

	rtl_write_byte(rtlpriv, macreg[i], 0x3F);

	for (i = 1; i < (IQK_MAC_REG_NUM - 1); i++)
		rtl_write_byte(rtlpriv, macreg[i],
			       (u8) (macbackup[i] & (~BIT(3))));
	rtl_write_byte(rtlpriv, macreg[i], (u8) (macbackup[i] & (~BIT(5))));
}

static u8 _rtl8723be_phy_path_a_iqk(struct ieee80211_hw *hw)
{
	u32 reg_eac, reg_e94, reg_e9c, tmp;
	u8 result = 0x00;

	/* leave IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	/* switch to path A */
	rtl_set_bbreg(hw, 0x948, MASKDWORD, 0x00000000);
	/* enable path A PA in TXIQK mode */
	rtl_set_rfreg(hw, RF90_PATH_A, RF_WE_LUT, RFREG_OFFSET_MASK, 0x800a0);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_RCK_OS, RFREG_OFFSET_MASK, 0x20000);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_TXPA_G1, RFREG_OFFSET_MASK, 0x0003f);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_TXPA_G2, RFREG_OFFSET_MASK, 0xc7f87);

	/* 1. TX IQK */
	/* path-A IQK setting */
	/* IQK setting */
	rtl_set_bbreg(hw, RTX_IQK, MASKDWORD, 0x01007c00);
	rtl_set_bbreg(hw, RRX_IQK, MASKDWORD, 0x01004800);
	/* path-A IQK setting */
	rtl_set_bbreg(hw, RTX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	rtl_set_bbreg(hw, RTX_IQK_PI_A, MASKDWORD, 0x821403ea);
	rtl_set_bbreg(hw, RRX_IQK_PI_A, MASKDWORD, 0x28160000);
	rtl_set_bbreg(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	rtl_set_bbreg(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);
	/* LO calibration setting */
	rtl_set_bbreg(hw, RIQK_AGC_RSP, MASKDWORD, 0x00462911);
	/* enter IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path A LOK & IQK */
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	mdelay(IQK_DELAY_TIME);

	/* leave IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);

	/* Check failed */
	reg_eac = rtl_get_bbreg(hw, 0xeac, MASKDWORD);
	reg_e94 = rtl_get_bbreg(hw, 0xe94, MASKDWORD);
	reg_e9c = rtl_get_bbreg(hw, 0xe9c, MASKDWORD);

	if (!(reg_eac & BIT(28)) &&
	    (((reg_e94 & 0x03FF0000) >> 16) != 0x142) &&
	    (((reg_e9c & 0x03FF0000) >> 16) != 0x42))
		result |= 0x01;
	else /* if Tx not OK, ignore Rx */
		return result;

	/* Allen 20131125 */
	tmp = (reg_e9c & 0x03FF0000) >> 16;
	if ((tmp & 0x200) > 0)
		tmp = 0x400 - tmp;

	if (!(reg_eac & BIT(28)) &&
	    (((reg_e94 & 0x03FF0000) >> 16) < 0x110) &&
	    (((reg_e94 & 0x03FF0000) >> 16) > 0xf0) &&
	    (tmp < 0xf))
		result |= 0x01;
	else /* if Tx not OK, ignore Rx */
		return result;

	return result;
}

/* bit0 = 1 => Tx OK, bit1 = 1 => Rx OK */
static u8 _rtl8723be_phy_path_a_rx_iqk(struct ieee80211_hw *hw)
{
	u32 reg_eac, reg_e94, reg_e9c, reg_ea4, u32tmp, tmp;
	u8 result = 0x00;

	/* leave IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);

	/* switch to path A */
	rtl_set_bbreg(hw, 0x948, MASKDWORD, 0x00000000);

	/* 1 Get TXIMR setting */
	/* modify RXIQK mode table */
	rtl_set_rfreg(hw, RF90_PATH_A, RF_WE_LUT, 0x80000, 0x1);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_RCK_OS, RFREG_OFFSET_MASK, 0x30000);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_TXPA_G1, RFREG_OFFSET_MASK, 0x0001f);
	/* LNA2 off, PA on for Dcut */
	rtl_set_rfreg(hw, RF90_PATH_A, RF_TXPA_G2, RFREG_OFFSET_MASK, 0xf7fb7);
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* IQK setting */
	rtl_set_bbreg(hw, RTX_IQK, MASKDWORD, 0x01007c00);
	rtl_set_bbreg(hw, RRX_IQK, MASKDWORD, 0x01004800);

	/* path-A IQK setting */
	rtl_set_bbreg(hw, RTX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	rtl_set_bbreg(hw, RTX_IQK_PI_A, MASKDWORD, 0x82160ff0);
	rtl_set_bbreg(hw, RRX_IQK_PI_A, MASKDWORD, 0x28110000);
	rtl_set_bbreg(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	rtl_set_bbreg(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);

	/* LO calibration setting */
	rtl_set_bbreg(hw, RIQK_AGC_RSP, MASKDWORD, 0x0046a911);

	/* enter IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path A LOK & IQK */
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	mdelay(IQK_DELAY_TIME);

	/* leave IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);

	/* Check failed */
	reg_eac = rtl_get_bbreg(hw, RRX_POWER_AFTER_IQK_A_2, MASKDWORD);
	reg_e94 = rtl_get_bbreg(hw, RTX_POWER_BEFORE_IQK_A, MASKDWORD);
	reg_e9c = rtl_get_bbreg(hw, RTX_POWER_AFTER_IQK_A, MASKDWORD);

	if (!(reg_eac & BIT(28)) &&
	    (((reg_e94 & 0x03FF0000) >> 16) != 0x142) &&
	    (((reg_e9c & 0x03FF0000) >> 16) != 0x42))
		result |= 0x01;
	else /* if Tx not OK, ignore Rx */
		return result;

	/* Allen 20131125 */
	tmp = (reg_e9c & 0x03FF0000) >> 16;
	if ((tmp & 0x200) > 0)
		tmp = 0x400 - tmp;

	if (!(reg_eac & BIT(28)) &&
	    (((reg_e94 & 0x03FF0000) >> 16) < 0x110) &&
	    (((reg_e94 & 0x03FF0000) >> 16) > 0xf0) &&
	    (tmp < 0xf))
		result |= 0x01;
	else /* if Tx not OK, ignore Rx */
		return result;

	u32tmp = 0x80007C00 | (reg_e94 & 0x3FF0000) |
		 ((reg_e9c & 0x3FF0000) >> 16);
	rtl_set_bbreg(hw, RTX_IQK, MASKDWORD, u32tmp);

	/* 1 RX IQK */
	/* modify RXIQK mode table */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_WE_LUT, 0x80000, 0x1);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_RCK_OS, RFREG_OFFSET_MASK, 0x30000);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_TXPA_G1, RFREG_OFFSET_MASK, 0x0001f);
	/* LAN2 on, PA off for Dcut */
	rtl_set_rfreg(hw, RF90_PATH_A, RF_TXPA_G2, RFREG_OFFSET_MASK, 0xf7d77);

	/* PA, PAD setting */
	rtl_set_rfreg(hw, RF90_PATH_A, 0xdf, RFREG_OFFSET_MASK, 0xf80);
	rtl_set_rfreg(hw, RF90_PATH_A, 0x55, RFREG_OFFSET_MASK, 0x4021f);

	/* IQK setting */
	rtl_set_bbreg(hw, RRX_IQK, MASKDWORD, 0x01004800);

	/* path-A IQK setting */
	rtl_set_bbreg(hw, RTX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	rtl_set_bbreg(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	rtl_set_bbreg(hw, RTX_IQK_PI_A, MASKDWORD, 0x82110000);
	rtl_set_bbreg(hw, RRX_IQK_PI_A, MASKDWORD, 0x2816001f);
	rtl_set_bbreg(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	rtl_set_bbreg(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);

	/* LO calibration setting */
	rtl_set_bbreg(hw, RIQK_AGC_RSP, MASKDWORD, 0x0046a8d1);

	/* enter IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path A LOK & IQK */
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	mdelay(IQK_DELAY_TIME);

	/* leave IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);

	/* Check failed */
	reg_eac = rtl_get_bbreg(hw, RRX_POWER_AFTER_IQK_A_2, MASKDWORD);
	reg_ea4 = rtl_get_bbreg(hw, RRX_POWER_BEFORE_IQK_A_2, MASKDWORD);

	/* leave IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	rtl_set_rfreg(hw, RF90_PATH_A, 0xdf, RFREG_OFFSET_MASK, 0x780);

	/* Allen 20131125 */
	tmp = (reg_eac & 0x03FF0000) >> 16;
	if ((tmp & 0x200) > 0)
		tmp = 0x400 - tmp;
	/* if Tx is OK, check whether Rx is OK */
	if (!(reg_eac & BIT(27)) &&
	    (((reg_ea4 & 0x03FF0000) >> 16) != 0x132) &&
	    (((reg_eac & 0x03FF0000) >> 16) != 0x36))
		result |= 0x02;
	else if (!(reg_eac & BIT(27)) &&
		 (((reg_ea4 & 0x03FF0000) >> 16) < 0x110) &&
		 (((reg_ea4 & 0x03FF0000) >> 16) > 0xf0) &&
		 (tmp < 0xf))
		result |= 0x02;

	return result;
}

static u8 _rtl8723be_phy_path_b_iqk(struct ieee80211_hw *hw)
{
	u32 reg_eac, reg_e94, reg_e9c, tmp;
	u8 result = 0x00;

	/* leave IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	/* switch to path B */
	rtl_set_bbreg(hw, 0x948, MASKDWORD, 0x00000280);

	/* enable path B PA in TXIQK mode */
	rtl_set_rfreg(hw, RF90_PATH_A, 0xed, RFREG_OFFSET_MASK, 0x00020);
	rtl_set_rfreg(hw, RF90_PATH_A, 0x43, RFREG_OFFSET_MASK, 0x40fc1);

	/* 1 Tx IQK */
	/* IQK setting */
	rtl_set_bbreg(hw, RTX_IQK, MASKDWORD, 0x01007c00);
	rtl_set_bbreg(hw, RRX_IQK, MASKDWORD, 0x01004800);
	/* path-A IQK setting */
	rtl_set_bbreg(hw, RTX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	rtl_set_bbreg(hw, RTX_IQK_PI_A, MASKDWORD, 0x821403ea);
	rtl_set_bbreg(hw, RRX_IQK_PI_A, MASKDWORD, 0x28110000);
	rtl_set_bbreg(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	rtl_set_bbreg(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);

	/* LO calibration setting */
	rtl_set_bbreg(hw, RIQK_AGC_RSP, MASKDWORD, 0x00462911);

	/* enter IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path B LOK & IQK */
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	mdelay(IQK_DELAY_TIME);

	/* leave IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);

	/* Check failed */
	reg_eac = rtl_get_bbreg(hw, RRX_POWER_AFTER_IQK_A_2, MASKDWORD);
	reg_e94 = rtl_get_bbreg(hw, RTX_POWER_BEFORE_IQK_A, MASKDWORD);
	reg_e9c = rtl_get_bbreg(hw, RTX_POWER_AFTER_IQK_A, MASKDWORD);

	if (!(reg_eac & BIT(28)) &&
	    (((reg_e94 & 0x03FF0000) >> 16) != 0x142) &&
	    (((reg_e9c & 0x03FF0000) >> 16) != 0x42))
		result |= 0x01;
	else
		return result;

	/* Allen 20131125 */
	tmp = (reg_e9c & 0x03FF0000) >> 16;
	if ((tmp & 0x200) > 0)
		tmp = 0x400 - tmp;

	if (!(reg_eac & BIT(28)) &&
	    (((reg_e94 & 0x03FF0000) >> 16) < 0x110) &&
	    (((reg_e94 & 0x03FF0000) >> 16) > 0xf0) &&
	    (tmp < 0xf))
		result |= 0x01;
	else
		return result;

	return result;
}

/* bit0 = 1 => Tx OK, bit1 = 1 => Rx OK */
static u8 _rtl8723be_phy_path_b_rx_iqk(struct ieee80211_hw *hw)
{
	u32 reg_e94, reg_e9c, reg_ea4, reg_eac, u32tmp, tmp;
	u8 result = 0x00;

	/* leave IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	/* switch to path B */
	rtl_set_bbreg(hw, 0x948, MASKDWORD, 0x00000280);

	/* 1 Get TXIMR setting */
	/* modify RXIQK mode table */
	rtl_set_rfreg(hw, RF90_PATH_A, RF_WE_LUT, RFREG_OFFSET_MASK, 0x800a0);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_RCK_OS, RFREG_OFFSET_MASK, 0x30000);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_TXPA_G1, RFREG_OFFSET_MASK, 0x0001f);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_TXPA_G2, RFREG_OFFSET_MASK, 0xf7ff7);

	/* open PA S1 & SMIXER */
	rtl_set_rfreg(hw, RF90_PATH_A, 0xed, RFREG_OFFSET_MASK, 0x00020);
	rtl_set_rfreg(hw, RF90_PATH_A, 0x43, RFREG_OFFSET_MASK, 0x60fed);

	/* IQK setting */
	rtl_set_bbreg(hw, RTX_IQK, MASKDWORD, 0x01007c00);
	rtl_set_bbreg(hw, RRX_IQK, MASKDWORD, 0x01004800);

	/* path-B IQK setting */
	rtl_set_bbreg(hw, RTX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	rtl_set_bbreg(hw, RTX_IQK_PI_A, MASKDWORD, 0x82160ff0);
	rtl_set_bbreg(hw, RRX_IQK_PI_A, MASKDWORD, 0x28110000);
	rtl_set_bbreg(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	rtl_set_bbreg(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);

	/* LO calibration setting */
	rtl_set_bbreg(hw, RIQK_AGC_RSP, MASKDWORD, 0x0046a911);
	/* enter IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path B TXIQK @ RXIQK */
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	mdelay(IQK_DELAY_TIME);

	/* leave IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	/* Check failed */
	reg_eac = rtl_get_bbreg(hw, RRX_POWER_AFTER_IQK_A_2, MASKDWORD);
	reg_e94 = rtl_get_bbreg(hw, RTX_POWER_BEFORE_IQK_A, MASKDWORD);
	reg_e9c = rtl_get_bbreg(hw, RTX_POWER_AFTER_IQK_A, MASKDWORD);

	if (!(reg_eac & BIT(28)) &&
	    (((reg_e94 & 0x03FF0000) >> 16) != 0x142) &&
	    (((reg_e9c & 0x03FF0000) >> 16) != 0x42))
		result |= 0x01;
	else	/* if Tx not OK, ignore Rx */
		return result;

	/* Allen 20131125 */
	tmp = (reg_e9c & 0x03FF0000) >> 16;
	if ((tmp & 0x200) > 0)
		tmp = 0x400 - tmp;

	if (!(reg_eac & BIT(28)) &&
	    (((reg_e94 & 0x03FF0000) >> 16) < 0x110) &&
	    (((reg_e94 & 0x03FF0000) >> 16) > 0xf0) &&
	    (tmp < 0xf))
		result |= 0x01;
	else
		return result;

	u32tmp = 0x80007C00 | (reg_e94 & 0x3FF0000)  |
		 ((reg_e9c & 0x3FF0000) >> 16);
	rtl_set_bbreg(hw, RTX_IQK, MASKDWORD, u32tmp);

	/* 1 RX IQK */

	/* <20121009, Kordan> RF Mode = 3 */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_WE_LUT, 0x80000, 0x1);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_RCK_OS, RFREG_OFFSET_MASK, 0x30000);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_TXPA_G1, RFREG_OFFSET_MASK, 0x0001f);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_TXPA_G2, RFREG_OFFSET_MASK, 0xf7d77);
	rtl_set_rfreg(hw, RF90_PATH_A, RF_WE_LUT, 0x80000, 0x0);

	/* open PA S1 & close SMIXER */
	rtl_set_rfreg(hw, RF90_PATH_A, 0xed, RFREG_OFFSET_MASK, 0x00020);
	rtl_set_rfreg(hw, RF90_PATH_A, 0x43, RFREG_OFFSET_MASK, 0x60fbd);

	/* IQK setting */
	rtl_set_bbreg(hw, RRX_IQK, MASKDWORD, 0x01004800);

	/* path-B IQK setting */
	rtl_set_bbreg(hw, RTX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	rtl_set_bbreg(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	rtl_set_bbreg(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	rtl_set_bbreg(hw, RTX_IQK_PI_A, MASKDWORD, 0x82110000);
	rtl_set_bbreg(hw, RRX_IQK_PI_A, MASKDWORD, 0x2816001f);
	rtl_set_bbreg(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	rtl_set_bbreg(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);

	/* LO calibration setting */
	rtl_set_bbreg(hw, RIQK_AGC_RSP, MASKDWORD, 0x0046a8d1);
	/* enter IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path B LOK & IQK */
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	rtl_set_bbreg(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	mdelay(IQK_DELAY_TIME);

	/* leave IQK mode */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	/* Check failed */
	reg_eac = rtl_get_bbreg(hw, RRX_POWER_AFTER_IQK_A_2, MASKDWORD);
	reg_ea4 = rtl_get_bbreg(hw, RRX_POWER_BEFORE_IQK_A_2, MASKDWORD);

	/* Allen 20131125 */
	tmp = (reg_eac & 0x03FF0000) >> 16;
	if ((tmp & 0x200) > 0)
		tmp = 0x400 - tmp;

	/* if Tx is OK, check whether Rx is OK */
	if (!(reg_eac & BIT(27)) &&
	    (((reg_ea4 & 0x03FF0000) >> 16) != 0x132) &&
	    (((reg_eac & 0x03FF0000) >> 16) != 0x36))
		result |= 0x02;
	else if (!(reg_eac & BIT(27)) &&
		 (((reg_ea4 & 0x03FF0000) >> 16) < 0x110) &&
		 (((reg_ea4 & 0x03FF0000) >> 16) > 0xf0) &&
		 (tmp < 0xf))
		result |= 0x02;
	else
		return result;

	return result;
}

static void _rtl8723be_phy_path_b_fill_iqk_matrix(struct ieee80211_hw *hw,
						  bool b_iqk_ok,
						  long result[][8],
						  u8 final_candidate,
						  bool btxonly)
{
	u32 oldval_1, x, tx1_a, reg;
	long y, tx1_c;

	if (final_candidate == 0xFF) {
		return;
	} else if (b_iqk_ok) {
		oldval_1 = (rtl_get_bbreg(hw, ROFDM0_XBTXIQIMBALANCE,
					  MASKDWORD) >> 22) & 0x3FF;
		x = result[final_candidate][4];
		if ((x & 0x00000200) != 0)
			x = x | 0xFFFFFC00;
		tx1_a = (x * oldval_1) >> 8;
		rtl_set_bbreg(hw, ROFDM0_XBTXIQIMBALANCE, 0x3FF, tx1_a);
		rtl_set_bbreg(hw, ROFDM0_ECCATHRESHOLD, BIT(27),
			      ((x * oldval_1 >> 7) & 0x1));
		y = result[final_candidate][5];
		if ((y & 0x00000200) != 0)
			y = y | 0xFFFFFC00;
		tx1_c = (y * oldval_1) >> 8;
		rtl_set_bbreg(hw, ROFDM0_XDTXAFE, 0xF0000000,
			      ((tx1_c & 0x3C0) >> 6));
		rtl_set_bbreg(hw, ROFDM0_XBTXIQIMBALANCE, 0x003F0000,
			      (tx1_c & 0x3F));
		rtl_set_bbreg(hw, ROFDM0_ECCATHRESHOLD, BIT(25),
			      ((y * oldval_1 >> 7) & 0x1));
		if (btxonly)
			return;
		reg = result[final_candidate][6];
		rtl_set_bbreg(hw, ROFDM0_XBRXIQIMBALANCE, 0x3FF, reg);
		reg = result[final_candidate][7] & 0x3F;
		rtl_set_bbreg(hw, ROFDM0_XBRXIQIMBALANCE, 0xFC00, reg);
		reg = (result[final_candidate][7] >> 6) & 0xF;
		/* rtl_set_bbreg(hw, 0xca0, 0xF0000000, reg); */
	}
}

static bool _rtl8723be_phy_simularity_compare(struct ieee80211_hw *hw,
					      long result[][8], u8 c1, u8 c2)
{
	u32 i, j, diff, simularity_bitmap, bound = 0;

	u8 final_candidate[2] = {0xFF, 0xFF}; /* for path A and path B */
	bool bresult = true; /* is2t = true*/
	s32 tmp1 = 0, tmp2 = 0;

	bound = 8;

	simularity_bitmap = 0;

	for (i = 0; i < bound; i++) {
		if ((i == 1) || (i == 3) || (i == 5) || (i == 7)) {
			if ((result[c1][i] & 0x00000200) != 0)
				tmp1 = result[c1][i] | 0xFFFFFC00;
			else
				tmp1 = result[c1][i];

			if ((result[c2][i] & 0x00000200) != 0)
				tmp2 = result[c2][i] | 0xFFFFFC00;
			else
				tmp2 = result[c2][i];
		} else {
			tmp1 = result[c1][i];
			tmp2 = result[c2][i];
		}

		diff = (tmp1 > tmp2) ? (tmp1 - tmp2) : (tmp2 - tmp1);

		if (diff > MAX_TOLERANCE) {
			if ((i == 2 || i == 6) && !simularity_bitmap) {
				if (result[c1][i] + result[c1][i + 1] == 0)
					final_candidate[(i / 4)] = c2;
				else if (result[c2][i] + result[c2][i + 1] == 0)
					final_candidate[(i / 4)] = c1;
				else
					simularity_bitmap |= (1 << i);
			} else
				simularity_bitmap |= (1 << i);
		}
	}

	if (simularity_bitmap == 0) {
		for (i = 0; i < (bound / 4); i++) {
			if (final_candidate[i] != 0xFF) {
				for (j = i * 4; j < (i + 1) * 4 - 2; j++)
					result[3][j] =
						result[final_candidate[i]][j];
				bresult = false;
			}
		}
		return bresult;
	} else {
		if (!(simularity_bitmap & 0x03)) { /* path A TX OK */
			for (i = 0; i < 2; i++)
				result[3][i] = result[c1][i];
		}
		if (!(simularity_bitmap & 0x0c)) { /* path A RX OK */
			for (i = 2; i < 4; i++)
				result[3][i] = result[c1][i];
		}
		if (!(simularity_bitmap & 0x30)) { /* path B TX OK */
			for (i = 4; i < 6; i++)
				result[3][i] = result[c1][i];
		}
		if (!(simularity_bitmap & 0xc0)) { /* path B RX OK */
			for (i = 6; i < 8; i++)
				result[3][i] = result[c1][i];
		}
		return false;
	}
}

static void _rtl8723be_phy_iq_calibrate(struct ieee80211_hw *hw,
					long result[][8], u8 t, bool is2t)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rtl_phy *rtlphy = &rtlpriv->phy;
	u32 i;
	u8 patha_ok, pathb_ok;
	u32 adda_reg[IQK_ADDA_REG_NUM] = {
		0x85c, 0xe6c, 0xe70, 0xe74,
		0xe78, 0xe7c, 0xe80, 0xe84,
		0xe88, 0xe8c, 0xed0, 0xed4,
		0xed8, 0xedc, 0xee0, 0xeec
	};

	u32 iqk_mac_reg[IQK_MAC_REG_NUM] = {
		0x522, 0x550, 0x551, 0x040
	};
	u32 iqk_bb_reg[IQK_BB_REG_NUM] = {
		ROFDM0_TRXPATHENABLE, ROFDM0_TRMUXPAR,
		RFPGA0_XCD_RFINTERFACESW, 0xb68, 0xb6c,
		0x870, 0x860,
		0x864, 0xa04
	};
	const u32 retrycount = 2;

	u32 path_sel_bb;/* path_sel_rf */

	u8 tmp_reg_c50, tmp_reg_c58;

	tmp_reg_c50 = rtl_get_bbreg(hw, 0xc50, MASKBYTE0);
	tmp_reg_c58 = rtl_get_bbreg(hw, 0xc58, MASKBYTE0);

	if (t == 0) {
		rtl8723_save_adda_registers(hw, adda_reg,
					    rtlphy->adda_backup, 16);
		rtl8723_phy_save_mac_registers(hw, iqk_mac_reg,
					       rtlphy->iqk_mac_backup);
		rtl8723_save_adda_registers(hw, iqk_bb_reg,
					    rtlphy->iqk_bb_backup,
					    IQK_BB_REG_NUM);
	}
	rtl8723_phy_path_adda_on(hw, adda_reg, true, is2t);
	if (t == 0) {
		rtlphy->rfpi_enable = (u8)rtl_get_bbreg(hw,
						RFPGA0_XA_HSSIPARAMETER1,
						BIT(8));
	}

	path_sel_bb = rtl_get_bbreg(hw, 0x948, MASKDWORD);

	rtl8723_phy_mac_setting_calibration(hw, iqk_mac_reg,
					    rtlphy->iqk_mac_backup);
	/*BB Setting*/
	rtl_set_bbreg(hw, 0xa04, 0x0f000000, 0xf);
	rtl_set_bbreg(hw, 0xc04, MASKDWORD, 0x03a05600);
	rtl_set_bbreg(hw, 0xc08, MASKDWORD, 0x000800e4);
	rtl_set_bbreg(hw, 0x874, MASKDWORD, 0x22204000);

	/* path A TX IQK */
	for (i = 0; i < retrycount; i++) {
		patha_ok = _rtl8723be_phy_path_a_iqk(hw);
		if (patha_ok == 0x01) {
			rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD,
				"Path A Tx IQK Success!!\n");
			result[t][0] = (rtl_get_bbreg(hw, 0xe94, MASKDWORD) &
					0x3FF0000) >> 16;
			result[t][1] = (rtl_get_bbreg(hw, 0xe9c, MASKDWORD) &
					0x3FF0000) >> 16;
			break;
		} else {
			rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD,
				"Path A Tx IQK Fail!!\n");
		}
	}
	/* path A RX IQK */
	for (i = 0; i < retrycount; i++) {
		patha_ok = _rtl8723be_phy_path_a_rx_iqk(hw);
		if (patha_ok == 0x03) {
			rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD,
				"Path A Rx IQK Success!!\n");
			result[t][2] = (rtl_get_bbreg(hw, 0xea4, MASKDWORD) &
					0x3FF0000) >> 16;
			result[t][3] = (rtl_get_bbreg(hw, 0xeac, MASKDWORD) &
					0x3FF0000) >> 16;
			break;
		}
		rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD,
			"Path A Rx IQK Fail!!\n");
	}

	if (0x00 == patha_ok)
		rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD, "Path A IQK Fail!!\n");

	if (is2t) {
		/* path B TX IQK */
		for (i = 0; i < retrycount; i++) {
			pathb_ok = _rtl8723be_phy_path_b_iqk(hw);
			if (pathb_ok == 0x01) {
				rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD,
					"Path B Tx IQK Success!!\n");
				result[t][4] = (rtl_get_bbreg(hw, 0xe94,
							      MASKDWORD) &
							      0x3FF0000) >> 16;
				result[t][5] = (rtl_get_bbreg(hw, 0xe9c,
							      MASKDWORD) &
							      0x3FF0000) >> 16;
				break;
			}
			rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD,
				"Path B Tx IQK Fail!!\n");
		}
		/* path B RX IQK */
		for (i = 0; i < retrycount; i++) {
			pathb_ok = _rtl8723be_phy_path_b_rx_iqk(hw);
			if (pathb_ok == 0x03) {
				rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD,
					"Path B Rx IQK Success!!\n");
				result[t][6] = (rtl_get_bbreg(hw, 0xea4,
							      MASKDWORD) &
							      0x3FF0000) >> 16;
				result[t][7] = (rtl_get_bbreg(hw, 0xeac,
							      MASKDWORD) &
							      0x3FF0000) >> 16;
				break;
			}
			rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD,
				"Path B Rx IQK Fail!!\n");
		}
	}

	/* Back to BB mode, load original value */
	rtl_set_bbreg(hw, RFPGA0_IQK, MASKDWORD, 0);

	if (t != 0) {
		rtl8723_phy_reload_adda_registers(hw, adda_reg,
						  rtlphy->adda_backup, 16);
		rtl8723_phy_reload_mac_registers(hw, iqk_mac_reg,
						 rtlphy->iqk_mac_backup);
		rtl8723_phy_reload_adda_registers(hw, iqk_bb_reg,
						  rtlphy->iqk_bb_backup,
						  IQK_BB_REG_NUM);

		rtl_set_bbreg(hw, 0x948, MASKDWORD, path_sel_bb);
		/*rtl_set_rfreg(hw, RF90_PATH_B, 0xb0, 0xfffff, path_sel_rf);*/

		rtl_set_bbreg(hw, 0xc50, MASKBYTE0, 0x50);
		rtl_set_bbreg(hw, 0xc50, MASKBYTE0, tmp_reg_c50);
		if (is2t) {
			rtl_set_bbreg(hw, 0xc58, MASKBYTE0, 0x50);
			rtl_set_bbreg(hw, 0xc58, MASKBYTE0, tmp_reg_c58);
		}
		rtl_set_bbreg(hw, 0xe30, MASKDWORD, 0x01008c00);
		rtl_set_bbreg(hw, 0xe34, MASKDWORD, 0x01008c00);
	}
	rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD, "8723be IQK Finish!!\n");
}

static u8 _get_right_chnl_place_for_iqk(u8 chnl)
{
	static const u8 channel_all[TARGET_CHNL_NUM_2G_5G] = {
		1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
		13, 14, 36, 38, 40, 42, 44, 46,
		48, 50, 52, 54, 56, 58, 60, 62, 64,
		100, 102, 104, 106, 108, 110,
		112, 114, 116, 118, 120, 122,
		124, 126, 128, 130, 132, 134, 136,
		138, 140, 149, 151, 153, 155, 157,
		159, 161, 163, 165
	};
	u8 place = chnl;

	if (chnl > 14) {
		for (place = 14; place < sizeof(channel_all); place++) {
			if (channel_all[place] == chnl)
				return place - 13;
		}
	}
	return 0;
}

static void _rtl8723be_phy_lc_calibrate(struct ieee80211_hw *hw, bool is2t)
{
	u8 tmpreg;
	u32 rf_a_mode = 0, rf_b_mode = 0;
	struct rtl_priv *rtlpriv = rtl_priv(hw);

	tmpreg = rtl_read_byte(rtlpriv, 0xd03);

	if ((tmpreg & 0x70) != 0)
		rtl_write_byte(rtlpriv, 0xd03, tmpreg & 0x8F);
	else
		rtl_write_byte(rtlpriv, REG_TXPAUSE, 0xFF);

	if ((tmpreg & 0x70) != 0) {
		rf_a_mode = rtl_get_rfreg(hw, RF90_PATH_A, 0x00, MASK12BITS);

		if (is2t)
			rf_b_mode = rtl_get_rfreg(hw, RF90_PATH_B, 0x00,
						  MASK12BITS);

		rtl_set_rfreg(hw, RF90_PATH_A, 0x00, MASK12BITS,
			      (rf_a_mode & 0x8FFFF) | 0x10000);

		if (is2t)
			rtl_set_rfreg(hw, RF90_PATH_B, 0x00, MASK12BITS,
				      (rf_b_mode & 0x8FFFF) | 0x10000);
	}
	rtl_get_rfreg(hw, RF90_PATH_A, 0x18, MASK12BITS);

	rtl_set_rfreg(hw, RF90_PATH_A, 0xb0, RFREG_OFFSET_MASK, 0xdfbe0);
	rtl_set_rfreg(hw, RF90_PATH_A, 0x18, MASK12BITS, 0x8c0a);

	/* In order not to disturb BT music when wifi init.(1ant NIC only) */
	/*mdelay(100);*/
	/* In order not to disturb BT music when wifi init.(1ant NIC only) */
	mdelay(50);

	rtl_set_rfreg(hw, RF90_PATH_A, 0xb0, RFREG_OFFSET_MASK, 0xdffe0);

	if ((tmpreg & 0x70) != 0) {
		rtl_write_byte(rtlpriv, 0xd03, tmpreg);
		rtl_set_rfreg(hw, RF90_PATH_A, 0x00, MASK12BITS, rf_a_mode);

		if (is2t)
			rtl_set_rfreg(hw, RF90_PATH_B, 0x00,
				      MASK12BITS, rf_b_mode);
	} else {
		rtl_write_byte(rtlpriv, REG_TXPAUSE, 0x00);
	}
	rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD, "\n");
}

static void _rtl8723be_phy_set_rfpath_switch(struct ieee80211_hw *hw,
					     bool bmain, bool is2t)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	rtl_dbg(rtlpriv, COMP_INIT, DBG_LOUD, "\n");

	if (bmain) /* left antenna */
		rtl_set_bbreg(hw, 0x92C, MASKDWORD, 0x1);
	else
		rtl_set_bbreg(hw, 0x92C, MASKDWORD, 0x2);
}

#undef IQK_ADDA_REG_NUM
#undef IQK_DELAY_TIME
/* IQK is merge from Merge Temp */
void rtl8723be_phy_iq_calibrate(struct ieee80211_hw *hw, bool b_recovery)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rtl_phy *rtlphy = &rtlpriv->phy;
	long result[4][8];
	u8 i, final_candidate, idx;
	bool b_patha_ok, b_pathb_ok;
	long reg_e94, reg_e9c, reg_ea4, reg_eb4, reg_ebc, reg_ec4;
	long reg_tmp = 0;
	bool is12simular, is13simular, is23simular;
	u32 iqk_bb_reg[9] = {
		ROFDM0_XARXIQIMBALANCE,
		ROFDM0_XBRXIQIMBALANCE,
		ROFDM0_ECCATHRESHOLD,
		ROFDM0_AGCRSSITABLE,
		ROFDM0_XATXIQIMBALANCE,
		ROFDM0_XBTXIQIMBALANCE,
		ROFDM0_XCTXAFE,
		ROFDM0_XDTXAFE,
		ROFDM0_RXIQEXTANTA
	};
	u32 path_sel_bb = 0; /* path_sel_rf = 0 */

	if (rtlphy->lck_inprogress)
		return;

	spin_lock(&rtlpriv->locks.iqk_lock);
	rtlphy->lck_inprogress = true;
	spin_unlock(&rtlpriv->locks.iqk_lock);

	if (b_recovery) {
		rtl8723_phy_reload_adda_registers(hw, iqk_bb_reg,
						  rtlphy->iqk_bb_backup, 9);
		goto label_done;
	}
	/* Save RF Path */
	path_sel_bb = rtl_get_bbreg(hw, 0x948, MASKDWORD);
	/* path_sel_rf = rtl_get_rfreg(hw, RF90_PATH_A, 0xb0, 0xfffff); */

	for (i = 0; i < 8; i++) {
		result[0][i] = 0;
		result[1][i] = 0;
		result[2][i] = 0;
		result[3][i] = 0;
	}
	final_candidate = 0xff;
	b_patha_ok = false;
	b_pathb_ok = false;
	is12simular = false;
	is23simular = false;
	is13simular = false;
	for (i = 0; i < 3; i++) {
		_rtl8723be_phy_iq_calibrate(hw, result, i, true);
		if (i == 1) {
			is12simular = _rtl8723be_phy_simularity_compare(hw,
									result,
									0, 1);
			if (is12simular) {
				final_candidate = 0;
				break;
			}
		}
		if (i == 2) {
			is13simular = _rtl8723be_phy_simularity_compare(hw,
									result,
									0, 2);
			if (is13simular) {
				final_candidate = 0;
				break;
			}
			is23simular = _rtl8723be_phy_simularity_compare(hw,
									result,
									1, 2);
			if (is23simular) {
				final_candidate = 1;
			} else {
				for (i = 0; i < 8; i++)
					reg_tmp += result[3][i];

				if (reg_tmp != 0)
					final_candidate = 3;
				else
					final_candidate = 0xFF;
			}
		}
	}
	for (i = 0; i < 4; i++) {
		reg_e94 = result[i][0];
		reg_e9c = result[i][1];
		reg_ea4 = result[i][2];
		reg_eb4 = result[i][4];
		reg_ebc = result[i][5];
		reg_ec4 = result[i][6];
	}
	if (final_candidate != 0xff) {
		reg_e94 = result[final_candidate][0];
		rtlphy->reg_e94 = reg_e94;
		reg_e9c = result[final_candidate][1];
		rtlphy->reg_e9c = reg_e9c;
		reg_ea4 = result[final_candidate][2];
		reg_eb4 = result[final_candidate][4];
		rtlphy->reg_eb4 = reg_eb4;
		reg_ebc = result[final_candidate][5];
		rtlphy->reg_ebc = reg_ebc;
		reg_ec4 = result[final_candidate][6];
		b_patha_ok = true;
		b_pathb_ok = true;
	} else {
		rtlphy->reg_e94 = 0x100;
		rtlphy->reg_eb4 = 0x100;
		rtlphy->reg_e9c = 0x0;
		rtlphy->reg_ebc = 0x0;
	}
	if (reg_e94 != 0)
		rtl8723_phy_path_a_fill_iqk_matrix(hw, b_patha_ok, result,
						   final_candidate,
						   (reg_ea4 == 0));
	if (reg_eb4 != 0)
		_rtl8723be_phy_path_b_fill_iqk_matrix(hw, b_pathb_ok, result,
						      final_candidate,
						      (reg_ec4 == 0));

	idx = _get_right_chnl_place_for_iqk(rtlphy->current_channel);

	if (final_candidate < 4) {
		for (i = 0; i < IQK_MATRIX_REG_NUM; i++)
			rtlphy->iqk_matrix[idx].value[0][i] =
						result[final_candidate][i];
		rtlphy->iqk_matrix[idx].iqk_done = true;

	}
	rtl8723_save_adda_registers(hw, iqk_bb_reg,
				    rtlphy->iqk_bb_backup, 9);

	rtl_set_bbreg(hw, 0x948, MASKDWORD, path_sel_bb);
	/* rtl_set_rfreg(hw, RF90_PATH_A, 0xb0, 0xfffff, path_sel_rf); */

label_done:
	spin_lock(&rtlpriv->locks.iqk_lock);
	rtlphy->lck_inprogress = false;
	spin_unlock(&rtlpriv->locks.iqk_lock);
}

void rtl8723be_phy_lc_calibrate(struct ieee80211_hw *hw)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rtl_phy *rtlphy = &rtlpriv->phy;
	struct rtl_hal *rtlhal = &rtlpriv->rtlhal;
	u32 timeout = 2000, timecount = 0;

	while (rtlpriv->mac80211.act_scanning && timecount < timeout) {
		udelay(50);
		timecount += 50;
	}

	rtlphy->lck_inprogress = true;
	RTPRINT(rtlpriv, FINIT, INIT_IQK,
		"LCK:Start!!! currentband %x delay %d ms\n",
		 rtlhal->current_bandtype, timecount);

	_rtl8723be_phy_lc_calibrate(hw, false);

	rtlphy->lck_inprogress = false;
}

void rtl8723be_phy_set_rfpath_switch(struct ieee80211_hw *hw, bool bmain)
{
	_rtl8723be_phy_set_rfpath_switch(hw, bmain, true);
}



void test_oracle_iqk(void *backend, bool recovery, struct test_oracle_result *out)
{
    struct rtl_priv priv = {0};
    struct ieee80211_hw hw = {backend, &priv};
    unsigned int i;
    priv.backend = backend;
    priv.rtlhal.hw_type = HARDWARE_TYPE_RTL8723BE;
    priv.phy.current_channel = 1;
    if (recovery)
        memcpy(priv.phy.iqk_bb_backup, out->recovery, sizeof(out->recovery));
    rtl8723be_phy_iq_calibrate(&hw, recovery);
    memcpy(out->recovery, priv.phy.iqk_bb_backup, sizeof(out->recovery));
    out->reg[0] = priv.phy.reg_e94;
    out->reg[1] = priv.phy.reg_e9c;
    out->reg[2] = priv.phy.reg_eb4;
    out->reg[3] = priv.phy.reg_ebc;
    for (i = 0; i < 8; i++)
        out->matrix[i] = priv.phy.iqk_matrix[0].value[0][i];
    out->matrix_done = priv.phy.iqk_matrix[0].iqk_done;
}
void test_oracle_lck(void *backend, bool scanning)
{
    struct rtl_priv priv = {0};
    struct ieee80211_hw hw = {backend, &priv};
    priv.backend = backend;
    priv.rtlhal.hw_type = HARDWARE_TYPE_RTL8723BE;
    priv.mac80211.act_scanning = scanning;
    rtl8723be_phy_lc_calibrate(&hw);
}
