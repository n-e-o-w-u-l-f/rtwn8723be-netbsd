#!/usr/bin/env python3
"""Compile real NetBSD datapath_unprepare against Linux hardware-stage proof.

A disestablished IRQ, closed TX admission and zero callbacks are insufficient
while the Linux controller owns RUNNING/STOPPING/partial-start firmware/MAC.
Clean unstarted probe stages and truly STOPPED hardware can be released.
Strict portable C11/UBSan only; no actual NetBSD IRQ or PCI DMA evidence.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DP = (ROOT / "src/rtwn8723be_datapath.c").read_text()
HDR = (ROOT / "src/rtwn8723be_datapath.h").read_text()
LINUX = (ROOT / "src/rtwn8723be_linux_state.c").read_text()
LINUX_HEADER = (ROOT / "src/rtwn8723be_linux_state.h").read_text()

def function(name: str) -> str:
    anchor = "\n" + name + "("
    assert DP.count(anchor) == 1, name
    tail = name + "(" + DP.split(anchor, 1)[1]
    depth = 0
    for i in range(tail.index("{"), len(tail)):
        if tail[i] == "{":
            depth += 1
        elif tail[i] == "}":
            depth -= 1
            if depth == 0:
                return "int\n" + tail[:i + 1]
    raise AssertionError(name)

unprepare = function("rtwn8723be_datapath_unprepare")

def contract(src: str, header: str, linux_header: str) -> None:
    assert "int rtwn8723be_datapath_unprepare(" in header
    assert "R23BE_STAGE_PROBED" in linux_header
    assert "R23BE_STAGE_STOPPING" in linux_header
    assert "R23BE_STAGE_STOPPED" in linux_header
    assert "state->stage = R23BE_STAGE_STOPPED;" in LINUX
    assert "state->started = false;" in LINUX
    assert "state->fw_ready = false;" in LINUX
    assert "state->mac_func_enable = false;" in LINUX
    begin = src.index("mutex_enter(&dp->tx_lock);")
    claim = src.index("if (dp->tx_enabled || dp->stop_pending ||", begin)
    busy = src.index("return EBUSY;", claim)
    unlock = src.index("mutex_exit(&dp->tx_lock);", busy)
    revoke = src.index("rtwn8723be_netbsd_irq_set_dispatch(sc, NULL, NULL);")
    destroy = src.index("mutex_destroy(&dp->tx_lock);")
    assert begin < claim < busy < unlock < revoke < destroy
    for token in (
        "dp->tx_enabled", "dp->stop_pending",
        "dp->tx_callback_active != 0", "dp->rx_callback_active != 0",
        "dp->tx_start_active != 0",
        "sc->sc_linux.started", "sc->sc_linux.fw_ready",
        "sc->sc_linux.mac_func_enable", "sc->sc_linux.being_init_adapter",
        "sc->sc_linux.stage != R23BE_STAGE_STOPPED",
        "sc->sc_linux.stage > R23BE_STAGE_PROBED",
    ):
        assert claim <= src.index(token, claim) < busy, token
    assert src.index("sc->sc_ih != NULL") < begin
    assert src.index("sc->sc_soft_ih != NULL") < begin
    assert src.index("sc->sc_pihp != NULL") < begin
    assert src.index("sc->sc_irq_requested") < begin
    assert src.index("sc->sc_irq_enabled") < begin

contract(unprepare, HDR, LINUX_HEADER)
mutations = (
    unprepare.replace("dp->tx_enabled ||", "false ||", 1),
    unprepare.replace("dp->stop_pending ||", "false ||", 1),
    unprepare.replace("dp->tx_callback_active != 0", "false", 1),
    unprepare.replace("dp->rx_callback_active != 0", "false", 1),
    unprepare.replace("dp->tx_start_active != 0", "false", 1),
    unprepare.replace("sc->sc_linux.started ||", "false ||", 1),
    unprepare.replace("sc->sc_linux.fw_ready ||", "false ||", 1),
    unprepare.replace("sc->sc_linux.mac_func_enable ||", "false ||", 1),
    unprepare.replace("sc->sc_linux.being_init_adapter ||", "false ||", 1),
    unprepare.replace("sc->sc_linux.stage != R23BE_STAGE_STOPPED",
                      "false", 1),
    unprepare.replace("sc->sc_linux.stage > R23BE_STAGE_PROBED",
                      "false", 1),
    unprepare.replace("sc->sc_soft_ih != NULL ||", "", 1),
    unprepare.replace("mutex_enter(&dp->tx_lock);", "", 1),
    unprepare.replace("mutex_destroy(&dp->tx_lock);", "", 1),
)
for i, altered in enumerate(mutations, 1):
    assert altered != unprepare, i
    try:
        contract(altered, HDR, LINUX_HEADER)
    except (ValueError, AssertionError):
        continue
    raise AssertionError(f"unsafe unprepare Linux lifecycle mutation {i}")

prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include "rtwn8723be_linux_state.h"
#define KASSERT assert

typedef struct { bool held, destroyed; } kmutex_t;
struct rtwn8723be_datapath;
struct rtwn8723be_irq_dispatch {
    void (*rx)(void *);
    void (*tx_done)(void *, unsigned int);
    void (*power_event)(void *);
};
struct rtwn8723be_softc {
    struct rtwn8723be_datapath *sc_datapath;
    void *sc_irq_arg, *sc_ih, *sc_soft_ih, *sc_pihp;
    bool sc_irq_requested, sc_irq_enabled, sc_irq_dispatch_ready;
    struct rtwn8723be_irq_dispatch sc_irq_dispatch;
    struct rtwn8723be_linux_state sc_linux;
};
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    kmutex_t tx_lock;
    bool prepared, tx_enabled, stop_pending;
    unsigned int rx_callback_active, tx_callback_active, tx_start_active;
};
static int enters, exits, destroys, revokes;
static void mutex_enter(kmutex_t *m)
{ assert(m && !m->held && !m->destroyed); m->held = true; enters++; }
static void mutex_exit(kmutex_t *m)
{ assert(m && m->held && !m->destroyed); m->held = false; exits++; }
static void mutex_destroy(kmutex_t *m)
{ assert(m && !m->held && !m->destroyed); m->destroyed=true; destroys++; }
static void rtwn8723be_dp_rx(void *arg) { (void)arg; }
static void rtwn8723be_dp_tx_done(void *arg, unsigned int qid)
{ (void)arg; (void)qid; }
static void rtwn8723be_netbsd_irq_set_dispatch(
    struct rtwn8723be_softc *sc,
    const struct rtwn8723be_irq_dispatch *irq, void *arg)
{
    assert(sc && irq == NULL && arg == NULL);
    sc->sc_irq_arg = NULL;
    sc->sc_irq_dispatch_ready = false;
    memset(&sc->sc_irq_dispatch, 0, sizeof(sc->sc_irq_dispatch));
    revokes++;
}
'''
tail = r'''
static void setup(struct rtwn8723be_softc *sc,
    struct rtwn8723be_datapath *dp)
{
    *sc = (struct rtwn8723be_softc){0};
    *dp = (struct rtwn8723be_datapath){0};
    dp->sc = sc;
    dp->prepared = true;
    sc->sc_datapath = dp;
    sc->sc_irq_arg = dp;
    sc->sc_irq_dispatch_ready = true;
    sc->sc_irq_dispatch.rx = rtwn8723be_dp_rx;
    sc->sc_irq_dispatch.tx_done = rtwn8723be_dp_tx_done;
    sc->sc_linux.stage = R23BE_STAGE_PROBED;
    enters = exits = destroys = revokes = 0;
}
static void retained(struct rtwn8723be_softc *sc,
    struct rtwn8723be_datapath *dp)
{
    assert(sc->sc_datapath == dp && sc->sc_irq_arg == dp);
    assert(dp->prepared && !dp->tx_lock.destroyed);
    assert(destroys == 0 && revokes == 0);
    assert(enters == exits && !dp->tx_lock.held);
}
static void freed(struct rtwn8723be_softc *sc,
    struct rtwn8723be_datapath *dp)
{
    assert(sc->sc_datapath == NULL && !sc->sc_irq_dispatch_ready);
    assert(sc->sc_irq_arg == NULL && !dp->prepared);
    assert(destroys == 1 && revokes == 1);
    assert(enters == exits && !dp->tx_lock.held);
}
int main(void)
{
    struct rtwn8723be_softc sc;
    struct rtwn8723be_datapath dp;

    /* Unstarted probe rollback is still permitted: clean owner only. */
    setup(&sc, &dp);
    assert(rtwn8723be_datapath_unprepare(&dp) == 0);
    freed(&sc, &dp);

    /* Interrupt establishment failed before hardware start. */
    setup(&sc, &dp);
    sc.sc_linux.stage = R23BE_STAGE_IRQ_ESTABLISH;
    assert(rtwn8723be_datapath_unprepare(&dp) == 0);
    freed(&sc, &dp);

    /* A pre-RUNNING hardware phase is not an unstarted probe unwind. */
    setup(&sc, &dp);
    sc.sc_linux.stage = R23BE_STAGE_FIRMWARE_DOWNLOAD;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    retained(&sc, &dp);
    sc.sc_linux.stage = R23BE_STAGE_PROBED;
    assert(rtwn8723be_datapath_unprepare(&dp) == 0);
    freed(&sc, &dp);

    /* Merely closing TX and disestablishing all IRQ does not stop MAC. */
    setup(&sc, &dp);
    sc.sc_linux.stage = R23BE_STAGE_RUNNING;
    sc.sc_linux.started = sc.sc_linux.fw_ready = true;
    dp.tx_enabled = false;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    retained(&sc, &dp);

    /* STOPPING is not STOPPED, even when software flags were cleared. */
    sc.sc_linux.stage = R23BE_STAGE_STOPPING;
    sc.sc_linux.started = sc.sc_linux.fw_ready = false;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    retained(&sc, &dp);

    /* Probed stage with firmware still published is not an early unwind. */
    sc.sc_linux.stage = R23BE_STAGE_PROBED;
    sc.sc_linux.fw_ready = true;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    retained(&sc, &dp);

    /* The real STOPPED stage is also not enough with leftover resources. */
    sc.sc_linux.stage = R23BE_STAGE_STOPPED;
    sc.sc_linux.fw_ready = false;
    sc.sc_linux.started = true;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    sc.sc_linux.started = false;
    sc.sc_linux.mac_func_enable = true;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    sc.sc_linux.mac_func_enable = false;
    sc.sc_linux.being_init_adapter = true;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    sc.sc_linux.being_init_adapter = false;

    /* Even proven STOPPED needs callback references and IRQ fully drained. */
    dp.tx_callback_active = 1;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    dp.tx_callback_active = 0;
    dp.rx_callback_active = 1;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    dp.rx_callback_active = 0;
    dp.tx_start_active = 1;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    dp.tx_start_active = 0;
    dp.stop_pending = true;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    dp.stop_pending = false;
    dp.tx_enabled = true;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    dp.tx_enabled = false;
    sc.sc_soft_ih = &sc;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    sc.sc_soft_ih = NULL;
    assert(rtwn8723be_datapath_unprepare(&dp) == 0);
    freed(&sc, &dp);

    puts("RTL_DATAPATH_UNPREPARE_LINUX_LIFECYCLE_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-unprepare-lifecycle-") as td:
    source = Path(td) / "check.c"
    binary = Path(td) / "check"
    source.write_text(prefix + "\n" + unprepare + "\n" + tail)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-pedantic", "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(ROOT / "src"), str(source), "-o", str(binary)
    ], check=True)
    subprocess.run([str(binary)], check=True)
print("RTL_DATAPATH_UNPREPARE_STAGE_MUTATIONS_OK negatives=14")
