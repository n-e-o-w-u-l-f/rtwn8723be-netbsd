/* SPDX-License-Identifier: GPL-2.0 */
/* Copyright(c) 2009-2014 Realtek Corporation. */
/*
 * Real frozen RTL8723BE IQK/LCK algorithm with fallible I/O and rollback.
 * Success retains the pinned writes, retry limits, signed similarity,
 * matrix selection, recovery register order and calibration delays.
 * Additional reads save every calibration-mutated register before writes.
 * A transport/ownership error stops forward writes, attempts full restore,
 * reports both errors, and never publishes a partially written cache.
 * This is not an MMIO binding or hardware acceptance claim.
 */
#include "rtwn8723be_calibration.h"

enum cal_kind { CAL_BB, CAL_RF, CAL_MAC };
struct cal_saved {
    enum cal_kind kind;
    uint32_t reg, value;
    unsigned int width;
};
struct calibration_work {
    const struct rtwn8723be_calibration_context *ctx;
    uint32_t adda_backup[16], bb_backup[9], mac_backup[4];
    uint8_t rfpi_enable;
    int error;
    bool touched;
    struct cal_saved saved[80];
    unsigned int saved_count;
};

static bool
cal_ready(struct calibration_work *hw)
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
cal_get_bb(struct calibration_work *hw, uint32_t reg, uint32_t mask)
{
    uint32_t value = 0;
    if (cal_ready(hw))
        hw->error = hw->ctx->io->read_bb(hw->ctx->arg, reg, mask, &value);
    return value;
}

static void
cal_set_bb(struct calibration_work *hw, uint32_t reg, uint32_t mask,
    uint32_t value)
{
    if (cal_ready(hw)) {
        hw->touched = true;
        hw->error = hw->ctx->io->write_bb(hw->ctx->arg, reg, mask, value);
    }
}

static uint32_t
cal_get_rf(struct calibration_work *hw, uint32_t reg, uint32_t mask)
{
    uint32_t value = 0;
    if (cal_ready(hw))
        hw->error = hw->ctx->io->read_rf(hw->ctx->arg, 0U, reg, mask, &value);
    return value;
}

static void
cal_set_rf(struct calibration_work *hw, unsigned int path, uint32_t reg,
    uint32_t mask, uint32_t value)
{
    if (cal_ready(hw)) {
        hw->touched = true;
        hw->error = hw->ctx->io->write_rf(hw->ctx->arg, path, reg, mask, value);
    }
}

static uint32_t
cal_get_mac(struct calibration_work *hw, uint32_t reg, unsigned int width)
{
    uint32_t value = 0;
    if (cal_ready(hw))
        hw->error = hw->ctx->io->read_mac(hw->ctx->arg, reg, width, &value);
    return value;
}

static void
cal_set_mac(struct calibration_work *hw, uint32_t reg, unsigned int width,
    uint32_t value)
{
    if (cal_ready(hw)) {
        hw->touched = true;
        hw->error = hw->ctx->io->write_mac(hw->ctx->arg, reg, width, value);
    }
}

static void
cal_delay(struct calibration_work *hw, unsigned int usec)
{
    if (cal_ready(hw))
        hw->error = hw->ctx->io->delay_us(hw->ctx->arg, usec);
}

static int
cal_init(struct calibration_work *hw,
    const struct rtwn8723be_calibration_context *ctx)
{
    const struct rtwn8723be_calibration_io *io;
    if (ctx == NULL || ctx->io == NULL)
        return EINVAL;
    io = ctx->io;
    if (io->ready == NULL || io->read_bb == NULL || io->write_bb == NULL ||
        io->read_rf == NULL || io->write_rf == NULL ||
        io->read_mac == NULL || io->write_mac == NULL ||
        io->delay_us == NULL || io->scan_active == NULL)
        return ENXIO;
    memset(hw, 0, sizeof(*hw));
    hw->ctx = ctx;
    return cal_ready(hw) ? 0 : hw->error;
}

static void
cal_snapshot(struct calibration_work *hw, enum cal_kind kind,
    uint32_t reg, unsigned int width)
{
    struct cal_saved *save;
    if (hw->error != 0)
        return;
    if (hw->saved_count >= sizeof(hw->saved) / sizeof(hw->saved[0])) {
        hw->error = EOVERFLOW;
        return;
    }
    save = &hw->saved[hw->saved_count];
    save->kind = kind;
    save->reg = reg;
    save->width = width;
    if (kind == CAL_BB)
        save->value = cal_get_bb(hw, reg, UINT32_MAX);
    else if (kind == CAL_RF)
        save->value = cal_get_rf(hw, reg, 0xfffffU);
    else
        save->value = cal_get_mac(hw, reg, width);
    if (hw->error == 0)
        hw->saved_count++;
}

