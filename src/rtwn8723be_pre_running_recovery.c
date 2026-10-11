/* SPDX-License-Identifier: BSD-2-Clause */
#include "rtwn8723be_os_compat.h"

#include "rtwn8723be_pre_running_recovery.h"

static bool
rtwn8723be_pre_running_stage(const struct rtwn8723be_linux_state *state)
{
    return state != NULL && !state->started && !state->being_init_adapter &&
        state->stage >= R23BE_STAGE_RESET_RINGS &&
        state->stage <= R23BE_STAGE_RX_CONFIG;
}

static bool
rtwn8723be_pre_running_resource_valid(
    enum rtwn8723be_pre_running_resource resource)
{
    uint32_t value = (uint32_t)resource;

    return value != 0 && (value & (value - 1U)) == 0 &&
        (value & ~R23BE_PRE_RUNNING_ALL_RESOURCES) == 0;
}

static int
rtwn8723be_pre_running_recovery_preflight(
    const struct rtwn8723be_pre_running_recovery *recovery,
    const struct rtwn8723be_pre_running_recovery_ops *ops)
{
    uint32_t acquired;

    if (ops == NULL)
        return EINVAL;
    acquired = recovery->acquired;
    if (acquired == 0)
        return EINVAL;
    if ((acquired & R23BE_PRE_RUNNING_IRQ_LIVE) != 0 &&
        (ops->mask_irq == NULL || ops->drain_irq == NULL))
        return ENOSYS;
    if ((acquired & R23BE_PRE_RUNNING_POST_HW_CONFIG) != 0 &&
        ops->undo_post_hw_config == NULL)
        return ENOSYS;
    if ((acquired & R23BE_PRE_RUNNING_DMA_DM) != 0 &&
        ops->undo_dma_dm == NULL)
        return ENOSYS;
    if ((acquired & R23BE_PRE_RUNNING_FW_PHY) != 0 &&
        ops->undo_fw_phy == NULL)
        return ENOSYS;
    if ((acquired & R23BE_PRE_RUNNING_LINK_MAC) != 0 &&
        ops->undo_link_mac == NULL)
        return ENOSYS;
    if ((acquired & R23BE_PRE_RUNNING_BTC_PREPARE) != 0 &&
        ops->undo_btc_prepare == NULL)
        return ENOSYS;
    if ((acquired & R23BE_PRE_RUNNING_RINGS_RESET) != 0 &&
        ops->undo_rings_reset == NULL)
        return ENOSYS;
    return 0;
}

static int
rtwn8723be_pre_running_recovery_call(void *ctx,
    struct rtwn8723be_pre_running_recovery *recovery,
    enum rtwn8723be_pre_running_resource resource, int (*op)(void *))
{
    int error;

    error = op(ctx);
    if (error != 0) {
        recovery->recovery_error = error;
        recovery->phase = R23BE_PRE_RUNNING_RECOVERY_FAILED;
        return error;
    }
    recovery->acquired &= ~(uint32_t)resource;
    recovery->released |= (uint32_t)resource;
    return 0;
}

void
rtwn8723be_pre_running_recovery_init(
    struct rtwn8723be_pre_running_recovery *recovery)
{
    if (recovery != NULL)
        memset(recovery, 0, sizeof(*recovery));
}

int
rtwn8723be_pre_running_recovery_arm(
    struct rtwn8723be_pre_running_recovery *recovery,
    const struct rtwn8723be_linux_state *state)
{
    if (recovery == NULL || state == NULL)
        return EINVAL;
    if (recovery->phase != R23BE_PRE_RUNNING_RECOVERY_IDLE)
        return EBUSY;
    if (state->started || state->being_init_adapter ||
        (state->stage != R23BE_STAGE_PROBED &&
        state->stage != R23BE_STAGE_STOPPED))
        return EAGAIN;
    recovery->phase = R23BE_PRE_RUNNING_RECOVERY_ARMED;
    return 0;
}

int
rtwn8723be_pre_running_recovery_mark(
    struct rtwn8723be_pre_running_recovery *recovery,
    const struct rtwn8723be_linux_state *state,
    enum rtwn8723be_pre_running_resource resource)
{
    uint32_t value = (uint32_t)resource;

    if (recovery == NULL || state == NULL)
        return EINVAL;
    if (recovery->phase != R23BE_PRE_RUNNING_RECOVERY_ARMED)
        return EBUSY;
    if (!rtwn8723be_pre_running_stage(state))
        return EAGAIN;
    if (!rtwn8723be_pre_running_resource_valid(resource))
        return EINVAL;
    if ((recovery->acquired & value) != 0)
        return EALREADY;
    recovery->acquired |= value;
    return 0;
}

