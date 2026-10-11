/* SPDX-License-Identifier: BSD-2-Clause */
/*
 * Explicit ownership for a NetBSD-only recovery after a failed Linux-order
 * adapter start, before HAL START has been published.
 *
 * Linux rtl_pci_start() returns directly for this failure class; it does not
 * call rtl_pci_stop().  This model keeps that forward-path behavior intact.
 * A future NetBSD adapter may use this journal only after it has recorded the
 * resources it actually acquired and obtained exclusive lifecycle ownership.
 */
#ifndef _RTWN8723BE_PRE_RUNNING_RECOVERY_H_
#define _RTWN8723BE_PRE_RUNNING_RECOVERY_H_

#include "rtwn8723be_linux_state.h"

enum rtwn8723be_pre_running_resource {
    R23BE_PRE_RUNNING_RINGS_RESET = UINT32_C(1) << 0,
    R23BE_PRE_RUNNING_BTC_PREPARE = UINT32_C(1) << 1,
    R23BE_PRE_RUNNING_LINK_MAC = UINT32_C(1) << 2,
    R23BE_PRE_RUNNING_FW_PHY = UINT32_C(1) << 3,
    R23BE_PRE_RUNNING_DMA_DM = UINT32_C(1) << 4,
    R23BE_PRE_RUNNING_POST_HW_CONFIG = UINT32_C(1) << 5,
    R23BE_PRE_RUNNING_IRQ_LIVE = UINT32_C(1) << 6
};

#define R23BE_PRE_RUNNING_ALL_RESOURCES ((uint32_t)( \
    R23BE_PRE_RUNNING_RINGS_RESET | R23BE_PRE_RUNNING_BTC_PREPARE | \
    R23BE_PRE_RUNNING_LINK_MAC | R23BE_PRE_RUNNING_FW_PHY | \
    R23BE_PRE_RUNNING_DMA_DM | R23BE_PRE_RUNNING_POST_HW_CONFIG | \
    R23BE_PRE_RUNNING_IRQ_LIVE))

enum rtwn8723be_pre_running_recovery_phase {
    R23BE_PRE_RUNNING_RECOVERY_IDLE = 0,
    R23BE_PRE_RUNNING_RECOVERY_ARMED,
    R23BE_PRE_RUNNING_RECOVERY_OPEN,
    R23BE_PRE_RUNNING_RECOVERY_RUNNING,
    R23BE_PRE_RUNNING_RECOVERY_FAILED,
    R23BE_PRE_RUNNING_RECOVERY_COMPLETE
};

struct rtwn8723be_pre_running_recovery {
    enum rtwn8723be_pre_running_recovery_phase phase;
    enum rtwn8723be_linux_stage failed_stage;
    uint32_t acquired;
    uint32_t released;
    int start_error;
    int recovery_error;
};

/* These are recovery-only compensators, not normal RUNNING stop callbacks. */
struct rtwn8723be_pre_running_recovery_ops {
    int (*mask_irq)(void *);
    int (*drain_irq)(void *);
    int (*undo_post_hw_config)(void *);
    int (*undo_dma_dm)(void *);
    int (*undo_fw_phy)(void *);
    int (*undo_link_mac)(void *);
    int (*undo_btc_prepare)(void *);
    int (*undo_rings_reset)(void *);
};

void rtwn8723be_pre_running_recovery_init(
    struct rtwn8723be_pre_running_recovery *);
int rtwn8723be_pre_running_recovery_arm(
    struct rtwn8723be_pre_running_recovery *,
    const struct rtwn8723be_linux_state *);
int rtwn8723be_pre_running_recovery_mark(
    struct rtwn8723be_pre_running_recovery *,
    const struct rtwn8723be_linux_state *,
    enum rtwn8723be_pre_running_resource);
int rtwn8723be_pre_running_recovery_begin(
    struct rtwn8723be_pre_running_recovery *,
    const struct rtwn8723be_linux_state *, int, bool);
int rtwn8723be_pre_running_recovery_run(void *,
    struct rtwn8723be_linux_state *,
    struct rtwn8723be_pre_running_recovery *,
    const struct rtwn8723be_pre_running_recovery_ops *);

#endif
