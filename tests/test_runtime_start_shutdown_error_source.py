#!/usr/bin/env python3
"""Guard two-error semantics during RTL firmware-start rollback.

Source-only guard. Hardware fault injection and a native NetBSD kernel build
must validate these branches before any F77 fallback is modified.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
r = (root / "src" / "rtwn8723be_runtime.c").read_text()
start = r.split("rtwn8723be_runtime_start(struct rtwn8723be_softc *sc)", 1)[1]
start = start.split("rtwn8723be_runtime_stop(struct rtwn8723be_softc *sc)", 1)[0]
shutdown = r.split("runtime_shutdown(struct rtwn8723be_softc *sc, bool normal)", 1)[1]
shutdown = shutdown.split("rtwn8723be_runtime_start(struct rtwn8723be_softc *sc)", 1)[0]
unreg = r.split("rtwn8723be_runtime_unregister(struct rtwn8723be_softc *sc)", 1)[1]
unreg = unreg.split("static int\nruntime_queue(", 1)[0]

assert "if (error != 0 && r->first_error == 0)" in start
assert "r->first_error = error;" in start
assert start.index("runtime_jobs_drain(sc);") < start.index(
    "cleanup = runtime_shutdown(sc, sc->sc_linux.started);")
assert start.index("cleanup = runtime_shutdown(sc, sc->sc_linux.started);") < (
    start.index("r->transition = false;\n    mutex_exit(&r->lifecycle_lock);"))
assert "return cleanup != 0 ? cleanup : (error != 0 ? error : EIO);" in start
assert "return error != 0 ? error : cleanup;" not in start

# Shutdown failure includes post-poweroff RX DMA / BTC / ASPM errors,
# not just poweroff failure. Do not publish an unregistered ifnet after it.
for token in (
    "r->poweroff_verified",
    "rtwn8723be_netbsd_reset_trx_ring(sc)",
    "rtwn8723be_btc_native_retire(sc)",
    "rtwn8723be_netbsd_enable_aspm(sc)",
    "r->shutdown_error = first;",
):
    assert token in shutdown
assert "if (error != 0)\n        return error;" in unreg
assert "if (error != 0 && !r->poweroff_verified)" not in unreg

print("RTL_START_FAILURE_SHUTDOWN_PRECEDENCE_SOURCE_PASS")
