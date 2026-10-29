#!/usr/bin/env python3
"""Compile and run actual NetBSD net80211 RX/ifstart production callbacks.

The harness controls the m_devget-to-splnet stop window and tracks whether
a stale frame is passed into ieee80211_input. It does NOT simulate NetBSD
kernel memory lifetime or replace native softint/PCI detach testing.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/rtwn8723be_net80211.c").read_text()
DP = (ROOT / "src/rtwn8723be_datapath.c").read_text()
DHP = (ROOT / "src/rtwn8723be_datapath.h").read_text()

def extract(name: str, declaration: str, source: str = SOURCE) -> str:
    marker = "\n" + name + "("
    assert source.count(marker) == 1, name
    fragment = name + "(" + source.split(marker, 1)[1]
    start = fragment.index("{")
    depth = 0
    for i in range(start, len(fragment)):
        if fragment[i] == "{":
            depth += 1
        elif fragment[i] == "}":
            depth -= 1
            if depth == 0:
                return declaration + "\n" + fragment[:i + 1]
    raise AssertionError(f"unclosed {name}")

rx = extract("rtwn8723be_net80211_input", "int")
tx = extract("rtwn8723be_n80211_ifstart", "static void")
ready = extract("rtwn8723be_datapath_running_ready", "bool", DP)
begin = extract("rtwn8723be_datapath_tx_start_begin", "bool", DP)
end = extract("rtwn8723be_datapath_tx_start_end", "void", DP)

def verify(rx_source: str, tx_source: str, ready_source: str) -> None:
    copied = rx_source.index("m = m_devget(")
    locked = rx_source.index("s = splnet();")
    gate = rx_source.index("if (!n->registered || n->sc == NULL ||", locked)
    deliver = rx_source.index("ieee80211_find_rxnode(")
    assert copied < locked < gate < deliver
    assert "(n->sc->sc_ec.ec_if.if_flags & IFF_RUNNING) == 0" in rx_source[:copied]
    readiness = "rtwn8723be_datapath_running_ready(n->sc->sc_datapath)"
    assert rx_source.count(readiness) == 2
    assert rx_source.index(readiness) < copied
    assert locked < rx_source.rindex(readiness) < deliver
    assert "m_freem(m);" in rx_source[rx_source.rindex(readiness):deliver]
    assert "(n->sc->sc_ec.ec_if.if_flags & IFF_RUNNING) == 0" in rx_source[gate:deliver]
    assert "!n->sc->sc_linux.started" in rx_source[gate:deliver]
    assert "n->sc->sc_linux.stage != R23BE_STAGE_RUNNING" in rx_source[gate:deliver]
    assert "m_freem(m);" in rx_source[gate:deliver]
    assert "return ENETDOWN;" in rx_source[gate:deliver]
    assert "splx(s);" in rx_source[gate:deliver]
    for token in (
        "n->sc == NULL",
        "!n->sc->sc_linux.started",
        "n->sc->sc_linux.stage != R23BE_STAGE_RUNNING",
        "(ifp->if_flags & (IFF_RUNNING | IFF_OACTIVE)) != IFF_RUNNING",
        "n->methods.tx_start == NULL",
    ):
        assert token in tx_source, token
    assert tx_source.index("n->sc->sc_linux.stage != R23BE_STAGE_RUNNING") < (
        tx_source.index("n->methods.tx_start(n->sc, ifp);"))
    acquire = "rtwn8723be_datapath_tx_start_begin(dp)"
    release = "rtwn8723be_datapath_tx_start_end(dp);"
    callback = "n->methods.tx_start(n->sc, ifp);"
    assert acquire in tx_source and release in tx_source
    assert tx_source.index(acquire) < tx_source.index(callback) < tx_source.index(release)
    assert "bool rtwn8723be_datapath_running_ready(" in DHP
    lock = ready_source.index("mutex_enter(&dp->tx_lock);")
    unlock = ready_source.index("mutex_exit(&dp->tx_lock);")
    for token in (
        "dp->tx_enabled", "!dp->stop_pending",
        "sc->sc_datapath == dp", "sc->sc_irq_arg == dp",
        "sc->sc_irq_dispatch_ready", "sc->sc_ih != NULL",
        "sc->sc_mapped", "sc->sc_rings_allocated",
        "sc->sc_linux.started", "sc->sc_linux.fw_ready",
        "sc->sc_linux.stage == R23BE_STAGE_RUNNING",
    ):
        assert lock < ready_source.index(token) < unlock

verify(rx, tx, ready)

unsafe = (
    (rx.replace("if (!n->registered || n->sc == NULL ||",
                "if (false ||", 1), tx),
    (rx.replace("(n->sc->sc_ec.ec_if.if_flags & IFF_RUNNING) == 0 ||",
                "false ||", 1), tx),
    (rx.replace("        m_freem(m);\n        return ENETDOWN;",
                "        return ENETDOWN;", 1), tx),
    (rx.replace("        !n->sc->sc_linux.started ||\n", "", 1), tx),
    (rx.replace("        n->sc->sc_linux.stage != R23BE_STAGE_RUNNING ||",
                "        false ||", 1), tx),
    (rx, tx.replace("!n->sc->sc_linux.started ||", "", 1)),
    (rx, tx.replace("n->sc->sc_linux.stage != R23BE_STAGE_RUNNING ||",
                    "", 1)),
    (rx, tx.replace("n->sc == NULL ||", "", 1)),
    (rx.replace("rtwn8723be_datapath_running_ready(n->sc->sc_datapath)", "true", 1), tx),
    (rx.replace("rtwn8723be_datapath_running_ready(n->sc->sc_datapath)", "true", 2), tx),
    (rx, tx.replace("rtwn8723be_datapath_tx_start_begin(dp)", "true", 1)),
)
for i, (mutated_rx, mutated_tx) in enumerate(unsafe, 1):
    assert mutated_rx != rx or mutated_tx != tx, i
    try:
        verify(mutated_rx, mutated_tx, ready)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe late RX/TX mutation {i} accepted")

prologue = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#include <string.h>

#define RTWN8723BE_RX_BUFFER_SIZE 4096
#define IFF_RUNNING 0x40U
#define IFF_OACTIVE 0x400U
#define R23BE_STAGE_RUNNING 43

typedef struct { bool locked; } kmutex_t;
struct rtwn8723be_softc;
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    kmutex_t tx_lock;
    bool prepared, tx_enabled, stop_pending;
    unsigned int tx_start_active;
};
struct ifnet { void *if_softc; unsigned int if_flags; };
struct ieee80211_frame_min { uint8_t octets[24]; };
struct ieee80211_node { int key; };
struct ieee80211com { unsigned int input_count; };
struct mbuf { uint8_t data[4096]; int length; };
struct rtwn8723be_softc {
    struct { struct ifnet ec_if; } sc_ec;
    struct ieee80211com sc_ic;
    struct { bool started, fw_ready; int stage; } sc_linux;
    struct rtwn8723be_datapath bridge;
    struct rtwn8723be_datapath *sc_datapath;
    void *sc_irq_arg, *sc_ih;
    bool sc_irq_dispatch_ready, sc_mapped, sc_rings_allocated;
};
struct rtwn8723be_net80211_methods {
    void (*tx_start)(struct rtwn8723be_softc *, struct ifnet *);
};
struct rtwn8723be_net80211 {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_net80211_methods methods;
    bool registered;
};
#define mtod(m, T) ((T)(void *)(m)->data)

static struct rtwn8723be_net80211 *global_net;
static struct ieee80211_node node = { .key = 4 };
static struct mbuf backing;
static int stopped_during_copy, allocation_failure, missing_node;
static unsigned int allocations, frees, deliveries, node_lookups, tx_calls;
static unsigned int locks, unlocks, dp_locks, dp_unlocks;
static int held;
static void mutex_enter(kmutex_t *m)
{ assert(m && !m->locked); m->locked = true; dp_locks++; }
static void mutex_exit(kmutex_t *m)
{ assert(m && m->locked); m->locked = false; dp_unlocks++; }

static int splnet(void) { assert(!held); held=1; locks++; return 5; }
static void splx(int s) { assert(s==5 && held); held=0; unlocks++; }
static struct mbuf *m_devget(char *data, int length, int ignored,
    struct ifnet *ifp)
{
    (void)ignored;
    assert(ifp && data && length > 0 && length <= 4096);
    allocations++;
    if (allocation_failure)
        return NULL;
    memset(&backing, 0, sizeof(backing));
    memcpy(backing.data, data, (size_t)length);
    backing.length = length;
    if (stopped_during_copy == 1)
        ifp->if_flags &= ~IFF_RUNNING;
    if (stopped_during_copy == 2)
        global_net->registered = false;
    if (stopped_during_copy == 3)
        global_net->sc = NULL;
    if (stopped_during_copy == 4)
        global_net->sc->sc_linux.started = false;
    if (stopped_during_copy == 5)
        global_net->sc->sc_linux.stage = 99;
    if (stopped_during_copy == 6)
        global_net->sc->bridge.stop_pending = true;
    if (stopped_during_copy == 7)
        global_net->sc->bridge.tx_enabled = false;
    if (stopped_during_copy == 8)
        global_net->sc->sc_irq_arg = NULL;
    if (stopped_during_copy == 9)
        global_net->sc->sc_linux.fw_ready = false;
    if (stopped_during_copy == 10)
        global_net->sc->sc_datapath = NULL;
    return &backing;
}
static void m_freem(struct mbuf *m) { assert(m == &backing); frees++; }
static struct ieee80211_node *
ieee80211_find_rxnode(struct ieee80211com *ic,
    struct ieee80211_frame_min *frm)
{
    assert(held && ic && frm);
    node_lookups++;
    return missing_node ? NULL : &node;
}
static void ieee80211_input(struct ieee80211com *ic,
    struct mbuf *m, struct ieee80211_node *ni, int rssi, int noise)
{
    assert(held && ic && ni == &node && m == &backing);
    assert(rssi == -64 && noise == 0);
    ic->input_count++;
    deliveries++;
    m_freem(m); /* ieee80211_input owns consumed mbuf */
}
static void ieee80211_free_node(struct ieee80211_node *ni)
{ assert(held && ni == &node); }
static void tx_submit(struct rtwn8723be_softc *sc, struct ifnet *ifp)
{ assert(sc && ifp && held == 0); tx_calls++; }
'''
epilogue = r'''
static void reset(struct rtwn8723be_softc *sc,
    struct rtwn8723be_net80211 *n)
{
    *sc = (struct rtwn8723be_softc){0};
    *n = (struct rtwn8723be_net80211){0};
    sc->sc_ec.ec_if.if_flags = IFF_RUNNING;
    sc->sc_ec.ec_if.if_softc = n;
    sc->sc_linux.started = true;
    sc->sc_linux.fw_ready = true;
    sc->sc_linux.stage = R23BE_STAGE_RUNNING;
    sc->bridge.sc = sc;
    sc->bridge.prepared = sc->bridge.tx_enabled = true;
    sc->sc_datapath = &sc->bridge;
    sc->sc_irq_arg = &sc->bridge;
    sc->sc_ih = sc;
    sc->sc_irq_dispatch_ready = sc->sc_mapped =
        sc->sc_rings_allocated = true;
    n->sc = sc;
    n->registered = true;
    n->methods.tx_start = tx_submit;
    global_net = n;
    stopped_during_copy = allocation_failure = missing_node = 0;
}
int main(void)
{
    struct rtwn8723be_softc sc = {0};
    struct rtwn8723be_net80211 n = {0};
    uint8_t bytes[32] = {0};

    reset(&sc,&n);
    assert(rtwn8723be_net80211_input(&n,bytes,sizeof(bytes),-64) == 0);
    assert(deliveries == 1 && frees == 1 && node_lookups == 1);
    assert(locks == unlocks && !held);
    rtwn8723be_n80211_ifstart(&sc.sc_ec.ec_if);
    assert(tx_calls == 1);

    for (int mode = 1; mode <= 10; mode++) {
        reset(&sc,&n);
        stopped_during_copy = mode;
        unsigned int olddel = deliveries, oldlook = node_lookups;
        assert(rtwn8723be_net80211_input(&n,bytes,sizeof(bytes),-64)
            == ENETDOWN);
        assert(deliveries == olddel && node_lookups == oldlook);
        assert(locks == unlocks && !held);
    }

    reset(&sc,&n);
    sc.sc_ec.ec_if.if_flags &= ~IFF_RUNNING;
    assert(rtwn8723be_net80211_input(&n,bytes,sizeof(bytes),-64)
        == ENETDOWN);

    /* An invalid native RUNNING bridge refuses RX before allocating an
     * mbuf, even with stale IFF_RUNNING and Linux RUNNING flags.
     */
    for (int mode = 1; mode <= 5; mode++) {
        reset(&sc, &n);
        if (mode == 1) sc.bridge.stop_pending = true;
        if (mode == 2) sc.bridge.tx_enabled = false;
        if (mode == 3) sc.sc_irq_arg = NULL;
        if (mode == 4) sc.sc_linux.fw_ready = false;
        if (mode == 5) sc.sc_datapath = NULL;
        unsigned int before_allocs = allocations;
        unsigned int before_lookups = node_lookups;
        assert(rtwn8723be_net80211_input(&n,bytes,sizeof(bytes),-64)
            == ENETDOWN);
        assert(allocations == before_allocs &&
            node_lookups == before_lookups);
        assert(!sc.bridge.tx_lock.locked && dp_locks == dp_unlocks);
    }

    reset(&sc,&n);
    missing_node = 1;
    unsigned int before = frees;
    assert(rtwn8723be_net80211_input(&n,bytes,sizeof(bytes),-64)
        == ENOENT && frees == before + 1);

    reset(&sc,&n);
    allocation_failure = 1;
    assert(rtwn8723be_net80211_input(&n,bytes,sizeof(bytes),-64)
        == ENOBUFS);

    reset(&sc,&n);
    assert(rtwn8723be_net80211_input(&n,NULL,sizeof(bytes),-64)
        == EINVAL);
    assert(rtwn8723be_net80211_input(&n,bytes,3,-64) == EINVAL);
    assert(rtwn8723be_net80211_input(&n,bytes,sizeof(bytes),-128)
        == EINVAL);

    reset(&sc,&n);
    sc.sc_linux.started = false;
    rtwn8723be_n80211_ifstart(&sc.sc_ec.ec_if);
    assert(tx_calls == 1);
    sc.sc_linux.started = true;
    sc.sc_linux.stage = 99;
    rtwn8723be_n80211_ifstart(&sc.sc_ec.ec_if);
    assert(tx_calls == 1);
    sc.sc_linux.stage = R23BE_STAGE_RUNNING;
    sc.sc_ec.ec_if.if_flags |= IFF_OACTIVE;
    rtwn8723be_n80211_ifstart(&sc.sc_ec.ec_if);
    assert(tx_calls == 1);
    sc.sc_ec.ec_if.if_flags &= ~IFF_OACTIVE;
    n.registered = false;
    rtwn8723be_n80211_ifstart(&sc.sc_ec.ec_if);
    assert(tx_calls == 1);
    n.registered = true;
    n.sc = NULL;
    rtwn8723be_n80211_ifstart(&sc.sc_ec.ec_if);
    assert(tx_calls == 1);

    /* Stale RUNNING flags alone never authorize net80211 dequeue. */
    reset(&sc,&n);
    sc.bridge.stop_pending = true;
    rtwn8723be_n80211_ifstart(&sc.sc_ec.ec_if);
    assert(tx_calls == 1);
    sc.bridge.stop_pending = false;
    sc.bridge.tx_enabled = false;
    rtwn8723be_n80211_ifstart(&sc.sc_ec.ec_if);
    assert(tx_calls == 1);
    sc.bridge.tx_enabled = true;
    sc.sc_irq_arg = NULL;
    rtwn8723be_n80211_ifstart(&sc.sc_ec.ec_if);
    assert(tx_calls == 1);
    sc.sc_irq_arg = &sc.bridge;
    sc.sc_linux.fw_ready = false;
    rtwn8723be_n80211_ifstart(&sc.sc_ec.ec_if);
    assert(tx_calls == 1);
    assert(locks == unlocks && !held);
    assert(dp_locks == dp_unlocks && !sc.bridge.tx_lock.locked);
    assert(sc.bridge.tx_start_active == 0);
    puts("RTL_NET80211_LATE_RX_STOP_TX_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtl-n80211-late-rx-") as path:
    src = Path(path) / "check.c"
    out = Path(path) / "check"
    src.write_text(prologue + ready + "\n" + begin + "\n" + end + "\n" + rx + "\n" + tx + "\n" + epilogue)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        str(src), "-o", str(out),
    ], check=True)
    subprocess.run([str(out)], check=True)
print("RTL_NET80211_LATE_RX_SOURCE_MUTATIONS_OK negatives=11")
