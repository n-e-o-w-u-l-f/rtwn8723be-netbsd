#!/usr/bin/env python3
"""Keep a failed adapter start on an explicit reverse-cleanup path.

Source contract only: native callbacks remain unbound.  The C11 fake-ops
test supplies behavioural coverage where a compiler is available.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src" / "rtwn8723be_linux_state.c").read_text()
HEADER = (ROOT / "src" / "rtwn8723be_linux_state.h").read_text()


def body_after(signature: str, successor: str) -> str:
    assert signature in SOURCE, f"missing {signature}"
    text = SOURCE.split(signature, 1)[1]
    assert successor in text, f"missing boundary after {signature}"
    return text.split(successor, 1)[0]


assert "int rtwn8723be_linux_adapter_abort(void *," in HEADER

start_ready = body_after(
    "rtwn8723be_start_ops_ready(const struct rtwn8723be_linux_ops *ops)",
    "#define R23BE_CALL",
)
assert "rtwn8723be_stop_ops_ready(ops)" in start_ready

abort = body_after(
    "rtwn8723be_linux_adapter_abort(void *ctx,",
    "int\nrtwn8723be_linux_adapter_stop",
)
required = (
    "rtwn8723be_stop_ops_ready(ops)",
    "state->stage = R23BE_STAGE_STOPPING;",
    "state->started = false;",
    "ops->bt_halt_deinit",
    "ops->mark_hal_stop",
    "ops->disable_interrupt",
    "ops->wait_rf_change_idle",
    "ops->hw_disable",
    "ops->enable_aspm",
    "if (first_error != 0)",
    "state->fw_ready = false;",
    "state->mac_func_enable = false;",
    "state->stage = R23BE_STAGE_STOPPED;",
)
positions = [abort.find(token) for token in required]
assert all(position >= 0 for position in positions), required
assert positions == sorted(positions), "failed-start cleanup order changed"

start = body_after(
    "rtwn8723be_linux_adapter_start(void *ctx,",
    "int\nrtwn8723be_linux_adapter_stop",
)
assert "rtwn8723be_linux_adapter_abort(ctx, state, ops)" in start

print("RTL_LINUX_START_FAILURE_RECOVERY_CONTRACT_OK")
