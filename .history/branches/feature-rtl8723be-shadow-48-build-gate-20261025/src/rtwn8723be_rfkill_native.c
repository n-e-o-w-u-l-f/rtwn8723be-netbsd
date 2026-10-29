/* SPDX-License-Identifier: GPL-2.0 */
/*
 * NetBSD 11 thread-context RTL8723BE RF-kill polling owner.
 *
 * Frozen Linux rtlwifi/base.c:rtl_init_rfkill() reads the real GPIO
 * and registers wiphy rfkill polling. NetBSD callouts run in softclock
 * context, where our GPIO sampler deliberately refuses to touch MMIO.
 * Hence a callout ENQUEUES one work item, and only the workqueue kernel
 * thread performs the actual RF-PS-serialized GPIO operation.
 *
 * This module owns its own complete timer/workqueue rollback and STOP.
 * Do NOT bind init_rfkill in the Linux ops yet: owner net80211 RF state
 * publication and full post-registration probe teardown are not wired.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <sys/cpu.h>
#include <sys/intr.h>
#include <sys/proc.h>
#include <sys/mutex.h>
#include <sys/callout.h>
#include <sys/workqueue.h>

#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_rfkill_native.h"

static void
rtwn8723be_rfkill_worker(struct work *wk, void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_rfkill_native *n = &sc->sc_rfkill_native;
    bool on = false;
    bool valid = false;
    bool active;
    int error = 0;

    if (wk != &n->poll_work)
        return; /* No foreign work may use our RF/PCI lifetime. */

    mutex_enter(&n->lock);
    active = n->initialized && n->active && n->work_queued;
    mutex_exit(&n->lock);

    /* Hardware access is restricted to this real NetBSD worker thread. */
    if (active)
        error = rtwn8723be_netbsd_rfkill_gpio_sample(sc, &on, &valid);

    mutex_enter(&n->lock);
    if (active) {
        n->samples++;
        n->last_error = error;
        if (error == 0 && valid) {
            n->last_valid = true;
            n->last_radio_on = on;
        }
        /* Busy/invalid polls NEVER publish an invented switch value. */
    }
    n->work_queued = false;
    if (n->active)
        callout_schedule(&n->timer, hz);
    mutex_exit(&n->lock);
}

/* Softclock must never call the real GPIO/MMIO sampler directly. */
static void
rtwn8723be_rfkill_timer(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_rfkill_native *n = &sc->sc_rfkill_native;

    mutex_enter(&n->lock);
    if (n->initialized && n->active && !n->work_queued &&
        n->wq != NULL) {
        n->work_queued = true;
        workqueue_enqueue(n->wq, &n->poll_work, NULL);
    }
    mutex_exit(&n->lock);
}

int
rtwn8723be_rfkill_native_init(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_rfkill_native *n;
    bool on = false;
    bool valid = false;
    int error;

    if (sc == NULL)
        return EINVAL;
    /* No sleeping workqueue allocation from hard/soft interrupts. */
    if (cpu_intr_p() || cpu_softintr_p())
        return EWOULDBLOCK;
    if (!sc->sc_rf_ps_lock_initialized || !sc->sc_mapped ||
        !sc->sc_core_initialized ||
        sc->sc_linux.stage != R23BE_STAGE_RFKILL)
        return EAGAIN;

    n = &sc->sc_rfkill_native;
    if (n->initialized)
        return EALREADY;

    /* Linux initializes physical switch state before polling. */
    memset(n, 0, sizeof(*n));
    mutex_init(&n->lock, MUTEX_DEFAULT, IPL_SOFTNET);
    callout_init(&n->timer, CALLOUT_MPSAFE);
    callout_setfunc(&n->timer, rtwn8723be_rfkill_timer, sc);
    error = workqueue_create(&n->wq, "r23berfk",
        rtwn8723be_rfkill_worker, sc, PRI_NONE, IPL_SOFTNET, WQ_MPSAFE);
    if (error != 0) {
        callout_destroy(&n->timer);
        mutex_destroy(&n->lock);
        memset(n, 0, sizeof(*n));
        return error;
    }

    error = rtwn8723be_netbsd_rfkill_gpio_sample(sc, &on, &valid);
    if (error != 0 && error != EBUSY) {
        /* No work was scheduled; unwinding the fresh queue is safe. */
        workqueue_destroy(n->wq);
        callout_destroy(&n->timer);
        mutex_destroy(&n->lock);
        memset(n, 0, sizeof(*n));
        return error;
    }

    mutex_enter(&n->lock);
    n->initialized = true;
    n->active = true;
    n->last_error = error;
    n->last_valid = error == 0 && valid;
    if (n->last_valid)
        n->last_radio_on = on;
    /* Deferred sample retries even if Linux's first GPIO read was busy. */
    callout_schedule(&n->timer, hz);
    mutex_exit(&n->lock);
    return 0;
}

int
rtwn8723be_rfkill_native_fini(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_rfkill_native *n;

    if (sc == NULL)
        return EINVAL;
    if (cpu_intr_p() || cpu_softintr_p())
        return EWOULDBLOCK;
    n = &sc->sc_rfkill_native;
    if (!n->initialized)
        return 0;

    /* External lifecycle owns ifnet shutdown and excludes fresh entrants.
     * Under the spin lock, stop the worker from rescheduling the timer.
     */
    mutex_enter(&n->lock);
    n->active = false;
    mutex_exit(&n->lock);

    /*
     * callout_halt sleeps if necessary: NEVER hold the spin mutex here.
     * The callback now observes !active and cannot enqueue new work.
     * The worker also observes !active before any timer reschedule.
     * Destroy queue before the BAR or RF-PS mutex can be torn down.
     */
    (void)callout_halt(&n->timer, NULL);
    workqueue_wait(n->wq, &n->poll_work);
    workqueue_destroy(n->wq);
    callout_destroy(&n->timer);
    mutex_destroy(&n->lock);
    memset(n, 0, sizeof(*n));
    return 0;
}
