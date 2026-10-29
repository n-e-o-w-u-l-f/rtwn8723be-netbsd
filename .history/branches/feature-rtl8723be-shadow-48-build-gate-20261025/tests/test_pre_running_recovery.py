#!/usr/bin/env python3
"""C11 behavior contract for unbound pre-RUNNING resource recovery.

This tests the real lifecycle controller plus the recovery-owner API.  It
does not compile a NetBSD kernel object or bind a hardware callback.
"""
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RECOVERY_SOURCE = (ROOT / "src" / "rtwn8723be_pre_running_recovery.c").read_text()

# This owner compensates only resources recorded by the failed start.  It may
# not steal probe-owned objects or invoke the normal RUNNING stop path.
for forbidden in (
        "pci_intr_disestablish", "bus_dmamap_destroy", "bus_dmamem_free",
        "rtwn8723be_linux_adapter_stop", "bt_halt_deinit", "mark_hal_stop",
        "disable_interrupt", "wait_rf_change_idle", "hw_disable"):
    assert forbidden not in RECOVERY_SOURCE, forbidden

HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "rtwn8723be_linux_state.h"
#include "rtwn8723be_pre_running_recovery.h"

enum trace_id {
    TRACE_MASK_IRQ = 1,
    TRACE_DRAIN_IRQ,
    TRACE_POST_HW,
    TRACE_DMA_DM,
    TRACE_FW_PHY,
    TRACE_LINK_MAC,
    TRACE_BTC,
    TRACE_RINGS
};

struct fixture {
    unsigned start_calls;
    unsigned generic_stop_calls;
    unsigned trace_count;
    unsigned trace[8];
    int recovery_failure;
    bool irq_requested;
    bool irq_enabled;
    bool softint_pending;
    bool rx_pending;
};

static int
start_step(void *arg)
{
    struct fixture *fx = arg;

    ++fx->start_calls;
    return 0;
}

static int
read_cr(void *arg, uint8_t *value)
{
    (void)arg;
    *value = 0;
    return 0;
}

static int
check_dma_hang(void *arg, bool *hang)
{
    (void)arg;
    *hang = false;
    return 0;
}

static int
reset_dma(void *arg, bool mac_enabled)
{
    (void)mac_enabled;
    return start_step(arg);
}

static int
enable_interrupt(void *arg)
{
    struct fixture *fx = arg;

    ++fx->start_calls;
    fx->irq_requested = true;
    fx->irq_enabled = true;
    fx->softint_pending = true;
    return 0;
}

static int
init_rx_config(void *arg)
{
    struct fixture *fx = arg;

    ++fx->start_calls;
    fx->rx_pending = true;
    return 0;
}

static int
fail_mark_hal_start(void *arg)
{
    struct fixture *fx = arg;

    ++fx->start_calls;
    return EIO;
}

static int
generic_stop(void *arg)
{
    struct fixture *fx = arg;

    ++fx->generic_stop_calls;
    return EAGAIN;
}

static struct rtwn8723be_linux_ops
start_ops(void)
{
    struct rtwn8723be_linux_ops ops = {0};

    ops.reset_trx_ring = start_step;
    ops.bt_prepare = start_step;
    ops.disable_aspm = start_step;
    ops.read_cr = read_cr;
    ops.check_pcie_dma_hang = check_dma_hang;
    ops.reset_pcie_interface_dma = reset_dma;
    ops.poweroff_adapter = start_step;
    ops.init_mac = start_step;
    ops.sys_cfg_clear_bit7 = start_step;
    ops.download_firmware = start_step;
    ops.phy_mac_config = start_step;
    ops.rcr_postprocess = start_step;
    ops.phy_bb_config = start_step;
    ops.phy_rf_config = start_step;
    ops.rf_channel_state_init = start_step;
    ops.hw_configure = start_step;
    ops.cam_reset_all = start_step;
    ops.enable_hw_security = start_step;
    ops.set_mac_address = start_step;
    ops.enable_aspm_backdoor = start_step;
    ops.enable_aspm = start_step;
    ops.bt_hw_init = start_step;
    ops.rf_calibration = start_step;
    ops.set_nav_upper_235 = start_step;
    ops.release_rx_dma = start_step;
    ops.release_pcie_dma = start_step;
    ops.dm_init = start_step;
    ops.set_retry_limit = start_step;
    ops.enable_interrupt = enable_interrupt;
    ops.init_rx_config = init_rx_config;
    ops.mark_hal_start = fail_mark_hal_start;

    /* Native-like stop callbacks expose a regression to generic abort. */
    ops.bt_halt_deinit = generic_stop;
    ops.mark_hal_stop = generic_stop;
    ops.disable_interrupt = generic_stop;
    ops.wait_rf_change_idle = generic_stop;
    ops.hw_disable = generic_stop;
    return ops;
}

