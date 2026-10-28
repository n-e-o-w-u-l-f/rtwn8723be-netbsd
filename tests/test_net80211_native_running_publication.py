#!/usr/bin/env python3
"""Execute native RUNNING owner gate + net80211 ifinit under C11/UBSan.

Extracts actual production C bodies. The mocked RFKill second sample can
revoke a datapath owner, close TX or latch STOP after the first post-start
check, before IFF_RUNNING publication. This is a Linux-host state test,
NOT a NetBSD interrupt/mutex implementation or an HP WLAN test.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DP = (ROOT / "src/rtwn8723be_datapath.c").read_text()
NET = (ROOT / "src/rtwn8723be_net80211.c").read_text()
H = (ROOT / "src/rtwn8723be_datapath.h").read_text()

def body(src: str, name: str, result: str) -> str:
    marker = "\n" + name + "("
    assert src.count(marker) == 1, name
    tail = name + "(" + src.split(marker, 1)[1]
    depth = 0
    for pos in range(tail.index("{"), len(tail)):
        if tail[pos] == "{":
            depth += 1
        elif tail[pos] == "}":
            depth -= 1
            if depth == 0:
                return result + "\n" + tail[:pos + 1]
    raise AssertionError(name)

ready = body(DP, "rtwn8723be_datapath_running_ready", "bool")
init = body(NET, "rtwn8723be_n80211_ifinit", "static int")

def contract(native: str, net: str, header: str) -> None:
    assert "bool rtwn8723be_datapath_running_ready(" in header
    enter = native.index("mutex_enter(&dp->tx_lock);")
    exit = native.index("mutex_exit(&dp->tx_lock);")
    for token in (
        "dp->tx_enabled", "!dp->stop_pending", "sc->sc_datapath == dp",
        "sc->sc_irq_arg == dp", "sc->sc_irq_dispatch_ready",
        "sc->sc_ih != NULL", "sc->sc_mapped", "sc->sc_rings_allocated",
        "sc->sc_linux.started", "sc->sc_linux.fw_ready",
        "sc->sc_linux.stage == R23BE_STAGE_RUNNING",
    ):
        assert enter < native.index(token) < exit, token
    assert "if (dp == NULL || !dp->prepared || dp->sc == NULL)" in native
    assert "return ready;" in native
    hw_start = net.index("error = n->methods.hw_start(sc);")
    first_check = net.index("rtwn8723be_datapath_running_ready(sc->sc_datapath)")
    rf_second = net.index("error = rtwn8723be_rfkill_native_radio_on(sc, &radio_on);", hw_start)
    rollback = net.index("int stop_error = n->methods.hw_stop(sc);")
    second_check = net.rindex("rtwn8723be_datapath_running_ready(sc->sc_datapath)")
    publish = net.index("ifp->if_flags |= IFF_RUNNING;")
    assert net.count("rtwn8723be_datapath_running_ready(sc->sc_datapath)") == 2
    assert hw_start < first_check < rf_second < rollback < second_check < publish
    assert net.index("return EIO;", first_check) < rf_second
    assert net.index("return EIO;", second_check) < publish
    for token in (
        "sc->sc_linux.stage != R23BE_STAGE_STOPPED",
        "sc->sc_linux.started", "sc->sc_linux.fw_ready",
        "sc->sc_linux.mac_func_enable",
        "sc->sc_linux.being_init_adapter",
    ):
        assert rollback < net.index(token, rollback) < second_check, token
    assert "return EIO;" in net[rollback:second_check]
    assert "return error != 0 ? error : ENETDOWN;" in net[rollback:second_check]

contract(ready, init, H)
mutations = (
    (ready.replace("dp->tx_enabled &&", "true &&", 1), init, H),
    (ready.replace("!dp->stop_pending", "true", 1), init, H),
    (ready.replace("sc->sc_datapath == dp", "true", 1), init, H),
    (ready.replace("sc->sc_irq_arg == dp", "true", 1), init, H),
    (ready.replace("sc->sc_irq_dispatch_ready", "true", 1), init, H),
    (ready.replace("sc->sc_linux.stage == R23BE_STAGE_RUNNING", "true", 1), init, H),
    (ready.replace("mutex_enter(&dp->tx_lock);", "", 1), init, H),
    (ready, init.replace(
        "rtwn8723be_datapath_running_ready(sc->sc_datapath)", "true", 1), H),
    (ready, init.replace(
        "rtwn8723be_datapath_running_ready(sc->sc_datapath)", "true", 2), H),
    (ready, init.replace(
        "sc->sc_linux.stage != R23BE_STAGE_STOPPED", "false", 1), H),
    (ready, init.replace("sc->sc_linux.mac_func_enable", "false", 1), H),
    (ready, init, H.replace("bool rtwn8723be_datapath_running_ready(", "bool absent(")),
)
for i, candidate in enumerate(mutations, 1):
    assert candidate != (ready, init, H), i
    try:
        contract(*candidate)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe START/RFKill native mutation {i}")

harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include "rtwn8723be_net80211_state.h"

#define IFF_RUNNING 0x40U
#define IFF_OACTIVE 0x400U
typedef struct { bool held; } kmutex_t;
struct rtwn8723be_softc;
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    kmutex_t tx_lock;
    bool prepared, tx_enabled, stop_pending;
};
struct ifnet { void *if_softc; unsigned if_flags; };
struct rtwn8723be_softc {
    struct rtwn8723be_linux_state sc_linux;
    struct rtwn8723be_datapath *sc_datapath;
    void *sc_irq_arg, *sc_ih;
    bool sc_irq_dispatch_ready, sc_mapped, sc_rings_allocated;
    struct rtwn8723be_datapath bridge;
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
static unsigned locks, unlocks, starts, stops, rf_reads;
static int start_mode, rf_invalidate, stop_mode, rf_error;
static bool radio_on;
static void mutex_enter(kmutex_t *m)
{ assert(m && !m->held); m->held = true; locks++; }
static void mutex_exit(kmutex_t *m)
{ assert(m && m->held); m->held = false; unlocks++; }
static int rtwn8723be_rfkill_native_radio_on(
    struct rtwn8723be_softc *sc, bool *on)
{
    rf_reads++;
    assert(sc && on);
    if (rf_reads == 2) {
        if (rf_invalidate == 1) sc->bridge.tx_enabled = false;
        if (rf_invalidate == 2) sc->sc_irq_arg = NULL;
        if (rf_invalidate == 3) sc->bridge.stop_pending = true;
        if (rf_invalidate == 4) sc->sc_datapath = NULL;
        if (rf_error) return rf_error;
    }
    *on = radio_on;
    return 0;
}
static int hw_start(struct rtwn8723be_softc *sc)
{
    starts++;
    if (start_mode == 5) return EIO;
    sc->sc_linux.started = sc->sc_linux.fw_ready = true;
    sc->sc_linux.stage = R23BE_STAGE_RUNNING;
    sc->bridge.tx_enabled = start_mode != 1;
    if (start_mode == 2) sc->sc_irq_arg = NULL;
    if (start_mode == 3) sc->bridge.stop_pending = true;
    if (start_mode == 4) sc->sc_irq_dispatch_ready = false;
    return 0;
}
static int hw_stop(struct rtwn8723be_softc *sc)
{
    stops++;
    if (stop_mode == 5) return EBUSY;
    if (stop_mode == 1) return 0;
    sc->sc_linux.started = false;
    sc->sc_linux.stage = R23BE_STAGE_STOPPED;
    sc->sc_linux.fw_ready = stop_mode == 2;
    sc->sc_linux.mac_func_enable = stop_mode == 3;
    sc->sc_linux.being_init_adapter = stop_mode == 4;
    sc->bridge.tx_enabled = false;
    return 0;
}
static void tx_start(struct rtwn8723be_softc *sc, struct ifnet *ifp)
{ (void)sc; (void)ifp; }
'''
checks = r'''
static void reset(struct rtwn8723be_softc *sc,
    struct rtwn8723be_net80211 *n, struct ifnet *ifp)
{
    *sc = (struct rtwn8723be_softc){0};
    *n = (struct rtwn8723be_net80211){0};
    *ifp = (struct ifnet){0};
    sc->bridge.sc = sc;
    sc->bridge.prepared = true;
    sc->sc_datapath = &sc->bridge;
    sc->sc_irq_arg = &sc->bridge;
    sc->sc_ih = sc;
    sc->sc_irq_dispatch_ready = sc->sc_mapped = sc->sc_rings_allocated = true;
    sc->sc_linux.stage = R23BE_STAGE_PROBED;
    n->sc = sc; n->registered = true;
    n->methods.hw_start = hw_start;
    n->methods.hw_stop = hw_stop;
    n->methods.tx_start = tx_start;
    ifp->if_softc = n;
    starts = stops = locks = unlocks = rf_reads = 0;
    start_mode = rf_invalidate = stop_mode = rf_error = 0;
    radio_on = true;
}
static void balanced(struct rtwn8723be_softc *sc)
{ assert(!sc->bridge.tx_lock.held && locks == unlocks); }
int main(void)
{
    struct rtwn8723be_softc sc;
    struct rtwn8723be_net80211 n;
    struct ifnet ifp;

    reset(&sc,&n,&ifp);
    assert(!rtwn8723be_datapath_running_ready(&sc.bridge));
    assert(!rtwn8723be_datapath_running_ready(NULL));
    assert(rtwn8723be_n80211_ifinit(&ifp) == 0);
    assert((ifp.if_flags & IFF_RUNNING) != 0);
    assert(starts == 1 && stops == 0 && rf_reads == 2);
    assert(rtwn8723be_datapath_running_ready(&sc.bridge));
    balanced(&sc);

    /* Fake SUCCESS from hw_start cannot publish IFF_RUNNING. */
    for (int mode = 1; mode <= 4; mode++) {
        reset(&sc,&n,&ifp);
        start_mode = mode;
        assert(rtwn8723be_n80211_ifinit(&ifp) == EIO);
        assert(starts == 1 && stops == 0 && rf_reads == 1);
        assert((ifp.if_flags & IFF_RUNNING) == 0);
        balanced(&sc);
    }
    reset(&sc,&n,&ifp);
    start_mode = 5;
    assert(rtwn8723be_n80211_ifinit(&ifp) == EIO);
    assert(starts == 1 && stops == 0 && rf_reads == 1);
    balanced(&sc);

    /* Valid initial admission, revoked by the RFKill second sample. */
    for (int mode = 1; mode <= 4; mode++) {
        reset(&sc,&n,&ifp);
        rf_invalidate = mode;
        assert(rtwn8723be_n80211_ifinit(&ifp) == EIO);
        assert(starts == 1 && stops == 0 && rf_reads == 2);
        assert((ifp.if_flags & IFF_RUNNING) == 0);
        balanced(&sc);
    }

    reset(&sc,&n,&ifp);
    radio_on = false;
    assert(rtwn8723be_n80211_ifinit(&ifp) == ENETDOWN);
    assert(starts == 0 && stops == 0);
    balanced(&sc);

    /* RFKill switch toggles while hw_start is active. */
    reset(&sc,&n,&ifp);
    rf_invalidate = 0;
    rf_error = EAGAIN;
    assert(rtwn8723be_n80211_ifinit(&ifp) == EAGAIN);
    assert(starts == 1 && stops == 1);
    assert(sc.sc_linux.stage == R23BE_STAGE_STOPPED);
    balanced(&sc);

    /* False-success RFKill rollback and explicit STOP error. */
    for (int mode = 1; mode <= 5; mode++) {
        reset(&sc,&n,&ifp);
        stop_mode = mode; rf_error = EAGAIN;
        assert(rtwn8723be_n80211_ifinit(&ifp) ==
               (mode == 5 ? EBUSY : EIO));
        assert(starts == 1 && stops == 1);
        assert((ifp.if_flags & IFF_RUNNING) == 0);
        balanced(&sc);
    }

    puts("RTL_NATIVE_RUNNING_IFF_PUBLICATION_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-native-running-") as td:
    src = Path(td) / "check.c"
    exe = Path(td) / "check"
    src.write_text(harness + "\n" + ready + "\n" + init + "\n" + checks)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(ROOT / "src"), str(src), "-o", str(exe)
    ], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_NATIVE_RUNNING_PUBLICATION_SOURCE_NEGATIVES_OK negatives=12")