static int
cal_restore(struct calibration_work *hw)
{
    const struct rtwn8723be_calibration_io *io = hw->ctx->io;
    struct cal_saved *save;
    unsigned int i;
    int error, first = 0;
    if (!hw->touched)
        return 0;
    /* No restoration access after the owner has revoked MMIO/RF lifetime. */
    for (i = hw->saved_count; i > 0; i--) {
        save = &hw->saved[i - 1];
        if (!io->ready(hw->ctx->arg)) {
            if (first == 0)
                first = ENXIO;
            break;
        }
        if (save->kind == CAL_BB)
            error = io->write_bb(hw->ctx->arg, save->reg, UINT32_MAX,
                save->value);
        else if (save->kind == CAL_RF)
            error = io->write_rf(hw->ctx->arg, 0U, save->reg, 0xfffffU,
                save->value);
        else
            error = io->write_mac(hw->ctx->arg, save->reg, save->width,
                save->value);
        if (first == 0 && error != 0)
            first = error;
    }
    return first;
}

static void
cal_save_bb(struct calibration_work *hw, const uint32_t *regs,
    uint32_t *values, unsigned int count)
{
    unsigned int i;
    for (i = 0; i < count; i++)
        values[i] = cal_get_bb(hw, regs[i], UINT32_MAX);
}

static void
cal_reload_bb(struct calibration_work *hw, const uint32_t *regs,
    const uint32_t *values, unsigned int count)
{
    unsigned int i;
    for (i = 0; i < count; i++)
        cal_set_bb(hw, regs[i], UINT32_MAX, values[i]);
}

static void
cal_save_mac(struct calibration_work *hw, const uint32_t *regs,
    uint32_t *values)
{
    unsigned int i;
    for (i = 0; i < 4; i++)
        values[i] = cal_get_mac(hw, regs[i], i == 3 ? 4U : 1U);
}

static void
cal_reload_mac(struct calibration_work *hw, const uint32_t *regs,
    const uint32_t *values)
{
    unsigned int i;
    for (i = 0; i < 4; i++)
        cal_set_mac(hw, regs[i], i == 3 ? 4U : 1U, values[i]);
}

static void
cal_adda_on(struct calibration_work *hw, const uint32_t *regs,
    bool path_a, bool is2t)
{
    unsigned int i;
    (void)path_a;
    (void)is2t;
    /* rtl8723com common helper's RTL8723BE branch. */
    for (i = 0; i < 16; i++)
        cal_set_bb(hw, regs[i], UINT32_MAX, 0x01c00014U);
}

static void
cal_mac_calibration(struct calibration_work *hw, const uint32_t *regs,
    const uint32_t *values)
{
    unsigned int i;
    cal_set_mac(hw, regs[0], 1U, 0x3fU);
    for (i = 1; i < 3; i++)
        cal_set_mac(hw, regs[i], 1U, (uint8_t)(values[i] & ~8U));
    cal_set_mac(hw, regs[3], 1U, (uint8_t)(values[3] & ~32U));
}

#include "rtwn8723be_calibration_linux.inc"

static const uint32_t cal_recovery_regs[9] = {
    0xc14, 0xc1c, 0xc4c, 0xc78, 0xc80, 0xc88, 0xc94, 0xc9c, 0xca0
};

