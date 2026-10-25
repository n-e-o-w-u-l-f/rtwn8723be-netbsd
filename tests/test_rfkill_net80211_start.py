#!/usr/bin/env python3
"""Compile production RFKill snapshot and net80211 start gate under C11/UBSan.

NetBSD IRQ/ifnet execution and asynchronous switch-off still need native
hardware testing. This checks state guards and two-phase start refusal.
"""
from pathlib import Path
import tempfile
import subprocess

ROOT = Path(__file__).resolve().parents[1]
rf = (ROOT / "src/rtwn8723be_rfkill_native.c").read_text()
net = (ROOT / "src/rtwn8723be_net80211.c").read_text()

def body(src: str, name: str) -> str:
    marker = "\n" + name + "("
    assert src.count(marker) == 1, name
    fragment = name + "(" + src.split(marker, 1)[1]
    i = fragment.index("{")
    level = 0
    for n in range(i, len(fragment)):
        if fragment[n] == "{": level += 1
        if fragment[n] == "}":
            level -= 1
            if not level: return fragment[:n+1]
    raise AssertionError(f"unterminated function {name}")

getter = body(rf, "rtwn8723be_rfkill_native_radio_on")
worker = body(rf, "rtwn8723be_rfkill_worker")
start = body(net, "rtwn8723be_n80211_ifinit")

before = start.index("error = n->methods.hw_start(sc);")
after = start.index("ifp->if_flags |= IFF_RUNNING;")
assert start.count("rtwn8723be_rfkill_native_radio_on(sc, &radio_on)") == 2
assert start.index("rtwn8723be_rfkill_native_radio_on(sc, &radio_on)") < before
assert start.rfind("rtwn8723be_rfkill_native_radio_on(sc, &radio_on)") > before
assert start.rfind("rtwn8723be_rfkill_native_radio_on(sc, &radio_on)") < after
assert "int stop_error = n->methods.hw_stop(sc);" in start[before:after]
assert "return error != 0 ? error : ENETDOWN;" in start
assert "n->last_valid = error == 0 && valid;" in worker
assert worker.index("n->last_error = error;") < worker.index(
    "n->last_valid = error == 0 && valid;") < worker.index(
    "n->last_radio_on = on;")
assert getter.index("mutex_enter(&n->lock);") < getter.index(
    "error = n->last_error;") < getter.index("mutex_exit(&n->lock);")
assert "if (!active || pending || !valid || error != 0)" in getter
assert "pending = n->work_queued;" in getter
assert getter.index("if (!active || !valid || error != 0)") < getter.index("*on = value;")

prologue = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <stdio.h>

#define IFF_RUNNING 0x40U
#define IFF_OACTIVE 0x400U
#define R23BE_STAGE_PROBED 18
#define R23BE_STAGE_STOPPED 45
#define R23BE_STAGE_RUNNING 43

typedef struct { int held; } kmutex_t;
static void mutex_enter(kmutex_t *m) { assert(!m->held); m->held = 1; }
static void mutex_exit(kmutex_t *m) { assert(m->held); m->held = 0; }

