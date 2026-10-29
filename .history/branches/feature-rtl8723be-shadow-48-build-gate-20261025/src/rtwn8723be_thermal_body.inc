/* SPDX-License-Identifier: GPL-2.0 */
/* Copyright(c) 2009-2014 Realtek Corporation. */
static void thermal_callback_body(
							struct thermal_work *hw)
{
	uint8_t thermalvalue = 0, delta, delta_lck, delta_iqk;
	uint8_t thermalvalue_avg_count = 0;
	uint32_t thermalvalue_avg = 0;
	int i = 0;

	uint8_t ofdm_min_index = 6;

	static const int8_t delta_swing_table_idx_tup_a[TXSCALE_TABLE_SIZE] = {
		0, 0, 1, 2, 2, 2, 3, 3, 3, 4,  5,
		5, 6, 6, 7, 7, 8, 8, 9, 9, 9, 10,
		10, 11, 11, 12, 12, 13, 14, 15};
	static const int8_t delta_swing_table_idx_tdown_a[TXSCALE_TABLE_SIZE] = {
		0, 0, 1, 2, 2, 2, 3, 3, 3, 4,  5,
		5, 6, 6, 6, 6, 7, 7, 7, 8, 8,  9,
		9, 10, 10, 11, 12, 13, 14, 15};

	/*Initilization ( 7 steps in total )*/
	hw->dm->txpower_trackinginit = true;
	((void)0);

	thermalvalue = (uint8_t)thermal_get_rf(hw,
		RF90_PATH_A, RF_T_METER, 0xfc00);
	if (!hw->dm->txpower_track_control || thermalvalue == 0 ||
	    hw->eeprom == 0xFF)
		return;
	((void)0);
	/*3 Initialize ThermalValues of RFCalibrateInfo*/
	if (!hw->dm->thermalvalue) {
		hw->dm->thermalvalue_lck = thermalvalue;
		hw->dm->thermalvalue_iqk = thermalvalue;
	}

	/*4 Calculate average thermal meter*/
	hw->dm->thermalvalue_avg[hw->dm->thermalvalue_avg_index] = thermalvalue;
	hw->dm->thermalvalue_avg_index++;
	if (hw->dm->thermalvalue_avg_index == AVG_THERMAL_NUM_8723BE)
		hw->dm->thermalvalue_avg_index = 0;

	for (i = 0; i < AVG_THERMAL_NUM_8723BE; i++) {
		if (hw->dm->thermalvalue_avg[i]) {
			thermalvalue_avg += hw->dm->thermalvalue_avg[i];
			thermalvalue_avg_count++;
		}
	}

	if (thermalvalue_avg_count)
		thermalvalue = (uint8_t)(thermalvalue_avg / thermalvalue_avg_count);

	/* 5 Calculate delta, delta_LCK, delta_IQK.*/
	delta = (thermalvalue > hw->dm->thermalvalue) ?
		(thermalvalue - hw->dm->thermalvalue) :
		(hw->dm->thermalvalue - thermalvalue);
	delta_lck = (thermalvalue > hw->dm->thermalvalue_lck) ?
		    (thermalvalue - hw->dm->thermalvalue_lck) :
		    (hw->dm->thermalvalue_lck - thermalvalue);
	delta_iqk = (thermalvalue > hw->dm->thermalvalue_iqk) ?
		    (thermalvalue - hw->dm->thermalvalue_iqk) :
		    (hw->dm->thermalvalue_iqk - thermalvalue);

	((void)0);
	/* 6 If necessary, do LCK.*/
	if (delta_lck >= IQK_THRESHOLD) {
		hw->dm->thermalvalue_lck = thermalvalue;
		thermal_lck(hw);
	}

	/* 7 If necessary, move the index of
	 * swing table to adjust Tx power.
	 */
	if (delta > 0 && hw->dm->txpower_track_control) {
		delta = (thermalvalue > hw->eeprom) ?
			(thermalvalue - hw->eeprom) :
			(hw->eeprom - thermalvalue);

		if (delta >= TXSCALE_TABLE_SIZE)
			delta = TXSCALE_TABLE_SIZE - 1;
		/* 7.1 Get the final CCK_index and
		 * OFDM_index for each swing table.
		 */
		if (thermalvalue > hw->eeprom) {
			hw->dm->delta_power_index_last[RF90_PATH_A] =
					hw->dm->delta_power_index[RF90_PATH_A];
			hw->dm->delta_power_index[RF90_PATH_A] =
					delta_swing_table_idx_tup_a[delta];
		} else {
			hw->dm->delta_power_index_last[RF90_PATH_A] =
					hw->dm->delta_power_index[RF90_PATH_A];
			hw->dm->delta_power_index[RF90_PATH_A] =
				-1 * delta_swing_table_idx_tdown_a[delta];
		}

		/* 7.2 Handle boundary conditions of index.*/
		if (hw->dm->delta_power_index[RF90_PATH_A] ==
		    hw->dm->delta_power_index_last[RF90_PATH_A])
			hw->dm->power_index_offset[RF90_PATH_A] = 0;
		else
			hw->dm->power_index_offset[RF90_PATH_A] =
				hw->dm->delta_power_index[RF90_PATH_A] -
				hw->dm->delta_power_index_last[RF90_PATH_A];

		hw->dm->ofdm_index[0] =
			hw->dm->swing_idx_ofdm_base[RF90_PATH_A] +
			hw->dm->power_index_offset[RF90_PATH_A];
		hw->dm->cck_index = hw->dm->swing_idx_cck_base +
				   hw->dm->power_index_offset[RF90_PATH_A];

		hw->dm->swing_idx_cck = hw->dm->cck_index;
		hw->dm->swing_idx_ofdm[0] = hw->dm->ofdm_index[0];

		if (hw->dm->ofdm_index[0] > OFDM_TABLE_SIZE - 1)
			hw->dm->ofdm_index[0] = OFDM_TABLE_SIZE - 1;
		else if (hw->dm->ofdm_index[0] < ofdm_min_index)
			hw->dm->ofdm_index[0] = ofdm_min_index;

		if (hw->dm->cck_index > CCK_TABLE_SIZE - 1)
			hw->dm->cck_index = CCK_TABLE_SIZE - 1;
		else if (hw->dm->cck_index < 0)
			hw->dm->cck_index = 0;
	} else {
		hw->dm->power_index_offset[RF90_PATH_A] = 0;
	}

	if ((hw->dm->power_index_offset[RF90_PATH_A] != 0) &&
	    (hw->dm->txpower_track_control)) {
		hw->dm->done_txpower = true;
		thermal_set_power(hw);

		hw->dm->swing_idx_cck_base = hw->dm->swing_idx_cck;
		hw->dm->swing_idx_ofdm_base[RF90_PATH_A] =
						hw->dm->swing_idx_ofdm[0];
		hw->dm->thermalvalue = thermalvalue;
	}

	if (delta_iqk >= IQK_THRESHOLD) {
		hw->dm->thermalvalue_iqk = thermalvalue;
		thermal_iqk(hw, false);
	}

	hw->dm->txpowercount = 0;
	((void)0);

}
