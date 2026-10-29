#!/usr/bin/env python3
"""Actual C11/UBSan RX softint lease + atomic STOP + detach admission test.

The production RX ring-drain stub reentrantly invokes begin_stop/unprepare.
Neither hardware STOP nor datapath teardown can succeed until the borrowed
DMA callback returns; a late queued RX callback cannot touch the ring after
STOPPING. This is not native NetBSD SMP/PCI or hardware evidence.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "src/rtwn8723be_datapath.c").read_text()
HEADER = (ROOT / "src/rtwn8723be_datapath.h").read_text()
LINUX = (ROOT / "src/rtwn8723be_linux_state.c").read_text()

def body(name: str, result: str) -> str:
    marker = "\n" + name + "("
    assert SRC.count(marker) == 1, name
    fragment = name + "(" + SRC.split(marker, 1)[1]
    start, depth = fragment.index("{"), 0
    for index in range(start, len(fragment)):
        if fragment[index] == "{":
            depth += 1
        elif fragment[index] == "}":
            depth -= 1
            if depth == 0:
                return result + "\n" + fragment[:index + 1]
    raise AssertionError(name)

rx = body("rtwn8723be_dp_rx", "static void")
stop = body("rtwn8723be_datapath_begin_stop", "int")
unprepare = body("rtwn8723be_datapath_unprepare", "int")

def contract(rx_src: str, stop_src: str, unprepare_src: str,
             header: str) -> None:
    assert "unsigned int rx_callback_active;" in header
    gate = rx_src.index("mutex_enter(&dp->tx_lock);")
    for token in ("!dp->tx_enabled", "dp->sc->sc_datapath != dp",
                  "dp->sc->sc_irq_arg != dp", "!dp->sc->sc_irq_dispatch_ready",
                  "!dp->sc->sc_linux.started", "!dp->sc->sc_linux.fw_ready",
                  "dp->sc->sc_linux.stage != R23BE_STAGE_RUNNING",
                  "dp->rx.frame == NULL", "dp->rx.c2h == NULL"):
        assert gate < rx_src.index(token) < rx_src.index(
            "dp->rx_callback_active++;"), token
    published = rx_src.index("dp->rx_callback_active++;")
    unlock = rx_src.index("mutex_exit(&dp->tx_lock);", published)
    drain = rx_src.index("rtwn8723be_rx_native_drain(")
    relock = rx_src.index("mutex_enter(&dp->tx_lock);", drain)
    release = rx_src.index("dp->rx_callback_active--;")
    assert published < unlock < drain < relock < release
    assert "KASSERT(dp->rx_callback_active != 0);" in rx_src
    assert rx_src.index("dp->rx_delivered += delivered;") > relock

    claim = stop_src.index("dp->rx_callback_active != 0 ||")
    assert "dp->tx_callback_active != 0" in stop_src[claim:]
    assert stop_src.index("mutex_enter(&dp->tx_lock);") < claim
    assert claim < stop_src.rindex("state->stage = R23BE_STAGE_STOPPING;")
    assert "error = EBUSY;" in stop_src[claim:]
    assert "dp->tx_enabled = false;" in stop_src[claim:]

    test = unprepare_src.index("dp->rx_callback_active != 0")
    assert "dp->tx_callback_active != 0" in unprepare_src[:test]
    assert unprepare_src.index("mutex_enter(&dp->tx_lock);") < test
    assert test < unprepare_src.index(
        "rtwn8723be_netbsd_irq_set_dispatch(sc, NULL, NULL);")
    assert test < unprepare_src.index("mutex_destroy(&dp->tx_lock);")
    assert "sc->sc_soft_ih != NULL" in unprepare_src
    assert "sc->sc_ih != NULL" in unprepare_src
    assert "error = ops->begin_stop(ctx, state);" in LINUX

contract(rx, stop, unprepare, HEADER)
controls = (
    (rx.replace("dp->rx_callback_active++;", "", 1), stop, unprepare, HEADER),
    (rx.replace("dp->rx_callback_active--;", "", 1), stop, unprepare, HEADER),
    (rx.replace("dp->sc->sc_datapath != dp", "false", 1), stop, unprepare, HEADER),
    (rx.replace("dp->sc->sc_irq_arg != dp", "false", 1), stop, unprepare, HEADER),
    (rx.replace("dp->sc->sc_linux.stage != R23BE_STAGE_RUNNING",
                "false", 1), stop, unprepare, HEADER),
    (rx.replace("mutex_enter(&dp->tx_lock);", "", 1), stop, unprepare, HEADER),
    (rx, stop.replace("dp->rx_callback_active != 0 ||", "false ||", 1),
     unprepare, HEADER),
    (rx, stop.replace("dp->tx_callback_active != 0", "false", 1),
     unprepare, HEADER),
    (rx, stop, unprepare.replace("dp->rx_callback_active != 0", "false", 1),
     HEADER),
    (rx, stop, unprepare, HEADER.replace(
        "unsigned int rx_callback_active;", "", 1)),
)
for idx, candidate in enumerate(controls, 1):
    assert candidate != (rx, stop, unprepare, HEADER), idx
    try:
        contract(*candidate)
    except (ValueError, AssertionError):
        continue
    raise AssertionError(f"unsafe RX lifetime mutation {idx}")

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

typedef struct { bool held, destroyed; } kmutex_t;
struct rtwn8723be_datapath;
struct rtwn8723be_linux_state { int stage; bool started, fw_ready, mac_func_enable, being_init_adapter; };
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
struct rtwn8723be_rx_dispatch {
    void *arg;
    int (*frame)(void *, const uint8_t *, size_t, const void *);
    int (*c2h)(void *, const uint8_t *, size_t, const void *);
};
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_rx_dispatch rx;
    kmutex_t tx_lock;
    bool prepared, tx_enabled, stop_pending;
    unsigned int rx_callback_active, tx_callback_active, tx_start_active;
    int rx_error, tx_error;
    uint64_t rx_delivered, tx_reclaimed;
};
static int enters, exits, destroys, dispatch_revoked, drain_calls;
static int called_stop_in_rx, called_unprepare_in_rx;
static void mutex_enter(kmutex_t *m)
{ assert(m && !m->held && !m->destroyed); m->held=true; enters++; }
static void mutex_exit(kmutex_t *m)
{ assert(m && m->held && !m->destroyed); m->held=false; exits++; }
static void mutex_destroy(kmutex_t *m)
{ assert(m && !m->held && !m->destroyed); m->destroyed=true; destroys++; }
static int frame_handler(void *arg, const uint8_t *buf, size_t n, const void *p)
{ (void)arg; (void)buf; (void)n; (void)p; return 0; }
static void rtwn8723be_dp_tx_done(void *arg, unsigned int qid)
{ (void)arg; (void)qid; }
static int rtwn8723be_netbsd_irq_set_dispatch(
    struct rtwn8723be_softc *sc,
    const struct rtwn8723be_irq_dispatch *irq, void *arg)
{
    assert(sc && irq == NULL && arg == NULL);
    sc->sc_irq_dispatch_ready=false;
    sc->sc_irq_arg=NULL;
    memset(&sc->sc_irq_dispatch,0,sizeof(sc->sc_irq_dispatch));
    dispatch_revoked++;
    return 0;
}
static int rtwn8723be_rx_native_drain(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_rx_dispatch *d, size_t *delivered);
'''
epilogue = r'''
static int rtwn8723be_rx_native_drain(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_rx_dispatch *d, size_t *delivered)
{
    struct rtwn8723be_datapath *dp = sc->sc_datapath;
    assert(dp && !dp->tx_lock.held && dp->rx_callback_active == 1);
    assert(d && d->frame == frame_handler && d->c2h == frame_handler);
    drain_calls++;
    assert(rtwn8723be_datapath_begin_stop(dp, &sc->sc_linux) == EBUSY);
    called_stop_in_rx++;
    assert(sc->sc_linux.stage == R23BE_STAGE_RUNNING && !dp->tx_enabled);
    assert(dp->stop_pending);
    assert(rtwn8723be_datapath_unprepare(dp) == EBUSY);
    called_unprepare_in_rx++;
    assert(!dp->tx_lock.destroyed && sc->sc_datapath == dp);
    *delivered = 3;
    return EIO; /* Failed RX parse still releases the lease. */
}
int main(void)
{
    struct rtwn8723be_softc sc = {0};
    struct rtwn8723be_datapath dp = {0};
    dp.sc = &sc;
    dp.prepared = dp.tx_enabled = true;
    dp.rx.frame = frame_handler;
    dp.rx.c2h = frame_handler;
    sc.sc_datapath = &dp;
    sc.sc_irq_arg = &dp;
    sc.sc_irq_dispatch_ready = true;
    sc.sc_irq_dispatch.rx = rtwn8723be_dp_rx;
    sc.sc_irq_dispatch.tx_done = rtwn8723be_dp_tx_done;
    sc.sc_linux.started = sc.sc_linux.fw_ready = true;
    sc.sc_linux.stage = R23BE_STAGE_RUNNING;

    rtwn8723be_dp_rx(&dp);
    assert(drain_calls == 1 && called_stop_in_rx == 1);
    assert(called_unprepare_in_rx == 1);
    assert(dp.rx_callback_active == 0 && dp.rx_delivered == 3);
    assert(dp.rx_error == EIO && dp.tx_enabled == false);
    assert(enters == exits && !dp.tx_lock.held);
    /* Closed admission prevents even a second ring DMA read. */
    rtwn8723be_dp_rx(&dp);
    assert(drain_calls == 1 && dp.rx_delivered == 3);

    /* A pending STOP cannot be bypassed by a probe-unwind release. */
    assert(dp.stop_pending && rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    /* Reattempt STOP after RX lease returned; no false STOPPED claim. */
    assert(rtwn8723be_datapath_begin_stop(&dp, &sc.sc_linux) == 0);
    assert(!dp.stop_pending);
    assert(sc.sc_linux.stage == R23BE_STAGE_STOPPING);
    rtwn8723be_dp_rx(&dp);
    assert(drain_calls == 1);

    /* A completed begin_stop is NOT a completed hardware shutdown. */
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    assert(sc.sc_datapath == &dp && dp.prepared);
    sc.sc_linux.stage = R23BE_STAGE_STOPPED;
    sc.sc_linux.started = false;
    sc.sc_linux.fw_ready = false;
    assert(rtwn8723be_datapath_unprepare(&dp) == 0);
    assert(destroys == 1 && dispatch_revoked == 1);
    assert(sc.sc_datapath == NULL && !sc.sc_irq_dispatch_ready);
    assert(!dp.prepared && dp.rx_callback_active == 0);
    assert(enters == exits);

    puts("RTL_RX_INFLIGHT_STOP_AND_UNPREPARE_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-rx-inflight-") as td:
    source = Path(td) / "harness.c"
    exe = Path(td) / "harness"
    source.write_text(prefix + "\n" + rx + "\n" + stop + "\n" +
                      unprepare + "\n" + epilogue)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        str(source), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_RX_INFLIGHT_SOURCE_MUTATIONS_OK negatives=10")
