/* SPDX-License-Identifier: GPL-2.0 */
/* Copyright(c) 2009-2014 Realtek Corporation. */
/* Mechanically adapted frozen Linux IQK helpers; see provenance report. */

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
#define IQK_ADDA_REG_NUM 16U
#define IQK_MAC_REG_NUM 4U
#define IQK_BB_REG_NUM 9U
#define IQK_DELAY_TIME 10U
#define MAX_TOLERANCE 5U
#define BIT(n) (UINT32_C(1) << (n))

static uint8_t cal_path_a_tx(struct calibration_work *hw)
{
	uint32_t reg_eac, reg_e94, reg_e9c, tmp;
	uint8_t result = 0x00;

	/* leave IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	/* switch to path A */
	cal_set_bb(hw, 0x948, MASKDWORD, 0x00000000);
	/* enable path A PA in TXIQK mode */
	cal_set_rf(hw, RF90_PATH_A, RF_WE_LUT, RFREG_OFFSET_MASK, 0x800a0);
	cal_set_rf(hw, RF90_PATH_A, RF_RCK_OS, RFREG_OFFSET_MASK, 0x20000);
	cal_set_rf(hw, RF90_PATH_A, RF_TXPA_G1, RFREG_OFFSET_MASK, 0x0003f);
	cal_set_rf(hw, RF90_PATH_A, RF_TXPA_G2, RFREG_OFFSET_MASK, 0xc7f87);

	/* 1. TX IQK */
	/* path-A IQK setting */
	/* IQK setting */
	cal_set_bb(hw, RTX_IQK, MASKDWORD, 0x01007c00);
	cal_set_bb(hw, RRX_IQK, MASKDWORD, 0x01004800);
	/* path-A IQK setting */
	cal_set_bb(hw, RTX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	cal_set_bb(hw, RTX_IQK_PI_A, MASKDWORD, 0x821403ea);
	cal_set_bb(hw, RRX_IQK_PI_A, MASKDWORD, 0x28160000);
	cal_set_bb(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	cal_set_bb(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);
	/* LO calibration setting */
	cal_set_bb(hw, RIQK_AGC_RSP, MASKDWORD, 0x00462911);
	/* enter IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path A LOK & IQK */
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	cal_delay(hw, (IQK_DELAY_TIME) * 1000U);

	/* leave IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);

	/* Check failed */
	reg_eac = cal_get_bb(hw, 0xeac, MASKDWORD);
	reg_e94 = cal_get_bb(hw, 0xe94, MASKDWORD);
	reg_e9c = cal_get_bb(hw, 0xe9c, MASKDWORD);

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

static uint8_t cal_path_a_rx(struct calibration_work *hw)
{
	uint32_t reg_eac, reg_e94, reg_e9c, reg_ea4, u32tmp, tmp;
	uint8_t result = 0x00;

	/* leave IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);

	/* switch to path A */
	cal_set_bb(hw, 0x948, MASKDWORD, 0x00000000);

	/* 1 Get TXIMR setting */
	/* modify RXIQK mode table */
	cal_set_rf(hw, RF90_PATH_A, RF_WE_LUT, 0x80000, 0x1);
	cal_set_rf(hw, RF90_PATH_A, RF_RCK_OS, RFREG_OFFSET_MASK, 0x30000);
	cal_set_rf(hw, RF90_PATH_A, RF_TXPA_G1, RFREG_OFFSET_MASK, 0x0001f);
	/* LNA2 off, PA on for Dcut */
	cal_set_rf(hw, RF90_PATH_A, RF_TXPA_G2, RFREG_OFFSET_MASK, 0xf7fb7);
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* IQK setting */
	cal_set_bb(hw, RTX_IQK, MASKDWORD, 0x01007c00);
	cal_set_bb(hw, RRX_IQK, MASKDWORD, 0x01004800);

	/* path-A IQK setting */
	cal_set_bb(hw, RTX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	cal_set_bb(hw, RTX_IQK_PI_A, MASKDWORD, 0x82160ff0);
	cal_set_bb(hw, RRX_IQK_PI_A, MASKDWORD, 0x28110000);
	cal_set_bb(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	cal_set_bb(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);

	/* LO calibration setting */
	cal_set_bb(hw, RIQK_AGC_RSP, MASKDWORD, 0x0046a911);

	/* enter IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path A LOK & IQK */
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	cal_delay(hw, (IQK_DELAY_TIME) * 1000U);

	/* leave IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);

	/* Check failed */
	reg_eac = cal_get_bb(hw, RRX_POWER_AFTER_IQK_A_2, MASKDWORD);
	reg_e94 = cal_get_bb(hw, RTX_POWER_BEFORE_IQK_A, MASKDWORD);
	reg_e9c = cal_get_bb(hw, RTX_POWER_AFTER_IQK_A, MASKDWORD);

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
	cal_set_bb(hw, RTX_IQK, MASKDWORD, u32tmp);

	/* 1 RX IQK */
	/* modify RXIQK mode table */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	cal_set_rf(hw, RF90_PATH_A, RF_WE_LUT, 0x80000, 0x1);
	cal_set_rf(hw, RF90_PATH_A, RF_RCK_OS, RFREG_OFFSET_MASK, 0x30000);
	cal_set_rf(hw, RF90_PATH_A, RF_TXPA_G1, RFREG_OFFSET_MASK, 0x0001f);
	/* LAN2 on, PA off for Dcut */
	cal_set_rf(hw, RF90_PATH_A, RF_TXPA_G2, RFREG_OFFSET_MASK, 0xf7d77);

	/* PA, PAD setting */
	cal_set_rf(hw, RF90_PATH_A, 0xdf, RFREG_OFFSET_MASK, 0xf80);
	cal_set_rf(hw, RF90_PATH_A, 0x55, RFREG_OFFSET_MASK, 0x4021f);

	/* IQK setting */
	cal_set_bb(hw, RRX_IQK, MASKDWORD, 0x01004800);

	/* path-A IQK setting */
	cal_set_bb(hw, RTX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	cal_set_bb(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	cal_set_bb(hw, RTX_IQK_PI_A, MASKDWORD, 0x82110000);
	cal_set_bb(hw, RRX_IQK_PI_A, MASKDWORD, 0x2816001f);
	cal_set_bb(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	cal_set_bb(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);

	/* LO calibration setting */
	cal_set_bb(hw, RIQK_AGC_RSP, MASKDWORD, 0x0046a8d1);

	/* enter IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path A LOK & IQK */
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	cal_delay(hw, (IQK_DELAY_TIME) * 1000U);

	/* leave IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);

	/* Check failed */
	reg_eac = cal_get_bb(hw, RRX_POWER_AFTER_IQK_A_2, MASKDWORD);
	reg_ea4 = cal_get_bb(hw, RRX_POWER_BEFORE_IQK_A_2, MASKDWORD);

	/* leave IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	cal_set_rf(hw, RF90_PATH_A, 0xdf, RFREG_OFFSET_MASK, 0x780);

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

static uint8_t cal_path_b_tx(struct calibration_work *hw)
{
	uint32_t reg_eac, reg_e94, reg_e9c, tmp;
	uint8_t result = 0x00;

	/* leave IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	/* switch to path B */
	cal_set_bb(hw, 0x948, MASKDWORD, 0x00000280);

	/* enable path B PA in TXIQK mode */
	cal_set_rf(hw, RF90_PATH_A, 0xed, RFREG_OFFSET_MASK, 0x00020);
	cal_set_rf(hw, RF90_PATH_A, 0x43, RFREG_OFFSET_MASK, 0x40fc1);

	/* 1 Tx IQK */
	/* IQK setting */
	cal_set_bb(hw, RTX_IQK, MASKDWORD, 0x01007c00);
	cal_set_bb(hw, RRX_IQK, MASKDWORD, 0x01004800);
	/* path-A IQK setting */
	cal_set_bb(hw, RTX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	cal_set_bb(hw, RTX_IQK_PI_A, MASKDWORD, 0x821403ea);
	cal_set_bb(hw, RRX_IQK_PI_A, MASKDWORD, 0x28110000);
	cal_set_bb(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	cal_set_bb(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);

	/* LO calibration setting */
	cal_set_bb(hw, RIQK_AGC_RSP, MASKDWORD, 0x00462911);

	/* enter IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path B LOK & IQK */
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	cal_delay(hw, (IQK_DELAY_TIME) * 1000U);

	/* leave IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);

	/* Check failed */
	reg_eac = cal_get_bb(hw, RRX_POWER_AFTER_IQK_A_2, MASKDWORD);
	reg_e94 = cal_get_bb(hw, RTX_POWER_BEFORE_IQK_A, MASKDWORD);
	reg_e9c = cal_get_bb(hw, RTX_POWER_AFTER_IQK_A, MASKDWORD);

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

static uint8_t cal_path_b_rx(struct calibration_work *hw)
{
	uint32_t reg_e94, reg_e9c, reg_ea4, reg_eac, u32tmp, tmp;
	uint8_t result = 0x00;

	/* leave IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	/* switch to path B */
	cal_set_bb(hw, 0x948, MASKDWORD, 0x00000280);

	/* 1 Get TXIMR setting */
	/* modify RXIQK mode table */
	cal_set_rf(hw, RF90_PATH_A, RF_WE_LUT, RFREG_OFFSET_MASK, 0x800a0);
	cal_set_rf(hw, RF90_PATH_A, RF_RCK_OS, RFREG_OFFSET_MASK, 0x30000);
	cal_set_rf(hw, RF90_PATH_A, RF_TXPA_G1, RFREG_OFFSET_MASK, 0x0001f);
	cal_set_rf(hw, RF90_PATH_A, RF_TXPA_G2, RFREG_OFFSET_MASK, 0xf7ff7);

	/* open PA S1 & SMIXER */
	cal_set_rf(hw, RF90_PATH_A, 0xed, RFREG_OFFSET_MASK, 0x00020);
	cal_set_rf(hw, RF90_PATH_A, 0x43, RFREG_OFFSET_MASK, 0x60fed);

	/* IQK setting */
	cal_set_bb(hw, RTX_IQK, MASKDWORD, 0x01007c00);
	cal_set_bb(hw, RRX_IQK, MASKDWORD, 0x01004800);

	/* path-B IQK setting */
	cal_set_bb(hw, RTX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	cal_set_bb(hw, RTX_IQK_PI_A, MASKDWORD, 0x82160ff0);
	cal_set_bb(hw, RRX_IQK_PI_A, MASKDWORD, 0x28110000);
	cal_set_bb(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	cal_set_bb(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);

	/* LO calibration setting */
	cal_set_bb(hw, RIQK_AGC_RSP, MASKDWORD, 0x0046a911);
	/* enter IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path B TXIQK @ RXIQK */
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	cal_delay(hw, (IQK_DELAY_TIME) * 1000U);

	/* leave IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	/* Check failed */
	reg_eac = cal_get_bb(hw, RRX_POWER_AFTER_IQK_A_2, MASKDWORD);
	reg_e94 = cal_get_bb(hw, RTX_POWER_BEFORE_IQK_A, MASKDWORD);
	reg_e9c = cal_get_bb(hw, RTX_POWER_AFTER_IQK_A, MASKDWORD);

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
	cal_set_bb(hw, RTX_IQK, MASKDWORD, u32tmp);

	/* 1 RX IQK */

	/* <20121009, Kordan> RF Mode = 3 */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	cal_set_rf(hw, RF90_PATH_A, RF_WE_LUT, 0x80000, 0x1);
	cal_set_rf(hw, RF90_PATH_A, RF_RCK_OS, RFREG_OFFSET_MASK, 0x30000);
	cal_set_rf(hw, RF90_PATH_A, RF_TXPA_G1, RFREG_OFFSET_MASK, 0x0001f);
	cal_set_rf(hw, RF90_PATH_A, RF_TXPA_G2, RFREG_OFFSET_MASK, 0xf7d77);
	cal_set_rf(hw, RF90_PATH_A, RF_WE_LUT, 0x80000, 0x0);

	/* open PA S1 & close SMIXER */
	cal_set_rf(hw, RF90_PATH_A, 0xed, RFREG_OFFSET_MASK, 0x00020);
	cal_set_rf(hw, RF90_PATH_A, 0x43, RFREG_OFFSET_MASK, 0x60fbd);

	/* IQK setting */
	cal_set_bb(hw, RRX_IQK, MASKDWORD, 0x01004800);

	/* path-B IQK setting */
	cal_set_bb(hw, RTX_IQK_TONE_A, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_A, MASKDWORD, 0x18008c1c);
	cal_set_bb(hw, RTX_IQK_TONE_B, MASKDWORD, 0x38008c1c);
	cal_set_bb(hw, RRX_IQK_TONE_B, MASKDWORD, 0x38008c1c);

	cal_set_bb(hw, RTX_IQK_PI_A, MASKDWORD, 0x82110000);
	cal_set_bb(hw, RRX_IQK_PI_A, MASKDWORD, 0x2816001f);
	cal_set_bb(hw, RTX_IQK_PI_B, MASKDWORD, 0x82110000);
	cal_set_bb(hw, RRX_IQK_PI_B, MASKDWORD, 0x28110000);

	/* LO calibration setting */
	cal_set_bb(hw, RIQK_AGC_RSP, MASKDWORD, 0x0046a8d1);
	/* enter IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x80800000);

	/* One shot, path B LOK & IQK */
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf9000000);
	cal_set_bb(hw, RIQK_AGC_PTS, MASKDWORD, 0xf8000000);

	cal_delay(hw, (IQK_DELAY_TIME) * 1000U);

	/* leave IQK mode */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0x00000000);
	/* Check failed */
	reg_eac = cal_get_bb(hw, RRX_POWER_AFTER_IQK_A_2, MASKDWORD);
	reg_ea4 = cal_get_bb(hw, RRX_POWER_BEFORE_IQK_A_2, MASKDWORD);

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

static void cal_fill_b(struct calibration_work *hw,
						  bool b_iqk_ok,
						  int32_t result[][8],
						  uint8_t final_candidate,
						  bool btxonly)
{
	uint32_t oldval_1, x, tx1_a, reg;
	int32_t y, tx1_c;

	if (final_candidate == 0xFF) {
		return;
	} else if (b_iqk_ok) {
		oldval_1 = (cal_get_bb(hw, ROFDM0_XBTXIQIMBALANCE,
					  MASKDWORD) >> 22) & 0x3FF;
		x = result[final_candidate][4];
		if ((x & 0x00000200) != 0)
			x = x | 0xFFFFFC00;
		tx1_a = (x * oldval_1) >> 8;
		cal_set_bb(hw, ROFDM0_XBTXIQIMBALANCE, 0x3FF, tx1_a);
		cal_set_bb(hw, ROFDM0_ECCATHRESHOLD, BIT(27),
			      ((x * oldval_1 >> 7) & 0x1));
		y = result[final_candidate][5];
		if ((y & 0x00000200) != 0)
			y -= 0x400;
		tx1_c = (y * oldval_1) >> 8;
		cal_set_bb(hw, ROFDM0_XDTXAFE, 0xF0000000,
			      ((tx1_c & 0x3C0) >> 6));
		cal_set_bb(hw, ROFDM0_XBTXIQIMBALANCE, 0x003F0000,
			      (tx1_c & 0x3F));
		cal_set_bb(hw, ROFDM0_ECCATHRESHOLD, BIT(25),
			      ((y * oldval_1 >> 7) & 0x1));
		if (btxonly)
			return;
		reg = result[final_candidate][6];
		cal_set_bb(hw, ROFDM0_XBRXIQIMBALANCE, 0x3FF, reg);
		reg = result[final_candidate][7] & 0x3F;
		cal_set_bb(hw, ROFDM0_XBRXIQIMBALANCE, 0xFC00, reg);
		reg = (result[final_candidate][7] >> 6) & 0xF;
		/* cal_set_bb(hw, 0xca0, 0xF0000000, reg); */
	}
}

static bool cal_compare(struct calibration_work *hw,
					      int32_t result[][8], uint8_t c1, uint8_t c2)
{
	(void)hw;
	uint32_t i, j, diff, simularity_bitmap, bound = 0;

	uint8_t final_candidate[2] = {0xFF, 0xFF}; /* for path A and path B */
	bool bresult = true; /* is2t = true*/
	int32_t tmp1 = 0, tmp2 = 0;

	bound = 8;

	simularity_bitmap = 0;

	for (i = 0; i < bound; i++) {
		if ((i == 1) || (i == 3) || (i == 5) || (i == 7)) {
			if ((result[c1][i] & 0x00000200) != 0)
				tmp1 = result[c1][i] - 0x400;
			else
				tmp1 = result[c1][i];

			if ((result[c2][i] & 0x00000200) != 0)
				tmp2 = result[c2][i] - 0x400;
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

static void cal_iqk_trial(struct calibration_work *hw,
					int32_t result[][8], uint8_t t, bool is2t)
{
	uint32_t i;
	uint8_t patha_ok, pathb_ok;
	uint32_t adda_reg[IQK_ADDA_REG_NUM] = {
		0x85c, 0xe6c, 0xe70, 0xe74,
		0xe78, 0xe7c, 0xe80, 0xe84,
		0xe88, 0xe8c, 0xed0, 0xed4,
		0xed8, 0xedc, 0xee0, 0xeec
	};

	uint32_t iqk_mac_reg[IQK_MAC_REG_NUM] = {
		0x522, 0x550, 0x551, 0x040
	};
	uint32_t iqk_bb_reg[IQK_BB_REG_NUM] = {
		ROFDM0_TRXPATHENABLE, ROFDM0_TRMUXPAR,
		RFPGA0_XCD_RFINTERFACESW, 0xb68, 0xb6c,
		0x870, 0x860,
		0x864, 0xa04
	};
	const uint32_t retrycount = 2;

	uint32_t path_sel_bb;/* path_sel_rf */

	uint8_t tmp_reg_c50, tmp_reg_c58;

	tmp_reg_c50 = cal_get_bb(hw, 0xc50, MASKBYTE0);
	tmp_reg_c58 = cal_get_bb(hw, 0xc58, MASKBYTE0);

	if (t == 0) {
		cal_save_bb(hw, adda_reg,
					    hw->adda_backup, 16);
		cal_save_mac(hw, iqk_mac_reg,
					       hw->mac_backup);
		cal_save_bb(hw, iqk_bb_reg,
					    hw->bb_backup,
					    IQK_BB_REG_NUM);
	}
	cal_adda_on(hw, adda_reg, true, is2t);
	if (t == 0) {
		hw->rfpi_enable = (uint8_t)cal_get_bb(hw,
						RFPGA0_XA_HSSIPARAMETER1,
						BIT(8));
	}

	path_sel_bb = cal_get_bb(hw, 0x948, MASKDWORD);

	cal_mac_calibration(hw, iqk_mac_reg,
					    hw->mac_backup);
	/*BB Setting*/
	cal_set_bb(hw, 0xa04, 0x0f000000, 0xf);
	cal_set_bb(hw, 0xc04, MASKDWORD, 0x03a05600);
	cal_set_bb(hw, 0xc08, MASKDWORD, 0x000800e4);
	cal_set_bb(hw, 0x874, MASKDWORD, 0x22204000);

	/* path A TX IQK */
	for (i = 0; i < retrycount; i++) {
		patha_ok = cal_path_a_tx(hw);
		if (patha_ok == 0x01) {
			((void)0);
			result[t][0] = (cal_get_bb(hw, 0xe94, MASKDWORD) &
					0x3FF0000) >> 16;
			result[t][1] = (cal_get_bb(hw, 0xe9c, MASKDWORD) &
					0x3FF0000) >> 16;
			break;
		} else {
			((void)0);
		}
	}
	/* path A RX IQK */
	for (i = 0; i < retrycount; i++) {
		patha_ok = cal_path_a_rx(hw);
		if (patha_ok == 0x03) {
			((void)0);
			result[t][2] = (cal_get_bb(hw, 0xea4, MASKDWORD) &
					0x3FF0000) >> 16;
			result[t][3] = (cal_get_bb(hw, 0xeac, MASKDWORD) &
					0x3FF0000) >> 16;
			break;
		}
		((void)0);
	}

	if (0x00 == patha_ok)
		((void)0);

	if (is2t) {
		/* path B TX IQK */
		for (i = 0; i < retrycount; i++) {
			pathb_ok = cal_path_b_tx(hw);
			if (pathb_ok == 0x01) {
				((void)0);
				result[t][4] = (cal_get_bb(hw, 0xe94,
							      MASKDWORD) &
							      0x3FF0000) >> 16;
				result[t][5] = (cal_get_bb(hw, 0xe9c,
							      MASKDWORD) &
							      0x3FF0000) >> 16;
				break;
			}
			((void)0);
		}
		/* path B RX IQK */
		for (i = 0; i < retrycount; i++) {
			pathb_ok = cal_path_b_rx(hw);
			if (pathb_ok == 0x03) {
				((void)0);
				result[t][6] = (cal_get_bb(hw, 0xea4,
							      MASKDWORD) &
							      0x3FF0000) >> 16;
				result[t][7] = (cal_get_bb(hw, 0xeac,
							      MASKDWORD) &
							      0x3FF0000) >> 16;
				break;
			}
			((void)0);
		}
	}

	/* Back to BB mode, load original value */
	cal_set_bb(hw, RFPGA0_IQK, MASKDWORD, 0);

	if (t != 0) {
		cal_reload_bb(hw, adda_reg,
						  hw->adda_backup, 16);
		cal_reload_mac(hw, iqk_mac_reg,
						 hw->mac_backup);
		cal_reload_bb(hw, iqk_bb_reg,
						  hw->bb_backup,
						  IQK_BB_REG_NUM);

		cal_set_bb(hw, 0x948, MASKDWORD, path_sel_bb);
		/*cal_set_rf(hw, RF90_PATH_B, 0xb0, 0xfffff, path_sel_rf);*/

		cal_set_bb(hw, 0xc50, MASKBYTE0, 0x50);
		cal_set_bb(hw, 0xc50, MASKBYTE0, tmp_reg_c50);
		if (is2t) {
			cal_set_bb(hw, 0xc58, MASKBYTE0, 0x50);
			cal_set_bb(hw, 0xc58, MASKBYTE0, tmp_reg_c58);
		}
		cal_set_bb(hw, 0xe30, MASKDWORD, 0x01008c00);
		cal_set_bb(hw, 0xe34, MASKDWORD, 0x01008c00);
	}
	((void)0);
}

static void cal_fill_a(struct calibration_work *hw,
					bool iqk_ok,
					int32_t result[][8],
					uint8_t final_candidate,
					bool btxonly)
{
	uint32_t oldval_0, x, tx0_a, reg;
	int32_t y, tx0_c;

	if (final_candidate == 0xFF) {
		return;
	} else if (iqk_ok) {
		oldval_0 = (cal_get_bb(hw, ROFDM0_XATXIQIMBALANCE,
					  MASKDWORD) >> 22) & 0x3FF;
		x = result[final_candidate][0];
		if ((x & 0x00000200) != 0)
			x = x | 0xFFFFFC00;
		tx0_a = (x * oldval_0) >> 8;
		cal_set_bb(hw, ROFDM0_XATXIQIMBALANCE, 0x3FF, tx0_a);
		cal_set_bb(hw, ROFDM0_ECCATHRESHOLD, BIT(31),
			      ((x * oldval_0 >> 7) & 0x1));
		y = result[final_candidate][1];
		if ((y & 0x00000200) != 0)
			y -= 0x400;
		tx0_c = (y * oldval_0) >> 8;
		cal_set_bb(hw, ROFDM0_XCTXAFE, 0xF0000000,
			      ((tx0_c & 0x3C0) >> 6));
		cal_set_bb(hw, ROFDM0_XATXIQIMBALANCE, 0x003F0000,
			      (tx0_c & 0x3F));
		cal_set_bb(hw, ROFDM0_ECCATHRESHOLD, BIT(29),
			      ((y * oldval_0 >> 7) & 0x1));
		if (btxonly)
			return;
		reg = result[final_candidate][2];
		cal_set_bb(hw, ROFDM0_XARXIQIMBALANCE, 0x3FF, reg);
		reg = result[final_candidate][3] & 0x3F;
		cal_set_bb(hw, ROFDM0_XARXIQIMBALANCE, 0xFC00, reg);
		reg = (result[final_candidate][3] >> 6) & 0xF;
		cal_set_bb(hw, 0xca0, 0xF0000000, reg);
	}
}
