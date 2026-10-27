#!/usr/bin/env python3
"""Strict C11/UBSan execution of the real datapath start and enqueue bodies.

Simulates STOPPING with started/firmware flags still true, a foreign bridge
owner, a stopped TX flag, and native ring enqueue backpressure. This does
NOT establish real NetBSD softint/IRQ, bus_dma or concurrent ifnet lifetimes.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DP = (ROOT / "src/rtwn8723be_datapath.c").read_text()
RX = (ROOT / "src/rtwn8723be_rx_binding.c").read_text()
NETH = (ROOT / "src/rtwn8723be_netbsd.h").read_text()
RXH = (ROOT / "src/rtwn8723be_rx_binding.h").read_text()

def body(source: str, name: str, result_type: str) -> str:
    anchor = "\n" + name + "("
    assert source.count(anchor) == 1, name
    fragment = name + "(" + source.split(anchor, 1)[1]
    start, depth = fragment.index("{"), 0
    for index in range(start, len(fragment)):
        if fragment[index] == "{":
            depth += 1
        elif fragment[index] == "}":
            depth -= 1
            if depth == 0:
                return result_type + "\n" + fragment[:index+1]
    raise AssertionError("missing native body: " + name)

start = body(DP, "rtwn8723be_datapath_start", "int")
enqueue = body(DP, "rtwn8723be_datapath_enqueue", "int")
def contract(start_body: str, enqueue_body: str, rx_source: str):
    assert "if (sc->sc_datapath != dp || sc->sc_irq_arg != dp)" in start_body
    assert "sc->sc_linux.stage != R23BE_STAGE_RUNNING" in start_body
    assert "mutex_enter(&dp->tx_lock);" in start_body
    assert "dp->tx_enabled = true;" in start_body
    gate = enqueue_body.index("if (!dp->tx_enabled ||")
    assert enqueue_body.index("mutex_enter(&dp->tx_lock);") < gate
    required = ("dp->sc->sc_datapath != dp", "!dp->sc->sc_linux.started",
                "!dp->sc->sc_linux.fw_ready",
                "dp->sc->sc_linux.stage != R23BE_STAGE_RUNNING")
    for tok in required:
        assert tok in enqueue_body[gate:], tok
        assert enqueue_body.index(tok) < enqueue_body.index(
            "rtwn8723be_tx_native_enqueue(")
    assert enqueue_body.index("rtwn8723be_tx_native_enqueue(") < (
        enqueue_body.index("mutex_exit(&dp->tx_lock);"))

    # The separate RX C file needs the complete native softc definition:
    # rx_binding.h intentionally holds only a net80211 pointer and its
    # transitive header only forward-declares the PCI device softc.
    assert "struct rtwn8723be_softc {" in NETH
    assert "struct rtwn8723be_softc {" not in RXH
    assert '#include "rtwn8723be_netbsd.h"' in rx_source
    assert rx_source.index('#include "rtwn8723be_netbsd.h"') < (
        rx_source.index('#include "rtwn8723be_rx_binding.h"'))
    assert "net->sc->sc_rx_binding" in rx_source
    assert "sc->sc_datapath" in rx_source

contract(start, enqueue, RX)

mutations = (
    (start.replace("sc->sc_datapath != dp ||", "false ||", 1), enqueue, RX),
    (start.replace("sc->sc_irq_arg != dp", "false", 1), enqueue, RX),
    (start.replace("sc->sc_linux.stage != R23BE_STAGE_RUNNING",
                   "false", 1), enqueue, RX),
    (start, enqueue.replace("dp->sc->sc_datapath != dp", "false", 1), RX),
    (start, enqueue.replace("dp->sc->sc_linux.stage != R23BE_STAGE_RUNNING",
                            "false", 1), RX),
    (start, enqueue.replace("!dp->sc->sc_linux.fw_ready", "false", 1), RX),
    (start, enqueue, RX.replace('#include "rtwn8723be_netbsd.h"\n', "", 1)),
)
for i, (a, b, c) in enumerate(mutations, 1):
    assert a != start or b != enqueue or c != RX, i
    try:
        contract(a, b, c)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe datapath/kernel declaration mutation {i}")

harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>

#define R23BE_STAGE_RUNNING 43
#define R23BE_STAGE_STOPPING 44
#define R23BE_STAGE_PROBED 18
typedef struct { bool held; } kmutex_t;
static int enters, exits;
static void mutex_enter(kmutex_t *m)
{ assert(m && !m->held); m->held = true; enters++; }
static void mutex_exit(kmutex_t *m)
{ assert(m && m->held); m->held = false; exits++; }

struct rtwn8723be_datapath;
struct rtwn8723be_softc {
    struct rtwn8723be_datapath *sc_datapath;
    void *sc_irq_arg, *sc_ih;
    struct { int stage; bool started, fw_ready; } sc_linux;
    bool sc_irq_dispatch_ready, sc_mapped, sc_rings_allocated;
};
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    kmutex_t tx_lock;
    bool prepared, tx_enabled;
};
struct mbuf { int id; };
struct rtwn8723be_tx_params { unsigned queue; };
static int hardware_tx_calls, hardware_tx_error;
static int rtwn8723be_tx_native_enqueue(struct rtwn8723be_softc *sc,
    unsigned int qid, struct mbuf *m,
    const struct rtwn8723be_tx_params *p, bool command)
{
    assert(sc && sc->sc_datapath && sc->sc_datapath->tx_lock.held);
    assert(sc->sc_linux.stage == R23BE_STAGE_RUNNING);
    assert(qid == 2 && m && m->id == 1 && p && !command);
    hardware_tx_calls++;
    return hardware_tx_error;
}
'''
epilogue = r'''
static void reset(struct rtwn8723be_softc *sc,
    struct rtwn8723be_datapath *dp)
{
    *sc = (struct rtwn8723be_softc){0};
    *dp = (struct rtwn8723be_datapath){0};
    dp->sc = sc;
    dp->prepared = true;
    sc->sc_datapath = dp;
    sc->sc_irq_arg = dp;
    sc->sc_irq_dispatch_ready = true;
    sc->sc_ih = sc;
    sc->sc_mapped = true;
    sc->sc_rings_allocated = true;
    sc->sc_linux.started = true;
    sc->sc_linux.fw_ready = true;
    sc->sc_linux.stage = R23BE_STAGE_RUNNING;
}
int main(void)
{
    struct rtwn8723be_softc sc={0};
    struct rtwn8723be_datapath dp={0};
    struct mbuf m={.id=1};
    struct rtwn8723be_tx_params params={.queue=2};

    assert(rtwn8723be_datapath_start(NULL) == EINVAL);
    reset(&sc,&dp);
    sc.sc_datapath = NULL;
    assert(rtwn8723be_datapath_start(&dp) == EBUSY);
    sc.sc_datapath = &dp;
    sc.sc_irq_arg = NULL;
    assert(rtwn8723be_datapath_start(&dp) == EBUSY);
    sc.sc_irq_arg = &dp;
    sc.sc_linux.stage = R23BE_STAGE_STOPPING;
    assert(rtwn8723be_datapath_start(&dp) == EAGAIN && !dp.tx_enabled);
    sc.sc_linux.stage = R23BE_STAGE_RUNNING;
    assert(rtwn8723be_datapath_start(&dp) == 0 && dp.tx_enabled);
    assert(rtwn8723be_datapath_enqueue(&dp,2,&m,&params,false) == 0);
    assert(hardware_tx_calls == 1 && enters == exits);

    /* STOPPING retains Linux started and firmware flags until STOPPED.
     * It is nevertheless NOT a valid TX DMA descriptor lifetime.
     */
    sc.sc_linux.stage = R23BE_STAGE_STOPPING;
    assert(rtwn8723be_datapath_enqueue(&dp,2,&m,&params,false) == EAGAIN);
    assert(hardware_tx_calls == 1 && enters == exits);
    sc.sc_linux.stage = R23BE_STAGE_RUNNING;
    sc.sc_datapath = NULL;
    assert(rtwn8723be_datapath_enqueue(&dp,2,&m,&params,false) == EAGAIN);
    assert(hardware_tx_calls == 1);
    sc.sc_datapath = &dp;
    sc.sc_linux.started = false;
    assert(rtwn8723be_datapath_enqueue(&dp,2,&m,&params,false) == EAGAIN);
    sc.sc_linux.started = true;
    sc.sc_linux.fw_ready = false;
    assert(rtwn8723be_datapath_enqueue(&dp,2,&m,&params,false) == EAGAIN);
    sc.sc_linux.fw_ready = true;
    dp.tx_enabled = false;
    assert(rtwn8723be_datapath_enqueue(&dp,2,&m,&params,false) == EAGAIN);
    dp.tx_enabled = true;
    hardware_tx_error = EBUSY;
    assert(rtwn8723be_datapath_enqueue(&dp,2,&m,&params,false) == EBUSY);
    assert(hardware_tx_calls == 2);
    assert(rtwn8723be_datapath_enqueue(&dp,2,NULL,&params,false) == EINVAL);
    assert(rtwn8723be_datapath_enqueue(&dp,2,&m,NULL,false) == EINVAL);
    assert(rtwn8723be_datapath_enqueue(NULL,2,&m,&params,false) == EINVAL);
    assert(enters == exits && !dp.tx_lock.held);
    puts("RTL_NATIVE_DATAPATH_TX_STAGE_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-datapath-stage-") as temp:
    source = Path(temp) / "test.c"
    exe = Path(temp) / "test"
    source.write_text(harness + "\n" + start + "\n" + enqueue +
                      "\n" + epilogue)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        str(source), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_NATIVE_DATAPATH_STAGE_AND_INCLUDE_OK negatives=7")
