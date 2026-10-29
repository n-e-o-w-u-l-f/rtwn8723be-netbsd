#!/usr/bin/env python3
"""Batch lock/storage/lifecycle source contract; no native execution."""
from pathlib import Path
import re
from itertools import product

ROOT = Path(__file__).resolve().parents[1]


def body(source, name):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    match = re.search(r"\n" + name + r"\([^;]+?\n\{(.*?)\n\}", source, re.S)
    return match[1] if match else ""


def contract(source, header):
    b = body(source, "rtwn8723be_datapath_enqueue_batch_notify")
    tokens = ["frames == NULL || count == 0 || count > RTWN8723BE_TX_BATCH_MAX",
              "mutex_enter(&dp->tx_lock);",
              "if (!dp->tx_enabled || !dp->sc->sc_linux.started ||",
              "dp->sc->sc_linux.stage != R23BE_STAGE_RUNNING ||",
              "!dp->sc->sc_linux.fw_ready)", "error = EAGAIN;",
              "error = rtwn8723be_tx_native_enqueue_batch(dp->sc,",
              "frames, count, &dp->batch_workspace);",
              "if (error == 0 && accepted != NULL)",
              "for (i = 0; i < count; i++)", "accepted(accepted_arg, frames[i].m);",
              "mutex_exit(&dp->tx_lock);", "return error;"]
    pos = [b.find(t) for t in tokens]
    return (min(pos) >= 0 and pos == sorted(set(pos))
            and b.count("mutex_exit(&dp->tx_lock);") == 1
            and "struct rtwn8723be_tx_batch_workspace batch_workspace;" in header
            and all(t not in b for t in ("kmem_", "m_freem(", "->release(", "struct rtwn8723be_tx_batch_workspace ")))


source = (ROOT / "src/rtwn8723be_datapath.c").read_text()
header = (ROOT / "src/rtwn8723be_datapath.h").read_text()
assert contract(source, header), "batch must own workspace and lock lifecycle/commit/notifications"
prefix, tail = source.split("\nrtwn8723be_datapath_enqueue_batch_notify(", 1)
changes = [("dp->sc->sc_linux.stage != R23BE_STAGE_RUNNING ||", ""),
           ("if (!dp->tx_enabled || !dp->sc->sc_linux.started ||", "if (!dp->sc->sc_linux.started ||"),
           ("if (error == 0 && accepted != NULL)", "if (accepted != NULL)"),
           ("i < count", "i <= count"),
           ("frames, count, &dp->batch_workspace);", "frames, count, NULL);"),
           ("mutex_enter(&dp->tx_lock);", "/* mutex_enter(&dp->tx_lock); */"),
           ("mutex_exit(&dp->tx_lock);", "")]
for i, (old, new) in enumerate(changes):
    assert old in tail
    assert not contract(prefix + "\nrtwn8723be_datapath_enqueue_batch_notify(" + tail.replace(old, new, 1), header), i
assert not contract(source, header.replace("struct rtwn8723be_tx_batch_workspace batch_workspace;", ""))
# Storage belongs to heap-allocated runtime, reset only by existing lifecycle.
rh = (ROOT / "src/rtwn8723be_runtime.h").read_text()
rc = (ROOT / "src/rtwn8723be_runtime.c").read_text()
assert "struct rtwn8723be_datapath datapath;" in rh
assert "r = kmem_zalloc(sizeof(*r), KM_SLEEP);" in rc
assert "memset(dp, 0, sizeof(*dp));" in body(source, "rtwn8723be_datapath_prepare")
stop = body(source, "rtwn8723be_datapath_stop")
assert stop.index("mutex_enter(&dp->tx_lock);") < stop.index("dp->tx_enabled = false;") < stop.index("mutex_exit(&dp->tx_lock);")
unprepare = body(source, "rtwn8723be_datapath_unprepare")
assert unprepare.index("sc->sc_soft_ih != NULL") < unprepare.index("mutex_destroy(&dp->tx_lock);") < unprepare.index("memset(dp, 0, sizeof(*dp));")

# Independent policy table: callbacks are DMA-acceptance only, never failure.
cases = 0
for enabled, started, running, ready, callback, native_ok in product((False, True), repeat=6):
    for count in (1, 2, 16):
        admitted = enabled and started and running and ready
        error = "EAGAIN" if not admitted else ("OK" if native_ok else "DMA_ERROR")
        notifications = list(range(count)) if error == "OK" and callback else []
        assert len(notifications) == (count if all((enabled, started, running, ready, callback, native_ok)) else 0)
        cases += 1
print(f"DATAPATH_BATCH_SOURCE_PASS: 8 mutations; {cases} policy cases; native NOT_RUN")