int
rtwn8723be_pre_running_recovery_begin(
    struct rtwn8723be_pre_running_recovery *recovery,
    const struct rtwn8723be_linux_state *state, int start_error,
    bool exclusive)
{
    if (recovery == NULL || state == NULL || start_error == 0)
        return EINVAL;
    if (recovery->phase != R23BE_PRE_RUNNING_RECOVERY_ARMED)
        return EBUSY;
    if (!exclusive)
        return EBUSY;
    if (!rtwn8723be_pre_running_stage(state))
        return EAGAIN;
    if (recovery->acquired == 0)
        return EINVAL;
    recovery->failed_stage = state->stage;
    recovery->start_error = start_error;
    recovery->recovery_error = 0;
    recovery->phase = R23BE_PRE_RUNNING_RECOVERY_OPEN;
    return 0;
}

int
rtwn8723be_pre_running_recovery_run(void *ctx,
    struct rtwn8723be_linux_state *state,
    struct rtwn8723be_pre_running_recovery *recovery,
    const struct rtwn8723be_pre_running_recovery_ops *ops)
{
    int error;

    if (state == NULL || recovery == NULL)
        return EINVAL;
    if (recovery->phase == R23BE_PRE_RUNNING_RECOVERY_COMPLETE)
        return EALREADY;
    if (recovery->phase != R23BE_PRE_RUNNING_RECOVERY_OPEN)
        return EBUSY;
    if (!rtwn8723be_pre_running_stage(state) ||
        state->stage != recovery->failed_stage)
        return EAGAIN;

    error = rtwn8723be_pre_running_recovery_preflight(recovery, ops);
    if (error != 0)
        return error;
    recovery->phase = R23BE_PRE_RUNNING_RECOVERY_RUNNING;

    if ((recovery->acquired & R23BE_PRE_RUNNING_IRQ_LIVE) != 0) {
        error = ops->mask_irq(ctx);
        if (error != 0) {
            recovery->recovery_error = error;
            recovery->phase = R23BE_PRE_RUNNING_RECOVERY_FAILED;
            return error;
        }
        error = rtwn8723be_pre_running_recovery_call(ctx, recovery,
            R23BE_PRE_RUNNING_IRQ_LIVE, ops->drain_irq);
        if (error != 0)
            return error;
    }
    if ((recovery->acquired & R23BE_PRE_RUNNING_POST_HW_CONFIG) != 0) {
        error = rtwn8723be_pre_running_recovery_call(ctx, recovery,
            R23BE_PRE_RUNNING_POST_HW_CONFIG, ops->undo_post_hw_config);
        if (error != 0)
            return error;
    }
    if ((recovery->acquired & R23BE_PRE_RUNNING_DMA_DM) != 0) {
        error = rtwn8723be_pre_running_recovery_call(ctx, recovery,
            R23BE_PRE_RUNNING_DMA_DM, ops->undo_dma_dm);
        if (error != 0)
            return error;
    }
    if ((recovery->acquired & R23BE_PRE_RUNNING_FW_PHY) != 0) {
        error = rtwn8723be_pre_running_recovery_call(ctx, recovery,
            R23BE_PRE_RUNNING_FW_PHY, ops->undo_fw_phy);
        if (error != 0)
            return error;
    }
    if ((recovery->acquired & R23BE_PRE_RUNNING_LINK_MAC) != 0) {
        error = rtwn8723be_pre_running_recovery_call(ctx, recovery,
            R23BE_PRE_RUNNING_LINK_MAC, ops->undo_link_mac);
        if (error != 0)
            return error;
    }
    if ((recovery->acquired & R23BE_PRE_RUNNING_BTC_PREPARE) != 0) {
        error = rtwn8723be_pre_running_recovery_call(ctx, recovery,
            R23BE_PRE_RUNNING_BTC_PREPARE, ops->undo_btc_prepare);
        if (error != 0)
            return error;
    }
    if ((recovery->acquired & R23BE_PRE_RUNNING_RINGS_RESET) != 0) {
        error = rtwn8723be_pre_running_recovery_call(ctx, recovery,
            R23BE_PRE_RUNNING_RINGS_RESET, ops->undo_rings_reset);
        if (error != 0)
            return error;
    }

    state->being_init_adapter = false;
    state->started = false;
    state->fw_ready = false;
    state->mac_func_enable = false;
    state->stage = R23BE_STAGE_STOPPED;
    recovery->phase = R23BE_PRE_RUNNING_RECOVERY_COMPLETE;
    return 0;
}
