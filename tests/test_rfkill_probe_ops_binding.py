#!/usr/bin/env python3
"""Execute the actual NetBSD RFKill callback, worker owner and unwind bodies.

The probe callback must reject an unregistered/foreign net80211 owner before
any workqueue creation. Real RFKill init/fini must preserve NetBSD stage,
thread-context, timer, queue and GPIO rollback semantics. Portable strict
C11/UBSan; no HP PCI GPIO or NetBSD kernel build implied.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NET = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
RF = (ROOT / "src/rtwn8723be_rfkill_native.c").read_text()
LINUX = (ROOT / "src/rtwn8723be_linux_state.c").read_text()
NATIVE = (ROOT / "src/rtwn8723be_native.c").read_text()

def extract(src: str, name: str, typ: str) -> str:
    needle = "\n" + name + "("
    assert src.count(needle) == 1, name
    body = name + "(" + src.split(needle, 1)[1]
    depth = 0
    for i in range(body.index("{"), len(body)):
        if body[i] == "{":
            depth += 1
        elif body[i] == "}":
            depth -= 1
            if depth == 0:
                return typ + "\n" + body[:i + 1]
    raise AssertionError(name)

adapter = extract(NET, "rtwn8723be_netbsd_init_rfkill", "static int")
init = extract(RF, "rtwn8723be_rfkill_native_init", "int")
worker = extract(RF, "rtwn8723be_rfkill_worker", "static void")
timer = extract(RF, "rtwn8723be_rfkill_timer", "static void")
fini = extract(RF, "rtwn8723be_rfkill_native_fini", "int")

def contract(a: str, b: str, c: str) -> None:
    assert ".init_rfkill = rtwn8723be_netbsd_init_rfkill," in NET
    for name in ("register_ieee80211", "bt_prepare", "dm_init"):
        assert "." + name + " =" not in NET.split(
            "const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops", 1)[1]
    assert "ops->init_rfkill == NULL" in LINUX
    assert LINUX.index("R23BE_STAGE_IEEE80211_REGISTER,") < LINUX.index(
        "R23BE_CALL(R23BE_STAGE_RFKILL, ops->init_rfkill, ctx);")
    assert "rtwn8723be_rfkill_native_fini(sc);" in NATIVE
    assert NATIVE.index("rtwn8723be_native_unwind_irq(") < (
        NATIVE.index("rtwn8723be_native_unwind_rfkill("))
    guarded = (
        "if (sc == NULL)", "return EINVAL;",
        "!sc->sc_net80211.registered",
        "sc->sc_net80211.sc != sc",
        "return EAGAIN;",
        "return rtwn8723be_rfkill_native_init(sc);",
    )
    for token in guarded:
        assert token in a, token
    assert a.index("if (sc == NULL)") < a.index(
        "!sc->sc_net80211.registered") < a.index(
        "return rtwn8723be_rfkill_native_init(sc);")
    assert "!sc->sc_rf_ps_lock_initialized || !sc->sc_mapped ||" in b
    assert "sc->sc_linux.stage != R23BE_STAGE_RFKILL" in b
    assert "cpu_intr_p() || cpu_softintr_p()" in b
    assert b.index("workqueue_create(") < b.index(
        "rtwn8723be_netbsd_rfkill_gpio_sample(")
    assert "workqueue_destroy(n->wq);" in b
    assert "callout_destroy(&n->timer);" in b
    assert "mutex_destroy(&n->lock);" in b
    assert "workqueue_wait(n->wq, &n->poll_work);" in c
    assert c.index("n->active = false;") < c.index(
        "callout_halt(&n->timer, NULL);") < c.index(
        "workqueue_wait(n->wq, &n->poll_work);") < c.index(
        "workqueue_destroy(n->wq);") < c.index(
        "mutex_destroy(&n->lock);")

contract(adapter, init, fini)
mutants = (
    (adapter.replace("if (sc == NULL)", "if (false)", 1), init, fini),
    (adapter.replace("!sc->sc_net80211.registered", "false", 1), init, fini),
    (adapter.replace("sc->sc_net80211.sc != sc", "false", 1), init, fini),
    (adapter.replace("return rtwn8723be_rfkill_native_init(sc);",
                     "return 0;", 1), init, fini),
    (adapter, init.replace("cpu_intr_p() || cpu_softintr_p()", "false", 1), fini),
    (adapter, init.replace("sc->sc_linux.stage != R23BE_STAGE_RFKILL",
                           "false", 1), fini),
    (adapter, init.replace("workqueue_destroy(n->wq);", "", 1), fini),
    (adapter, init, fini.replace("workqueue_wait(n->wq, &n->poll_work);",
                                "", 1)),
    (adapter, init, fini.replace("n->active = false;", "", 1)),
)
for i, mutant in enumerate(mutants, 1):
    assert mutant != (adapter, init, fini), i
    try:
        contract(*mutant)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe RFKill owner mutation {i} passed")

prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_linux_state.h"

#define MUTEX_DEFAULT 0
#define IPL_SOFTNET 1
#define PRI_NONE 0
#define WQ_MPSAFE 1
#define CALLOUT_MPSAFE 1
static const int hz = 100;
typedef struct { bool active; } kmutex_t;
typedef struct { bool active; } callout_t;
struct work { int mark; };
struct workqueue { int mark; };
struct rtwn8723be_softc;
struct rtwn8723be_net80211 {
    struct rtwn8723be_softc *sc;
    bool registered;
};
struct rtwn8723be_rfkill_native {
    kmutex_t lock;
    callout_t timer;
    struct workqueue *wq;
    struct work poll_work;
    bool initialized, active, work_queued, last_valid, last_radio_on;
    unsigned int samples;
    int last_error;
};
struct rtwn8723be_softc {
    struct rtwn8723be_net80211 sc_net80211;
    struct rtwn8723be_rfkill_native sc_rfkill_native;
    struct rtwn8723be_linux_state sc_linux;
    bool sc_rf_ps_lock_initialized, sc_mapped, sc_core_initialized;
};
static int create_error, gpio_error, create_count, destroy_count;
static int callout_init_count, callout_destroy_count, halt_count, wait_count;
static int gpio_count, schedule_count, enqueue_count;
static bool gpio_valid = true, gpio_on = true;
static bool hard_irq, soft_irq;
static struct workqueue queue;
static void mutex_init(kmutex_t *m,int kind,int ipl)
{ assert(m && kind==MUTEX_DEFAULT && ipl==IPL_SOFTNET); m->active=true; }
static void mutex_enter(kmutex_t *m) { assert(m && m->active); }
static void mutex_exit(kmutex_t *m) { assert(m && m->active); }
static void mutex_destroy(kmutex_t *m) { assert(m && m->active); m->active=false; }
static bool cpu_intr_p(void) { return hard_irq; }
static bool cpu_softintr_p(void) { return soft_irq; }
static void callout_init(callout_t *c,int flags)
{ assert(c && flags==CALLOUT_MPSAFE); c->active=true; callout_init_count++; }
static void callout_setfunc(callout_t *c,void (*f)(void *),void *arg)
{ assert(c && c->active && f && arg); }
static void callout_schedule(callout_t *c,int interval)
{ assert(c && c->active && interval==hz); schedule_count++; }
static int callout_halt(callout_t *c,void *unused)
{ assert(c && c->active && unused==NULL);halt_count++;return 0; }
static void callout_destroy(callout_t *c)
{ assert(c && c->active);c->active=false;callout_destroy_count++; }
static void rtwn8723be_rfkill_worker(struct work *, void *);
static int workqueue_create(struct workqueue **target,const char *name,
    void (*fn)(struct work *,void *),void *arg,int pri,int ipl,int flags)
{
    assert(target && name && fn==rtwn8723be_rfkill_worker && arg);
    assert(pri==PRI_NONE && ipl==IPL_SOFTNET && flags==WQ_MPSAFE);
    create_count++;
    if (create_error) return create_error;
    *target = &queue; return 0;
}
static void workqueue_enqueue(struct workqueue *wq,struct work *wk,void *cpu)
{ assert(wq==&queue && wk && cpu==NULL); enqueue_count++; }
static void workqueue_wait(struct workqueue *wq,struct work *wk)
{ assert(wq==&queue && wk);wait_count++; }
static void workqueue_destroy(struct workqueue *wq)
{ assert(wq==&queue); destroy_count++; }
static int rtwn8723be_netbsd_rfkill_gpio_sample(
    struct rtwn8723be_softc *sc,bool *on,bool *valid)
{
    assert(sc && on && valid);gpio_count++;
    if (gpio_error) return gpio_error;
    *on=gpio_on;*valid=gpio_valid;return 0;
}
'''
tail = r'''
static void reset(struct rtwn8723be_softc *sc)
{
    *sc=(struct rtwn8723be_softc){0};
    sc->sc_linux.stage=R23BE_STAGE_RFKILL;
    sc->sc_net80211.sc=sc;
    sc->sc_net80211.registered=true;
    sc->sc_rf_ps_lock_initialized=true;
    sc->sc_mapped=true;
    sc->sc_core_initialized=true;
    create_error=gpio_error=create_count=destroy_count=0;
    callout_init_count=callout_destroy_count=halt_count=wait_count=0;
    gpio_count=schedule_count=enqueue_count=0;
    gpio_valid=gpio_on=true;
    hard_irq=soft_irq=false;
}
static void unchanged(struct rtwn8723be_softc *sc)
{
    assert(!sc->sc_rfkill_native.initialized);
    assert(sc->sc_rfkill_native.wq==NULL);
    assert(create_count==0 && gpio_count==0);
}
int main(void)
{
    struct rtwn8723be_softc sc, foreign;
    reset(&sc);
    assert(rtwn8723be_netbsd_init_rfkill(NULL)==EINVAL);
    sc.sc_net80211.registered=false;
    assert(rtwn8723be_netbsd_init_rfkill(&sc)==EAGAIN);
    unchanged(&sc);
    sc.sc_net80211.registered=true;
    sc.sc_net80211.sc=&foreign;
    assert(rtwn8723be_netbsd_init_rfkill(&sc)==EAGAIN);
    unchanged(&sc);

    /* The real RFKill function owns stage/context admission. */
    reset(&sc);
    sc.sc_linux.stage=R23BE_STAGE_PROBED;
    assert(rtwn8723be_netbsd_init_rfkill(&sc)==EAGAIN);
    unchanged(&sc);
    reset(&sc);
    sc.sc_rf_ps_lock_initialized=false;
    assert(rtwn8723be_netbsd_init_rfkill(&sc)==EAGAIN);
    unchanged(&sc);
    reset(&sc);
    hard_irq=true;
    assert(rtwn8723be_netbsd_init_rfkill(&sc)==EWOULDBLOCK);
    unchanged(&sc);
    hard_irq=false;
    soft_irq=true;
    assert(rtwn8723be_netbsd_init_rfkill(&sc)==EWOULDBLOCK);
    unchanged(&sc);

    /* Failed workqueue create destroys timer and lock, not PCI owners. */
    reset(&sc);
    create_error=ENOMEM;
    assert(rtwn8723be_netbsd_init_rfkill(&sc)==ENOMEM);
    assert(create_count==1 && destroy_count==0 &&
        callout_destroy_count==1 && wait_count==0);
    assert(!sc.sc_rfkill_native.initialized && sc.sc_rfkill_native.wq==NULL);

    /* Failed initial GPIO sample also destroys queue and timer. */
    reset(&sc);
    gpio_error=EIO;
    assert(rtwn8723be_netbsd_init_rfkill(&sc)==EIO);
    assert(create_count==1 && destroy_count==1 &&
        callout_destroy_count==1 && gpio_count==1);
    assert(!sc.sc_rfkill_native.initialized);

    /* EBUSY means poller schedules fresh work; no fabricated radio-on. */
    reset(&sc);
    gpio_error=EBUSY;
    assert(rtwn8723be_netbsd_init_rfkill(&sc)==0);
    assert(sc.sc_rfkill_native.initialized &&
        sc.sc_rfkill_native.active && !sc.sc_rfkill_native.last_valid &&
        sc.sc_rfkill_native.last_error==EBUSY && schedule_count==1);
    assert(rtwn8723be_rfkill_native_fini(&sc)==0);
    assert(halt_count==1 && wait_count==1 && destroy_count==1);
    assert(!sc.sc_rfkill_native.initialized && sc.sc_rfkill_native.wq==NULL);

    /* Normal poller can be torn down exactly once, idempotently. */
    reset(&sc);
    assert(rtwn8723be_netbsd_init_rfkill(&sc)==0);
    assert(sc.sc_rfkill_native.last_valid && sc.sc_rfkill_native.last_radio_on);
    assert(rtwn8723be_netbsd_init_rfkill(&sc)==EALREADY);
    rtwn8723be_rfkill_timer(&sc);
    assert(sc.sc_rfkill_native.work_queued && enqueue_count==1);
    rtwn8723be_rfkill_timer(&sc);
    assert(enqueue_count==1); /* Cannot requeue same outstanding work. */
    rtwn8723be_rfkill_worker(&sc.sc_rfkill_native.poll_work,&sc);
    assert(!sc.sc_rfkill_native.work_queued && schedule_count==2);
    assert(rtwn8723be_rfkill_native_fini(&sc)==0);
    assert(halt_count==1 && wait_count==1 && destroy_count==1 &&
        callout_destroy_count==1);
    assert(rtwn8723be_rfkill_native_fini(&sc)==0);
    assert(wait_count==1);

    puts("RTL_RFKILL_REAL_PROBE_CALLBACK_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtl-rfkill-ops-binding-") as td:
    source = Path(td) / "check.c"
    exe = Path(td) / "check"
    source.write_text(prefix + "\n" + worker + "\n" + timer + "\n" +
                      init + "\n" + fini + "\n" + adapter + "\n" + tail)
    subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror",
                    "-pedantic","-fsanitize=undefined",
                    "-fno-sanitize-recover=all","-I",str(ROOT/"src"),
                    str(source),"-o",str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print("RTL_RFKILL_REAL_PROBE_BINDING_MUTATIONS_OK negatives=9")
