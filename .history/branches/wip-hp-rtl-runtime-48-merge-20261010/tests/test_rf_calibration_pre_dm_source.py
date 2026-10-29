#!/usr/bin/env python3
"""Guard pinned rtl8723be_hw_init(): ERFON IQK/LCK before DM initialization.

This detects the previous deterministic first-start ENXIO dependency cycle:
calibration required dm.software_initialized although its dm_init callback
executes AFTER calibration. It does not validate a real RF or WPA2 exchange.
"""
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "src"
state = (src / "rtwn8723be_linux_state.c").read_text()
runtime = (src / "rtwn8723be_runtime.c").read_text()
cal = (src / "rtwn8723be_calibration.c").read_text()
test = (src.parent / "tests" / "calibration_check.c").read_text()

hw = state.split("rtwn8723be_linux_hw_init(void *ctx", 1)[1].split(
    "rtwn8723be_linux_adapter_start(void *ctx", 1)[0]
cal_stage = "R23BE_CALL(R23BE_STAGE_RF_CALIBRATION, ops->rf_calibration, ctx);"
dm_stage = "R23BE_CALL(R23BE_STAGE_DM_INIT, ops->dm_init, ctx);"
assert hw.count(cal_stage) == 1 and hw.count(dm_stage) == 1
assert hw.index(cal_stage) < hw.index(dm_stage)

owner = runtime.split("cal_owner_acquire(void *arg", 1)[1].split(
    "static bool cal_owner_ready", 1)[0]
assert "in->dm_state_valid = r->dm.software_initialized;" in owner
assert "in->txpower_tracking = r->dm.thermal.txpower_tracking;" in owner
block = cal.split("rtwn8723be_calibration_run(", 1)[1]
block = block.split("error = cal_init(&work, ctx);", 1)[0]
assert "if (!input->btc_bound || !input->btc_initialized)" in block
assert "if (input->txpower_tracking && !input->dm_state_valid)" in block
assert "!input->btc_initialized ||\n        !input->dm_state_valid" not in block
assert "input.dm_state_valid = false;" in test
assert "input.txpower_tracking = true;" in test
assert "input.txpower_tracking = false;" in test
assert "assert(actual.calls != 0 && !state.lck_inprogress);" in test
print("RTL_RF_CALIBRATION_BEFORE_DM_OWNER_ORDER_SOURCE_PASS")
