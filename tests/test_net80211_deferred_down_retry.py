#!/usr/bin/env python3
"""Execute real net80211 DOWN ioctl/ifstop and native deferred-stop predicate.

Portable strict C11/UBSan: first DOWN returns EBUSY while RX borrows DMA,
repeated DOWN must retry, eventual callback exit permits hardware STOP,
and an additional DOWN must not call STOP again. No real NetBSD ifnet,
interrupt scheduling, PCI DMA, or autonomous retry is simulated.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NET = (ROOT / "src/rtwn8723be_net80211.c").read_text()
DP = (ROOT / "src/rtwn8723be_datapath.c").read_text()
HEADER = (ROOT / "src/rtwn8723be_datapath.h").read_text()

def extract(source: str, name: str, return_type: str) -> str:
    anchor = "\n" + name + "("
    assert source.count(anchor) == 1, (name, source.count(anchor))
    tail = name + "(" + source.split(anchor, 1)[1]
    start, depth = tail.index("{"), 0
    for i in range(start, len(tail)):
        if tail[i] == "{":
            depth += 1
        elif tail[i] == "}":
            depth -= 1
            if depth == 0:
                return return_type + "\n" + tail[:i + 1]
    raise AssertionError("unbalanced production function " + name)

ifstop = extract(NET, "rtwn8723be_n80211_ifstop", "static int")
ioctl = extract(NET, "rtwn8723be_n80211_ioctl", "static int")
retry = extract(DP, "rtwn8723be_datapath_stop_retry_ready", "bool")
begin_stop = extract(DP, "rtwn8723be_datapath_begin_stop", "int")

def contract(stop_body: str, ioctl_body: str, retry_body: str,
             start_stop_body: str, header: str) -> None:
    assert "bool rtwn8723be_datapath_stop_retry_ready(" in header
    assert "ifp->if_flags &= ~(IFF_RUNNING | IFF_OACTIVE);" in stop_body
    assert "return n->methods.hw_stop(n->sc);" in stop_body
    flags = "(ifp->if_flags & (IFF_UP | IFF_RUNNING)) == 0"
    call = "rtwn8723be_datapath_stop_retry_ready("
    assert flags in ioctl_body
    down_gate = ioctl_body.index(flags)
    ready = ioctl_body.index(call, down_gate)
    retry_stop = ioctl_body.index(
        "error = rtwn8723be_n80211_ifstop(n);", ready)
    assert down_gate < ready < retry_stop
    assert ioctl_body.index("ifioctl_common(ifp, cmd, data);") < down_gate
    assert ioctl_body.index("if ((ifp->if_flags & (IFF_UP | IFF_RUNNING)) == IFF_UP)") < down_gate
    assert ioctl_body.index("==\n            IFF_RUNNING)") < down_gate
    assert "n->sc->sc_datapath" in ioctl_body[ready:retry_stop]
    assert "ifp->if_flags |= IFF_RUNNING;" not in ioctl_body[down_gate:retry_stop]
    lock = retry_body.index("mutex_enter(&dp->tx_lock);")
    unlock = retry_body.index("mutex_exit(&dp->tx_lock);")
    for token in (
        "dp->stop_pending", "!dp->tx_enabled", "sc->sc_datapath == dp",
        "sc->sc_irq_arg == dp", "sc->sc_irq_dispatch_ready",
        "sc->sc_linux.started",
        "sc->sc_linux.stage == R23BE_STAGE_RUNNING",
    ):
        assert lock < retry_body.index(token) < unlock, token
    assert "return false;" in retry_body[:lock]
    assert "return ready;" in retry_body
    assert "dp->stop_pending = true;" in start_stop_body
    assert "dp->stop_pending = false;" in start_stop_body
    assert "state->stage = R23BE_STAGE_STOPPING;" in start_stop_body

contract(ifstop, ioctl, retry, begin_stop, HEADER)
negative_controls = (
    (ifstop, ioctl.replace(
        "rtwn8723be_datapath_stop_retry_ready(", "false && (", 1),
     retry, begin_stop, HEADER),
    (ifstop, ioctl.replace(
        "(ifp->if_flags & (IFF_UP | IFF_RUNNING)) == 0",
        "(ifp->if_flags & (IFF_UP | IFF_RUNNING)) == IFF_RUNNING", 1),
     retry, begin_stop, HEADER),
    (ifstop, ioctl.replace(
        "error = rtwn8723be_n80211_ifstop(n);",
        "error = 0;", 1).replace(
        "error = rtwn8723be_n80211_ifstop(n);",
        "error = 0;", 1), retry, begin_stop, HEADER),
    (ifstop.replace(
        "ifp->if_flags &= ~(IFF_RUNNING | IFF_OACTIVE);", "", 1),
     ioctl, retry, begin_stop, HEADER),
    (ifstop, ioctl, retry.replace("dp->stop_pending", "true", 1),
     begin_stop, HEADER),
    (ifstop, ioctl, retry.replace("!dp->tx_enabled", "true", 1),
     begin_stop, HEADER),
    (ifstop, ioctl, retry.replace(
        "sc->sc_datapath == dp", "true", 1),
     begin_stop, HEADER),
    (ifstop, ioctl, retry.replace(
        "sc->sc_linux.stage == R23BE_STAGE_RUNNING", "true", 1),
     begin_stop, HEADER),
    (ifstop, ioctl, retry.replace(
        "mutex_enter(&dp->tx_lock);", "", 1),
     begin_stop, HEADER),
    (ifstop, ioctl, retry, begin_stop, HEADER.replace(
        "bool rtwn8723be_datapath_stop_retry_ready(", "bool absent(")),
)
for i, mutated in enumerate(negative_controls, 1):
    assert mutated != (ifstop, ioctl, retry, begin_stop, HEADER), i
    try:
        contract(*mutated)
    except (ValueError, AssertionError):
        continue
    raise AssertionError(f"unsafe DOWN-retry source mutation {i} passed")

prologue = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <errno.h>
#include <assert.h>
#include "rtwn8723be_linux_state.h"

#define IFF_UP 0x1U
#define IFF_RUNNING 0x40U
#define IFF_OACTIVE 0x400U
#define SIOCSIFFLAGS 0x100U
#define SIOCADDMULTI 0x101U
#define SIOCDELMULTI 0x102U
#define ENETRESET 1023
typedef unsigned long u_long;
typedef struct { bool held; } kmutex_t;
struct rtwn8723be_datapath;
struct ifnet {
    void *if_softc;
    unsigned int if_flags;
    int if_timer;
};
struct ieee80211com { int placeholder; };
struct rtwn8723be_softc {
    struct { struct ifnet ec_if; } sc_ec;
    struct ieee80211com sc_ic;
    struct rtwn8723be_linux_state sc_linux;
    struct rtwn8723be_datapath *sc_datapath;
    void *sc_irq_arg;
    bool sc_irq_dispatch_ready;
};
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    kmutex_t tx_lock;
    bool prepared, tx_enabled, stop_pending;
    unsigned int rx_callback_active, tx_callback_active;
};
struct rtwn8723be_net80211_methods {
    int (*hw_start)(struct rtwn8723be_softc *);
    int (*hw_stop)(struct rtwn8723be_softc *);
    void (*tx_start)(struct rtwn8723be_softc *, struct ifnet *);
};
struct rtwn8723be_net80211 {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_net80211_methods methods;
    bool registered;
};
struct req { bool up; };
static int starts, stops, locks, unlocks, inits;
static void mutex_enter(kmutex_t *l)
{ assert(l && !l->held); l->held = true; locks++; }
static void mutex_exit(kmutex_t *l)
{ assert(l && l->held); l->held = false; unlocks++; }
static int splnet(void) { return 1; }
static void splx(int saved) { assert(saved == 1); }
static int ifioctl_common(struct ifnet *ifp, u_long cmd, void *data)
{
    assert(ifp && cmd == SIOCSIFFLAGS && data);
    if (((struct req *)data)->up) ifp->if_flags |= IFF_UP;
    else ifp->if_flags &= ~IFF_UP;
    return 0;
}
static int ether_ioctl(struct ifnet *ifp, u_long cmd, void *data)
{ (void)ifp; (void)cmd; (void)data; return 0; }
static int ieee80211_ioctl(struct ieee80211com *ic, u_long cmd, void *data)
{ (void)ic; (void)cmd; (void)data; return 0; }
static int rtwn8723be_n80211_ifinit(struct ifnet *ifp)
{ (void)ifp; inits++; return EAGAIN; }
static int rtwn8723be_datapath_begin_stop(struct rtwn8723be_datapath *,
    struct rtwn8723be_linux_state *);
'''
epilogue = r'''
static int hw_stop(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_datapath *dp = sc->sc_datapath;
    stops++;
    int error = rtwn8723be_datapath_begin_stop(dp, &sc->sc_linux);
    if (error != 0) return error;
    assert(sc->sc_linux.stage == R23BE_STAGE_STOPPING);
    sc->sc_linux.started = false;
    sc->sc_linux.fw_ready = false;
    sc->sc_linux.stage = R23BE_STAGE_STOPPED;
    return 0;
}
static void reset(struct rtwn8723be_softc *sc,
    struct rtwn8723be_datapath *dp, struct rtwn8723be_net80211 *n)
{
    *sc = (struct rtwn8723be_softc){0};
    *dp = (struct rtwn8723be_datapath){0};
    *n = (struct rtwn8723be_net80211){0};
    n->sc = sc; n->registered = true; n->methods.hw_stop = hw_stop;
    dp->sc = sc; dp->prepared = dp->tx_enabled = true;
    sc->sc_datapath = dp;
    sc->sc_irq_arg = dp;
    sc->sc_irq_dispatch_ready = true;
    sc->sc_linux.started = sc->sc_linux.fw_ready = true;
    sc->sc_linux.stage = R23BE_STAGE_RUNNING;
    sc->sc_ec.ec_if.if_softc = n;
    sc->sc_ec.ec_if.if_flags = IFF_UP | IFF_RUNNING | IFF_OACTIVE;
    sc->sc_ec.ec_if.if_timer = 10;
    locks=unlocks=starts=stops=inits=0;
}
static void balanced(struct rtwn8723be_datapath *dp)
{ assert(!dp->tx_lock.held && locks == unlocks); }
int main(void)
{
    struct rtwn8723be_softc sc;
    struct rtwn8723be_datapath dp;
    struct rtwn8723be_net80211 n;
    struct ifnet *ifp;
    struct req down = {.up = false}, up = {.up = true};
    reset(&sc, &dp, &n);
    ifp = &sc.sc_ec.ec_if;
    dp.rx_callback_active = 1;

    /* 1. Actual net80211 first DOWN clears RUNNING but RX is borrowed. */
    assert(rtwn8723be_n80211_ioctl(ifp, SIOCSIFFLAGS, &down) == EBUSY);
    assert(stops == 1 && ifp->if_flags == 0 && ifp->if_timer == 0);
    assert(sc.sc_linux.stage == R23BE_STAGE_RUNNING);
    assert(dp.stop_pending && !dp.tx_enabled);
    assert(rtwn8723be_datapath_stop_retry_ready(&dp));
    balanced(&dp);

    /* 2. No completion yet: explicit repeated DOWN retries but stays safe. */
    assert(rtwn8723be_n80211_ioctl(ifp, SIOCSIFFLAGS, &down) == EBUSY);
    assert(stops == 2 && dp.stop_pending && ifp->if_flags == 0);
    balanced(&dp);

    /* 3. An attempted UP is denied while a STOP owns the device. */
    assert(rtwn8723be_n80211_ioctl(ifp, SIOCSIFFLAGS, &up) == EAGAIN);
    assert(inits == 1 && (ifp->if_flags & IFF_UP) == 0);
    assert(stops == 2 && dp.stop_pending);
    balanced(&dp);

    /* 4. RX callback finished; a new DOWN completes the real STOP. */
    dp.rx_callback_active = 0;
    assert(rtwn8723be_n80211_ioctl(ifp, SIOCSIFFLAGS, &down) == 0);
    assert(stops == 3 && !dp.stop_pending && !dp.tx_enabled);
    assert(sc.sc_linux.stage == R23BE_STAGE_STOPPED);
    assert(!sc.sc_linux.started && !sc.sc_linux.fw_ready);
    assert(!rtwn8723be_datapath_stop_retry_ready(&dp));
    balanced(&dp);

    /* 5. Further DOWN does not repeat STOP after its owner is retired. */
    assert(rtwn8723be_n80211_ioctl(ifp, SIOCSIFFLAGS, &down) == 0);
    assert(stops == 3 && inits == 1 && ifp->if_flags == 0);
    balanced(&dp);

    /* 6. A stale/foreign datapath cannot authorize retry. */
    reset(&sc, &dp, &n);
    sc.sc_ec.ec_if.if_flags = 0;
    dp.stop_pending = true; dp.tx_enabled = false;
    sc.sc_irq_arg = NULL;
    assert(!rtwn8723be_datapath_stop_retry_ready(&dp));
    assert(rtwn8723be_n80211_ioctl(&sc.sc_ec.ec_if,
        SIOCSIFFLAGS, &down) == 0);
    assert(stops == 0);
    balanced(&dp);

    /* 7. Normal first-time successful DOWN still works. */
    reset(&sc, &dp, &n);
    assert(rtwn8723be_n80211_ioctl(&sc.sc_ec.ec_if,
        SIOCSIFFLAGS, &down) == 0);
    assert(stops == 1 && sc.sc_linux.stage == R23BE_STAGE_STOPPED);
    balanced(&dp);

    puts("RTL_NET80211_DOWN_RETRY_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-net80211-down-retry-") as directory:
    source = Path(directory) / "test.c"
    exe = Path(directory) / "test"
    source.write_text(prologue + "\n" + retry + "\n" + begin_stop + "\n" +
                      ifstop + "\n" + ioctl + "\n" + epilogue)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all",
                    "-I", str(ROOT / "src"),
                    str(source), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_NET80211_DOWN_RETRY_SOURCE_NEGATIVES_OK negatives=10")