int
rtwn8723be_calibration_iqk(const struct rtwn8723be_calibration_context *ctx,
    struct rtwn8723be_calibration_state *state, bool recovery)
{
    static const uint32_t bb_regs[] = {
        /* e28 is first so error restoration restores the entry mode last. */
        0xe28, 0x85c, 0xe6c, 0xe70, 0xe74, 0xe78, 0xe7c, 0xe80,
        0xe84, 0xe88, 0xe8c, 0xed0, 0xed4, 0xed8, 0xedc, 0xee0, 0xeec,
        0xc04, 0xc08, 0x874, 0xb68, 0xb6c, 0x870, 0x860, 0x864, 0xa04,
        0xc14, 0xc1c, 0xc4c, 0xc78, 0xc80, 0xc88, 0xc94, 0xc9c, 0xca0,
        0x948, 0xc50, 0xc58, 0xe30, 0xe34, 0xe38, 0xe3c, 0xe40,
        0xe44, 0xe48, 0xe4c, 0xe50, 0xe54, 0xe58, 0xe5c
    };
    static const uint32_t rf_regs[] = {0xef, 0x30, 0x31, 0x32,
        0xed, 0x43, 0xdf, 0x55};
    static const uint32_t mac_regs[] = {0x522, 0x550, 0x551, 0x40};
    struct calibration_work work;
    struct rtwn8723be_calibration_state next;
    int32_t result[4][8] = {{0}};
    uint32_t path_sel;
    unsigned int i, j;
    uint8_t candidate = 0xff;
    int error;
    if (state == NULL)
        return EINVAL;
    if (state->lck_inprogress)
        return EBUSY;
    if (recovery && (!state->iqk_initialized || !state->iqk_recovery_valid))
        return ENXIO;
    error = cal_init(&work, ctx);
    if (error != 0)
        return error;
    next = *state;
    state->lck_inprogress = true;
    if (recovery) {
        for (i = 0; i < 9; i++)
            cal_snapshot(&work, CAL_BB, cal_recovery_regs[i], 4U);
        cal_reload_bb(&work, cal_recovery_regs, state->recovery, 9U);
        goto finish;
    }
    for (i = 0; i < sizeof(bb_regs) / sizeof(bb_regs[0]); i++)
        cal_snapshot(&work, CAL_BB, bb_regs[i], 4U);
    for (i = 0; i < sizeof(rf_regs) / sizeof(rf_regs[0]); i++)
        cal_snapshot(&work, CAL_RF, rf_regs[i], 4U);
    for (i = 0; i < 4; i++)
        cal_snapshot(&work, CAL_MAC, mac_regs[i], i == 3 ? 4U : 1U);
    path_sel = cal_get_bb(&work, 0x948, UINT32_MAX);
    for (i = 0; i < 3 && work.error == 0; i++) {
        /* This is antenna-route A+B IQK, including the one-TX RF part. */
        cal_iqk_trial(&work, result, (uint8_t)i, true);
        if (i == 1 && cal_compare(&work, result, 0, 1)) {
            candidate = 0;
            break;
        }
        if (i == 2) {
            if (cal_compare(&work, result, 0, 2))
                candidate = 0;
            else if (cal_compare(&work, result, 1, 2))
                candidate = 1;
            else {
                int32_t sum = 0;
                for (j = 0; j < 8; j++)
                    sum += result[3][j];
                if (sum != 0)
                    candidate = 3;
            }
        }
    }
    next.final_candidate = candidate;
    next.reg_e94 = next.reg_eb4 = 0x100;
    next.reg_e9c = next.reg_ebc = 0;
    if (candidate != 0xff) {
        next.reg_e94 = result[candidate][0];
        next.reg_e9c = result[candidate][1];
        next.reg_eb4 = result[candidate][4];
        next.reg_ebc = result[candidate][5];
        if (next.reg_e94 != 0)
            cal_fill_a(&work, true, result, candidate,
                result[candidate][2] == 0);
        if (next.reg_eb4 != 0)
            cal_fill_b(&work, true, result, candidate,
                result[candidate][6] == 0);
        for (i = 0; i < 8; i++)
            next.iqk_matrix[i] = result[candidate][i];
        next.iqk_matrix_done = true;
    }
    cal_save_bb(&work, cal_recovery_regs, next.recovery, 9U);
    cal_set_bb(&work, 0x948, UINT32_MAX, path_sel);
    next.iqk_initialized = true;
    next.iqk_recovery_valid = true;
finish:
    error = work.error;
    state->lck_inprogress = false;
    if (error != 0) {
        state->last_restore_error = cal_restore(&work);
        /* A failed write never licenses later replay of a partial matrix. */
        if (work.touched) {
            state->iqk_initialized = false;
            state->iqk_recovery_valid = false;
        }
        state->last_error = error;
        return error;
    }
    next.lck_inprogress = false;
    next.last_error = next.last_restore_error = 0;
    *state = next;
    return 0;
}

