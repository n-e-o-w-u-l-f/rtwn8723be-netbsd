#!/usr/bin/env python3
"""Strict C11 regression against the committed Linux-order lifecycle source.

Host-only unit test with mocked callbacks. Does NOT compile a NetBSD
kernel object or establish hardware stop/restart correctness.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_linux_state.h"

struct context { unsigned calls; unsigned fail_at; };
static int step(void *arg)
{
    struct context *c = arg;
    ++c->calls;
    return c->calls == c->fail_at ? EIO : 0;
}
static struct rtwn8723be_linux_state running(void)
{
    struct rtwn8723be_linux_state s = {0};
    s.stage = R23BE_STAGE_RUNNING;
    s.started = true;
    s.fw_ready = true;
    s.mac_func_enable = true;
    return s;
}
static int read_cr(void *arg, uint8_t *value)
{
    (void)arg;
    *value = 0;
    return 0;
}
static int check_dma_hang(void *arg, bool *hang)
{
    (void)arg;
    *hang = false;
    return 0;
}
static int reset_dma(void *arg, bool mac_on)
{
    (void)mac_on;
    return step(arg);
}
static int fail_mark_start(void *arg)
{
    struct context *c = arg;
    ++c->calls;
    return EIO;
}
static struct rtwn8723be_linux_ops start_ops(void)
{
    struct rtwn8723be_linux_ops o = {0};
    o.reset_trx_ring = step;
    o.bt_prepare = step;
    o.disable_aspm = step;
    o.read_cr = read_cr;
    o.check_pcie_dma_hang = check_dma_hang;
    o.reset_pcie_interface_dma = reset_dma;
    o.poweroff_adapter = step;
    o.init_mac = step;
    o.sys_cfg_clear_bit7 = step;
    o.download_firmware = step;
    o.phy_mac_config = step;
    o.rcr_postprocess = step;
    o.phy_bb_config = step;
    o.phy_rf_config = step;
    o.rf_channel_state_init = step;
    o.hw_configure = step;
    o.cam_reset_all = step;
    o.enable_hw_security = step;
    o.set_mac_address = step;
    o.enable_aspm_backdoor = step;
    o.enable_aspm = step;
    o.bt_hw_init = step;
    o.rf_calibration = step;
    o.set_nav_upper_235 = step;
    o.release_rx_dma = step;
    o.release_pcie_dma = step;
    o.dm_init = step;
    o.set_retry_limit = step;
    o.enable_interrupt = step;
    o.init_rx_config = step;
    o.mark_hal_start = step;
    return o;
}

static struct rtwn8723be_linux_ops stop_ops(void)
{
    struct rtwn8723be_linux_ops o = {0};
    o.bt_halt_deinit = step;
    o.mark_hal_stop = step;
    o.disable_interrupt = step;
    o.wait_rf_change_idle = step;
    o.hw_disable = step;
    o.enable_aspm = step;
    return o;
}
int main(void)
{
    struct context c = {0};
    struct rtwn8723be_linux_state s;
    struct rtwn8723be_linux_ops ops;

    s = running();
    ops = stop_ops();
    ops.hw_disable = NULL;
    assert(rtwn8723be_linux_adapter_stop(&c, &s, &ops) == ENOSYS);
    assert(s.stage == R23BE_STAGE_RUNNING && s.started &&
           s.fw_ready && s.mac_func_enable && c.calls == 0);

    s = running();
    ops = stop_ops();
    assert(rtwn8723be_linux_adapter_stop(&c, &s, &ops) == 0);
    assert(c.calls == 6 && s.stage == R23BE_STAGE_STOPPED &&
           !s.started && !s.fw_ready && !s.mac_func_enable);

    c.calls = 0;
    s = running();
    ops = stop_ops();
    s.stage = R23BE_STAGE_PROBED;
    assert(rtwn8723be_linux_adapter_stop(&c, &s, &ops) == EAGAIN);
    assert(c.calls == 0 && s.started);

    c.calls = 0;
    s = running();
    ops = stop_ops();
    c.fail_at = 3;
    assert(rtwn8723be_linux_adapter_stop(&c, &s, &ops) == EIO);
    assert(c.calls == 3 && s.stage == R23BE_STAGE_STOPPING);
    /* A callback runtime error remains an explicit recovery blocker. */
    assert(s.started && s.fw_ready);
    c.fail_at = 0;

    c.calls = 0;
    s = running();
    ops = stop_ops();
    assert(rtwn8723be_linux_adapter_start(&c, &s, &ops) == EALREADY);
    assert(c.calls == 0 && s.stage == R23BE_STAGE_RUNNING);

    s.stage = R23BE_STAGE_STOPPING;
    s.started = false;
    assert(rtwn8723be_linux_adapter_start(&c, &s, &ops) == EAGAIN);
    assert(c.calls == 0 && s.stage == R23BE_STAGE_STOPPING);

    /*
     * A failing final start callback must NOT publish RUNNING. The half
     * started adapter requires explicit recovery; blind retry is blocked.
     */
    c.calls = 0;
    s = (struct rtwn8723be_linux_state){0};
    s.stage = R23BE_STAGE_PROBED;
    ops = start_ops();
    ops.mark_hal_start = fail_mark_start;
    assert(rtwn8723be_linux_adapter_start(&c, &s, &ops) == EIO);
    assert(s.stage == R23BE_STAGE_RX_CONFIG && !s.started &&
           s.fw_ready && !s.being_init_adapter);
    {
        unsigned calls_after_failure = c.calls;
        assert(rtwn8723be_linux_adapter_start(&c, &s, &ops) == EAGAIN);
        assert(c.calls == calls_after_failure);
    }

    c.calls = 0;
    s = (struct rtwn8723be_linux_state){0};
    s.stage = R23BE_STAGE_PROBED;
    ops = start_ops();
    assert(rtwn8723be_linux_adapter_start(&c, &s, &ops) == 0);
    assert(s.stage == R23BE_STAGE_RUNNING && s.started &&
           s.fw_ready && !s.being_init_adapter);
    c.calls = 0;
    ops = stop_ops();
    assert(rtwn8723be_linux_adapter_stop(&c, &s, &ops) == 0);
    assert(s.stage == R23BE_STAGE_STOPPED && !s.started);

    puts("RTL_LIFECYCLE_STOP_START_C11_OK");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-lifecycle-") as name:
    p = Path(name)
    source = p / "test.c"
    binary = p / "test"
    source.write_text(HARNESS)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
         "-pedantic", "-fsanitize=undefined",
         "-fno-sanitize-recover=all",
         "-I", str(ROOT / "src"),
         str(ROOT / "src/rtwn8723be_linux_state.c"),
         str(source), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
