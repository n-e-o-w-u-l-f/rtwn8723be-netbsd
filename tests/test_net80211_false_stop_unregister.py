#!/usr/bin/env python3
"""Real net80211 unregister must retain registered owner after false-success STOP.

C11/UBSan extracts actual ifstop/unregister production C bodies. Stubs
model if_detach/ieee80211_ifdetach as destructive operations and assert that
no such operation occurs when HW stop falsely returns zero without STOPPED
postconditions, or reports EBUSY. This is NOT a native NetBSD kernel link.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "src/rtwn8723be_net80211.c").read_text()

def body(name: str, ret: str) -> str:
    marker = "\n" + name + "("
    assert SRC.count(marker) == 1, name
    frag = name + "(" + SRC.split(marker, 1)[1]
    start, depth = frag.index("{"), 0
    for j in range(start, len(frag)):
        if frag[j] == "{":
            depth += 1
        elif frag[j] == "}":
            depth -= 1
            if depth == 0:
                return ret + "\n" + frag[:j + 1]
    raise AssertionError(name)

stop = body("rtwn8723be_n80211_ifstop", "static int")
unregister = body("rtwn8723be_net80211_unregister", "int")

def contract(s: str, u: str):
    call = "error = n->methods.hw_stop(n->sc);"
    post = "if (n->sc->sc_linux.stage != R23BE_STAGE_STOPPED ||"
    assert s.index(call) < s.index("if (error != 0)") < s.index(post)
    for guard in (
        "n->sc->sc_linux.started",
        "n->sc->sc_linux.fw_ready",
        "n->sc->sc_linux.mac_func_enable",
        "n->sc->sc_linux.being_init_adapter",
    ):
        assert s.index(post) < s.index(guard, s.index(post)) < s.index("return EIO;", s.index(post))
    ordered = (
        "error = rtwn8723be_n80211_ifstop(n);",
        "if (error != 0) {",
        "splx(s);",
        "return error;",
        "n->sc->sc_security_policy_valid = false;",
        "ieee80211_ifdetach(&n->sc->sc_ic);",
        "if_detach(ifp);",
        "n->registered = false;",
        "n->sc = NULL;",
        "memset(&n->methods, 0, sizeof(n->methods));",
    )
    positions = [u.index(x) for x in ordered]
    assert positions == sorted(positions)
    assert "if (!n->registered)" in u
    assert "if (n->sc == NULL)" in u

contract(stop, unregister)
negative = (
    (stop.replace("n->sc->sc_linux.stage != R23BE_STAGE_STOPPED",
                  "false", 1), unregister),
    (stop.replace("n->sc->sc_linux.started ||", "false ||", 1), unregister),
    (stop.replace("n->sc->sc_linux.fw_ready", "false", 1), unregister),
    (stop.replace("n->sc->sc_linux.mac_func_enable", "false", 1), unregister),
    (stop.replace("n->sc->sc_linux.being_init_adapter", "false", 1), unregister),
    (stop, unregister.replace(
        "error = rtwn8723be_n80211_ifstop(n);", "error = 0;", 1)),
    (stop, unregister.replace("if (error != 0) {", "if (false) {", 1)),
    (stop, unregister.replace(
        "ieee80211_ifdetach(&n->sc->sc_ic);", "", 1)),
    (stop, unregister.replace("if_detach(ifp);", "", 1)),
    (stop, unregister.replace("n->registered = false;", "", 1)),
)
for i, changed in enumerate(negative, 1):
    assert changed != (stop, unregister), i
    try:
        contract(*changed)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe net80211 unregister mutation {i}")

head = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_net80211_state.h"

#define IFF_RUNNING 0x40U
#define IFF_OACTIVE 0x400U

struct ifnet { unsigned int if_flags, if_timer; };
struct ieee80211com { unsigned int marker; };
struct rtwn8723be_softc {
    struct { struct ifnet ec_if; } sc_ec;
    struct ieee80211com sc_ic;
    struct rtwn8723be_linux_state sc_linux;
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
static int stop_calls, stop_mode, net80211_detaches, if_detaches, spl_enters, spl_exits;
static int splnet(void)
{ spl_enters++; return 1; }
static void splx(int level)
{ assert(level == 1); spl_exits++; }
static void ieee80211_ifdetach(struct ieee80211com *ic)
{ assert(ic != NULL); net80211_detaches++; }
static void if_detach(struct ifnet *ifp)
{ assert(ifp != NULL); if_detaches++; }
static int hw_stop(struct rtwn8723be_softc *sc)
{
    stop_calls++;
    assert(sc->sc_linux.started &&
           sc->sc_linux.stage == R23BE_STAGE_RUNNING);
    if (stop_mode == 1)
        return 0; /* false success: still RUNNING */
    if (stop_mode == 2)
        return EBUSY;
    if (stop_mode == 3) {
        sc->sc_linux.stage = R23BE_STAGE_STOPPED;
        sc->sc_linux.started = false;
        return 0; /* false success: firmware owned */
    }
    sc->sc_linux.stage = R23BE_STAGE_STOPPED;
    sc->sc_linux.started = false;
    sc->sc_linux.fw_ready = false;
    sc->sc_linux.mac_func_enable = false;
    sc->sc_linux.being_init_adapter = false;
    return 0;
}
'''
tail = r'''
static void reset(struct rtwn8723be_softc *sc,
    struct rtwn8723be_net80211 *n, int mode)
{
    *sc = (struct rtwn8723be_softc){0};
    *n = (struct rtwn8723be_net80211){0};
    sc->sc_linux.started = true;
    sc->sc_linux.fw_ready = true;
    sc->sc_linux.stage = R23BE_STAGE_RUNNING;
    sc->sc_linux.mac_func_enable = true;
    sc->sc_security_policy_valid = true;
    sc->sc_security_configured = true;
    sc->sc_hw_security_enabled = true;
    sc->sc_ec.ec_if.if_flags = IFF_RUNNING | IFF_OACTIVE;
    sc->sc_ec.ec_if.if_timer = 9;
    n->registered = true;
    n->sc = sc;
    n->methods.hw_stop = hw_stop;
    stop_calls = net80211_detaches = if_detaches = spl_enters = spl_exits = 0;
    stop_mode = mode;
}
int main(void)
{
    struct rtwn8723be_softc sc = {0};
    struct rtwn8723be_net80211 n = {0};

    assert(rtwn8723be_net80211_unregister(NULL) == EINVAL);
    assert(rtwn8723be_net80211_unregister(&n) == 0);

    for (int mode = 1; mode <= 3; mode++) {
        reset(&sc, &n, mode);
        int expected = mode == 2 ? EBUSY : EIO;
        assert(rtwn8723be_net80211_unregister(&n) == expected);
        assert(stop_calls == 1);
        assert(net80211_detaches == 0 && if_detaches == 0);
        assert(n.registered && n.sc == &sc && n.methods.hw_stop == hw_stop);
        assert(sc.sc_security_policy_valid && sc.sc_security_configured);
        assert(sc.sc_hw_security_enabled);
        assert((sc.sc_ec.ec_if.if_flags & IFF_RUNNING) == 0);
        assert(spl_enters == 1 && spl_exits == 1);
    }

    reset(&sc, &n, 0);
    assert(rtwn8723be_net80211_unregister(&n) == 0);
    assert(stop_calls == 1 && net80211_detaches == 1 && if_detaches == 1);
    assert(!n.registered && n.sc == NULL && n.methods.hw_stop == NULL);
    assert(!sc.sc_security_policy_valid && !sc.sc_security_configured);
    assert(!sc.sc_hw_security_enabled);
    assert(spl_enters == 1 && spl_exits == 1);
    assert(rtwn8723be_net80211_unregister(&n) == 0);
    assert(net80211_detaches == 1 && if_detaches == 1);
    puts("RTL_NET80211_FALSE_STOP_UNREGISTER_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-n80211-unregister-") as td:
    source = Path(td) / "check.c"
    binary = Path(td) / "check"
    source.write_text(head + "\n" + stop + "\n" + unregister + "\n" + tail)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(ROOT / "src"), str(source), "-o", str(binary)
    ], check=True)
    subprocess.run([str(binary)], check=True)
print("RTL_NET80211_UNREGISTER_SOURCE_NEGATIVES_OK negatives=10")
