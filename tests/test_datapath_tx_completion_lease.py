#!/usr/bin/env python3
"""Compile real TX done, atomic begin_stop and unprepare with strict C11/UBSan.

The TX completion callback intentionally attempts STOPPING while holding
its lifetime reference. The native controller MUST return EBUSY, then
unprepare must also refuse while the callback runs. After it returns,
a second begin_stop and unprepare may succeed, preserving the TX mutex,
IRQ dispatch and owner storage until the reference has been released.
Actual NetBSD softint_disestablish and kernel scheduling are not simulated.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "src/rtwn8723be_datapath.c").read_text()
HDR = (ROOT / "src/rtwn8723be_datapath.h").read_text()

def function(name: str, result: str) -> str:
    marker = "\n" + name + "("
    assert SRC.count(marker) == 1, name
    tail = name + "(" + SRC.split(marker, 1)[1]
    i = tail.index("{")
    depth = 0
    for j in range(i, len(tail)):
        if tail[j] == "{":
            depth += 1
        elif tail[j] == "}":
            depth -= 1
            if depth == 0:
                return result + "\n" + tail[:j+1]
    raise AssertionError(name)

done = function("rtwn8723be_dp_tx_done", "static void")
stop = function("rtwn8723be_datapath_begin_stop", "int")
unprepare = function("rtwn8723be_datapath_unprepare", "int")

def contract(done_src: str, stop_src: str, unprepare_src: str,
             header: str) -> None:
    assert "unsigned int tx_callback_active;" in header
    inc = done_src.index("dp->tx_callback_active++;")
    unlock = done_src.index("mutex_exit(&dp->tx_lock);", inc)
    notify = done_src.index("notify(notify_arg, qid, reclaimed);")
    reacquire = done_src.index("mutex_enter(&dp->tx_lock);", notify)
    dec = done_src.index("dp->tx_callback_active--;")
    unlock2 = done_src.index("mutex_exit(&dp->tx_lock);", dec)
    assert inc < unlock < notify < reacquire < dec < unlock2
    assert "KASSERT(dp->tx_callback_active != 0);" in done_src
    assert "if (error == 0 && reclaimed != 0 && dp->tx_complete != NULL)" in done_src
    assert "state->stage = R23BE_STAGE_STOPPING;" in stop_src
    assert "dp->tx_enabled = false;" in stop_src
    assert stop_src.index("mutex_enter(&dp->tx_lock);") < (
        stop_src.index("state->stage = R23BE_STAGE_STOPPING;"))

    check = ("if (dp->tx_enabled || dp->stop_pending ||\n"
             "        dp->tx_callback_active != 0 || dp->rx_callback_active != 0 ||\n"
             "        dp->tx_start_active != 0 ||")
    lock = unprepare_src.index("mutex_enter(&dp->tx_lock);")
    test = unprepare_src.index(check)
    leave_busy = unprepare_src.index("return EBUSY;", test)
    unlock3 = unprepare_src.index("mutex_exit(&dp->tx_lock);", leave_busy)
    unbind = unprepare_src.index(
        "rtwn8723be_netbsd_irq_set_dispatch(sc, NULL, NULL);")
    destroy = unprepare_src.index("mutex_destroy(&dp->tx_lock);")
    assert lock < test < leave_busy < unlock3 < unbind < destroy
    assert "sc->sc_soft_ih != NULL" in unprepare_src[:lock]
    assert "sc->sc_ih != NULL" in unprepare_src[:lock]
    assert "sc->sc_irq_requested" in unprepare_src[:lock]

contract(done, stop, unprepare, HDR)
controls = (
    (done.replace("dp->tx_callback_active++;", "", 1), stop, unprepare, HDR),
    (done.replace("dp->tx_callback_active--;", "", 1), stop, unprepare, HDR),
    (done.replace("KASSERT(dp->tx_callback_active != 0);", "", 1), stop, unprepare, HDR),
    (done.replace("if (error == 0 && reclaimed != 0 && dp->tx_complete != NULL)",
                  "if (reclaimed != 0 && dp->tx_complete != NULL)", 1), stop, unprepare, HDR),
    (done, stop, unprepare.replace(
        "dp->tx_callback_active != 0 || dp->rx_callback_active != 0",
        "dp->rx_callback_active != 0", 1), HDR),
    (done, stop, unprepare.replace("sc->sc_soft_ih != NULL ||", "", 1), HDR),
    (done, stop, unprepare.replace("mutex_enter(&dp->tx_lock);", "", 1), HDR),
    (done, stop.replace("state->stage = R23BE_STAGE_STOPPING;",
                        "state->stage = R23BE_STAGE_RUNNING;", 1), unprepare, HDR),
    (done, stop, unprepare, HDR.replace(
        "unsigned int tx_callback_active;", "", 1)),
)
for i, mutation in enumerate(controls, 1):
    assert mutation != (done, stop, unprepare, HDR), i
    try:
        contract(*mutation)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe TX completion/unprepare mutation {i}")

prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

#define KASSERT assert
#define R23BE_STAGE_RUNNING 43
#define R23BE_STAGE_STOPPING 44
#define R23BE_STAGE_PROBED 18
#define R23BE_STAGE_STOPPED 45
#define RTWN8723BE_TX_QUEUE_COUNT 9

typedef struct { bool held, destroyed; } kmutex_t;
struct rtwn8723be_datapath;
struct rtwn8723be_linux_state {
    int stage;
    bool started, fw_ready, mac_func_enable, being_init_adapter;
};
struct rtwn8723be_irq_dispatch {
    void (*rx)(void *);
    void (*tx_done)(void *, unsigned int);
    void (*power_event)(void *);
};
struct rtwn8723be_softc {
    struct rtwn8723be_datapath *sc_datapath;
    void *sc_irq_arg, *sc_ih, *sc_soft_ih, *sc_pihp;
    bool sc_irq_dispatch_ready, sc_irq_requested, sc_irq_enabled;
    struct rtwn8723be_irq_dispatch sc_irq_dispatch;
    struct rtwn8723be_linux_state sc_linux;
};
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    kmutex_t tx_lock;
    bool prepared, tx_enabled, stop_pending;
    unsigned int tx_callback_active, rx_callback_active, tx_start_active;
    int tx_error;
    uint64_t tx_reclaimed;
    void (*tx_complete)(void *, unsigned int, size_t);
    void *tx_complete_arg;
};
static int enters, exits, destroys, unbinds, reclaim_calls, notify_calls;
static int inside_unprepare;
static void mutex_enter(kmutex_t *lock)
{
    assert(lock && !lock->held && !lock->destroyed);
    lock->held = true; enters++;
}
static void mutex_exit(kmutex_t *lock)
{
    assert(lock && lock->held && !lock->destroyed);
    lock->held = false; exits++;
}
static void mutex_destroy(kmutex_t *lock)
{
    assert(lock && !lock->held && !lock->destroyed);
    lock->destroyed = true; destroys++;
}
static void rtwn8723be_dp_rx(void *arg)
{ (void)arg; }
static int rtwn8723be_tx_native_reclaim(struct rtwn8723be_softc *sc,
    unsigned int qid, size_t *reclaimed)
{
    assert(sc && sc->sc_datapath && sc->sc_datapath->tx_lock.held);
    assert(qid == 2);
    *reclaimed = 1;
    reclaim_calls++;
    return 0;
}
static void rtwn8723be_netbsd_irq_set_dispatch(
    struct rtwn8723be_softc *sc,
    const struct rtwn8723be_irq_dispatch *dispatch, void *arg)
{
    assert(sc && dispatch == NULL && arg == NULL);
    sc->sc_irq_arg = NULL;
    memset(&sc->sc_irq_dispatch, 0, sizeof(sc->sc_irq_dispatch));
    sc->sc_irq_dispatch_ready = false;
    unbinds++;
}
'''
epilogue = r'''
static void notify(void *arg, unsigned int qid, size_t reclaimed)
{
    struct rtwn8723be_datapath *dp = arg;
    struct rtwn8723be_softc *sc = dp->sc;
    assert(qid == 2 && reclaimed == 1);
    assert(!dp->tx_lock.held);
    assert(dp->tx_callback_active == 1);
    notify_calls++;
    assert(rtwn8723be_datapath_begin_stop(dp, &sc->sc_linux) == EBUSY);
    assert(sc->sc_linux.stage == R23BE_STAGE_RUNNING);
    assert(!dp->tx_enabled && dp->stop_pending);
    assert(rtwn8723be_datapath_unprepare(dp) == EBUSY);
    assert(dp->prepared && dp->tx_callback_active == 1);
    assert(sc->sc_datapath == dp && sc->sc_irq_arg == dp);
    assert(!dp->tx_lock.destroyed && destroys == 0 && unbinds == 0);
    inside_unprepare++;
}
int main(void)
{
    struct rtwn8723be_softc sc = {0};
    struct rtwn8723be_datapath dp = {0};
    dp.sc = &sc;
    dp.prepared = dp.tx_enabled = true;
    dp.tx_complete = notify;
    dp.tx_complete_arg = &dp;
    sc.sc_datapath = &dp;
    sc.sc_irq_arg = &dp;
    sc.sc_irq_dispatch_ready = true;
    sc.sc_irq_dispatch.rx = rtwn8723be_dp_rx;
    sc.sc_irq_dispatch.tx_done = rtwn8723be_dp_tx_done;
    sc.sc_linux.started = sc.sc_linux.fw_ready = true;
    sc.sc_linux.stage = R23BE_STAGE_RUNNING;

    rtwn8723be_dp_tx_done(&dp, 2);
    assert(reclaim_calls == 1 && notify_calls == 1 && inside_unprepare == 1);
    assert(dp.tx_callback_active == 0 && enters == exits);
    assert(!dp.tx_lock.held && !dp.tx_lock.destroyed);
    assert(sc.sc_datapath == &dp && sc.sc_irq_dispatch_ready);
    assert(rtwn8723be_datapath_begin_stop(&dp, &sc.sc_linux) == 0);
    assert(sc.sc_linux.stage == R23BE_STAGE_STOPPING);
    assert(!dp.stop_pending);
    /* A completed begin_stop is NOT a completed hardware shutdown. */
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    assert(sc.sc_datapath == &dp && dp.prepared);
    sc.sc_linux.stage = R23BE_STAGE_STOPPED;
    sc.sc_linux.started = false;
    sc.sc_linux.fw_ready = false;
    assert(rtwn8723be_datapath_unprepare(&dp) == 0);
    assert(destroys == 1 && unbinds == 1 && sc.sc_datapath == NULL);
    assert(!sc.sc_irq_dispatch_ready && sc.sc_irq_arg == NULL);
    assert(!dp.prepared && dp.tx_callback_active == 0 && enters == exits);

    puts("RTL_TX_COMPLETION_REENTRANT_UNPREPARE_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtl-tx-lease-") as td:
    source = Path(td) / "check.c"
    exe = Path(td) / "check"
    source.write_text(prefix + "\n" + done + "\n" + stop + "\n" +
                      unprepare + "\n" + epilogue)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        str(source), "-o", str(exe)
    ], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_TX_COMPLETION_LEASE_SOURCE_NEGATIVES_OK negatives=9")