static int
record(struct fixture *fx, unsigned id)
{
    assert(fx->trace_count < sizeof(fx->trace) / sizeof(fx->trace[0]));
    fx->trace[fx->trace_count++] = id;
    return fx->recovery_failure == (int)id ? EBUSY : 0;
}

static int
mask_irq(void *arg)
{
    struct fixture *fx = arg;
    int error = record(fx, TRACE_MASK_IRQ);

    if (error == 0) {
        fx->irq_requested = false;
        fx->irq_enabled = false;
    }
    return error;
}

static int
drain_irq(void *arg)
{
    struct fixture *fx = arg;
    int error = record(fx, TRACE_DRAIN_IRQ);

    if (error == 0) {
        fx->softint_pending = false;
        fx->rx_pending = false;
    }
    return error;
}

static int post_hw(void *arg) { return record(arg, TRACE_POST_HW); }
static int dma_dm(void *arg) { return record(arg, TRACE_DMA_DM); }
static int fw_phy(void *arg) { return record(arg, TRACE_FW_PHY); }
static int link_mac(void *arg) { return record(arg, TRACE_LINK_MAC); }
static int btc(void *arg) { return record(arg, TRACE_BTC); }
static int rings(void *arg) { return record(arg, TRACE_RINGS); }

static struct rtwn8723be_pre_running_recovery_ops
recovery_ops(void)
{
    struct rtwn8723be_pre_running_recovery_ops ops = {
        .mask_irq = mask_irq,
        .drain_irq = drain_irq,
        .undo_post_hw_config = post_hw,
        .undo_dma_dm = dma_dm,
        .undo_fw_phy = fw_phy,
        .undo_link_mac = link_mac,
        .undo_btc_prepare = btc,
        .undo_rings_reset = rings,
    };
    return ops;
}

static void
mark_all(struct rtwn8723be_pre_running_recovery *recovery,
    const struct rtwn8723be_linux_state *state)
{
    assert(rtwn8723be_pre_running_recovery_mark(recovery, state,
        R23BE_PRE_RUNNING_RINGS_RESET) == 0);
    assert(rtwn8723be_pre_running_recovery_mark(recovery, state,
        R23BE_PRE_RUNNING_BTC_PREPARE) == 0);
    assert(rtwn8723be_pre_running_recovery_mark(recovery, state,
        R23BE_PRE_RUNNING_LINK_MAC) == 0);
    assert(rtwn8723be_pre_running_recovery_mark(recovery, state,
        R23BE_PRE_RUNNING_FW_PHY) == 0);
    assert(rtwn8723be_pre_running_recovery_mark(recovery, state,
        R23BE_PRE_RUNNING_DMA_DM) == 0);
    assert(rtwn8723be_pre_running_recovery_mark(recovery, state,
        R23BE_PRE_RUNNING_POST_HW_CONFIG) == 0);
    assert(rtwn8723be_pre_running_recovery_mark(recovery, state,
        R23BE_PRE_RUNNING_IRQ_LIVE) == 0);
}

