#!/usr/bin/env python3
"""Run real net80211 unregister with every outstanding NetBSD owner.

The actual ifstop/unregister C bodies must preserve ifnet/net80211 while
IRQ, softint, datapath, RX binding or RFKill worker can still use it.
The separate probe-unwind journal is verified for the intended reverse
ordering. This is strict Linux-host C11/UBSan, not native kernel SMP proof.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/rtwn8723be_net80211.c").read_text()
UNWIND = (ROOT / "src/rtwn8723be_probe_unwind.h").read_text()
NATIVE = (ROOT / "src/rtwn8723be_native.c").read_text()

def function(name: str, result: str) -> str:
    anchor = "\n" + name + "("
    assert SOURCE.count(anchor) == 1, name
    fragment = name + "(" + SOURCE.split(anchor, 1)[1]
    depth = 0
    for i in range(fragment.index("{"), len(fragment)):
        if fragment[i] == "{":
            depth += 1
        elif fragment[i] == "}":
            depth -= 1
            if depth == 0:
                return result + "\n" + fragment[:i + 1]
    raise AssertionError(name)

stop = function("rtwn8723be_n80211_ifstop", "static int")
unregister = function("rtwn8723be_net80211_unregister", "int")

OWNERS = (
    "n->sc->sc_irq_requested", "n->sc->sc_irq_enabled",
    "n->sc->sc_ih != NULL", "n->sc->sc_soft_ih != NULL",
    "n->sc->sc_pihp != NULL", "n->sc->sc_irq_dispatch_ready",
    "n->sc->sc_irq_arg != NULL",
    "n->sc->sc_irq_dispatch.rx != NULL",
    "n->sc->sc_irq_dispatch.tx_done != NULL",
    "n->sc->sc_irq_dispatch.power_event != NULL",
    "n->sc->sc_datapath != NULL", "n->sc->sc_rx_binding != NULL",
    "n->sc->sc_rfkill_native.initialized",
    "n->sc->sc_rfkill_native.active",
    "n->sc->sc_rfkill_native.wq != NULL",
)

def contract(src: str, unwind: str, native: str) -> None:
    ordered = (
        "error = rtwn8723be_n80211_ifstop(n);",
        "if (error != 0) {",
        "return error; /* Retain registered resources on failed hardware stop. */",
        "if (n->sc->sc_irq_requested",
        "return EBUSY; /* Preserve registration and security policy. */",
        "n->sc->sc_security_policy_valid = false;",
        "ieee80211_ifdetach(&n->sc->sc_ic);",
        "if_detach(ifp);",
        "n->registered = false;",
        "n->sc = NULL;",
        "memset(&n->methods, 0, sizeof(n->methods));",
    )
    pos = [src.index(x) for x in ordered]
    assert pos == sorted(pos)
    claim = pos[3]
    busy = pos[4]
    for own in OWNERS:
        assert claim <= src.index(own, claim) < busy, own
    assert src.rfind("splx(s);", claim, busy) != -1
    assert src.index("return EBUSY;", claim) < src.index(
        "n->sc->sc_security_policy_valid = false;")
    assert "if (n == NULL)" in src
    assert "if (!n->registered)" in src
    assert "if (n->sc == NULL)" in src
    stages = (
        "ops->disestablish_irq(owner);",
        "ops->unprepare_datapath(owner);",
        "ops->unbind_rx(owner);",
        "ops->drain_rfkill(owner);",
        "ops->unregister_net80211(owner);",
    )
    indexes = [unwind.index(x) for x in stages]
    assert indexes == sorted(indexes)
    for marker in (
        ".disestablish_irq = rtwn8723be_native_unwind_irq,",
        ".unprepare_datapath = rtwn8723be_native_unwind_datapath,",
        ".unbind_rx = rtwn8723be_native_unwind_rx_binding,",
        ".drain_rfkill = rtwn8723be_native_unwind_rfkill,",
        ".unregister_net80211 = rtwn8723be_native_unwind_net80211,",
    ):
        assert marker in native

contract(unregister, UNWIND, NATIVE)
mutations = tuple(
    unregister.replace(token, "false", 1) for token in OWNERS
) + (
    unregister.replace("if (n->sc->sc_irq_requested",
                       "if (false", 1),
    unregister.replace("return EBUSY; /* Preserve registration and security policy. */",
                       "return 0;", 1),
    unregister.replace("ieee80211_ifdetach(&n->sc->sc_ic);", "", 1),
    unregister.replace("error = rtwn8723be_n80211_ifstop(n);",
                       "error = 0;", 1),
)
for i, changed in enumerate(mutations, 1):
    assert changed != unregister, i
    try:
        contract(changed, UNWIND, NATIVE)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe async owner detach mutation {i}")

prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_net80211_state.h"

#define IFF_RUNNING 0x40U
#define IFF_OACTIVE 0x400U

struct ifnet { unsigned int if_flags, if_timer; };
struct ieee80211com { unsigned int count; };
struct rtwn8723be_irq_dispatch {
    void (*rx)(void *);
    void (*tx_done)(void *, unsigned int);
    void (*power_event)(void *);
};
struct rtwn8723be_rfkill_native {
    bool initialized, active;
    void *wq;
};
struct rtwn8723be_softc {
    struct { struct ifnet ec_if; } sc_ec;
    struct ieee80211com sc_ic;
    struct rtwn8723be_linux_state sc_linux;
    void *sc_ih, *sc_soft_ih, *sc_pihp, *sc_irq_arg;
    void *sc_datapath, *sc_rx_binding;
    bool sc_irq_requested, sc_irq_enabled, sc_irq_dispatch_ready;
    struct rtwn8723be_irq_dispatch sc_irq_dispatch;
    struct rtwn8723be_rfkill_native sc_rfkill_native;
    bool sc_security_policy_valid, sc_security_configured;
    bool sc_hw_security_enabled;
};
struct rtwn8723be_net80211_methods {
    int (*hw_stop)(struct rtwn8723be_softc *);
};
struct rtwn8723be_net80211 {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_net80211_methods methods;
    bool registered;
};
static int net_detaches, if_detaches, spl_enters, spl_exits, stop_calls;
static int splnet(void)
{ spl_enters++; return 1; }
static void splx(int s)
{ assert(s == 1); spl_exits++; }
static void ieee80211_ifdetach(struct ieee80211com *ic)
{ assert(ic); net_detaches++; }
static void if_detach(struct ifnet *ifp)
{ assert(ifp); if_detaches++; }
static int hw_stop(struct rtwn8723be_softc *sc)
{
    stop_calls++;
    assert(sc && sc->sc_linux.stage == R23BE_STAGE_RUNNING);
    assert(sc->sc_linux.started);
    sc->sc_linux.stage = R23BE_STAGE_STOPPED;
    sc->sc_linux.started = false;
    sc->sc_linux.fw_ready = false;
    sc->sc_linux.mac_func_enable = false;
    sc->sc_linux.being_init_adapter = false;
    return 0;
}
static void dummy_rx(void *p) { (void)p; }
static void dummy_tx(void *p, unsigned int q) { (void)p; (void)q; }
'''
tail = r'''
static void setup(struct rtwn8723be_softc *sc,
    struct rtwn8723be_net80211 *n, bool running)
{
    *sc = (struct rtwn8723be_softc){0};
    *n = (struct rtwn8723be_net80211){0};
    n->sc = sc;
    n->registered = true;
    n->methods.hw_stop = hw_stop;
    sc->sc_security_policy_valid = sc->sc_security_configured = true;
    sc->sc_hw_security_enabled = true;
    sc->sc_linux.stage = running ? R23BE_STAGE_RUNNING : R23BE_STAGE_PROBED;
    sc->sc_linux.started = sc->sc_linux.fw_ready = running;
    sc->sc_ec.ec_if.if_flags = IFF_RUNNING | IFF_OACTIVE;
    sc->sc_ec.ec_if.if_timer = 10;
    net_detaches = if_detaches = spl_enters = spl_exits = stop_calls = 0;
}
static void retained(struct rtwn8723be_softc *sc,
    struct rtwn8723be_net80211 *n)
{
    assert(n->sc == sc && n->registered);
    assert(n->methods.hw_stop == hw_stop);
    assert(sc->sc_security_policy_valid && sc->sc_security_configured &&
           sc->sc_hw_security_enabled);
    assert(net_detaches == 0 && if_detaches == 0);
    assert(spl_enters == spl_exits);
}
static void detached(struct rtwn8723be_softc *sc,
    struct rtwn8723be_net80211 *n)
{
    assert(!n->registered && n->sc == NULL && n->methods.hw_stop == NULL);
    assert(!sc->sc_security_policy_valid && !sc->sc_security_configured &&
           !sc->sc_hw_security_enabled);
    assert(net_detaches == 1 && if_detaches == 1);
    assert(spl_enters == spl_exits);
}
static void set_owner(struct rtwn8723be_softc *sc, int mode)
{
    switch (mode) {
    case 1: sc->sc_irq_requested = true; break;
    case 2: sc->sc_irq_enabled = true; break;
    case 3: sc->sc_ih = sc; break;
    case 4: sc->sc_soft_ih = sc; break;
    case 5: sc->sc_pihp = sc; break;
    case 6: sc->sc_irq_dispatch_ready = true; break;
    case 7: sc->sc_irq_arg = sc; break;
    case 8: sc->sc_irq_dispatch.rx = dummy_rx; break;
    case 9: sc->sc_irq_dispatch.tx_done = dummy_tx; break;
    case 10: sc->sc_irq_dispatch.power_event = dummy_rx; break;
    case 11: sc->sc_datapath = sc; break;
    case 12: sc->sc_rx_binding = sc; break;
    case 13: sc->sc_rfkill_native.initialized = true; break;
    case 14: sc->sc_rfkill_native.active = true; break;
    case 15: sc->sc_rfkill_native.wq = sc; break;
    default: assert(false);
    }
}
int main(void)
{
    struct rtwn8723be_softc sc;
    struct rtwn8723be_net80211 n;

    /* Each asynchronous owner independently forbids net80211 detach. */
    for (int mode = 1; mode <= 15; mode++) {
        setup(&sc, &n, false);
        set_owner(&sc, mode);
        assert(rtwn8723be_net80211_unregister(&n) == EBUSY);
        retained(&sc, &n);
        assert(stop_calls == 0);
        /* Clearing the owner after a real external drain admits detach. */
        setup(&sc, &n, false);
        assert(rtwn8723be_net80211_unregister(&n) == 0);
        detached(&sc, &n);
        assert(stop_calls == 0);
    }

    /* A successfully stopped MAC still needs *separate* IRQ/worker drain. */
    setup(&sc, &n, true);
    sc.sc_irq_dispatch.rx = dummy_rx;
    sc.sc_rfkill_native.active = true;
    assert(rtwn8723be_net80211_unregister(&n) == EBUSY);
    assert(stop_calls == 1);
    assert(sc.sc_linux.stage == R23BE_STAGE_STOPPED);
    retained(&sc, &n);
    sc.sc_irq_dispatch.rx = NULL;
    sc.sc_rfkill_native.active = false;
    assert(rtwn8723be_net80211_unregister(&n) == 0);
    detached(&sc, &n);
    assert(stop_calls == 1);

    assert(rtwn8723be_net80211_unregister(&n) == 0);
    assert(net_detaches == 1 && if_detaches == 1);
    puts("RTL_NET80211_OWNER_QUIESCENCE_UNREGISTER_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-net80211-owner-drain-") as td:
    source = Path(td) / "check.c"
    exe = Path(td) / "check"
    source.write_text(prefix + "\n" + stop + "\n" + unregister + "\n" + tail)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(ROOT / "src"), str(source), "-o", str(exe)
    ], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_NET80211_OWNER_QUIESCENCE_SOURCE_MUTATIONS_OK negatives=19")
