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

    puts("RTL_LIFECYCLE_STOP_PREFLIGHT_C11_OK");
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
