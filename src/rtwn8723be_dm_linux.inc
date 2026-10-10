/* SPDX-License-Identifier: GPL-2.0 */
/* Frozen dm.c algorithms: only native field/I/O names and per-device
 * EDCA history lowering; debug-print statements omitted. */

static void dm_write_dig(struct dm_work *hw, uint8_t current_igi)
{
	struct rtwn8723be_dm_dig *dm_digtable = &hw->dm->dig;

	if (dm_digtable->stop_dig)
		return;

	if (dm_digtable->cur_igvalue != current_igi) {
		dm_set_bb(hw, ROFDM0_XAAGCCORE1, 0x7f, current_igi);
		if (hw->dm->rf_path_count != 1U)
			dm_set_bb(hw, ROFDM0_XBAGCCORE1,
				      0x7f, current_igi);
	}
	dm_digtable->pre_igvalue = dm_digtable->cur_igvalue;
	dm_digtable->cur_igvalue = current_igi;
}

static void dm_dig(struct dm_work *hw)
{
	struct rtwn8723be_dm_dig *dm_digtable = &hw->dm->dig;
	uint8_t dig_min_0, dig_maxofmin;
	bool bfirstconnect, bfirstdisconnect;
	uint8_t dm_dig_max, dm_dig_min;
	uint8_t current_igi = dm_digtable->cur_igvalue;
	uint8_t offset;

	/* AP,BT */
	if (hw->input->scanning)
		return;

	dig_min_0 = dm_digtable->dig_min_0;
	bfirstconnect = (hw->input->linked) &&
			!dm_digtable->media_connect_0;
	bfirstdisconnect = (!hw->input->linked) &&
			(dm_digtable->media_connect_0);

	dm_dig_max = 0x5a;
	dm_dig_min = DM_DIG_MIN;
	dig_maxofmin = DM_DIG_MAX_AP;

	if (hw->input->linked) {
		if ((dm_digtable->rssi_val_min + 10) > dm_dig_max)
			dm_digtable->rx_gain_max = dm_dig_max;
		else if ((dm_digtable->rssi_val_min + 10) < dm_dig_min)
			dm_digtable->rx_gain_max = dm_dig_min;
		else
			dm_digtable->rx_gain_max =
				dm_digtable->rssi_val_min + 10;

		if (hw->dm->one_entry_only) {
			offset = 12;
			if (dm_digtable->rssi_val_min - offset < dm_dig_min)
				dig_min_0 = dm_dig_min;
			else if (dm_digtable->rssi_val_min - offset >
							dig_maxofmin)
				dig_min_0 = dig_maxofmin;
			else
				dig_min_0 =
					dm_digtable->rssi_val_min - offset;
		} else {
			dig_min_0 = dm_dig_min;
		}

	} else {
		dm_digtable->rx_gain_max = dm_dig_max;
		dig_min_0 = dm_dig_min;
		
	}

	if (hw->dm->false_alarm.cnt_all > 10000) {
		if (dm_digtable->large_fa_hit != 3)
			dm_digtable->large_fa_hit++;
		if (dm_digtable->forbidden_igi < current_igi) {
			dm_digtable->forbidden_igi = current_igi;
			dm_digtable->large_fa_hit = 1;
		}

		if (dm_digtable->large_fa_hit >= 3) {
			if ((dm_digtable->forbidden_igi + 1) >
			     dm_digtable->rx_gain_max)
				dm_digtable->rx_gain_min =
						dm_digtable->rx_gain_max;
			else
				dm_digtable->rx_gain_min =
						dm_digtable->forbidden_igi + 1;
			dm_digtable->recover_cnt = 3600;
		}
	} else {
		if (dm_digtable->recover_cnt != 0) {
			dm_digtable->recover_cnt--;
		} else {
			if (dm_digtable->large_fa_hit < 3) {
				if ((dm_digtable->forbidden_igi - 1) <
				     dig_min_0) {
					dm_digtable->forbidden_igi =
							dig_min_0;
					dm_digtable->rx_gain_min =
							dig_min_0;
				} else {
					dm_digtable->forbidden_igi--;
					dm_digtable->rx_gain_min =
						dm_digtable->forbidden_igi + 1;
				}
			} else {
				dm_digtable->large_fa_hit = 0;
			}
		}
	}
	if (dm_digtable->rx_gain_min > dm_digtable->rx_gain_max)
		dm_digtable->rx_gain_min = dm_digtable->rx_gain_max;

	if (hw->input->linked) {
		if (bfirstconnect) {
			current_igi = dm_min(dm_digtable->rssi_val_min, dig_maxofmin);

			dm_digtable->large_fa_hit = 0;
		} else {
			if (hw->dm->false_alarm.cnt_all > DM_DIG_FA_TH2)
				current_igi += 4;
			else if (hw->dm->false_alarm.cnt_all > DM_DIG_FA_TH1)
				current_igi += 2;
			else if (hw->dm->false_alarm.cnt_all < DM_DIG_FA_TH0)
				current_igi -= 2;
		}
	} else {
		if (bfirstdisconnect) {
			current_igi = dm_digtable->rx_gain_min;
		} else {
			if (hw->dm->false_alarm.cnt_all > 10000)
				current_igi += 4;
			else if (hw->dm->false_alarm.cnt_all > 8000)
				current_igi += 2;
			else if (hw->dm->false_alarm.cnt_all < 500)
				current_igi -= 2;
		}
	}

	if (current_igi > dm_digtable->rx_gain_max)
		current_igi = dm_digtable->rx_gain_max;
	else if (current_igi < dm_digtable->rx_gain_min)
		current_igi = dm_digtable->rx_gain_min;

	dm_write_dig(hw, current_igi);
	dm_digtable->media_connect_0 =
		((hw->input->linked) ? true : false);
	dm_digtable->dig_min_0 = dig_min_0;
}