struct work { int marker; };
struct rtwn8723be_rfkill_native {
    kmutex_t lock;
    struct work poll_work;
    int timer;
    bool initialized, active, work_queued, last_valid, last_radio_on;
    unsigned int samples;
    int last_error;
};
struct rtwn8723be_softc {
    struct rtwn8723be_rfkill_native sc_rfkill_native;
    struct { int stage; bool started, fw_ready; } sc_linux;
    bool sc_irq_dispatch_ready, sc_rings_allocated, sc_mapped;
    void *sc_ih;
};
struct ifnet {
    void *if_softc;
    unsigned int if_flags;
};
struct rtwn8723be_net80211_methods {
    int (*hw_start)(struct rtwn8723be_softc *);
    int (*hw_stop)(struct rtwn8723be_softc *);
    void (*tx_start)(struct rtwn8723be_softc *, struct ifnet *);
};
struct rtwn8723be_net80211 {
    bool registered;
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_net80211_methods methods;
};
int rtwn8723be_rfkill_native_radio_on(struct rtwn8723be_softc *, bool *);
static int sample_error;
static bool sample_valid, sample_on;
static int callout_count;
static const int hz = 100;
static int rtwn8723be_netbsd_rfkill_gpio_sample(
    struct rtwn8723be_softc *sc, bool *on, bool *valid)
{
    assert(sc != NULL);
    *valid = sample_valid;
    *on = sample_on;
    return sample_error;
}
static void callout_schedule(int *timer, int frequency)
{
    assert(timer != NULL && frequency == hz);
    callout_count++;
}
'''
epilogue = r'''
static int starts, stops, start_errno, stop_errno, change_on_start;
static int hw_start(struct rtwn8723be_softc *sc)
{
    starts++;
    if (start_errno) return start_errno;
    if (change_on_start == 3) {
        sc->sc_linux.fw_ready = true;
        return 0; /* partial start; not started */
    }
    sc->sc_linux.stage = R23BE_STAGE_RUNNING;
    sc->sc_linux.started = true;
    sc->sc_linux.fw_ready = true;
    if (change_on_start == 1)
        sc->sc_rfkill_native.last_radio_on = false;
    if (change_on_start == 2)
        sc->sc_rfkill_native.last_error = EBUSY;
    return 0;
}
static int hw_stop(struct rtwn8723be_softc *sc)
{
    stops++;
    if (stop_errno) return stop_errno;
    sc->sc_linux.started = false;
    sc->sc_linux.fw_ready = false;
    sc->sc_linux.stage = R23BE_STAGE_STOPPED;
    return 0;
}
static void tx_start(struct rtwn8723be_softc *sc, struct ifnet *ifp)
{ (void)sc; (void)ifp; }
static void reset(struct rtwn8723be_softc *sc,
    struct rtwn8723be_net80211 *n, struct ifnet *ifp)
{
    *sc = (struct rtwn8723be_softc){0};
    *n = (struct rtwn8723be_net80211){0};
    *ifp = (struct ifnet){0};
    sc->sc_rfkill_native.initialized = true;
    sc->sc_rfkill_native.active = true;
    sc->sc_rfkill_native.last_valid = true;
    sc->sc_rfkill_native.last_radio_on = true;
    sc->sc_linux.stage = R23BE_STAGE_PROBED;
    sc->sc_irq_dispatch_ready = true;
    sc->sc_rings_allocated = true;
    sc->sc_mapped = true;
    sc->sc_ih = sc;
    n->registered = true;
    n->sc = sc;
    n->methods.hw_start = hw_start;
    n->methods.hw_stop = hw_stop;
    n->methods.tx_start = tx_start;
    ifp->if_softc = n;
    starts = stops = start_errno = stop_errno = change_on_start = 0;
}
int main(void)
{
    struct rtwn8723be_softc sc;
    struct rtwn8723be_net80211 n;
    struct ifnet ifp;
    bool on = false;
    int ret;
    reset(&sc,&n,&ifp);

    assert(rtwn8723be_rfkill_native_radio_on(NULL,&on) == EINVAL);
    assert(rtwn8723be_rfkill_native_radio_on(&sc,NULL) == EINVAL);
    assert(rtwn8723be_rfkill_native_radio_on(&sc,&on) == 0 && on);
    on = false;
    sc.sc_rfkill_native.last_error = EBUSY;
    assert(rtwn8723be_rfkill_native_radio_on(&sc,&on) == EAGAIN && !on);
    sc.sc_rfkill_native.last_error = 0;
    sc.sc_rfkill_native.last_valid = false;
    assert(rtwn8723be_rfkill_native_radio_on(&sc,&on) == EAGAIN && !on);
    sc.sc_rfkill_native.last_valid = true;
    sc.sc_rfkill_native.active = false;
    assert(rtwn8723be_rfkill_native_radio_on(&sc,&on) == EAGAIN && !on);
    sc.sc_rfkill_native.active = true;
    sc.sc_rfkill_native.work_queued = true;
    assert(rtwn8723be_rfkill_native_radio_on(&sc,&on) == EAGAIN && !on);
    sc.sc_rfkill_native.work_queued = false;
    sc.sc_rfkill_native.initialized = false;
    assert(rtwn8723be_rfkill_native_radio_on(&sc,&on) == ENXIO && !on);

    /* Exercise production workqueue state update, not a copied algorithm. */
    reset(&sc,&n,&ifp);
    sc.sc_rfkill_native.work_queued = true;
    sample_error = 0; sample_valid = true; sample_on = true;
    rtwn8723be_rfkill_worker(&sc.sc_rfkill_native.poll_work, &sc);
    assert(sc.sc_rfkill_native.last_valid &&
        sc.sc_rfkill_native.last_radio_on && callout_count == 1);
    sc.sc_rfkill_native.work_queued = true;
    sample_error = EBUSY;
    rtwn8723be_rfkill_worker(&sc.sc_rfkill_native.poll_work, &sc);
    assert(!sc.sc_rfkill_native.last_valid &&
        rtwn8723be_rfkill_native_radio_on(&sc,&on) == EAGAIN);
    sc.sc_rfkill_native.work_queued = true;
    sample_error = 0; sample_valid = false;
    rtwn8723be_rfkill_worker(&sc.sc_rfkill_native.poll_work, &sc);
    assert(!sc.sc_rfkill_native.last_valid);
    sc.sc_rfkill_native.work_queued = true;
    sample_valid = true; sample_on = false;
    rtwn8723be_rfkill_worker(&sc.sc_rfkill_native.poll_work, &sc);
    assert(sc.sc_rfkill_native.last_valid &&
        !sc.sc_rfkill_native.last_radio_on);
    assert(rtwn8723be_rfkill_native_radio_on(&sc,&on) == 0 && !on);

    reset(&sc,&n,&ifp);
    assert(rtwn8723be_n80211_ifinit(&ifp) == 0);
    assert(starts == 1 && stops == 0 &&
        (ifp.if_flags & IFF_RUNNING) != 0);

    reset(&sc,&n,&ifp);
    sc.sc_rfkill_native.last_radio_on = false;
    ret = rtwn8723be_n80211_ifinit(&ifp);
    assert(ret == ENETDOWN && starts == 0 && stops == 0 &&
        (ifp.if_flags & IFF_RUNNING) == 0);

    reset(&sc,&n,&ifp);
    sc.sc_rfkill_native.last_error = EBUSY;
    assert(rtwn8723be_n80211_ifinit(&ifp) == EAGAIN &&
        starts == 0 && stops == 0);
    reset(&sc,&n,&ifp);
    sc.sc_rfkill_native.work_queued = true;
    assert(rtwn8723be_n80211_ifinit(&ifp) == EAGAIN &&
        starts == 0 && stops == 0);


    reset(&sc,&n,&ifp);
    sc.sc_rfkill_native.initialized = false;
    assert(rtwn8723be_n80211_ifinit(&ifp) == ENXIO &&
        starts == 0);

    reset(&sc,&n,&ifp);
    sc.sc_linux.stage = R23BE_STAGE_RUNNING;
    assert(rtwn8723be_n80211_ifinit(&ifp) == EAGAIN && starts == 0);

    reset(&sc,&n,&ifp);
    start_errno = EIO;
    assert(rtwn8723be_n80211_ifinit(&ifp) == EIO &&
        starts == 1 && stops == 0);

    for (int mode = 1; mode <= 3; mode++) {
        reset(&sc,&n,&ifp);
        change_on_start = mode;
        ret = rtwn8723be_n80211_ifinit(&ifp);
        assert(ret == (mode == 1 ? ENETDOWN :
            mode == 2 ? EAGAIN : EIO));
        assert(starts == 1 && stops == 1 &&
            (ifp.if_flags & IFF_RUNNING) == 0);
    }

    reset(&sc,&n,&ifp);
    change_on_start = 1;
    stop_errno = EIO;
    assert(rtwn8723be_n80211_ifinit(&ifp) == EIO &&
        starts == 1 && stops == 1 &&
        (ifp.if_flags & IFF_RUNNING) == 0);
    puts("RTL_RFKILL_NET80211_TWO_PHASE_START_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtl-rfkill-start-") as d:
    source = Path(d) / "test.c"
    exe = Path(d) / "test"
    source.write_text(prologue + "static void\n" + worker +
        "\nint\n" + getter + "\nstatic int\n" + start + epilogue)
    subprocess.run([
        "cc","-std=c11","-Wall","-Wextra","-Werror","-pedantic",
        "-fsanitize=undefined","-fno-sanitize-recover=all",
        str(source),"-o",str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
