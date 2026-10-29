#!/usr/bin/env python3
"""Source gate: 50-unit WIP start requires real reverse owners before DMA.

The main branch intentionally lacks complete hardware lifecycle and is not
covered by this opt-in driver rule. Physical shutdown acceptance still open.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
linux = (root / "src/rtwn8723be_linux_state.c").read_text()
native = (root / "src/rtwn8723be_netbsd.c").read_text()
mock = (root / "tests/test_linux_lifecycle_stop.py").read_text()

def section(text, start, end):
    assert text.count(start) == 1, start
    s = text.split(start, 1)[1]
    assert end in s, end
    return s.split(end, 1)[0]

preflight = section(linux,
    "rtwn8723be_start_ops_ready(const struct rtwn8723be_linux_ops *ops)",
    "\n#define R23BE_CALL")
assert "error = rtwn8723be_hw_ops_ready(ops);" in preflight
assert "if (error != 0)\n        return error;" in preflight
assert "return rtwn8723be_stop_ops_ready(ops);" in preflight
start = section(linux,
    "rtwn8723be_linux_adapter_start(void *ctx,",
    "\nint\nrtwn8723be_linux_adapter_stop")
assert start.index("rtwn8723be_start_ops_ready(ops);") < (
    start.index("ops->reset_trx_ring, ctx"))
for binding in (
    ".bt_halt_deinit = rtwn8723be_netbsd_bt_halt_deinit,",
    ".mark_hal_stop = rtwn8723be_netbsd_mark_hal_stop,",
    ".disable_interrupt = rtwn8723be_netbsd_disable_interrupt,",
    ".wait_rf_change_idle = rtwn8723be_netbsd_wait_rf_change_idle,",
    ".hw_disable = rtwn8723be_netbsd_hw_disable,",
    ".enable_aspm = rtwn8723be_netbsd_enable_aspm,",
):
    assert binding in native, binding
for fake in (
    "o.establish_irq = step;",
    "o.bt_halt_deinit = step;",
    "o.mark_hal_stop = step;",
    "o.disable_interrupt = step;",
    "o.wait_rf_change_idle = step;",
    "o.hw_disable = step;",
    "ops.hw_disable = NULL;",
    "assert(c.calls == 0 && s.stage == R23BE_STAGE_PROBED",
):
    assert fake in mock, fake
print("RTL_WIP_START_REVERSE_OWNER_PREFLIGHT_SOURCE_PASS")