static void dm_false_alarm_counter_statistics(
					struct dm_work *hw)
{
	uint32_t ret_value;
	struct rtwn8723be_dm_false_alarm *falsealm_cnt = &hw->dm->false_alarm;

	dm_set_bb(hw, DM_REG_OFDM_FA_HOLDC_11N, BIT(31), 1);
	dm_set_bb(hw, DM_REG_OFDM_FA_RSTD_11N, BIT(31), 1);

	ret_value = dm_get_bb(hw, DM_REG_OFDM_FA_TYPE1_11N, MASKDWORD);
	falsealm_cnt->cnt_fast_fsync_fail = ret_value & 0xffff;
	falsealm_cnt->cnt_sb_search_fail = (ret_value & 0xffff0000) >> 16;

	ret_value = dm_get_bb(hw, DM_REG_OFDM_FA_TYPE2_11N, MASKDWORD);
	falsealm_cnt->cnt_ofdm_cca = ret_value & 0xffff;
	falsealm_cnt->cnt_parity_fail = (ret_value & 0xffff0000) >> 16;

	ret_value = dm_get_bb(hw, DM_REG_OFDM_FA_TYPE3_11N, MASKDWORD);
	falsealm_cnt->cnt_rate_illegal = ret_value & 0xffff;
	falsealm_cnt->cnt_crc8_fail = (ret_value & 0xffff0000) >> 16;

	ret_value = dm_get_bb(hw, DM_REG_OFDM_FA_TYPE4_11N, MASKDWORD);
	falsealm_cnt->cnt_mcs_fail = ret_value & 0xffff;

	falsealm_cnt->cnt_ofdm_fail = falsealm_cnt->cnt_parity_fail +
				      falsealm_cnt->cnt_rate_illegal +
				      falsealm_cnt->cnt_crc8_fail +
				      falsealm_cnt->cnt_mcs_fail +
				      falsealm_cnt->cnt_fast_fsync_fail +
				      falsealm_cnt->cnt_sb_search_fail;

	dm_set_bb(hw, DM_REG_CCK_FA_RST_11N, BIT(12), 1);
	dm_set_bb(hw, DM_REG_CCK_FA_RST_11N, BIT(14), 1);

