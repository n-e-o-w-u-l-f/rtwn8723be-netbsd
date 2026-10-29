/* SPDX-License-Identifier: GPL-2.0 */
/* Copyright(c) 2009-2014 Realtek Corporation. */
/*
 * Pinned RTL8723BE DM thermal callback and its BBSWING helpers.
 * Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab, rtl8723be/dm.c.
 * The callback always calls BBSWING on RF path A, matrix index zero. The
 * unused TXAGC and RF-path-B branch of set_power are outside this module.
 * State publishes only after successful fallible I/O; partial swing
 * writes are rolled back while the owner still grants hardware lifetime.
 */
#include "rtwn8723be_thermal.h"

#define RF90_PATH_A 0U
#define RF_T_METER 0x42U
#define ROFDM0_XATXIQIMBALANCE 0xc80U
#define ROFDM0_XCTXAFE 0xc94U
#define ROFDM0_ECCATHRESHOLD 0xc4cU
#define MASKDWORD UINT32_MAX
#define MASKH4BITS 0xf0000000U
#define BIT(n) (UINT32_C(1) << (n))
#define TXSCALE_TABLE_SIZE 30U
#define OFDM_TABLE_SIZE 37
#define CCK_TABLE_SIZE 33
#define AVG_THERMAL_NUM_8723BE 4
#define IQK_THRESHOLD 8U
#define EEPROM_THERMAL_METER_88E 0xbaU
#define EEPROM_DEFAULT_THERMALMETER 0x18U

struct thermal_work {
    const struct rtwn8723be_calibration_context *ctx;
    struct rtwn8723be_calibration_state *calibration;
    struct rtwn8723be_thermal_state *dm;
    uint8_t eeprom;
    uint32_t bb_saved[3];
    uint8_t cck_saved[8];
    int error, restore_error;
    bool touched;
};

static bool
thermal_ready(struct thermal_work *hw)
{
    if (hw->error != 0)
        return false;
    if (!hw->ctx->io->ready(hw->ctx->arg)) {
        hw->error = ENXIO;
        return false;
    }
    return true;
}

static uint32_t
thermal_get_rf(struct thermal_work *hw, unsigned int path, uint32_t reg,
    uint32_t mask)
{
    uint32_t value = 0;
    if (thermal_ready(hw))
        hw->error = hw->ctx->io->read_rf(hw->ctx->arg, path, reg, mask, &value);
    return value;
}

static void
thermal_set_bb(struct thermal_work *hw, uint32_t reg, uint32_t mask,
    uint32_t value)
{
    if (thermal_ready(hw)) {
        hw->touched = true;
        hw->error = hw->ctx->io->write_bb(hw->ctx->arg, reg, mask, value);
    }
}

static void
thermal_set_mac(struct thermal_work *hw, uint32_t reg, uint8_t value)
{
    if (thermal_ready(hw)) {
        hw->touched = true;
        hw->error = hw->ctx->io->write_mac(hw->ctx->arg, reg, 1U, value);
    }
}

static void
thermal_lck(struct thermal_work *hw)
{
    if (thermal_ready(hw)) {
        hw->error = rtwn8723be_calibration_lck(hw->ctx, hw->calibration);
        if (hw->error != 0)
            hw->restore_error = hw->calibration->last_restore_error;
    }
}

static void
thermal_iqk(struct thermal_work *hw, bool recovery)
{
    bool initialized = hw->calibration->iqk_initialized;
    if (thermal_ready(hw)) {
        hw->error = rtwn8723be_calibration_iqk(hw->ctx, hw->calibration, recovery);
        /* Only hw_init sets iqk_initialized in the pin; DM IQK does not. */
        if (hw->error == 0)
            hw->calibration->iqk_initialized = initialized;
        else
            hw->restore_error = hw->calibration->last_restore_error;
    }
}

#include "rtwn8723be_thermal_linux.inc"

static void
thermal_set_power(struct thermal_work *hw)
{
    const uint8_t *cck;
    unsigned int i;
    if (hw->dm->swing_idx_cck >= CCK_TABLE_SIZE)
        hw->dm->swing_idx_cck = CCK_TABLE_SIZE - 1;
    cck = hw->dm->cck_inch14 ? cckswing_table_ch14[hw->dm->swing_idx_cck] :
        cckswing_table_ch1ch13[hw->dm->swing_idx_cck];
    for (i = 0; i < 8U; i++)
        thermal_set_mac(hw, 0xa22U + i, cck[i]);
    thermal_set_matrix(hw, hw->dm->swing_idx_ofdm[0], RF90_PATH_A,
        hw->calibration->iqk_matrix[0], hw->calibration->iqk_matrix[1]);
}

