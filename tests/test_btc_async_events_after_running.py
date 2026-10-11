#!/usr/bin/env python3
"""WIP 50-unit source-gate: BTC async events start ONLY after full HW RUNNING.

Previously runtime_dm_init called btc_native_enable_events while the
linux_hw_init stage was DM_INIT, started=false and IRQ disabled, even though
btc_native_enable_events strictly requires RUNNING/started/IRQ-enabled.
That gives unavoidable EAGAIN on the first valid HW start. This guard
protects the exact causal order, not real on-device firmware acceptance.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "src"
runtime = (root / "rtwn8723be_runtime.c").read_text()
linux = (root / "rtwn8723be_linux_state.c").read_text()
btc = (root / "rtwn8723be_btc_native.c").read_text()

def body(data: str, start: str, end: str) -> str:
    assert data.count(start) == 1, start
    v = data.split(start, 1)[1]
    assert end in v, end
    return v.split(end, 1)[0]

dm = body(runtime, "rtwn8723be_runtime_dm_init(void *arg)",
          "\nint\nrtwn8723be_runtime_bt_halt")
start = body(runtime,
    "rtwn8723be_runtime_start(struct rtwn8723be_softc *sc)",
    "\nint\nrtwn8723be_runtime_stop(")
gate = body(btc,
    "rtwn8723be_btc_native_enable_events(struct rtwn8723be_softc *sc)",
    "\nint\nrtwn8723be_btc_native_enqueue(")
hw = body(linux,
    "rtwn8723be_linux_hw_init(void *ctx",
    "\nint\nrtwn8723be_linux_adapter_start(")
linux_start = body(linux,
    "rtwn8723be_linux_adapter_start(void *ctx,",
    "\nint\nrtwn8723be_linux_adapter_stop(")

assert "rtwn8723be_btc_native_enable_events" not in dm
assert "return rtwn8723be_dm_native_init(sc, &r->dm, &in);" in dm
assert runtime.count("rtwn8723be_btc_native_enable_events(sc)") == 1

# Prove this is a real guard, not a gratuitous reordering:
# DM_INIT executes before IRQ_ENABLE/mark_hal_start, but the BTC interface
# explicitly denies enabling notifications in that pre-RUNNING stage.
assert "R23BE_CALL(R23BE_STAGE_DM_INIT, ops->dm_init, ctx);" in hw
assert "R23BE_CALL(R23BE_STAGE_IRQ_ENABLE, ops->enable_interrupt, ctx);" in linux_start
assert "state->stage = R23BE_STAGE_RUNNING;" in linux_start
for contract in (
    "!sc->sc_linux.started",
    "!sc->sc_linux.fw_ready",
    "sc->sc_linux.stage != R23BE_STAGE_RUNNING",
    "!sc->sc_irq_enabled",
):
    assert contract in gate, contract

sequence = (
    "rtwn8723be_linux_adapter_start(sc,",
    "rtwn8723be_runtime_io_exit(sc);",
    "rtwn8723be_datapath_start(&r->datapath)",
    "rtwn8723be_net80211_tx_run(&r->tx)",
    "if (error == 0) error = rtwn8723be_btc_native_enable_events(sc);",
    "r->jobs_enabled = true;",
    "ieee80211_new_state(&sc->sc_ic, IEEE80211_S_SCAN, -1);",
)
positions = [start.find(x) for x in sequence]
assert min(positions) >= 0 and positions == sorted(positions), list(zip(sequence, positions))
assert "if (error != 0) goto fail;" in start.split(sequence[4])[1]
assert "cleanup = runtime_shutdown(sc, sc->sc_linux.started);" in start

print("RTL_BTC_ASYNC_EVENTS_AFTER_RUNNING_SOURCE_PASS")
