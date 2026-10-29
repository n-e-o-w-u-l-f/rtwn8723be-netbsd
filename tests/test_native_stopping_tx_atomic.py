#!/usr/bin/env python3
"""Compile actual native STOPPING and TX-gate functions using C11/UBSan.

An instrumented IPL_NET mutex injects a pending TX producer / state
transition at lock acquisition. Source guards validate the real Linux
stop callback preflight plus native binding, not just a model.
The external NetBSD IRQ, DMA and hardware callbacks remain untested.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DP = (ROOT / "src/rtwn8723be_datapath.c").read_text()
NETBSD = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
LINUX = (ROOT / "src/rtwn8723be_linux_state.c").read_text()
LINUX_H = (ROOT / "src/rtwn8723be_linux_state.h").read_text()

def func(src: str, name: str, result: str) -> str:
    marker = "\n" + name + "("
    assert src.count(marker) == 1, (name, src.count(marker))
    code = name + "(" + src.split(marker, 1)[1]
    start, level = code.index("{"), 0
    for i in range(start, len(code)):
        if code[i] == "{":
            level += 1
        elif code[i] == "}":
            level -= 1
            if level == 0:
                return result + "\n" + code[:i+1]
    raise AssertionError("unbalanced native body " + name)

begin = func(DP, "rtwn8723be_datapath_begin_stop", "int")
start = func(DP, "rtwn8723be_datapath_start", "int")
enqueue = func(DP, "rtwn8723be_datapath_enqueue", "int")
glue = func(NETBSD, "rtwn8723be_netbsd_begin_stop", "static int")

def contract(b: str, glue_src: str, l: str, h: str) -> None:
    lock = b.index("mutex_enter(&dp->tx_lock);")
    owner = b.index("sc->sc_datapath != dp || sc->sc_irq_arg != dp")
    stage = b.index("state->stage != R23BE_STAGE_RUNNING")
    disable = b.rindex("dp->tx_enabled = false;")
    transition = b.index("state->stage = R23BE_STAGE_STOPPING;")
    unlock = b.index("mutex_exit(&dp->tx_lock);")
    assert lock < owner < stage < disable < transition < unlock
    assert "state != &sc->sc_linux" in b
    assert "!state->fw_ready" in b
    assert "return error;" in b
    assert "rtwn8723be_datapath_begin_stop(sc->sc_datapath, state)" in glue_src
    assert ".begin_stop = rtwn8723be_netbsd_begin_stop," in NETBSD
    assert "int (*begin_stop)(void *, struct rtwn8723be_linux_state *);" in h

    stop = func(l, "rtwn8723be_linux_adapter_stop", "int")
    assert "ops->begin_stop == NULL" in l
    assert "error = ops->begin_stop(ctx, state);" in stop
    assert stop.index("error = ops->begin_stop(ctx, state);") < (
        stop.index("R23BE_CALL(R23BE_STAGE_STOPPING, ops->bt_halt_deinit"))
    assert "if (!state->started || state->stage != R23BE_STAGE_STOPPING)" in stop
    assert "state->stage = R23BE_STAGE_STOPPING;" not in stop

contract(begin, glue, LINUX, LINUX_H)
mutations = (
    (begin.replace("sc->sc_datapath != dp ||", "false ||", 1), glue, LINUX, LINUX_H),
    (begin.replace("sc->sc_irq_arg != dp ||", "false ||", 1), glue, LINUX, LINUX_H),
    (begin.replace("state != &sc->sc_linux", "false", 1), glue, LINUX, LINUX_H),
    (begin.replace("state->stage != R23BE_STAGE_RUNNING", "false", 1), glue, LINUX, LINUX_H),
    (begin.replace("mutex_enter(&dp->tx_lock);", "/* lock gone */", 1), glue, LINUX, LINUX_H),
    (begin.replace("state->stage = R23BE_STAGE_STOPPING;", "/* never change stage */", 1), glue, LINUX, LINUX_H),
    (begin, glue.replace("rtwn8723be_datapath_begin_stop(sc->sc_datapath, state)", "0", 1), LINUX, LINUX_H),
    (begin, glue, LINUX.replace("error = ops->begin_stop(ctx, state);", "error = 0;", 1), LINUX_H),
    (begin, glue, LINUX.replace("if (ops->begin_stop == NULL ||", "if (", 1), LINUX_H),
    (begin, glue, LINUX, LINUX_H.replace("int (*begin_stop)(void *, struct rtwn8723be_linux_state *);", "", 1)),
)
for i, candidate in enumerate(mutations, 1):
    assert candidate != (begin, glue, LINUX, LINUX_H), i
    try:
        contract(*candidate)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe STOPPING transition mutation {i} passed")

harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <errno.h>

#define R23BE_STAGE_RUNNING 43
#define R23BE_STAGE_STOPPING 44
struct rtwn8723be_datapath;
struct rtwn8723be_linux_state {
    int stage;
    bool being_init_adapter, mac_func_enable, fw_ready, started;
};
struct rtwn8723be_softc {
    struct rtwn8723be_datapath *sc_datapath;
    void *sc_irq_arg, *sc_ih;
    struct rtwn8723be_linux_state sc_linux;
    bool sc_irq_dispatch_ready, sc_mapped, sc_rings_allocated;
};
typedef struct { bool held; } kmutex_t;
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    kmutex_t tx_lock;
    bool prepared, tx_enabled, stop_pending;
    unsigned int tx_callback_active, rx_callback_active, tx_start_active;
};
struct mbuf { unsigned id; };
struct ieee80211_node { unsigned id; };
struct rtwn8723be_tx_params { unsigned queue; };
static struct rtwn8723be_softc *active_sc;
static int on_lock, locks, unlocks, native_enqueues, invoke_stop;
static void mutex_enter(kmutex_t *m)
{
    assert(m && !m->held);
    m->held = true;
    locks++;
    if (on_lock == 1)
        active_sc->sc_linux.stage = R23BE_STAGE_STOPPING;
    if (on_lock == 2)
        active_sc->sc_datapath = NULL;
    if (on_lock == 3)
        active_sc->sc_linux.fw_ready = false;
    on_lock = 0;
}
static void mutex_exit(kmutex_t *m)
{ assert(m && m->held); m->held = false; unlocks++; }
static int rtwn8723be_tx_native_enqueue(struct rtwn8723be_softc *sc,
    unsigned int qid, struct mbuf *m, struct ieee80211_node *ni,
    const struct rtwn8723be_tx_params *p, bool command)
{
    assert(sc->sc_datapath->tx_lock.held && !command);
    assert(sc->sc_linux.stage == R23BE_STAGE_RUNNING);
    assert(qid == 2 && m && ni && ni->id == 17 && p);
    native_enqueues++;
    return 0;
}
'''
checks = r'''
static void setup(struct rtwn8723be_softc *sc,
    struct rtwn8723be_datapath *dp)
{
    *sc = (struct rtwn8723be_softc){0};
    *dp = (struct rtwn8723be_datapath){0};
    sc->sc_datapath = dp;
    sc->sc_irq_arg = dp;
    sc->sc_irq_dispatch_ready = true;
    sc->sc_linux.stage = R23BE_STAGE_RUNNING;
    sc->sc_linux.started = sc->sc_linux.fw_ready = true;
    sc->sc_rings_allocated = sc->sc_mapped = true;
    sc->sc_ih = sc;
    dp->sc = sc;
    dp->prepared = dp->tx_enabled = true;
    active_sc = sc;
    native_enqueues = locks = unlocks = invoke_stop = on_lock = 0;
}
static void balanced(struct rtwn8723be_datapath *dp)
{ assert(!dp->tx_lock.held && locks == unlocks); }
int main(void)
{
    struct rtwn8723be_softc sc;
    struct rtwn8723be_datapath dp;
    struct mbuf m = {.id = 3};
    struct ieee80211_node node = {.id = 17};
    struct rtwn8723be_tx_params p = {.queue = 2};

    setup(&sc, &dp);
    assert(rtwn8723be_netbsd_begin_stop(&sc, &sc.sc_linux) == 0);
    assert(sc.sc_linux.stage == R23BE_STAGE_STOPPING && !dp.tx_enabled);
    assert(rtwn8723be_datapath_enqueue(&dp, 2, &m, &node, &p, false) == EAGAIN);
    assert(native_enqueues == 0);
    balanced(&dp);

    setup(&sc, &dp);
    on_lock = 1; /* state changed before lock acquired */
    assert(rtwn8723be_netbsd_begin_stop(&sc, &sc.sc_linux) == EAGAIN);
    assert(sc.sc_linux.stage == R23BE_STAGE_STOPPING && !dp.tx_enabled);
    balanced(&dp);

    setup(&sc, &dp);
    on_lock = 2;
    assert(rtwn8723be_datapath_begin_stop(&dp, &sc.sc_linux) == EBUSY);
    assert(sc.sc_linux.stage == R23BE_STAGE_RUNNING);
    sc.sc_datapath = &dp;
    balanced(&dp);

    setup(&sc, &dp);
    on_lock = 3;
    assert(rtwn8723be_datapath_begin_stop(&dp, &sc.sc_linux) == EAGAIN);
    assert(!dp.tx_enabled && sc.sc_linux.stage == R23BE_STAGE_RUNNING);
    balanced(&dp);

    setup(&sc, &dp);
    assert(rtwn8723be_netbsd_begin_stop(NULL, &sc.sc_linux) == EINVAL);
    assert(rtwn8723be_netbsd_begin_stop(&sc, NULL) == EINVAL);
    struct rtwn8723be_linux_state foreign = sc.sc_linux;
    assert(rtwn8723be_netbsd_begin_stop(&sc, &foreign) == EINVAL);
    assert(rtwn8723be_datapath_begin_stop(NULL, &sc.sc_linux) == EINVAL);
    assert(rtwn8723be_datapath_begin_stop(&dp, &foreign) == EINVAL);

    setup(&sc, &dp);
    dp.rx_callback_active = 1;
    assert(rtwn8723be_netbsd_begin_stop(&sc, &sc.sc_linux) == EBUSY);
    assert(sc.sc_linux.stage == R23BE_STAGE_RUNNING && !dp.tx_enabled);
    assert(dp.stop_pending);
    dp.rx_callback_active = 0;
    assert(rtwn8723be_netbsd_begin_stop(&sc, &sc.sc_linux) == 0);
    assert(sc.sc_linux.stage == R23BE_STAGE_STOPPING && !dp.stop_pending);
    balanced(&dp);

    setup(&sc, &dp);
    dp.tx_callback_active = 1;
    assert(rtwn8723be_netbsd_begin_stop(&sc, &sc.sc_linux) == EBUSY);
    assert(sc.sc_linux.stage == R23BE_STAGE_RUNNING && !dp.tx_enabled);
    dp.tx_callback_active = 0;
    assert(rtwn8723be_netbsd_begin_stop(&sc, &sc.sc_linux) == 0);
    balanced(&dp);

    setup(&sc, &dp);
    assert(rtwn8723be_datapath_enqueue(&dp, 2, &m, &node, &p, false) == 0);
    assert(native_enqueues == 1);
    assert(rtwn8723be_netbsd_begin_stop(&sc, &sc.sc_linux) == 0);
    assert(rtwn8723be_datapath_enqueue(&dp, 2, &m, &node, &p, false) == EAGAIN);
    assert(native_enqueues == 1);
    balanced(&dp);

    puts("RTL_NATIVE_STOPPING_ATOMIC_TX_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtl-native-begin-stop-") as td:
    src = Path(td) / "test.c"
    binary = Path(td) / "test"
    src.write_text(harness + "\n" + begin + "\n" + glue + "\n" +
                   enqueue + "\n" + checks)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        str(src), "-o", str(binary)
    ], check=True)
    subprocess.run([str(binary)], check=True)
print("RTL_NATIVE_STOPPING_SOURCE_MUTATIONS_OK negatives=10")