int
rtwn8723be_calibration_lck(const struct rtwn8723be_calibration_context *ctx,
    struct rtwn8723be_calibration_state *state)
{
    struct calibration_work work;
    uint32_t mode = 0, tmp;
    unsigned int waited = 0;
    bool scanning = false;
    int error;
    if (state == NULL)
        return EINVAL;
    if (state->lck_inprogress)
        return EBUSY;
    error = cal_init(&work, ctx);
    if (error != 0)
        return error;
    while (work.error == 0) {
        if (!cal_ready(&work))
            break;
        work.error = ctx->io->scan_active(ctx->arg, &scanning);
        if (!scanning || waited >= 2000U || work.error != 0)
            break;
        cal_delay(&work, 50U);
        waited += 50U;
    }
    state->lck_inprogress = true;
    cal_snapshot(&work, CAL_MAC, 0xd03U, 1U);
    cal_snapshot(&work, CAL_MAC, REG_TXPAUSE, 1U);
    cal_snapshot(&work, CAL_RF, 0U, 4U);
    cal_snapshot(&work, CAL_RF, 0x18U, 4U);
    cal_snapshot(&work, CAL_RF, 0xb0U, 4U);
    tmp = cal_get_mac(&work, 0xd03U, 1U);
    if ((tmp & 0x70U) != 0) {
        cal_set_mac(&work, 0xd03U, 1U, tmp & 0x8fU);
        mode = cal_get_rf(&work, 0U, MASK12BITS);
        cal_set_rf(&work, 0U, 0U, MASK12BITS,
            (mode & 0x8ffffU) | 0x10000U);
    } else {
        cal_set_mac(&work, REG_TXPAUSE, 1U, 0xffU);
    }
    (void)cal_get_rf(&work, 0x18U, MASK12BITS);
    cal_set_rf(&work, 0U, 0xb0U, RFREG_OFFSET_MASK, 0xdfbe0U);
    cal_set_rf(&work, 0U, 0x18U, MASK12BITS, 0x8c0aU);
    cal_delay(&work, 50000U);
    cal_set_rf(&work, 0U, 0xb0U, RFREG_OFFSET_MASK, 0xdffe0U);
    if ((tmp & 0x70U) != 0) {
        cal_set_mac(&work, 0xd03U, 1U, tmp);
        cal_set_rf(&work, 0U, 0U, MASK12BITS, mode);
    } else {
        cal_set_mac(&work, REG_TXPAUSE, 1U, 0U);
    }
    state->lck_inprogress = false;
    state->last_error = work.error;
    state->last_restore_error = work.error == 0 ? 0 : cal_restore(&work);
    return work.error;
}

int
rtwn8723be_calibration_run(const struct rtwn8723be_calibration_context *ctx,
    struct rtwn8723be_calibration_state *state,
    const struct rtwn8723be_calibration_inputs *input)
{
    struct calibration_work work;
    int error;
    if (state == NULL || input == NULL)
        return EINVAL;
    state->tracking_changed = false;
    state->last_restore_error = 0;
    if (!input->rf_state_valid)
        return ENXIO;
    /* Linux's entire calibration block is conditional on ERFON. */
    if (!input->rf_on)
        return 0;
    if (!input->btc_bound || !input->btc_initialized ||
        !input->dm_state_valid)
        return ENXIO;
    if (input->btc_ant_num > 1U || input->current_channel < 1U ||
        input->current_channel > 14U)
        return EINVAL;
    if (state->lck_inprogress)
        return EBUSY;
    error = cal_init(&work, ctx);
    if (error != 0)
        return error;
    if (input->txpower_tracking && input->tm_trigger &&
        ctx->io->thermal_track == NULL)
        return ENOTSUP;
    /* Preserve the old routing if a later calibration transport fails. */
    cal_snapshot(&work, CAL_BB, 0x92cU, 4U);
    cal_set_bb(&work, 0x92cU, UINT32_MAX, 1U);
    error = work.error;
    if (error == 0 && input->btc_ant_num == 0U)
        error = rtwn8723be_calibration_iqk(ctx, state,
            state->iqk_initialized);
    if (error == 0 && input->txpower_tracking) {
        if (!input->tm_trigger) {
            cal_set_rf(&work, 0U, RF_T_METER, BIT(17) | BIT(16), 3U);
            error = work.error;
        } else {
            error = ctx->io->thermal_track(ctx->arg, ctx, state);
        }
        if (error == 0)
            state->tm_trigger = !input->tm_trigger;
        if (error == 0)
            state->tracking_changed = true;
    }
    if (error == 0)
        error = rtwn8723be_calibration_lck(ctx, state);
    state->last_error = error;
    if (error != 0) {
        int restore = cal_restore(&work);
        if (state->last_restore_error == 0)
            state->last_restore_error = restore;
    }
    return error;
}