	ret_value = dm_get_bb(hw, DM_REG_CCK_FA_RST_11N, MASKBYTE0);
	falsealm_cnt->cnt_cck_fail = ret_value;

	ret_value = dm_get_bb(hw, DM_REG_CCK_FA_MSB_11N, MASKBYTE3);
	falsealm_cnt->cnt_cck_fail += (ret_value & 0xff) << 8;

	ret_value = dm_get_bb(hw, DM_REG_CCK_CCA_CNT_11N, MASKDWORD);
	falsealm_cnt->cnt_cck_cca = ((ret_value & 0xff) << 8) |
				    ((ret_value & 0xff00) >> 8);

	falsealm_cnt->cnt_all = falsealm_cnt->cnt_fast_fsync_fail +
				falsealm_cnt->cnt_sb_search_fail +
				falsealm_cnt->cnt_parity_fail +
				falsealm_cnt->cnt_rate_illegal +
				falsealm_cnt->cnt_crc8_fail +
				falsealm_cnt->cnt_mcs_fail +
				falsealm_cnt->cnt_cck_fail;

	falsealm_cnt->cnt_cca_all = falsealm_cnt->cnt_ofdm_cca +
				    falsealm_cnt->cnt_cck_cca;

	dm_set_bb(hw, DM_REG_OFDM_FA_RSTC_11N, BIT(31), 1);
	dm_set_bb(hw, DM_REG_OFDM_FA_RSTC_11N, BIT(31), 0);
	dm_set_bb(hw, DM_REG_OFDM_FA_RSTD_11N, BIT(27), 1);
	dm_set_bb(hw, DM_REG_OFDM_FA_RSTD_11N, BIT(27), 0);

	dm_set_bb(hw, DM_REG_OFDM_FA_HOLDC_11N, BIT(31), 0);
	dm_set_bb(hw, DM_REG_OFDM_FA_RSTD_11N, BIT(31), 0);

	dm_set_bb(hw, DM_REG_CCK_FA_RST_11N, BIT(13) | BIT(12), 0);
	dm_set_bb(hw, DM_REG_CCK_FA_RST_11N, BIT(13) | BIT(12), 2);

	dm_set_bb(hw, DM_REG_CCK_FA_RST_11N, BIT(15) | BIT(14), 0);
	dm_set_bb(hw, DM_REG_CCK_FA_RST_11N, BIT(15) | BIT(14), 2);

}

static bool dm_is_edca_turbo_disable(struct dm_work *hw)
{

	if (hw->input->wireless_mode == WIRELESS_MODE_B)
		return true;

	return false;
}

static void dm_check_edca_turbo(struct dm_work *hw)
{

	uint64_t last_txok_cnt = hw->dm->last_txok_cnt;
	uint64_t last_rxok_cnt = hw->dm->last_rxok_cnt;
	uint64_t cur_txok_cnt = 0;
	uint64_t cur_rxok_cnt = 0;
	uint32_t edca_be_ul = 0x6ea42b;
	uint32_t edca_be_dl = 0x6ea42b;/*not sure*/
	uint32_t edca_be = 0x5ea42b;
	uint32_t iot_peer = 0;
	bool b_is_cur_rdlstate;
	bool b_bias_on_rx = false;
	bool b_edca_turbo_on = false;

	cur_txok_cnt = hw->input->txbytesunicast - last_txok_cnt;
	cur_rxok_cnt = hw->input->rxbytesunicast - last_rxok_cnt;

	iot_peer = hw->input->peer_vendor;
	b_bias_on_rx = (iot_peer == PEER_RAL || iot_peer == PEER_ATH) ?
		       true : false;
	b_edca_turbo_on = ((!hw->dm->is_any_nonbepkts) &&
			   (!hw->dm->disable_framebursting)) ?
			   true : false;

	if ((iot_peer == PEER_CISCO) &&
	    (hw->input->wireless_mode == WIRELESS_MODE_N_24G)) {
		edca_be_dl = edca_setting_dl[iot_peer];
		edca_be_ul = edca_setting_ul[iot_peer];
	}
	if (dm_is_edca_turbo_disable(hw))
		goto exit;

	if (b_edca_turbo_on) {
		if (b_bias_on_rx)
			b_is_cur_rdlstate = (cur_txok_cnt > cur_rxok_cnt * 4) ?
					    false : true;
		else
			b_is_cur_rdlstate = (cur_rxok_cnt > cur_txok_cnt * 4) ?
					    true : false;

		edca_be = (b_is_cur_rdlstate) ? edca_be_dl : edca_be_ul;
		dm_write32(hw, REG_EDCA_BE_PARAM, edca_be);
		hw->dm->is_cur_rdlstate = b_is_cur_rdlstate;
		hw->dm->current_turbo_edca = true;
	} else {
		if (hw->dm->current_turbo_edca) {
			dm_set_ac_param(hw);
		}
		hw->dm->current_turbo_edca = false;
	}

exit:
	hw->dm->is_any_nonbepkts = false;
	hw->dm->last_txok_cnt = hw->input->txbytesunicast;
	hw->dm->last_rxok_cnt = hw->input->rxbytesunicast;
}

