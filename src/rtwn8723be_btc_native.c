/* SPDX-License-Identifier: GPL-2.0 */
/* Native per-device, sleepable, serialized BTC notification lifetime. */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <sys/cpu.h>
#include <sys/intr.h>
#include <sys/proc.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_btc_native.h"

static bool
btc_thread(void)
{
    return !cpu_intr_p() && !cpu_softintr_p();
}

static void
btc_fault(struct rtwn8723be_btc_native *n, int error)
{
    mutex_enter(&n->queue_lock);
    if (!n->faulted) {
        n->faulted = true;
        n->last_error = error;
    }
    n->events_enabled = false;
    mutex_exit(&n->queue_lock);
}

static int
btc_run(struct rtwn8723be_softc *sc, const struct rtwn8723be_btc_event *event)
{
    struct rtwn8723be_btc_native *n = &sc->sc_btc;
    int error;

    error = n->owner->acquire(n->owner_arg, sc);
    if (error != 0) {
        /* An accepted notification cannot be silently lost on owner failure. */
        btc_fault(n, error);
        return error;
    }
    mutex_enter(&n->engine_lock);
    n->first_error = 0;
    mutex_enter(&n->queue_lock);
    error = n->faulted ? n->last_error : 0;
    mutex_exit(&n->queue_lock);
    if (error != 0) {
        mutex_exit(&n->engine_lock);
        n->owner->release(n->owner_arg, sc, error);
        return error;
    }
    error = rtwn8723be_btc_event_validate(&n->engine, event);
    if (error != 0) {
        mutex_exit(&n->engine_lock);
        n->owner->release(n->owner_arg, sc, error);
        return error;
    }
    if (!n->owner->ready(n->owner_arg, sc))
        error = ENXIO;
    else {
        error = rtwn8723be_btc_engine_execute(&n->engine, event);
        if (n->first_error != 0)
            error = n->first_error;
        /*
         * Frozen exhalbtc_init_coex_dm() publishes initialized only after
         * the antenna-specific initialization.  Native providers can fail,
         * so do not publish the state of an incomplete hardware setup.
         */
        if (error == 0 && event->kind == R23BE_BTC_INIT_DM)
            n->engine.btc.initialized = true;
    }
    if (error != 0) {
        btc_fault(n, error);
    }
    mutex_exit(&n->engine_lock);
    n->owner->release(n->owner_arg, sc, error);
    return error;
}

static void
btc_worker(struct work *work, void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_btc_native *n = &sc->sc_btc;
    struct rtwn8723be_btc_event event;
    bool faulted;
    (void)work;
    mutex_enter(&n->queue_lock);
    n->worker = curlwp;
    mutex_exit(&n->queue_lock);
    for (;;) {
        mutex_enter(&n->queue_lock);
        if (n->count == 0) {
            n->scheduled = false;
            n->worker = NULL;
            mutex_exit(&n->queue_lock);
            return;
        }
        event = n->events[n->head];
        memset(&n->events[n->head], 0, sizeof(event));
        n->head = (n->head + 1U) % R23BE_BTC_QUEUE_SIZE;
        n->count--;
        faulted = n->faulted;
        mutex_exit(&n->queue_lock);
        /* Once failed, discard copied notifications without more IO. */
        if (!faulted) (void)btc_run(sc, &event);
    }
}

int
rtwn8723be_btc_native_init(struct rtwn8723be_softc *sc,
    const struct btc_coexist *context,
    const struct rtwn8723be_btc_native_owner *owner, void *owner_arg)
{
    struct rtwn8723be_btc_native *n;
    int error;
    if (sc == NULL || context == NULL || owner == NULL) return EINVAL;
    if (!btc_thread()) return EWOULDBLOCK;
    n = &sc->sc_btc;
    if (n->initialized) return EALREADY;
    if (owner->acquire == NULL || owner->ready == NULL || owner->release == NULL)
        return ENOSYS;
    if (context->adapter != sc) return EINVAL;
    /* Preflight the complete provider/context BEFORE creating native state. */
    error = rtwn8723be_btc_callbacks_ready(context);
    if (error != 0) return error;
    memset(n, 0, sizeof(*n));
    error = rtwn8723be_btc_engine_init(&n->engine, context);
    if (error != 0) return error;
    n->owner = owner;
    n->owner_arg = owner_arg;
    mutex_init(&n->queue_lock, MUTEX_DEFAULT, IPL_SOFTNET);
    mutex_init(&n->engine_lock, MUTEX_DEFAULT, IPL_NONE);
    cv_init(&n->calls_cv, "btccalls");
    error = workqueue_create(&n->workqueue, "r23bebtc", btc_worker, sc,
        PRI_NONE, IPL_SOFTNET, WQ_MPSAFE);
    if (error != 0) {
        cv_destroy(&n->calls_cv);
        mutex_destroy(&n->engine_lock);
        mutex_destroy(&n->queue_lock);
        memset(n, 0, sizeof(*n));
        return error;
    }
    n->initialized = true;
    return 0;
}

