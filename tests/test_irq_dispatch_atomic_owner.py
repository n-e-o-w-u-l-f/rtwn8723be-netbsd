#!/usr/bin/env python3
"""Execute real native IRQ dispatch attach/revoke and datapath failure rollback.

Strict C11/UBSan with production function bodies. Missing callback arguments
and active IRQ lifetimes must not publish or retire IRQ callback pointers.
The datapath owner must cleanly roll back a failed attach and retain its
storage when a concurrent IRQ enable rejects a final unbind.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
IRQ = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
DP = (ROOT / "src/rtwn8723be_datapath.c").read_text()
IRQ_H = (ROOT / "src/rtwn8723be_netbsd.h").read_text()

def extract(src: str, name: str, ret: str) -> str:
    marker = "\n" + name + "("
    assert src.count(marker) == 1, name
    x = name + "(" + src.split(marker, 1)[1]
    depth = 0
    for i in range(x.index("{"), len(x)):
        if x[i] == "{":
            depth += 1
        elif x[i] == "}":
            depth -= 1
            if depth == 0:
                return ret + "\n" + x[:i + 1]
    raise AssertionError(name)

publish = extract(IRQ, "rtwn8723be_netbsd_irq_set_dispatch", "int")
prepare = extract(DP, "rtwn8723be_datapath_prepare", "int")
unprepare = extract(DP, "rtwn8723be_datapath_unprepare", "int")

def contract(pub: str, prep: str, unprep: str) -> None:
    assert "int rtwn8723be_netbsd_irq_set_dispatch(" in IRQ_H
    assert "if (sc == NULL || !sc->sc_irq_lock_initialized)" in pub
    assert "dispatch == NULL && dispatch_arg != NULL" in pub
    assert "dispatch->rx == NULL || dispatch->tx_done == NULL ||" in pub
    assert "dispatch_arg == NULL" in pub
    assert "sc->sc_irq_requested || sc->sc_irq_enabled ||" in pub
    for token in ("sc->sc_ih != NULL", "sc->sc_soft_ih != NULL",
                  "sc->sc_pihp != NULL"):
        assert token in pub
    entry = pub.index("mutex_enter(&sc->sc_irq_lock);")
    busy = pub.index("return EBUSY;", entry)
    ready = pub.index("sc->sc_irq_dispatch_ready = true;", busy)
    unlock = pub.index("mutex_exit(&sc->sc_irq_lock);", ready)
    assert entry < busy < ready < unlock
    assert "sc->sc_irq_dispatch_ready = false;" in pub
    assert "sc->sc_irq_arg = NULL;" in pub
    assert pub.index("sc->sc_irq_dispatch = *dispatch;") < ready
    assert pub.index("sc->sc_irq_arg = dispatch_arg;") < ready

    assignment = "error = rtwn8723be_netbsd_irq_set_dispatch(sc, &irq, dp);"
    assert assignment in prep
    assert prep.index(assignment) < prep.index("if (error != 0) {")
    pos = prep.index("if (error != 0) {", prep.index(assignment))
    for token in ("sc->sc_datapath = NULL;", "dp->prepared = false;",
                  "mutex_destroy(&dp->tx_lock);", "memset(dp, 0, sizeof(*dp));",
                  "return error;"):
        assert token in prep[pos:]
    rollback = prep.index("mutex_destroy(&dp->tx_lock);", pos)
    assert pos < prep.index("sc->sc_datapath = NULL;", pos) < rollback
    assert rollback < prep.index("return error;", rollback)

    assignment = "error = rtwn8723be_netbsd_irq_set_dispatch(sc, NULL, NULL);"
    assert assignment in unprep
    assign_at = unprep.index(assignment)
    guard = unprep.index("if (error != 0)", assign_at)
    preserved = unprep.index("return error;", guard)
    free = unprep.index("sc->sc_datapath = NULL;", preserved)
    assert assign_at < guard < preserved < free
    assert "mutex_destroy(&dp->tx_lock);" in unprep[free:]

contract(publish, prepare, unprepare)
mutations = (
    (publish.replace("dispatch_arg == NULL", "false", 1), prepare, unprepare),
    (publish.replace("dispatch->rx == NULL", "false", 1), prepare, unprepare),
    (publish.replace("dispatch->tx_done == NULL", "false", 1), prepare, unprepare),
    (publish.replace("sc->sc_irq_requested", "false", 1), prepare, unprepare),
    (publish.replace("sc->sc_irq_enabled", "false", 1), prepare, unprepare),
    (publish.replace("sc->sc_ih != NULL", "false", 1), prepare, unprepare),
    (publish.replace("sc->sc_soft_ih != NULL", "false", 1), prepare, unprepare),
    (publish.replace("sc->sc_pihp != NULL", "false", 1), prepare, unprepare),
    (publish.replace("mutex_enter(&sc->sc_irq_lock);", "", 1), prepare, unprepare),
    (publish.replace("sc->sc_irq_dispatch_ready = true;", "", 1), prepare, unprepare),
    (publish, prepare.replace(
        "error = rtwn8723be_netbsd_irq_set_dispatch(sc, &irq, dp);",
        "error = 0;", 1), unprepare),
    (publish, prepare.replace("mutex_destroy(&dp->tx_lock);", "", 1), unprepare),
    (publish, prepare, unprepare.replace(
        "error = rtwn8723be_netbsd_irq_set_dispatch(sc, NULL, NULL);",
        "error = 0;", 1)),
    (publish, prepare, unprepare.replace("if (error != 0)\n        return error;",
                                         "", 1)),
)
for i, mutant in enumerate(mutations, 1):
    assert mutant != (publish, prepare, unprepare), i
    try:
        contract(*mutant)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe dispatch mutation {i} accepted")

prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define MUTEX_DEFAULT 0
#define IPL_NET 3
#define R23BE_STAGE_PROBED 8
#define R23BE_STAGE_STOPPED 24
#define KASSERT assert
typedef struct { bool initialized, locked, destroyed; } kmutex_t;
struct rtwn8723be_softc;
struct rtwn8723be_datapath;
struct rtwn8723be_irq_dispatch {
    void (*rx)(void *);
    void (*tx_done)(void *, unsigned int);
    void (*power_event)(void *);
};
struct rtwn8723be_rx_dispatch {
    void *arg;
    int (*frame)(void);
    int (*c2h)(void);
};
struct rtwn8723be_linux_state {
    int stage;
    bool started, fw_ready, mac_func_enable, being_init_adapter;
};
struct rtwn8723be_softc {
    kmutex_t sc_irq_lock;
    bool sc_irq_lock_initialized, sc_irq_requested, sc_irq_enabled;
    bool sc_irq_dispatch_ready, sc_core_initialized, sc_rings_allocated;
    bool sc_dma_32bit;
    void *sc_ih, *sc_soft_ih, *sc_pihp, *sc_irq_arg, *sc_dmat;
    struct rtwn8723be_irq_dispatch sc_irq_dispatch;
    struct rtwn8723be_datapath *sc_datapath;
    struct rtwn8723be_linux_state sc_linux;
};
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_rx_dispatch rx;
    kmutex_t tx_lock;
    bool prepared, tx_enabled, stop_pending;
    unsigned int tx_callback_active, rx_callback_active, tx_start_active;
    void (*tx_complete)(void *, unsigned int, size_t);
    void *tx_complete_arg;
};
static int enters, exits, destroys, refuse_release;
static struct rtwn8723be_softc *current_sc;
static struct rtwn8723be_datapath *current_dp;
static void mutex_init(kmutex_t *m, int a, int b)
{ (void)a; (void)b; assert(m && !m->initialized); m->initialized = true; }
static void mutex_enter(kmutex_t *m)
{ assert(m && m->initialized && !m->destroyed && !m->locked);
  m->locked = true; enters++; }
static void mutex_exit(kmutex_t *m)
{ assert(m && m->locked && !m->destroyed);
  m->locked = false; exits++;
  if (refuse_release && current_dp && m == &current_dp->tx_lock) {
    refuse_release = 0;
    assert(current_sc);
    current_sc->sc_irq_requested = true;
  }
}
static void mutex_destroy(kmutex_t *m)
{ assert(m && m->initialized && !m->locked && !m->destroyed);
  m->destroyed = true; destroys++; }
static void rtwn8723be_dp_rx(void *x) { (void)x; }
static void rtwn8723be_dp_tx_done(void *x, unsigned int i)
{ (void)x; (void)i; }
static int frame_stub(void) { return 0; }
static int c2h_stub(void) { return 0; }
'''
tail = r'''
static void setup(struct rtwn8723be_softc *sc,
    struct rtwn8723be_datapath *dp)
{
    *sc = (struct rtwn8723be_softc){0};
    *dp = (struct rtwn8723be_datapath){0};
    sc->sc_irq_lock_initialized = true;
    mutex_init(&sc->sc_irq_lock, MUTEX_DEFAULT, IPL_NET);
    sc->sc_core_initialized = sc->sc_rings_allocated = sc->sc_dma_32bit = true;
    sc->sc_dmat = sc;
    sc->sc_linux.stage = R23BE_STAGE_PROBED;
    enters = exits = destroys = refuse_release = 0;
    current_sc = sc;
    current_dp = dp;
}
static struct rtwn8723be_rx_dispatch callbacks(void)
{
    struct rtwn8723be_rx_dispatch result = {
        .frame = frame_stub, .c2h = c2h_stub,
    };
    return result;
}
static void no_owner(struct rtwn8723be_softc *sc,
    struct rtwn8723be_datapath *dp)
{
    assert(sc->sc_datapath == NULL && sc->sc_irq_arg == NULL &&
        !sc->sc_irq_dispatch_ready && !dp->prepared);
    assert(sc->sc_irq_dispatch.rx == NULL &&
        sc->sc_irq_dispatch.tx_done == NULL);
    assert(enters == exits);
}
static void live_owner(struct rtwn8723be_softc *sc,
    struct rtwn8723be_datapath *dp)
{
    assert(sc->sc_datapath == dp && sc->sc_irq_arg == dp);
    assert(sc->sc_irq_dispatch_ready &&
        sc->sc_irq_dispatch.rx == rtwn8723be_dp_rx &&
        sc->sc_irq_dispatch.tx_done == rtwn8723be_dp_tx_done);
    assert(dp->prepared && dp->sc == sc && !dp->tx_lock.destroyed);
    assert(enters == exits);
}
int main(void)
{
    struct rtwn8723be_softc sc;
    struct rtwn8723be_datapath dp;
    struct rtwn8723be_rx_dispatch rx = callbacks();
    struct rtwn8723be_irq_dispatch partial = {
        .rx = rtwn8723be_dp_rx, .tx_done = rtwn8723be_dp_tx_done
    };

    setup(&sc, &dp);
    assert(rtwn8723be_netbsd_irq_set_dispatch(&sc, &partial, NULL) == EINVAL);
    assert(rtwn8723be_netbsd_irq_set_dispatch(&sc, NULL, &sc) == EINVAL);
    partial.rx = NULL;
    assert(rtwn8723be_netbsd_irq_set_dispatch(&sc, &partial, &sc) == EINVAL);
    partial.rx = rtwn8723be_dp_rx;
    partial.tx_done = NULL;
    assert(rtwn8723be_netbsd_irq_set_dispatch(&sc, &partial, &sc) == EINVAL);
    partial.tx_done = rtwn8723be_dp_tx_done;
    no_owner(&sc, &dp);
    assert(destroys == 0);

    /* A concurrent already-requested IRQ blocks datapath publication,
     * and prepare rolls back its bridge and the just-initialized TX lock.
     */
    sc.sc_irq_requested = true;
    assert(rtwn8723be_datapath_prepare(&dp, &sc, &rx, NULL, NULL) == EBUSY);
    no_owner(&sc, &dp);
    assert(destroys == 1);
    sc.sc_irq_requested = false;

    /* A fully typed callback argument is required for a live bridge. */
    assert(rtwn8723be_datapath_prepare(&dp, &sc, &rx, NULL, NULL) == 0);
    live_owner(&sc, &dp);

    /* Every IRQ execution owner independently rejects unbind. */
    for (int i = 0; i < 5; i++) {
        sc.sc_irq_requested = (i == 0);
        sc.sc_irq_enabled = (i == 1);
        sc.sc_ih = (i == 2) ? &sc : NULL;
        sc.sc_soft_ih = (i == 3) ? &sc : NULL;
        sc.sc_pihp = (i == 4) ? &sc : NULL;
        assert(rtwn8723be_netbsd_irq_set_dispatch(&sc, NULL, NULL) == EBUSY);
        live_owner(&sc, &dp);
    }
    sc.sc_irq_requested = sc.sc_irq_enabled = false;
    sc.sc_ih = sc.sc_soft_ih = sc.sc_pihp = NULL;

    /* Simulate another CPU enabling IRQ after unprepare's preflight
     * and TX-stage check but before dispatch revocation: do not free.
     */
    refuse_release = 1;
    assert(rtwn8723be_datapath_unprepare(&dp) == EBUSY);
    live_owner(&sc, &dp);
    sc.sc_irq_requested = false;
    assert(rtwn8723be_datapath_unprepare(&dp) == 0);
    no_owner(&sc, &dp);
    assert(destroys == 2);
    puts("RTL_IRQ_DISPATCH_ATOMIC_OWNER_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtwn-irq-dispatch-publish-") as td:
    source = Path(td) / "check.c"
    exe = Path(td) / "check"
    source.write_text(prefix + "\n" + publish + "\n" +
                      prepare + "\n" + unprepare + "\n" + tail)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra",
                    "-Werror", "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all", str(source),
                    "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_IRQ_DISPATCH_ATOMIC_MUTATIONS_OK negatives=14")
