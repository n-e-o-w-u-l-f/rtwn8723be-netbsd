#!/usr/bin/env python3
"""Execute production net80211 ifstop with native Linux-stage admission.

This protects the error path where ifnet traffic must be blocked BEFORE
hardware stop, while failed hardware stop retains the actual device state
for explicit recovery. Portable C11 does not prove NetBSD stop/IRQ drain.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/rtwn8723be_net80211.c").read_text()
marker = "\nrtwn8723be_n80211_ifstop(struct rtwn8723be_net80211 *n)\n{"
assert SOURCE.count(marker) == 1
fragment = SOURCE.split(marker, 1)[1]
stop = "static int\nrtwn8723be_n80211_ifstop(struct rtwn8723be_net80211 *n)\n{" + (
    fragment.split("\n}\n", 1)[0] + "\n}")

def contract(text: str) -> None:
    entry = "if (n == NULL || !n->registered || n->sc == NULL)"
    assert entry in text
    assert text.index(entry) < text.index("ifp = &n->sc->sc_ec.ec_if;")
    blocked = "ifp->if_flags &= ~(IFF_RUNNING | IFF_OACTIVE);"
    assert blocked in text
    assert text.index(blocked) < text.index("if (!n->sc->sc_linux.started)")
    assert "rtwn8723be_net80211_unstarted_detach_allowed(" in text
    assert "n->sc->sc_linux.stage != R23BE_STAGE_RUNNING" in text
    assert "n->methods.hw_stop == NULL" in text
    assert "return n->methods.hw_stop(n->sc);" in text
    assert text.index("n->sc->sc_linux.stage != R23BE_STAGE_RUNNING") < (
        text.index("return n->methods.hw_stop(n->sc);"))

contract(stop)
mutated = (
    stop.replace(" || n->sc == NULL", "", 1),
    stop.replace("ifp->if_flags &= ~(IFF_RUNNING | IFF_OACTIVE);",
                 "/* TX still admitted */", 1),
    stop.replace("rtwn8723be_net80211_unstarted_detach_allowed(",
                 "some_unsafe_bypass(", 1),
    stop.replace("n->sc->sc_linux.stage != R23BE_STAGE_RUNNING",
                 "false", 1),
    stop.replace("return n->methods.hw_stop(n->sc);", "return 0;", 1),
)
for i, candidate in enumerate(mutated, 1):
    assert candidate != stop, i
    try:
        contract(candidate)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe net80211 stop mutation {i} accepted")

prologue = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stddef.h>
#include "rtwn8723be_net80211_state.h"

#define IFF_RUNNING 0x40U
#define IFF_OACTIVE 0x400U
struct ifnet { unsigned int if_flags, if_timer; };
struct rtwn8723be_softc {
    struct { struct ifnet ec_if; } sc_ec;
    struct rtwn8723be_linux_state sc_linux;
};
struct rtwn8723be_net80211_methods {
    int (*hw_stop)(struct rtwn8723be_softc *);
};
struct rtwn8723be_net80211 {
    bool registered;
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_net80211_methods methods;
};
static unsigned int stops;
static int stop_error;
static int stop_hw(struct rtwn8723be_softc *sc)
{
    stops++;
    assert(sc->sc_linux.started &&
        sc->sc_linux.stage == R23BE_STAGE_RUNNING);
    if (stop_error != 0)
        return stop_error;
    sc->sc_linux.started = false;
    sc->sc_linux.stage = R23BE_STAGE_STOPPED;
    sc->sc_linux.fw_ready = false;
    return 0;
}
'''
epilogue = r'''
static void reset(struct rtwn8723be_softc *sc,
    struct rtwn8723be_net80211 *n)
{
    *sc = (struct rtwn8723be_softc){0};
    *n = (struct rtwn8723be_net80211){0};
    sc->sc_ec.ec_if.if_flags = IFF_RUNNING | IFF_OACTIVE;
    sc->sc_ec.ec_if.if_timer = 7;
    sc->sc_linux.started = true;
    sc->sc_linux.stage = R23BE_STAGE_RUNNING;
    n->registered = true;
    n->sc = sc;
    n->methods.hw_stop = stop_hw;
    stops = 0;
    stop_error = 0;
}
int main(void)
{
    struct rtwn8723be_softc sc;
    struct rtwn8723be_net80211 n;

    reset(&sc,&n);
    assert(rtwn8723be_n80211_ifstop(NULL) == ENXIO);
    n.registered = false;
    assert(rtwn8723be_n80211_ifstop(&n) == ENXIO);
    assert(sc.sc_ec.ec_if.if_flags == (IFF_RUNNING | IFF_OACTIVE));
    n.registered = true;
    n.sc = NULL;
    assert(rtwn8723be_n80211_ifstop(&n) == ENXIO);
    assert(sc.sc_ec.ec_if.if_flags == (IFF_RUNNING | IFF_OACTIVE));

    reset(&sc,&n);
    stop_error = EIO;
    assert(rtwn8723be_n80211_ifstop(&n) == EIO);
    assert(stops == 1 && sc.sc_linux.started &&
        sc.sc_linux.stage == R23BE_STAGE_RUNNING);
    assert((sc.sc_ec.ec_if.if_flags & (IFF_RUNNING | IFF_OACTIVE)) == 0);
    assert(sc.sc_ec.ec_if.if_timer == 0);
    stop_error = 0;
    assert(rtwn8723be_n80211_ifstop(&n) == 0 && stops == 2);
    assert(!sc.sc_linux.started &&
        sc.sc_linux.stage == R23BE_STAGE_STOPPED);

    reset(&sc,&n);
    sc.sc_linux.stage = R23BE_STAGE_STOPPING;
    assert(rtwn8723be_n80211_ifstop(&n) == EBUSY &&
        stops == 0 && sc.sc_linux.started);
    assert((sc.sc_ec.ec_if.if_flags & IFF_RUNNING) == 0);

    reset(&sc,&n);
    n.methods.hw_stop = NULL;
    assert(rtwn8723be_n80211_ifstop(&n) == ENOSYS &&
        stops == 0 && (sc.sc_ec.ec_if.if_flags & IFF_RUNNING) == 0);

    reset(&sc,&n);
    sc.sc_linux.started = false;
    sc.sc_linux.stage = R23BE_STAGE_PROBED;
    assert(rtwn8723be_n80211_ifstop(&n) == 0 && stops == 0);
    assert((sc.sc_ec.ec_if.if_flags & IFF_RUNNING) == 0);

    reset(&sc,&n);
    sc.sc_linux.started = false;
    sc.sc_linux.stage = R23BE_STAGE_FIRMWARE_DOWNLOAD;
    assert(rtwn8723be_n80211_ifstop(&n) == EBUSY &&
        stops == 0);
    puts("RTL_NET80211_STOP_FAILURE_OWNER_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtl-n80211-stop-owner-") as directory:
    source = Path(directory) / "test.c"
    binary = Path(directory) / "test"
    source.write_text(prologue + stop + "\n" + epilogue)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(ROOT / "src"), str(source), "-o", str(binary)
    ], check=True)
    subprocess.run([str(binary)], check=True)
print("RTL_NET80211_STOP_FAILURE_SOURCE_OK negatives=5")