int
rtwn8723be_btc_native_execute(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_btc_event *event)
{
    struct rtwn8723be_btc_native *n;
    int error;
    if (sc == NULL) return EINVAL;
    if (!btc_thread()) return EWOULDBLOCK;
    n = &sc->sc_btc;
    if (!n->initialized) return ENXIO;
    mutex_enter(&n->queue_lock);
    if (n->closing || n->faulted) {
        error = n->faulted ? n->last_error : ECANCELED;
        mutex_exit(&n->queue_lock);
        return error;
    }
    if (n->calls == (unsigned int)-1) {
        mutex_exit(&n->queue_lock);
        return EOVERFLOW;
    }
    n->calls++;
    mutex_exit(&n->queue_lock);
    error = btc_run(sc, event);
    mutex_enter(&n->queue_lock);
    n->calls--;
    if (n->calls == 0) cv_broadcast(&n->calls_cv);
    mutex_exit(&n->queue_lock);
    return error;
}

int
rtwn8723be_btc_native_enable_events(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_btc_native *n;
    int error = 0;
    if (sc == NULL) return EINVAL;
    if (!btc_thread()) return EWOULDBLOCK;
    n = &sc->sc_btc;
    if (!n->initialized) return ENXIO;
    /* An explicit real MCU-ready/old-RX-drain lifetime is still required. */
    if (!sc->sc_linux.started || !sc->sc_linux.fw_ready ||
        sc->sc_linux.stage != R23BE_STAGE_RUNNING || !sc->sc_irq_enabled)
        return EAGAIN;
    mutex_enter(&n->queue_lock);
    if (n->closing || n->faulted) error = EAGAIN;
    else n->events_enabled = true;
    mutex_exit(&n->queue_lock);
    return error;
}

int
rtwn8723be_btc_native_enqueue(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_btc_event *event)
{
    struct rtwn8723be_btc_native *n;
    unsigned int tail;
    if (sc == NULL || event == NULL) return EINVAL;
    if (cpu_intr_p()) return EWOULDBLOCK;
    n = &sc->sc_btc;
    if (!n->initialized) return ENXIO;
    /* Async payload is scalar/copy-only, never a borrowed diagnostic sink.
     * Initialization, firmware preload and terminal HALT are owner calls.
     */
    if ((unsigned int)event->kind >= R23BE_BTC_EVENT_COUNT ||
        event->kind < R23BE_BTC_IPS || event->kind == R23BE_BTC_HALT ||
        event->kind == R23BE_BTC_DISPLAY || event->diagnostic != NULL ||
        (event->kind == R23BE_BTC_INFO &&
         (event->length == 0 || event->length > R23BE_BTC_INFO_MAX)))
        return EINVAL;
    if (event->kind == R23BE_BTC_RF_STATUS &&
        n->engine.btc.board_info.btdm_ant_num == 2)
        return ENOTSUP;
    mutex_enter(&n->queue_lock);
    if (n->closing || n->faulted || !n->events_enabled) {
        mutex_exit(&n->queue_lock);
        return EAGAIN;
    }
    if (n->count == R23BE_BTC_QUEUE_SIZE) {
        /* Lost notifications invalidate algorithm history: quarantine. */
        n->faulted = true;
        n->last_error = ENOBUFS;
        n->events_enabled = false;
        mutex_exit(&n->queue_lock);
        return ENOBUFS;
    }
    tail = (n->head + n->count) % R23BE_BTC_QUEUE_SIZE;
    n->events[tail] = *event;
    n->count++;
    if (!n->scheduled) {
        n->scheduled = true;
        /* Enqueue under admission lock: stop cannot overtake submission. */
        workqueue_enqueue(n->workqueue, &n->work, NULL);
    }
    mutex_exit(&n->queue_lock);
    return 0;
}