#include "rtwn8723be_thermal_body.inc"

void
rtwn8723be_thermal_txpower_init(struct rtwn8723be_thermal_state *dm)
{
    if (dm == NULL)
        return;
    dm->txpower_tracking = true;
    dm->txpower_track_control = true;
    dm->thermalvalue = 0;
    dm->ofdm_index[0] = 30;
    dm->cck_index = 20;
    dm->swing_idx_cck_base = (uint8_t)dm->cck_index;
    dm->swing_idx_ofdm_base[0] = (uint8_t)dm->ofdm_index[0];
    dm->delta_power_index[0] = 0;
    dm->delta_power_index_last[0] = 0;
    dm->power_index_offset[0] = 0;
    dm->txpower_state_valid = true;
}

int
rtwn8723be_thermal_meter_parse(const uint8_t *map, size_t length,
    bool autoload_ok, uint8_t *meter, bool *ignored)
{
    uint8_t parsed;
    bool ignore;
    if (meter == NULL || ignored == NULL)
        return EINVAL;
    if (autoload_ok && (map == NULL || length <= EEPROM_THERMAL_METER_88E))
        return EINVAL;
    parsed = autoload_ok ? map[EEPROM_THERMAL_METER_88E] :
        EEPROM_DEFAULT_THERMALMETER;
    ignore = !autoload_ok || parsed == 0xffU;
    if (ignore)
        parsed = EEPROM_DEFAULT_THERMALMETER;
    *meter = parsed;
    *ignored = ignore;
    return 0;
}

int
rtwn8723be_thermal_callback(const struct rtwn8723be_calibration_context *ctx,
    struct rtwn8723be_calibration_state *calibration,
    struct rtwn8723be_thermal_state *dm,
    const struct rtwn8723be_thermal_inputs *input)
{
    static const uint32_t bb_regs[] = {0xc80U, 0xc94U, 0xc4cU};
    struct rtwn8723be_thermal_state next;
    struct thermal_work hw;
    const struct rtwn8723be_calibration_io *io;
    uint32_t value;
    unsigned int i;
    int error, restore;
    if (ctx == NULL || ctx->io == NULL || calibration == NULL ||
        dm == NULL || input == NULL)
        return EINVAL;
    if (!dm->txpower_state_valid || !input->eeprom_meter_valid)
        return ENXIO;
    if (input->current_channel < 1U || input->current_channel > 14U ||
        dm->thermalvalue_avg_index >= AVG_THERMAL_NUM_8723BE ||
        dm->cck_inch14 != (input->current_channel == 14U))
        return EINVAL;
    if (calibration->lck_inprogress)
        return EBUSY;
    io = ctx->io;
    if (io->ready == NULL || io->read_bb == NULL || io->write_bb == NULL ||
        io->read_rf == NULL || io->write_rf == NULL ||
        io->read_mac == NULL || io->write_mac == NULL ||
        io->delay_us == NULL || io->scan_active == NULL)
        return ENXIO;
    memset(&hw, 0, sizeof(hw));
    next = *dm;
    hw.ctx = ctx;
    hw.calibration = calibration;
    hw.dm = &next;
    hw.eeprom = input->eeprom_thermalmeter;
    for (i = 0; i < 3U && thermal_ready(&hw); i++)
        hw.error = io->read_bb(ctx->arg, bb_regs[i], UINT32_MAX, &hw.bb_saved[i]);
    for (i = 0; i < 8U && thermal_ready(&hw); i++) {
        hw.error = io->read_mac(ctx->arg, 0xa22U + i, 1U, &value);
        if (hw.error == 0)
            hw.cck_saved[i] = (uint8_t)value;
    }
    if (hw.error == 0)
        thermal_callback_body(&hw);
    error = hw.error;
    if (error == 0) {
        next.last_error = next.last_restore_error = 0;
        *dm = next;
        return 0;
    }
    dm->last_error = error;
    dm->last_restore_error = hw.restore_error;
    if (hw.touched) {
        /* Attempt each restoration even if a previous one fails. */
        for (i = 0; i < 11U; i++) {
            if (!io->ready(ctx->arg)) {
                if (dm->last_restore_error == 0)
                    dm->last_restore_error = ENXIO;
                break;
            }
            if (i < 8U)
                restore = io->write_mac(ctx->arg, 0xa22U + i, 1U,
                    hw.cck_saved[i]);
            else
                restore = io->write_bb(ctx->arg, bb_regs[i - 8U], UINT32_MAX,
                    hw.bb_saved[i - 8U]);
            if (dm->last_restore_error == 0 && restore != 0)
                dm->last_restore_error = restore;
        }
    }
    return error;
}
