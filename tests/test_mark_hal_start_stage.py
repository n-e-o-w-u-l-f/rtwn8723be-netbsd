#!/usr/bin/env python3
"""Compile actual native HAL-start callback; verify Linux controller stage order.

Mock host-C11/UBSan contract, not a NetBSD kernel or HP hardware test.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
native = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
linux = (ROOT / "src/rtwn8723be_linux_state.c").read_text()
start = native.index("int\nrtwn8723be_netbsd_mark_hal_start(void *arg)")
end = native.index("int\nrtwn8723be_netbsd_mark_hal_stop(void *arg)", start)
body = native[start:end]
controller = linux.index("int\nrtwn8723be_linux_adapter_start(")
mark_call = linux.index("error = ops->mark_hal_start(ctx);", controller)
assert linux.index("R23BE_CALL(R23BE_STAGE_RX_CONFIG,", controller) < mark_call
assert mark_call < linux.index("state->stage = R23BE_STAGE_RUNNING;", mark_call)

C = r"""
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <assert.h>
#include <stdio.h>

enum { R23BE_STAGE_IDLE, R23BE_STAGE_RX_CONFIG, R23BE_STAGE_RUNNING };
struct linux_state {
    bool fw_ready;
    int stage;
};
struct rtwn8723be_softc {
    struct linux_state sc_linux;
    bool sc_core_initialized;
    bool sc_rings_allocated;
    bool sc_irq_enabled;
    bool sc_irq_dispatch_ready;
    bool sc_hal_started;
};
""" + body + r"""
int main(void)
{
    struct rtwn8723be_softc sc = {0};
    assert(rtwn8723be_netbsd_mark_hal_start(NULL) == EAGAIN);
    sc.sc_linux.stage = R23BE_STAGE_RX_CONFIG;
    assert(rtwn8723be_netbsd_mark_hal_start(&sc) == EAGAIN);
    sc.sc_linux.fw_ready = true;
    sc.sc_core_initialized = true;
    sc.sc_rings_allocated = true;
    sc.sc_irq_enabled = true;
    sc.sc_irq_dispatch_ready = true;
    assert(rtwn8723be_netbsd_mark_hal_start(&sc) == 0);
    assert(sc.sc_hal_started);
    sc.sc_hal_started = false;
    sc.sc_linux.stage = R23BE_STAGE_RUNNING;
    assert(rtwn8723be_netbsd_mark_hal_start(&sc) == EAGAIN);
    assert(!sc.sc_hal_started);
    sc.sc_linux.stage = R23BE_STAGE_RX_CONFIG;
    sc.sc_irq_enabled = false;
    assert(rtwn8723be_netbsd_mark_hal_start(&sc) == EAGAIN);
    assert(!sc.sc_hal_started);
    puts("RTL_HAL_START_STAGE_C11_UBSAN_OK");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtwn-hal-stage-") as directory:
    source = Path(directory) / "harness.c"
    executable = Path(directory) / "harness"
    source.write_text(C)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all", str(source),
                    "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