static void dm_cck_packet_detection_thresh(struct dm_work *hw)
{
	struct rtwn8723be_dm_dig *dm_digtable = &hw->dm->dig;
	uint8_t cur_cck_cca_thresh;

	if (hw->input->linked) {
		if (dm_digtable->rssi_val_min > 25) {
			cur_cck_cca_thresh = 0xcd;
		} else if ((dm_digtable->rssi_val_min <= 25) &&
			   (dm_digtable->rssi_val_min > 10)) {
			cur_cck_cca_thresh = 0x83;
		} else {
			if (hw->dm->false_alarm.cnt_cck_fail > 1000)
				cur_cck_cca_thresh = 0x83;
			else
				cur_cck_cca_thresh = 0x40;
		}
	} else {
		if (hw->dm->false_alarm.cnt_cck_fail > 1000)
			cur_cck_cca_thresh = 0x83;
		else
			cur_cck_cca_thresh = 0x40;
	}

	if (dm_digtable->cur_cck_cca_thres != cur_cck_cca_thresh)
		dm_set_bb(hw, RCCK0_CCA, MASKBYTE2, cur_cck_cca_thresh);

	dm_digtable->pre_cck_cca_thres = dm_digtable->cur_cck_cca_thres;
	dm_digtable->cur_cck_cca_thres = cur_cck_cca_thresh;
	
}

static void dm_dynamic_edcca(struct dm_work *hw)
{
	uint8_t reg_c50, reg_c58;
	bool fw_current_in_ps_mode = false;

	fw_current_in_ps_mode = hw->input->fw_in_ps;
	if (fw_current_in_ps_mode)
		return;

	reg_c50 = dm_get_bb(hw, ROFDM0_XAAGCCORE1, MASKBYTE0);
	reg_c58 = dm_get_bb(hw, ROFDM0_XBAGCCORE1, MASKBYTE0);

	if (reg_c50 > 0x28 && reg_c58 > 0x28) {
		if (!hw->dm->pre_edcca_enable) {
			dm_write8(hw, ROFDM0_ECCATHRESHOLD, 0x03);
			dm_write8(hw, ROFDM0_ECCATHRESHOLD + 2, 0x00);
		}
	} else if (reg_c50 < 0x25 && reg_c58 < 0x25) {
		if (hw->dm->pre_edcca_enable) {
			dm_write8(hw, ROFDM0_ECCATHRESHOLD, 0x7f);
			dm_write8(hw, ROFDM0_ECCATHRESHOLD + 2, 0x7f);
		}
	}
}