int
rtwn8723be_btc_native_c2h_info(void *arg,
    const struct rtwn8723be_c2h_event *event)
{
    struct rtwn8723be_btc_event copied;
    if (event == NULL || event->id != R23BE_C2H_BT_INFO ||
        event->payload == NULL || event->payload_length == 0 ||
        event->payload_length > R23BE_BTC_INFO_MAX)
        return EINVAL;
    memset(&copied, 0, sizeof(copied));
    copied.kind = R23BE_BTC_INFO;
    copied.length = (u8)event->payload_length;
    memcpy(copied.info, event->payload, copied.length);
    return rtwn8723be_btc_native_enqueue(arg, &copied);
}

bool
rtwn8723be_btc_native_provider_ready(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_btc_native *n = &sc->sc_btc;
    KASSERT(mutex_owned(&n->engine_lock));
    return n->first_error == 0 && n->owner->ready(n->owner_arg, sc);
}

void
rtwn8723be_btc_native_provider_error(struct rtwn8723be_softc *sc, int error)
{
    struct rtwn8723be_btc_native *n = &sc->sc_btc;
    KASSERT(mutex_owned(&n->engine_lock));
    if (error != 0 && n->first_error == 0) n->first_error = error;
}

int
rtwn8723be_btc_native_stop(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_btc_native *n;
    int error;
    if (sc == NULL) return EINVAL;
    if (!btc_thread()) return EWOULDBLOCK;
    n = &sc->sc_btc;
    if (!n->initialized) return 0;
    /* Owner must call outside all provider/worker callbacks and RF holds. */
    if (mutex_owned(&n->engine_lock)) return EDEADLK;
    mutex_enter(&n->queue_lock);
    if (n->worker == curlwp) {
        mutex_exit(&n->queue_lock);
        return EDEADLK;
    }
    n->closing = true;
    n->events_enabled = false;
    while (n->calls != 0) cv_wait(&n->calls_cv, &n->queue_lock);
    mutex_exit(&n->queue_lock);
    workqueue_wait(n->workqueue, &n->work);
    mutex_enter(&n->queue_lock);
    KASSERT(n->count == 0 && !n->scheduled && n->calls == 0);
    error = n->faulted ? n->last_error : 0;
    mutex_exit(&n->queue_lock);
    if (error == 0 && !n->halted) {
        struct rtwn8723be_btc_event halt;
        memset(&halt, 0, sizeof(halt));
        halt.kind = R23BE_BTC_HALT;
        error = btc_run(sc, &halt);
        if (error == 0) n->halted = true;
    }
    return error;
}

int
rtwn8723be_btc_native_fini(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_btc_native *n;
    int error;
    if (sc == NULL) return EINVAL;
    if (!btc_thread()) return EWOULDBLOCK;
    n = &sc->sc_btc;
    if (!n->initialized) return 0;
    /* External owner excludes all new entry points and drained RX first. */
    error = rtwn8723be_btc_native_stop(sc);
    if (error != 0) return error; /* keep failed state for owner recovery */
    workqueue_destroy(n->workqueue);
    cv_destroy(&n->calls_cv);
    mutex_destroy(&n->engine_lock);
    mutex_destroy(&n->queue_lock);
    memset(n, 0, sizeof(*n));
    return 0;
}

/*
 * Frozen rtlwifi/pci.c:rtl_pci_stop() first sends btc_halt_notify when
 * coexistence is active, then unconditionally btc_deinit_variables when
 * btc_ops exists.  The native fini path performs exactly that lifetime:
 * drain accepted work/callers, run one HALT event, then destroy BTC state.
 */
int
rtwn8723be_netbsd_bt_halt_deinit(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    if (sc == NULL)
        return EINVAL;
    if (sc->sc_linux.stage != R23BE_STAGE_STOPPING ||
        !sc->sc_linux.started)
        return EAGAIN;

    /*
     * A coexistence-capable board must have been prepared by bt_prepare.
     * Returning success here would otherwise hide a missing provider/owner.
     * Wi-Fi-only operation legitimately has no full coexistence context.
     */
    if (sc->sc_btcoexist && !sc->sc_btc.initialized)
        return ENXIO;

    return rtwn8723be_btc_native_fini(sc);
}
