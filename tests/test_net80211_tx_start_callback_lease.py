#!/usr/bin/env python3
"""Run production net80211 if_start, native TX lease/STOP/unprepare under C11 UBSan.

An external tx_start callback reentrantly asks to STOP and unprepare
while still borrowing the net80211/PCI owner. Both must fail closed.
The callback returns; a later explicit retry may transition to STOPPING.
This is not a NetBSD SMP, PCI, or automatic stop-drain test.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DP = (ROOT / "src/rtwn8723be_datapath.c").read_text()
NET = (ROOT / "src/rtwn8723be_net80211.c").read_text()
HDR = (ROOT / "src/rtwn8723be_datapath.h").read_text()
LINUX = (ROOT / "src/rtwn8723be_linux_state.c").read_text()

def function(src: str, name: str, ret: str) -> str:
    anchor = "\n" + name + "("
    assert src.count(anchor) == 1, name
    tail = name + "(" + src.split(anchor, 1)[1]
    depth = 0
    for i in range(tail.index("{"), len(tail)):
        if tail[i] == "{":
            depth += 1
        elif tail[i] == "}":
            depth -= 1
            if depth == 0:
                return ret + "\n" + tail[:i + 1]
    raise AssertionError(name)

ifstart = function(NET, "rtwn8723be_n80211_ifstart", "static void")
borrow = function(DP, "rtwn8723be_datapath_tx_start_begin", "bool")
release = function(DP, "rtwn8723be_datapath_tx_start_end", "void")
stop = function(DP, "rtwn8723be_datapath_begin_stop", "int")
unprepare = function(DP, "rtwn8723be_datapath_unprepare", "int")

def contract(a: str, b: str, e: str, s: str, u: str, h: str):
    assert "unsigned int tx_start_active;" in h
    assert "bool rtwn8723be_datapath_tx_start_begin(" in h
    assert "void rtwn8723be_datapath_tx_start_end(" in h
    assert "rtwn8723be_datapath_tx_start_begin(dp)" in a
    assert "rtwn8723be_datapath_tx_start_end(dp);" in a
    acq = a.index("rtwn8723be_datapath_tx_start_begin(dp)")
    callback = a.index("n->methods.tx_start(n->sc, ifp);")
    rel = a.index("rtwn8723be_datapath_tx_start_end(dp);")
    assert acq < callback < rel
    assert "if (!rtwn8723be_datapath_tx_start_begin(dp))" in a
    assert "(ifp->if_flags & (IFF_RUNNING | IFF_OACTIVE)) != IFF_RUNNING" in a

    locked = b.index("mutex_enter(&dp->tx_lock);")
    inc = b.index("dp->tx_start_active++;")
    unlock = b.index("mutex_exit(&dp->tx_lock);")
    assert locked < inc < unlock
    assert "if (ready)" in b[locked:inc]
    for token in (
        "dp->tx_enabled", "!dp->stop_pending", "sc->sc_datapath == dp",
        "sc->sc_irq_arg == dp", "sc->sc_irq_dispatch_ready",
        "sc->sc_ih != NULL", "sc->sc_mapped", "sc->sc_rings_allocated",
        "sc->sc_linux.started", "sc->sc_linux.fw_ready",
        "sc->sc_linux.stage == R23BE_STAGE_RUNNING",
    ):
        assert locked < b.index(token) < inc, token
    assert "if (dp == NULL || !dp->prepared || dp->sc == NULL)" in b
    assert "return ready;" in b

    assert e.index("mutex_enter(&dp->tx_lock);") < e.index(
        "dp->tx_start_active--;") < e.index("mutex_exit(&dp->tx_lock);")
    assert "KASSERT(dp->tx_start_active != 0);" in e
    assert "dp->rx_callback_active != 0 ||" in s
    assert "dp->tx_callback_active != 0 || dp->tx_start_active != 0" in s
    assert s.index("mutex_enter(&dp->tx_lock);") < s.index(
        "dp->tx_start_active != 0") < s.index(
        "state->stage = R23BE_STAGE_STOPPING;")
    assert "dp->stop_pending = true;" in s
    assert "dp->tx_enabled = false;" in s
    guard = "dp->tx_callback_active != 0 || dp->rx_callback_active != 0 ||"
    assert guard in u
    assert "dp->tx_start_active != 0" in u[u.index(guard):]
    assert u.index("mutex_enter(&dp->tx_lock);") < u.index(
        "dp->tx_start_active != 0") < u.index(
        "rtwn8723be_netbsd_irq_set_dispatch(sc, NULL, NULL);")
    assert "error = ops->begin_stop(ctx, state);" in LINUX

contract(ifstart, borrow, release, stop, unprepare, HDR)
negatives = (
    (ifstart.replace("rtwn8723be_datapath_tx_start_begin(dp)",
                     "true", 1), borrow, release, stop, unprepare, HDR),
    (ifstart.replace("rtwn8723be_datapath_tx_start_end(dp);", "", 1),
     borrow, release, stop, unprepare, HDR),
    (ifstart.replace("n->methods.tx_start(n->sc, ifp);", "", 1),
     borrow, release, stop, unprepare, HDR),
    (ifstart, borrow.replace("dp->tx_start_active++;", "", 1),
     release, stop, unprepare, HDR),
    (ifstart, borrow.replace("!dp->stop_pending", "true", 1),
     release, stop, unprepare, HDR),
    (ifstart, borrow.replace("sc->sc_datapath == dp", "true", 1),
     release, stop, unprepare, HDR),
    (ifstart, borrow.replace("mutex_enter(&dp->tx_lock);", "", 1),
     release, stop, unprepare, HDR),
    (ifstart, borrow, release.replace("dp->tx_start_active--;", "", 1),
     stop, unprepare, HDR),
    (ifstart, borrow, release.replace("KASSERT(dp->tx_start_active != 0);",
                                     "", 1), stop, unprepare, HDR),
    (ifstart, borrow, release,
     stop.replace("dp->tx_start_active != 0", "false", 1),
     unprepare, HDR),
    (ifstart, borrow, release, stop,
     unprepare.replace("dp->tx_start_active != 0", "false", 1), HDR),
    (ifstart, borrow, release, stop, unprepare,
     HDR.replace("unsigned int tx_start_active;", "", 1)),
)
for i, mutant in enumerate(negatives, 1):
    assert mutant != (ifstart, borrow, release, stop, unprepare, HDR), i
    try:
        contract(*mutant)
    except (ValueError, AssertionError):
        continue
    raise AssertionError(f"unsafe if_start lifetime mutation {i} accepted")

prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define KASSERT assert
#define R23BE_STAGE_RUNNING 43
#define R23BE_STAGE_STOPPING 44
#define IFF_RUNNING 0x40U
#define IFF_OACTIVE 0x400U

typedef struct { bool held, destroyed; } kmutex_t;
struct rtwn8723be_datapath;
struct rtwn8723be_linux_state { int stage; bool started, fw_ready; };
struct rtwn8723be_irq_dispatch {
    void (*rx)(void *);
    void (*tx_done)(void *, unsigned int);
    void (*power_event)(void *);
};
struct ifnet { void *if_softc; unsigned int if_flags; };
struct rtwn8723be_softc {
    struct rtwn8723be_datapath *sc_datapath;
    void *sc_irq_arg, *sc_ih, *sc_soft_ih, *sc_pihp;
    bool sc_irq_dispatch_ready, sc_irq_requested, sc_irq_enabled;
    bool sc_mapped, sc_rings_allocated;
    struct rtwn8723be_irq_dispatch sc_irq_dispatch;
    struct rtwn8723be_linux_state sc_linux;
};
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    kmutex_t tx_lock;
    bool prepared, tx_enabled, stop_pending;
    unsigned int tx_callback_active, rx_callback_active, tx_start_active;
};
struct rtwn8723be_net80211_methods {
    void (*tx_start)(struct rtwn8723be_softc *, struct ifnet *);
};
struct rtwn8723be_net80211 {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_net80211_methods methods;
    bool registered;
};
static int locks, unlocks, destroys, unbinds, tx_calls, in_callback;
static void mutex_enter(kmutex_t *m)
{ assert(m && !m->held && !m->destroyed); m->held = true; locks++; }
static void mutex_exit(kmutex_t *m)
{ assert(m && m->held && !m->destroyed); m->held = false; unlocks++; }
static void mutex_destroy(kmutex_t *m)
{ assert(m && !m->held && !m->destroyed); m->destroyed = true; destroys++; }
static void rtwn8723be_dp_rx(void *arg) { (void)arg; }
static void rtwn8723be_dp_tx_done(void *arg, unsigned int id)
{ (void)arg; (void)id; }
static void rtwn8723be_netbsd_irq_set_dispatch(
    struct rtwn8723be_softc *sc,
    const struct rtwn8723be_irq_dispatch *callbacks, void *arg)
{
    assert(sc && callbacks == NULL && arg == NULL);
    sc->sc_irq_dispatch_ready = false;
    sc->sc_irq_arg = NULL;
    memset(&sc->sc_irq_dispatch, 0, sizeof(sc->sc_irq_dispatch));
    unbinds++;
}
'''
epilogue = r'''
static void callback(struct rtwn8723be_softc *sc, struct ifnet *ifp)
{
    struct rtwn8723be_datapath *dp = sc->sc_datapath;
    assert(!dp->tx_lock.held && dp->tx_start_active == 1);
    assert(ifp->if_flags == IFF_RUNNING);
    tx_calls++;
    assert(rtwn8723be_datapath_begin_stop(dp, &sc->sc_linux) == EBUSY);
    assert(sc->sc_linux.stage == R23BE_STAGE_RUNNING);
    assert(dp->stop_pending && !dp->tx_enabled);
    /* Model IRQ handlers already disestablished: only the lease can
     * still prohibit unprepare. Restore IRQ owner after this probe. */
    sc->sc_ih = NULL;
    assert(rtwn8723be_datapath_unprepare(dp) == EBUSY);
    sc->sc_ih = sc;
    assert(dp->prepared && dp->tx_start_active == 1);
    assert(sc->sc_datapath == dp && sc->sc_irq_arg == dp);
    assert(destroys == 0 && unbinds == 0);
    in_callback++;
}
int main(void)
{
    struct rtwn8723be_softc sc = {0};
    struct rtwn8723be_datapath dp = {0};
    struct rtwn8723be_net80211 net = {0};
    struct ifnet ifp = {0};
    dp.sc = &sc;
    dp.prepared = dp.tx_enabled = true;
    sc.sc_datapath = &dp;
    sc.sc_irq_arg = &dp;
    sc.sc_irq_dispatch_ready = true;
    sc.sc_ih = &sc;
    sc.sc_mapped = sc.sc_rings_allocated = true;
    sc.sc_irq_dispatch.rx = rtwn8723be_dp_rx;
    sc.sc_irq_dispatch.tx_done = rtwn8723be_dp_tx_done;
    sc.sc_linux.started = sc.sc_linux.fw_ready = true;
    sc.sc_linux.stage = R23BE_STAGE_RUNNING;
    net.registered = true;
    net.sc = &sc;
    net.methods.tx_start = callback;
    ifp.if_softc = &net;
    ifp.if_flags = IFF_RUNNING;

    rtwn8723be_n80211_ifstart(&ifp);
    assert(tx_calls == 1 && in_callback == 1);
    assert(dp.tx_start_active == 0 && dp.stop_pending);
    assert(locks == unlocks && !dp.tx_lock.held);
    /* Pending STOP forbids a second callback, despite stale IFF_RUNNING. */
    rtwn8723be_n80211_ifstart(&ifp);
    assert(tx_calls == 1 && dp.tx_start_active == 0);

    /* A later explicit retry can enter STOPPING only once callback ends. */
    assert(rtwn8723be_datapath_begin_stop(&dp, &sc.sc_linux) == 0);
    assert(sc.sc_linux.stage == R23BE_STAGE_STOPPING);
    assert(!dp.stop_pending && !dp.tx_enabled);
    rtwn8723be_n80211_ifstart(&ifp);
    assert(tx_calls == 1);
    sc.sc_ih = NULL; /* External IRQ owner disestablished the handler. */
    assert(rtwn8723be_datapath_unprepare(&dp) == 0);
    assert(destroys == 1 && unbinds == 1 && !dp.prepared);
    assert(!sc.sc_irq_dispatch_ready && sc.sc_datapath == NULL);
    assert(locks == unlocks);

    /* Zero active lease in an invalid owner cannot authorize fresh TX. */
    struct rtwn8723be_softc invalid_sc = {0};
    struct rtwn8723be_datapath invalid_dp = {0};
    invalid_dp.sc = &invalid_sc;
    invalid_dp.prepared = invalid_dp.tx_enabled = true;
    invalid_sc.sc_linux.started = invalid_sc.sc_linux.fw_ready = true;
    invalid_sc.sc_linux.stage = R23BE_STAGE_RUNNING;
    assert(!rtwn8723be_datapath_tx_start_begin(&invalid_dp));
    assert(invalid_dp.tx_start_active == 0);
    assert(locks == unlocks);
    puts("RTL_NET80211_TX_START_CALLBACK_LEASE_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtl-tx-start-lease-") as td:
    source = Path(td) / "harness.c"
    exe = Path(td) / "harness"
    source.write_text(prefix + "\n" + borrow + "\n" + release + "\n" +
                      stop + "\n" + unprepare + "\n" + ifstart + "\n" + epilogue)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all", str(source),
                    "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_NET80211_TX_START_LEASE_SOURCE_NEGATIVES_OK negatives=12")