static void dm_dynamic_atc_switch(struct dm_work *hw)
{
	struct rtwn8723be_dm_native *rtldm = hw->dm;
	uint8_t crystal_cap;
	uint32_t packet_count;
	int cfo_khz_a, cfo_khz_b, cfo_ave = 0, adjust_xtal = 0;
	int cfo_ave_diff;

	if (!hw->input->linked) {
		if (rtldm->atc_status == ATC_STATUS_OFF) {
			dm_set_bb(hw, ROFDM1_CFOTRACKING, BIT(11),
				      ATC_STATUS_ON);
			rtldm->atc_status = ATC_STATUS_ON;
		}
		if (hw->input->btc_active) {
			if (!hw->input->bt_disabled) {
				
				return;
			}
		}

		if (rtldm->crystal_cap != hw->dm->eeprom_crystal_cap) {
			rtldm->crystal_cap = hw->dm->eeprom_crystal_cap;
			crystal_cap = rtldm->crystal_cap & 0x3f;
			dm_set_bb(hw, REG_MAC_PHY_CTRL, 0xFFF000,
				      (crystal_cap | (crystal_cap << 6)));
		}
	} else {
		cfo_khz_a = (int)(rtldm->cfo_tail[0] * 3125) / 1280;
		cfo_khz_b = (int)(rtldm->cfo_tail[1] * 3125) / 1280;
		packet_count = rtldm->packet_count;

		if (packet_count == rtldm->packet_count_pre)
			return;

		rtldm->packet_count_pre = packet_count;

		if (hw->dm->rf_path_count == 1U)
			cfo_ave = cfo_khz_a;
		else
			cfo_ave = (int)(cfo_khz_a + cfo_khz_b) >> 1;

		cfo_ave_diff = (rtldm->cfo_ave_pre >= cfo_ave) ?
			       (rtldm->cfo_ave_pre - cfo_ave) :
			       (cfo_ave - rtldm->cfo_ave_pre);

		if (cfo_ave_diff > 20 && !rtldm->large_cfo_hit) {
			rtldm->large_cfo_hit = true;
			return;
		} else
			rtldm->large_cfo_hit = false;

		rtldm->cfo_ave_pre = cfo_ave;

		if (cfo_ave >= -rtldm->cfo_threshold &&
		    cfo_ave <= rtldm->cfo_threshold && rtldm->is_freeze == 0) {
			if (rtldm->cfo_threshold == CFO_THRESHOLD_XTAL) {
				rtldm->cfo_threshold = CFO_THRESHOLD_XTAL + 10;
				rtldm->is_freeze = 1;
			} else {
				rtldm->cfo_threshold = CFO_THRESHOLD_XTAL;
			}
		}

		if (cfo_ave > rtldm->cfo_threshold && rtldm->crystal_cap < 0x3f)
			adjust_xtal = ((cfo_ave - CFO_THRESHOLD_XTAL) >> 1) + 1;
		else if ((cfo_ave < -hw->dm->cfo_threshold) &&
					hw->dm->crystal_cap > 0)
			adjust_xtal = ((cfo_ave + CFO_THRESHOLD_XTAL) >> 1) - 1;

		if (adjust_xtal != 0) {
			rtldm->is_freeze = 0;
			rtldm->crystal_cap += adjust_xtal;

			if (rtldm->crystal_cap > 0x3f)
				rtldm->crystal_cap = 0x3f;
			else if (rtldm->crystal_cap < 0)
				rtldm->crystal_cap = 0;

			crystal_cap = rtldm->crystal_cap & 0x3f;
			dm_set_bb(hw, REG_MAC_PHY_CTRL, 0xFFF000,
				      (crystal_cap | (crystal_cap << 6)));
		}

		if (cfo_ave < CFO_THRESHOLD_ATC &&
		    cfo_ave > -CFO_THRESHOLD_ATC) {
			if (rtldm->atc_status == ATC_STATUS_ON) {
				dm_set_bb(hw, ROFDM1_CFOTRACKING, BIT(11),
					      ATC_STATUS_OFF);
				rtldm->atc_status = ATC_STATUS_OFF;
			}
		} else {
			if (rtldm->atc_status == ATC_STATUS_OFF) {
				dm_set_bb(hw, ROFDM1_CFOTRACKING, BIT(11),
					      ATC_STATUS_ON);
				rtldm->atc_status = ATC_STATUS_ON;
			}
		}
	}
}