int
main(void)
{
    static const unsigned want_trace[] = {
        TRACE_MASK_IRQ, TRACE_DRAIN_IRQ, TRACE_DMA_DM, TRACE_POST_HW,
        TRACE_FW_PHY, TRACE_LINK_MAC, TRACE_BTC, TRACE_RINGS
    };
    struct fixture fx = {0};
    struct rtwn8723be_linux_state state = {
        .stage = R23BE_STAGE_PROBED
    };
    struct rtwn8723be_linux_ops start = start_ops();
    struct rtwn8723be_pre_running_recovery recovery;
    struct rtwn8723be_pre_running_recovery ordering;
    struct rtwn8723be_pre_running_recovery_ops ops = recovery_ops();

    rtwn8723be_pre_running_recovery_init(&recovery);
    rtwn8723be_pre_running_recovery_init(&ordering);
    assert(rtwn8723be_pre_running_recovery_arm(&recovery, &state) == 0);
    assert(rtwn8723be_pre_running_recovery_arm(&ordering, &state) == 0);
    assert(rtwn8723be_linux_adapter_start(&fx, &state, &start) == EIO);
    assert(state.stage == R23BE_STAGE_RX_CONFIG && !state.started &&
        !state.being_init_adapter && state.fw_ready &&
        state.mac_func_enable);
    assert(fx.generic_stop_calls == 0);
    assert(fx.irq_requested && fx.irq_enabled && fx.softint_pending &&
        fx.rx_pending);

    /* The resource journal may skip a phase, but never reorder Linux start. */
    assert(rtwn8723be_pre_running_recovery_mark(&ordering, &state,
        R23BE_PRE_RUNNING_FW_PHY) == 0);
    assert(rtwn8723be_pre_running_recovery_mark(&ordering, &state,
        R23BE_PRE_RUNNING_LINK_MAC) == EINVAL);
    assert(ordering.acquired == R23BE_PRE_RUNNING_FW_PHY);

    mark_all(&recovery, &state);
    assert(rtwn8723be_pre_running_recovery_begin(&recovery, &state, EIO,
        false) == EBUSY);
    assert(recovery.phase == R23BE_PRE_RUNNING_RECOVERY_ARMED);
    assert(rtwn8723be_pre_running_recovery_begin(&recovery, &state, EIO,
        true) == 0);

    /* Missing compensation is rejected before the first cleanup effect. */
    ops.undo_fw_phy = NULL;
    assert(rtwn8723be_pre_running_recovery_run(&fx, &state, &recovery,
        &ops) == ENOSYS);
    assert(recovery.phase == R23BE_PRE_RUNNING_RECOVERY_OPEN);
    assert(fx.trace_count == 0 && fx.generic_stop_calls == 0);
    assert(state.stage == R23BE_STAGE_RX_CONFIG && !state.started);
    ops = recovery_ops();

    /* A drain failure quarantines the owner and must not advance teardown. */
    fx.recovery_failure = TRACE_DRAIN_IRQ;
    assert(rtwn8723be_pre_running_recovery_run(&fx, &state, &recovery,
        &ops) == EBUSY);
    assert(recovery.phase == R23BE_PRE_RUNNING_RECOVERY_FAILED);
    assert(recovery.recovery_error == EBUSY);
    assert(fx.trace_count == 2 && fx.trace[0] == TRACE_MASK_IRQ &&
        fx.trace[1] == TRACE_DRAIN_IRQ);
    assert(!fx.irq_requested && !fx.irq_enabled && fx.softint_pending &&
        fx.rx_pending);
    assert(state.stage == R23BE_STAGE_RX_CONFIG && !state.started &&
        state.fw_ready && state.mac_func_enable);

    /* A new journal is required after a real cleanup failure. */
    memset(&fx, 0, sizeof(fx));
    fx.irq_requested = fx.irq_enabled = fx.softint_pending = fx.rx_pending =
        true;
    state = (struct rtwn8723be_linux_state){
        .stage = R23BE_STAGE_PROBED
    };
    rtwn8723be_pre_running_recovery_init(&recovery);
    assert(rtwn8723be_pre_running_recovery_arm(&recovery, &state) == 0);
    assert(rtwn8723be_linux_adapter_start(&fx, &state, &start) == EIO);
    mark_all(&recovery, &state);
    assert(rtwn8723be_pre_running_recovery_begin(&recovery, &state, EIO,
        true) == 0);
    assert(rtwn8723be_pre_running_recovery_run(&fx, &state, &recovery,
        &ops) == 0);
    assert(recovery.phase == R23BE_PRE_RUNNING_RECOVERY_COMPLETE);
    assert(recovery.acquired == 0 &&
        recovery.released == R23BE_PRE_RUNNING_ALL_RESOURCES &&
        recovery.start_error == EIO && recovery.recovery_error == 0);
    assert(fx.trace_count == sizeof(want_trace) / sizeof(want_trace[0]) &&
        memcmp(fx.trace, want_trace, sizeof(want_trace)) == 0);
    assert(!fx.irq_requested && !fx.irq_enabled && !fx.softint_pending &&
        !fx.rx_pending);
    assert(state.stage == R23BE_STAGE_STOPPED && !state.started &&
        !state.fw_ready && !state.mac_func_enable);
    assert(fx.generic_stop_calls == 0);
    assert(rtwn8723be_linux_adapter_start(&fx, &state, &start) == EIO);
    assert(rtwn8723be_pre_running_recovery_run(&fx, &state, &recovery,
        &ops) == EALREADY);

    state.stage = R23BE_STAGE_PROBED;
    rtwn8723be_pre_running_recovery_init(&recovery);
    assert(rtwn8723be_pre_running_recovery_arm(&recovery, &state) == 0);
    assert(rtwn8723be_pre_running_recovery_begin(&recovery, &state, EIO,
        true) == EAGAIN);
    assert(recovery.phase == R23BE_PRE_RUNNING_RECOVERY_ARMED);

    puts("RTL_PRE_RUNNING_RECOVERY_C11_UBSAN_OK");
    return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="rtl-pre-running-recovery-") as name:
    work = Path(name)
    source = work / "recovery_check.c"
    binary = work / "recovery_check"
    source.write_text(HARNESS)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=undefined", "-fno-sanitize-recover=all",
         "-I", str(ROOT / "src"),
         str(ROOT / "src/rtwn8723be_linux_state.c"),
         str(ROOT / "src/rtwn8723be_pre_running_recovery.c"),
         str(source), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
