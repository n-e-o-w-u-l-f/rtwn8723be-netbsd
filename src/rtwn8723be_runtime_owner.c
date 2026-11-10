/* SPDX-License-Identifier: GPL-2.0 */
/* Genuine net80211/bridge ownership; missing real providers remain errors. */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/intr.h>
#include <sys/cpu.h>
#include <sys/kmem.h>
#include <sys/lwp.h>
#include <sys/mutex.h>
#include <sys/pserialize.h>
#include <sys/xcall.h>

#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_runtime_owner.h"
#include "rtwn8723be_datapath.h"
#include "rtwn8723be_rx_binding.h"
#include "rtwn8723be_net80211_state.h"
#include "rtwn8723be_btc_context.h"
#include "rtwn8723be_btc_policy.h"
#include "rtwn8723be_btc_providers_native.h"
#include "rtwn8723be_dm.h"

enum runtime_io_kind { R23BE_IO_NONE, R23BE_IO_BTC, R23BE_IO_DM };

/* Caller-owned bridge storage survives every failed compensator/STOP. */
struct rtwn8723be_runtime_context {
    struct rtwn8723be_c2h_handlers firmware;
    struct rtwn8723be_rx_binding rx;
    struct rtwn8723be_datapath dp;
    struct rtwn8723be_btc_policy_ops ports;
    struct rtwn8723be_btc_policy policy;
    struct rtwn8723be_dm_state dm;
    struct lwp *io_lwp;
    enum runtime_io_kind io_kind;
    int io_giant_count, provider_error;
    unsigned int pending_btc;
    bool providers_configured, btc_prepared, rf_owned;
    bool faulted;
    bool irq_drained;
    uint32_t drained_epoch;
};

static bool runtime_ports_ok(const struct rtwn8723be_btc_policy_ops *);

static bool
runtime_thread_ok(void)
{
    return !cpu_intr_p() && !cpu_softintr_p() &&
        pserialize_not_in_read_section();
}

/*
 * Public orchestration must not wait, call a module or drain IRQ while
 * borrowing any driver lock. The caller owns the softc/bridge lifetime;
 * only initialized/prepared locks are inspected.
 */
static bool
runtime_caller_locks_held(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_owner *owner = &sc->sc_runtime_owner;
    struct rtwn8723be_datapath *dp = sc->sc_datapath;

    if (owner->initialized &&
        (mutex_owned(&owner->lifecycle_lock) ||
         mutex_owned(&owner->io_lock)))
        return true;
    if ((sc->sc_irq_lock_initialized && mutex_owned(&sc->sc_irq_lock)) ||
        (sc->sc_rf_ps_lock_initialized &&
         mutex_owned(&sc->sc_rf_ps_lock)))
        return true;
    return dp != NULL && dp->prepared && dp->sc == sc &&
        mutex_owned(&dp->tx_lock);
}

static bool
runtime_handlers_ok(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_c2h_handlers *h)
{
    return h != NULL && h->arg == sc && h->tx_report != NULL &&
        h->ra_report != NULL && h->bt_info != NULL && h->bt_mp != NULL;
}

/* Match the actual calibration/HW-disable adapters, without calling them. */
static int
runtime_provider_ops_ready(struct rtwn8723be_softc *sc)
{
    const struct rtwn8723be_calibration_owner *cal;
    const struct rtwn8723be_hw_disable_owner *off;
    int error;

    error = rtwn8723be_linux_runtime_ops_ready(&rtwn8723be_netbsd_ops);
    if (error != 0)
        return error;
    cal = sc->sc_calibration_owner;
    off = sc->sc_hw_disable_owner;
    if (cal == NULL || cal->acquire == NULL || cal->ready == NULL ||
        cal->scan_active == NULL || cal->release == NULL ||
        off == NULL || off->acquire == NULL || off->ready == NULL ||
        off->release == NULL)
        return ENOSYS;
    return 0;
}

static int
runtime_context_ready(struct rtwn8723be_softc *sc,
    struct rtwn8723be_runtime_context *ctx)
{
    if (ctx == NULL || !runtime_handlers_ok(sc, &ctx->firmware) ||
        !ctx->providers_configured || !ctx->policy.initialized ||
        !runtime_ports_ok(&ctx->ports))
        return ENOSYS;
    return runtime_provider_ops_ready(sc);
}

/* No module callback, allocation, MMIO or waiting while this lock is held. */
static int
runtime_claim(struct rtwn8723be_softc *sc,
    enum rtwn8723be_runtime_operation operation, bool allow_fault,
    struct rtwn8723be_runtime_context **context)
{
    struct rtwn8723be_runtime_owner *owner;
    int error = 0;

    if (sc == NULL || context == NULL)
        return EINVAL;
    if (!runtime_thread_ok())
        return EWOULDBLOCK;
    owner = &sc->sc_runtime_owner;
    if (!owner->initialized)
        return ENXIO;
    if (runtime_caller_locks_held(sc) ||
        !mutex_tryenter(&owner->lifecycle_lock))
        return EBUSY;
    if (!owner->initialized || owner->closing ||
        owner->operation != R23BE_RUNTIME_NONE ||
        owner->operation_lwp != NULL || owner->io_depth != 0 ||
        (owner->context != NULL && owner->context->pending_btc != 0))
        error = EBUSY;
    else if (operation != R23BE_RUNTIME_CONFIGURE &&
        owner->context == NULL)
        error = ENOSYS;
    else if (!allow_fault && owner->context != NULL &&
        owner->context->faulted)
        error = EIO;
    else {
        owner->operation = operation;
        owner->operation_lwp = curlwp;
        *context = owner->context;
    }
    mutex_exit(&owner->lifecycle_lock);
    return error;
}

static void
runtime_release(struct rtwn8723be_softc *sc,
    enum rtwn8723be_runtime_operation operation)
{
    struct rtwn8723be_runtime_owner *owner = &sc->sc_runtime_owner;

    mutex_enter(&owner->lifecycle_lock);
    KASSERT(owner->operation == operation);
    KASSERT(owner->operation_lwp == curlwp);
    owner->operation_lwp = NULL;
    owner->operation = R23BE_RUNTIME_NONE;
    mutex_exit(&owner->lifecycle_lock);
}

/* Configure may accept genuine pure provider bindings, never live owners. */
static bool
runtime_publication_present(struct rtwn8723be_softc *sc)
{
    return sc->sc_net80211.registered || sc->sc_net80211.sc != NULL ||
        sc->sc_net80211.tx_busy ||
        sc->sc_net80211.tx_key_update_depth != 0 ||
        sc->sc_net80211.tx_pending_m != NULL ||
        sc->sc_net80211.tx_pending_ni != NULL ||
        sc->sc_net80211.tx_key_begin_saved != NULL ||
        sc->sc_net80211.tx_key_end_saved != NULL ||
        sc->sc_datapath != NULL || sc->sc_rx_binding != NULL ||
        sc->sc_irq_arg != NULL || sc->sc_irq_dispatch_ready ||
        sc->sc_irq_dispatch.rx != NULL ||
        sc->sc_irq_dispatch.tx_done != NULL ||
        sc->sc_irq_dispatch.power_event != NULL ||
        sc->sc_ih != NULL || sc->sc_soft_ih != NULL || sc->sc_pihp != NULL ||
        sc->sc_irq_requested || sc->sc_irq_enabled ||
        sc->sc_irq_pending[0] != 0 || sc->sc_irq_pending[1] != 0 ||
        sc->sc_rfkill_native.initialized || sc->sc_rfkill_native.active ||
        sc->sc_rfkill_native.wq != NULL ||
        sc->sc_rfkill_native.work_queued ||
        sc->sc_h2c.initialized || sc->sc_h2c.sc != NULL ||
        sc->sc_h2c.state.firmware_ready ||
        sc->sc_btc.initialized || sc->sc_btc.workqueue != NULL ||
        sc->sc_btc.owner != NULL || sc->sc_btc.owner_arg != NULL ||
        sc->sc_btc.worker != NULL || sc->sc_btc.calls != 0 ||
        sc->sc_btc.scheduled || sc->sc_btc.count != 0 ||
        sc->sc_btc_mp.initialized || sc->sc_btc_mp.active ||
        sc->sc_btc_mp.busy || sc->sc_btc_mp.pending ||
        sc->sc_rfchange_inprogress ||
        sc->sc_initial_pci_saved || sc->sc_mapped ||
        sc->sc_core_initialized || sc->sc_rings_allocated ||
        sc->sc_dmat_owned || sc->sc_dma_32bit ||
        sc->sc_hal_started ||
        sc->sc_linux.stage != R23BE_STAGE_IDLE ||
        sc->sc_linux.started || sc->sc_linux.fw_ready ||
        sc->sc_linux.mac_func_enable || sc->sc_linux.being_init_adapter;
}

void
rtwn8723be_runtime_owner_init(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_owner *owner;

    KASSERT(sc != NULL);
    owner = &sc->sc_runtime_owner;
    KASSERT(!owner->initialized && owner->context == NULL);
    mutex_init(&owner->lifecycle_lock, MUTEX_DEFAULT, IPL_NET);
    mutex_init(&owner->io_lock, MUTEX_DEFAULT, IPL_NONE);
    owner->io_depth = 0;
    owner->closing = false;
    owner->operation = R23BE_RUNTIME_NONE;
    owner->operation_lwp = NULL;
    owner->context = NULL;
    owner->initialized = true;
}

int
rtwn8723be_runtime_owner_configure(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_c2h_handlers *firmware)
{
    struct rtwn8723be_runtime_owner *owner;
    struct rtwn8723be_runtime_context *ctx = NULL;
    struct rtwn8723be_runtime_context *created;
    int error;

    if (sc == NULL || !runtime_handlers_ok(sc, firmware))
        return EINVAL;
    error = runtime_claim(sc, R23BE_RUNTIME_CONFIGURE, false, &ctx);
    if (error != 0)
        return error;
    owner = &sc->sc_runtime_owner;
    if (ctx != NULL) {
        error = EALREADY;
        goto out;
    }
    if (runtime_publication_present(sc)) {
        error = EBUSY;
        goto out;
    }
    created = kmem_zalloc(sizeof(*created), KM_NOSLEEP);
    if (created == NULL) {
        error = ENOMEM;
        goto out;
    }
    created->firmware = *firmware;
    /* The accepted CONFIGURE operation excludes replacement and teardown. */
    mutex_enter(&owner->lifecycle_lock);
    KASSERT(owner->context == NULL);
    owner->context = created;
    mutex_exit(&owner->lifecycle_lock);
    error = 0;
out:
    runtime_release(sc, R23BE_RUNTIME_CONFIGURE);
    return error;
}

int
rtwn8723be_runtime_probe_ready(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_owner *owner;
    int error;

    if (sc == NULL)
        return EINVAL;
    if (!runtime_thread_ok())
        return EWOULDBLOCK;
    owner = &sc->sc_runtime_owner;
    if (!owner->initialized)
        return ENOSYS;
    if (runtime_caller_locks_held(sc) ||
        !mutex_tryenter(&owner->lifecycle_lock))
        return EBUSY;
    if (!owner->initialized || owner->closing ||
        owner->operation != R23BE_RUNTIME_NONE ||
        owner->operation_lwp != NULL || owner->io_depth != 0)
        error = EBUSY;
    else if (owner->context != NULL && owner->context->faulted)
        error = EIO;
    else
        error = runtime_context_ready(sc, owner->context);
    mutex_exit(&owner->lifecycle_lock);
    return error;
}

static int
runtime_registration_rollback(struct rtwn8723be_softc *sc,
    struct rtwn8723be_runtime_context *ctx)
{
    int error;

    if (ctx->dp.prepared || ctx->dp.sc != NULL ||
        sc->sc_datapath != NULL) {
        if (!ctx->dp.prepared || ctx->dp.sc != sc ||
            sc->sc_datapath != &ctx->dp)
            return EBUSY;
        error = rtwn8723be_datapath_unprepare(&ctx->dp);
        if (error != 0)
            return error;
        if (ctx->dp.prepared || ctx->dp.sc != NULL ||
            sc->sc_datapath != NULL || sc->sc_irq_arg != NULL ||
            sc->sc_irq_dispatch_ready)
            return EIO;
    }
    if (ctx->rx.net != NULL || ctx->rx.dispatch.arg != NULL ||
        ctx->rx.dispatch.frame != NULL || ctx->rx.dispatch.c2h != NULL ||
        sc->sc_rx_binding != NULL) {
        if (ctx->rx.net != &sc->sc_net80211 ||
            sc->sc_rx_binding != &ctx->rx)
            return EBUSY;
        error = rtwn8723be_rx_binding_fini(&ctx->rx);
        if (error != 0)
            return error;
        if (ctx->rx.net != NULL || ctx->rx.dispatch.arg != NULL ||
            ctx->rx.dispatch.frame != NULL || ctx->rx.dispatch.c2h != NULL ||
            sc->sc_rx_binding != NULL)
            return EIO;
    }
    if (sc->sc_net80211.registered) {
        error = rtwn8723be_net80211_unregister(&sc->sc_net80211);
        if (error != 0)
            return error;
        if (sc->sc_net80211.registered || sc->sc_net80211.sc != NULL)
            return EIO;
    }
    return 0;
}

static bool runtime_dp_quiet(struct rtwn8723be_runtime_context *);

static bool
runtime_bridge_identity(struct rtwn8723be_softc *sc,
    struct rtwn8723be_runtime_context *ctx)
{
    const struct rtwn8723be_c2h_handlers *a = &ctx->firmware;
    const struct rtwn8723be_c2h_handlers *b = &ctx->rx.firmware;

    return sc->sc_net80211.registered &&
        sc->sc_net80211.sc == sc &&
        sc->sc_net80211.methods.hw_start == rtwn8723be_runtime_hw_start &&
        sc->sc_net80211.methods.hw_stop == rtwn8723be_runtime_hw_stop &&
        sc->sc_net80211.methods.tx_start == rtwn8723be_net80211_tx_start &&
        sc->sc_rx_binding == &ctx->rx &&
        ctx->rx.net == &sc->sc_net80211 &&
        ctx->rx.dispatch.arg == &ctx->rx &&
        ctx->rx.dispatch.frame != NULL && ctx->rx.dispatch.c2h != NULL &&
        a->arg == b->arg && a->tx_report == b->tx_report &&
        a->ra_report == b->ra_report && a->bt_info == b->bt_info &&
        a->bt_mp == b->bt_mp &&
        sc->sc_datapath == &ctx->dp && ctx->dp.prepared &&
        ctx->dp.sc == sc &&
        ctx->dp.rx.arg == ctx->rx.dispatch.arg &&
        ctx->dp.rx.frame == ctx->rx.dispatch.frame &&
        ctx->dp.rx.c2h == ctx->rx.dispatch.c2h &&
        sc->sc_irq_arg == &ctx->dp && sc->sc_irq_dispatch_ready &&
        sc->sc_irq_dispatch.rx != NULL &&
        sc->sc_irq_dispatch.tx_done != NULL &&
        sc->sc_irq_dispatch.power_event == NULL &&
        ctx->dp.tx_complete == NULL && ctx->dp.tx_complete_arg == NULL;
}

static bool
runtime_registration_owned(struct rtwn8723be_softc *sc,
    struct rtwn8723be_runtime_context *ctx)
{
    return runtime_bridge_identity(sc, ctx) &&
        !sc->sc_irq_requested && !sc->sc_irq_enabled &&
        sc->sc_ih == NULL && sc->sc_soft_ih == NULL &&
        sc->sc_pihp == NULL &&
        sc->sc_irq_pending[0] == 0 && sc->sc_irq_pending[1] == 0 &&
        runtime_dp_quiet(ctx);
}

int
rtwn8723be_netbsd_register_ieee80211(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime_context *ctx = NULL;
    const struct rtwn8723be_net80211_methods methods = {
        .hw_start = rtwn8723be_runtime_hw_start,
        .hw_stop = rtwn8723be_runtime_hw_stop,
        .tx_start = rtwn8723be_net80211_tx_start,
    };
    int error, unwind_error;

    error = runtime_claim(sc, R23BE_RUNTIME_REGISTER, false, &ctx);
    if (error != 0)
        return error;
    error = runtime_context_ready(sc, ctx);
    if (error != 0)
        goto out;
    if (!rtwn8723be_net80211_registration_checkpoint_ok(&sc->sc_linux) ||
        ctx->dp.prepared || ctx->dp.sc != NULL || ctx->rx.net != NULL ||
        sc->sc_net80211.registered || sc->sc_net80211.sc != NULL ||
        sc->sc_datapath != NULL || sc->sc_rx_binding != NULL) {
        error = EBUSY;
        goto out;
    }
    error = rtwn8723be_net80211_register(&sc->sc_net80211, sc, &methods);
    if (error != 0)
        goto rollback;
    error = rtwn8723be_rx_binding_init(&ctx->rx, &sc->sc_net80211,
        &ctx->firmware);
    if (error != 0)
        goto rollback;
    error = rtwn8723be_datapath_prepare(&ctx->dp, sc, &ctx->rx.dispatch,
        NULL, NULL);
    if (error == 0 && runtime_registration_owned(sc, ctx))
        goto out;
    if (error == 0) {
        ctx->faulted = true;
        error = EIO; /* A false-success publication is never accepted. */
    }
rollback:
    unwind_error = runtime_registration_rollback(sc, ctx);
    if (unwind_error != 0) {
        ctx->faulted = true;
        error = unwind_error;
    }
out:
    runtime_release(sc, R23BE_RUNTIME_REGISTER);
    return error;
}

static bool
runtime_bridge_owned(struct rtwn8723be_softc *sc,
    struct rtwn8723be_runtime_context *ctx)
{
    return runtime_bridge_identity(sc, ctx) &&
        sc->sc_ih != NULL && sc->sc_soft_ih != NULL &&
        sc->sc_pihp != NULL && sc->sc_irq_lock_initialized &&
        sc->sc_rf_ps_lock_initialized &&
        sc->sc_mapped && sc->sc_core_initialized &&
        sc->sc_rings_allocated && sc->sc_dmat != NULL &&
        sc->sc_dma_32bit && sc->sc_h2c.initialized &&
        sc->sc_h2c.sc == sc &&
        sc->sc_rfkill_native.initialized &&
        sc->sc_rfkill_native.active && sc->sc_rfkill_native.wq != NULL;
}

static bool
runtime_dp_quiet(struct rtwn8723be_runtime_context *ctx)
{
    bool quiet;

    mutex_enter(&ctx->dp.tx_lock);
    quiet = !ctx->dp.tx_enabled && !ctx->dp.stop_pending &&
        ctx->dp.tx_callback_active == 0 && ctx->dp.rx_callback_active == 0 &&
        ctx->dp.tx_start_active == 0;
    mutex_exit(&ctx->dp.tx_lock);
    return quiet;
}

static bool
runtime_irq_drained(struct rtwn8723be_softc *sc,
    struct rtwn8723be_runtime_context *ctx)
{
    bool drained;

    mutex_enter(&sc->sc_irq_lock);
    drained = ctx->irq_drained &&
        sc->sc_irq_epoch == ctx->drained_epoch &&
        !sc->sc_irq_requested && !sc->sc_irq_enabled &&
        sc->sc_irq_pending[0] == 0 && sc->sc_irq_pending[1] == 0;
    mutex_exit(&sc->sc_irq_lock);
    return drained;
}

int
rtwn8723be_runtime_hw_start(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_context *ctx = NULL;
    bool radio_on, irq_requested;
    int error;

    error = runtime_claim(sc, R23BE_RUNTIME_START, false, &ctx);
    if (error != 0)
        return error;
    error = runtime_context_ready(sc, ctx);
    if (error != 0)
        goto out;
    if (!runtime_bridge_owned(sc, ctx) ||
        !rtwn8723be_net80211_start_checkpoint_ok(&sc->sc_linux) ||
        sc->sc_hal_started || !runtime_dp_quiet(ctx) ||
        sc->sc_net80211.tx_busy ||
        sc->sc_net80211.tx_key_update_depth != 0 ||
        sc->sc_net80211.tx_pending_m != NULL ||
        sc->sc_net80211.tx_pending_ni != NULL ||
        (sc->sc_ec.ec_if.if_flags & IFF_RUNNING) != 0) {
        error = EBUSY;
        goto out;
    }
    if (sc->sc_linux.stage == R23BE_STAGE_STOPPED &&
        !runtime_irq_drained(sc, ctx)) {
        error = EBUSY;
        goto out;
    }
    mutex_enter(&sc->sc_irq_lock);
    if (sc->sc_irq_requested || sc->sc_irq_enabled) {
        mutex_exit(&sc->sc_irq_lock);
        error = EBUSY;
        goto out;
    }
    mutex_exit(&sc->sc_irq_lock);
    error = rtwn8723be_rfkill_native_radio_on(sc, &radio_on);
    if (error != 0 || !radio_on) {
        if (error == 0)
            error = ENETDOWN;
        goto out;
    }
    ctx->irq_drained = false;
    error = rtwn8723be_linux_adapter_start(sc, &sc->sc_linux,
        &rtwn8723be_netbsd_ops);
    if (error != 0) {
        ctx->faulted = true;
        goto out;
    }
    error = rtwn8723be_datapath_start(&ctx->dp);
    mutex_enter(&sc->sc_irq_lock);
    irq_requested = sc->sc_irq_requested;
    mutex_exit(&sc->sc_irq_lock);
    if (error != 0 || !runtime_bridge_owned(sc, ctx) ||
        !sc->sc_hal_started || !irq_requested ||
        !rtwn8723be_datapath_running_ready(&ctx->dp)) {
        ctx->faulted = true;
        if (error == 0)
            error = EIO;
    }
out:
    runtime_release(sc, R23BE_RUNTIME_START);
    return error;
}

/*
 * Linux STOP calls this immediately after mark_hal_stop and before RF wait
 * and hw_disable. Masking/epoch retirement alone cannot drain a softint
 * that already took pending bits and may still access HSISR directly.
 */
static int
runtime_disable_interrupt_drain(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime_owner *owner;
    struct rtwn8723be_runtime_context *ctx;
    pci_intr_handle_t *pih;
    void *ih, *soft_ih;
    uint32_t epoch;
    int error, giant_count = 0;
    bool owned, valid;

    if (sc == NULL)
        return EINVAL;
    if (!runtime_thread_ok())
        return EWOULDBLOCK;
    owner = &sc->sc_runtime_owner;
    if (!owner->initialized || mutex_owned(&owner->io_lock) ||
        mutex_owned(&owner->lifecycle_lock))
        return EBUSY;
    mutex_enter(&owner->lifecycle_lock);
    ctx = owner->context;
    owned = owner->operation == R23BE_RUNTIME_STOP &&
        owner->operation_lwp == curlwp && owner->io_depth == 0 &&
        !owner->closing && ctx != NULL;
    mutex_exit(&owner->lifecycle_lock);
    if (!owned || sc->sc_linux.stage != R23BE_STAGE_STOPPING ||
        !sc->sc_linux.started || sc->sc_hal_started ||
        !runtime_bridge_owned(sc, ctx))
        return EBUSY;
    if (mutex_owned(&ctx->dp.tx_lock) ||
        mutex_owned(&sc->sc_irq_lock) || !runtime_dp_quiet(ctx))
        return EBUSY;
    ctx->irq_drained = false;
    error = rtwn8723be_netbsd_disable_interrupt(sc);
    if (error != 0)
        return error;
    mutex_enter(&sc->sc_irq_lock);
    epoch = sc->sc_irq_epoch;
    ih = sc->sc_ih;
    soft_ih = sc->sc_soft_ih;
    pih = sc->sc_pihp;
    valid = !sc->sc_irq_requested && !sc->sc_irq_enabled &&
        sc->sc_irq_pending[0] == 0 && sc->sc_irq_pending[1] == 0;
    mutex_exit(&sc->sc_irq_lock);
    if (!valid)
        return EBUSY;

    /* No owner/DP/IRQ/I/O lock is held; let non-MPSAFE softints take Giant. */
    if (KERNEL_LOCKED_P())
        KERNEL_UNLOCK_ALL(NULL, &giant_count);
    xc_barrier(XC_HIGHPRI_IPL(IPL_SOFTNET));
    KERNEL_LOCK(giant_count, NULL);

    mutex_enter(&sc->sc_irq_lock);
    valid = sc->sc_irq_epoch == epoch && !sc->sc_irq_requested &&
        !sc->sc_irq_enabled && sc->sc_irq_pending[0] == 0 &&
        sc->sc_irq_pending[1] == 0 &&
        sc->sc_ih == ih && sc->sc_soft_ih == soft_ih && sc->sc_pihp == pih;
    mutex_exit(&sc->sc_irq_lock);
    if (!valid)
        return EBUSY;
    ctx->drained_epoch = epoch;
    ctx->irq_drained = true;
    return 0;
}

int
rtwn8723be_runtime_hw_stop(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_context *ctx = NULL;
    struct rtwn8723be_linux_ops ops;
    int error;

    /* An orphan RUNNING start failure still has a genuine stop obligation. */
    error = runtime_claim(sc, R23BE_RUNTIME_STOP, true, &ctx);
    if (error != 0)
        return error;
    error = runtime_context_ready(sc, ctx);
    if (error != 0)
        goto out;
    if (!runtime_bridge_owned(sc, ctx) ||
        !rtwn8723be_net80211_running_hw_stop_needed(&sc->sc_linux) ||
        sc->sc_net80211.tx_busy ||
        sc->sc_net80211.tx_key_update_depth != 0) {
        error = EBUSY;
        goto out;
    }
    /* Direct native STOP callers revoke logical dequeue after admission. */
    sc->sc_ec.ec_if.if_flags &= ~(IFF_RUNNING | IFF_OACTIVE);
    sc->sc_ec.ec_if.if_timer = 0;
    ops = rtwn8723be_netbsd_ops;
    ops.disable_interrupt = runtime_disable_interrupt_drain;
    ctx->irq_drained = false;
    error = rtwn8723be_linux_adapter_stop(sc, &sc->sc_linux, &ops);
    if (error != 0) {
        if (sc->sc_linux.stage != R23BE_STAGE_RUNNING ||
            error != EBUSY)
            ctx->faulted = true;
        goto out;
    }
    if (sc->sc_linux.stage != R23BE_STAGE_STOPPED ||
        sc->sc_linux.started || sc->sc_linux.fw_ready ||
        sc->sc_linux.mac_func_enable || sc->sc_linux.being_init_adapter ||
        sc->sc_hal_started || !runtime_dp_quiet(ctx) ||
        !runtime_irq_drained(sc, ctx)) {
        ctx->faulted = true;
        error = EIO;
    } else {
        ctx->faulted = false;
    }
out:
    runtime_release(sc, R23BE_RUNTIME_STOP);
    return error;
}


/*
 * Provider storage is device-owned; pure configuration is not hardware
 * readiness.  Each accepted BTC entry pins this stable bridge before it may
 * inspect mutable BTC state.  An I/O reservation additionally excludes all
 * lifecycle changes while waiting for/holding the sleepable I/O mutex.
 */
static const struct rtwn8723be_btc_native_owner runtime_btc_owner;
static const struct rtwn8723be_btc_policy_ops runtime_policy_ops;

static bool
runtime_ports_ok(const struct rtwn8723be_btc_policy_ops *p)
{
    return p != NULL && p->snapshot != NULL && p->clock_msec != NULL &&
        p->aggregate_apply != NULL && p->lps_enter != NULL &&
        p->lps_leave != NULL && p->bt_query != NULL && p->fault != NULL;
}

int
rtwn8723be_runtime_provider_configure(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_btc_policy_ops *ports, void *arg)
{
    struct rtwn8723be_runtime_context *ctx = NULL;
    struct rtwn8723be_btc_policy policy;
    struct rtwn8723be_dm_state dm;
    int error;

    if (sc == NULL || arg != sc)
        return EINVAL;
    if (!runtime_ports_ok(ports))
        return ENOSYS;
    error = runtime_claim(sc, R23BE_RUNTIME_CONFIGURE, false, &ctx);
    if (error != 0)
        return error;
    if (ctx == NULL)
        error = ENOSYS; /* The immutable C2H bridge must exist first. */
    else if (ctx->providers_configured)
        error = EALREADY;
    else if (runtime_publication_present(sc))
        error = EBUSY;
    else {
        memset(&policy, 0, sizeof(policy));
        error = rtwn8723be_btc_policy_init(&policy, &runtime_policy_ops, sc);
        if (error == 0) {
            rtwn8723be_dm_construct(&dm); /* real cold sw_vars, once/device */
            mutex_enter(&sc->sc_runtime_owner.lifecycle_lock);
            ctx->ports = *ports;
            ctx->policy = policy;
            ctx->dm = dm;
            ctx->providers_configured = true;
            mutex_exit(&sc->sc_runtime_owner.lifecycle_lock);
        }
    }
    runtime_release(sc, R23BE_RUNTIME_CONFIGURE);
    return error;
}

static bool
runtime_btc_phase(struct rtwn8723be_softc *sc,
    struct rtwn8723be_runtime_context *ctx, bool halt)
{
    struct rtwn8723be_runtime_owner *o = &sc->sc_runtime_owner;

    if (ctx == NULL || !ctx->providers_configured || !ctx->btc_prepared ||
        !ctx->policy.initialized || !sc->sc_btc.initialized ||
        sc->sc_btc.owner != &runtime_btc_owner || sc->sc_btc.owner_arg != sc ||
        sc->sc_btc.engine.btc.adapter != sc ||
        sc->sc_btc.engine.btc.r23be_policy != &ctx->policy)
        return false;
    if (o->operation == R23BE_RUNTIME_START)
        return o->operation_lwp == curlwp &&
            sc->sc_linux.being_init_adapter && !sc->sc_linux.started &&
            sc->sc_linux.stage == R23BE_STAGE_BT_HW;
    if (halt && o->operation == R23BE_RUNTIME_STOP)
        return o->operation_lwp == curlwp && sc->sc_linux.started &&
            sc->sc_linux.stage == R23BE_STAGE_STOPPING;
    return o->operation == R23BE_RUNTIME_NONE &&
        o->operation_lwp == NULL && sc->sc_linux.started &&
        sc->sc_hal_started && sc->sc_linux.stage == R23BE_STAGE_RUNNING;
}

/* Admission never sleeps and is safe in the copied C2H SOFTINT_NET path. */
int
rtwn8723be_runtime_btc_admit(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_owner *o;
    struct rtwn8723be_runtime_context *ctx;
    int error = 0;

    if (sc == NULL)
        return EINVAL;
    if (cpu_intr_p())
        return EWOULDBLOCK;
    o = &sc->sc_runtime_owner;
    if (!o->initialized)
        return ENXIO;
    if (mutex_owned(&o->lifecycle_lock))
        return EDEADLK;
    mutex_enter(&o->lifecycle_lock);
    ctx = o->context;
    /* Reject stage/operation before inspecting a potentially retired BTC. */
    if (o->closing || ctx == NULL || !ctx->providers_configured ||
        !ctx->btc_prepared ||
        (o->operation != R23BE_RUNTIME_NONE &&
         (o->operation != R23BE_RUNTIME_START ||
          o->operation_lwp != curlwp || !runtime_thread_ok())) ||
        (o->operation == R23BE_RUNTIME_NONE &&
         (!sc->sc_linux.started || !sc->sc_hal_started ||
          sc->sc_linux.stage != R23BE_STAGE_RUNNING)))
        error = EAGAIN;
    else if (ctx->provider_error != 0 || ctx->faulted)
        error = ctx->provider_error != 0 ? ctx->provider_error : EIO;
    else if (!runtime_btc_phase(sc, ctx, false))
        error = ENXIO;
    else if (mutex_owned(&sc->sc_btc.engine_lock) ||
        mutex_owned(&o->io_lock))
        error = EDEADLK;
    else if (ctx->pending_btc == (unsigned int)-1)
        error = EOVERFLOW;
    else
        ctx->pending_btc++;
    mutex_exit(&o->lifecycle_lock);
    return error;
}

void
rtwn8723be_runtime_btc_drop(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_owner *o = &sc->sc_runtime_owner;
    struct rtwn8723be_runtime_context *ctx;

    mutex_enter(&o->lifecycle_lock);
    ctx = o->context; /* pending_btc is the real lifetime pin. */
    KASSERT(ctx != NULL && ctx->pending_btc != 0);
    if (ctx != NULL && ctx->pending_btc != 0)
        ctx->pending_btc--;
    else if (ctx != NULL) {
        ctx->faulted = true;
        ctx->provider_error = EIO;
    }
    mutex_exit(&o->lifecycle_lock);
}

static bool
runtime_io_phase(struct rtwn8723be_softc *sc,
    struct rtwn8723be_runtime_context *ctx, enum runtime_io_kind kind)
{
    struct rtwn8723be_runtime_owner *o = &sc->sc_runtime_owner;

    if (ctx == NULL || !ctx->providers_configured ||
        !ctx->policy.initialized || !sc->sc_mapped ||
        !sc->sc_core_initialized || !sc->sc_rf_ps_lock_initialized ||
        !sc->sc_bb_valid || !sc->sc_rf_chnlval_valid ||
        !sc->sc_phy_identity_valid || !sc->sc_phy_identity.pci_interface ||
        !sc->sc_rf_path_count_valid ||
        sc->sc_rf_path_count != 1U || !sc->sc_linux.fw_ready ||
        !sc->sc_h2c.initialized)
        return false;
    if (kind == R23BE_IO_BTC)
        return runtime_btc_phase(sc, ctx, true) &&
            (ctx->pending_btc != 0 ||
             (o->operation == R23BE_RUNTIME_STOP &&
              o->operation_lwp == curlwp));
    return kind == R23BE_IO_DM && ctx->btc_prepared &&
        sc->sc_btc.initialized && sc->sc_btc.engine.btc.initialized &&
        sc->sc_btc.owner == &runtime_btc_owner &&
        sc->sc_btc.owner_arg == sc &&
        sc->sc_btc.engine.btc.adapter == sc &&
        sc->sc_btc.engine.btc.r23be_policy == &ctx->policy &&
        o->operation == R23BE_RUNTIME_START && o->operation_lwp == curlwp &&
        sc->sc_linux.being_init_adapter && !sc->sc_linux.started &&
        sc->sc_linux.stage == R23BE_STAGE_DM_INIT && sc->sc_xtal_valid &&
        sc->sc_xtal_cap <= 0x3fU &&
        sc->sc_mapsize >= R23BE_DM_ATC_REG + sizeof(uint32_t);
}

static int
runtime_io_acquire(struct rtwn8723be_softc *sc, enum runtime_io_kind kind)
{
    struct rtwn8723be_runtime_owner *o;
    struct rtwn8723be_runtime_context *ctx;
    int error = 0, giant_count = 0;
    unsigned int waited = 0;

    if (sc == NULL)
        return EINVAL;
    if (!runtime_thread_ok())
        return EWOULDBLOCK;
    o = &sc->sc_runtime_owner;
    if (!o->initialized)
        return ENXIO;
    if (runtime_caller_locks_held(sc))
        return EBUSY;
    mutex_enter(&o->lifecycle_lock);
    ctx = o->context;
    if (o->closing || !runtime_io_phase(sc, ctx, kind))
        error = EAGAIN;
    else if (ctx->provider_error != 0)
        error = ctx->provider_error;
    else if (o->io_depth == (unsigned int)-1)
        error = EOVERFLOW;
    else
        o->io_depth++; /* reserves storage before any sleep */
    mutex_exit(&o->lifecycle_lock);
    if (error != 0)
        return error;
    /* A producer may need Giant; no waiter may retain it across this lease. */
    if (KERNEL_LOCKED_P())
        KERNEL_UNLOCK_ALL(NULL, &giant_count);
    mutex_enter(&o->io_lock);
    mutex_enter(&o->lifecycle_lock);
    if (o->context != ctx || o->closing ||
        !runtime_io_phase(sc, ctx, kind))
        error = ENXIO;
    else if (ctx->provider_error != 0)
        error = ctx->provider_error;
    mutex_exit(&o->lifecycle_lock);
    if (error == 0) {
        /* A short RF-kill sample may already own RF; never steal its hold. */
        for (;;) {
            mutex_enter(&sc->sc_rf_ps_lock);
            if (!sc->sc_rfchange_inprogress) {
                sc->sc_rfchange_inprogress = true;
                mutex_exit(&sc->sc_rf_ps_lock);
                break;
            }
            mutex_exit(&sc->sc_rf_ps_lock);
            if (waited++ >= 100U) {
                error = ETIMEDOUT;
                break;
            }
            delay(1000);
        }
    }
    mutex_enter(&o->lifecycle_lock);
    if (error == 0) {
        ctx->io_lwp = curlwp;
        ctx->io_kind = kind;
        ctx->io_giant_count = giant_count;
        ctx->rf_owned = true;
    } else {
        KASSERT(o->io_depth != 0);
        o->io_depth--;
    }
    mutex_exit(&o->lifecycle_lock);
    if (error != 0) {
        mutex_exit(&o->io_lock);
        KERNEL_LOCK(giant_count, NULL);
    }
    return error;
}

static bool
runtime_io_ready(struct rtwn8723be_softc *sc, enum runtime_io_kind kind)
{
    struct rtwn8723be_runtime_owner *o;
    struct rtwn8723be_runtime_context *ctx;
    bool ready, rf;

    if (sc == NULL || !runtime_thread_ok())
        return false;
    o = &sc->sc_runtime_owner;
    if (!o->initialized || !mutex_owned(&o->io_lock))
        return false;
    mutex_enter(&o->lifecycle_lock);
    ctx = o->context;
    ready = !o->closing && o->io_depth != 0 && ctx != NULL &&
        ctx->io_lwp == curlwp && ctx->io_kind == kind &&
        ctx->rf_owned && ctx->provider_error == 0 &&
        runtime_io_phase(sc, ctx, kind);
    mutex_exit(&o->lifecycle_lock);
    if (!ready)
        return false;
    mutex_enter(&sc->sc_rf_ps_lock);
    rf = sc->sc_rfchange_inprogress;
    mutex_exit(&sc->sc_rf_ps_lock);
    return rf;
}

static void
runtime_io_release(struct rtwn8723be_softc *sc, int error)
{
    struct rtwn8723be_runtime_owner *o = &sc->sc_runtime_owner;
    struct rtwn8723be_runtime_context *ctx;
    int giant_count;

    KASSERT(mutex_owned(&o->io_lock));
    mutex_enter(&o->lifecycle_lock);
    ctx = o->context;
    KASSERT(ctx != NULL && ctx->io_lwp == curlwp && o->io_depth != 0);
    giant_count = ctx->io_giant_count;
    if (error != 0 && ctx->provider_error == 0)
        ctx->provider_error = error;
    mutex_exit(&o->lifecycle_lock);
    mutex_enter(&sc->sc_rf_ps_lock);
    if (ctx->rf_owned && sc->sc_rfchange_inprogress)
        sc->sc_rfchange_inprogress = false;
    else if (error == 0)
        error = EIO;
    mutex_exit(&sc->sc_rf_ps_lock);
    mutex_enter(&o->lifecycle_lock);
    if (error != 0 && ctx->provider_error == 0)
        ctx->provider_error = error;
    ctx->rf_owned = false;
    ctx->io_lwp = NULL;
    ctx->io_kind = R23BE_IO_NONE;
    ctx->io_giant_count = 0;
    o->io_depth--;
    mutex_exit(&o->lifecycle_lock);
    mutex_exit(&o->io_lock);
    KERNEL_LOCK(giant_count, NULL);
}

static struct rtwn8723be_runtime_context *
runtime_policy_context(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    return runtime_io_ready(sc, R23BE_IO_BTC) &&
        mutex_owned(&sc->sc_btc.engine_lock) &&
        sc->sc_btc.first_error == 0 ?
        sc->sc_runtime_owner.context : NULL;
}

static int
runtime_snapshot(void *arg, struct rtwn8723be_btc_wifi_snapshot *v)
{
    struct rtwn8723be_runtime_context *c = runtime_policy_context(arg);
    return c != NULL ? c->ports.snapshot(arg, v) : ENXIO;
}
static int
runtime_clock(void *arg, uint64_t *v)
{
    struct rtwn8723be_runtime_context *c = runtime_policy_context(arg);
    return c != NULL ? c->ports.clock_msec(arg, v) : ENXIO;
}
static int
runtime_aggregate(void *arg, const struct btc_bt_info *v)
{
    struct rtwn8723be_runtime_context *c = runtime_policy_context(arg);
    return c != NULL ? c->ports.aggregate_apply(arg, v) : ENXIO;
}
static int
runtime_lps_enter(void *arg)
{
    struct rtwn8723be_runtime_context *c = runtime_policy_context(arg);
    return c != NULL ? c->ports.lps_enter(arg) : ENXIO;
}
static int
runtime_lps_leave(void *arg)
{
    struct rtwn8723be_runtime_context *c = runtime_policy_context(arg);
    return c != NULL ? c->ports.lps_leave(arg) : ENXIO;
}
static int
runtime_bt_query(void *arg, struct btc_coexist *btc,
    enum rtwn8723be_btc_policy_bt_query query, uint32_t *v)
{
    struct rtwn8723be_runtime_context *c = runtime_policy_context(arg);
    return c != NULL ? c->ports.bt_query(arg, btc, query, v) : ENXIO;
}
static void
runtime_policy_fault(void *arg, int error)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime_owner *o;
    struct rtwn8723be_runtime_context *ctx;
    bool notify = false;

    if (sc == NULL || error == 0)
        return;
    o = &sc->sc_runtime_owner;
    if (!o->initialized || !mutex_owned(&o->io_lock))
        return;
    mutex_enter(&o->lifecycle_lock);
    ctx = o->context;
    if (ctx == NULL || o->io_depth == 0 || ctx->io_lwp != curlwp ||
        ctx->io_kind != R23BE_IO_BTC || !ctx->btc_prepared ||
        !sc->sc_btc.initialized ||
        !mutex_owned(&sc->sc_btc.engine_lock)) {
        mutex_exit(&o->lifecycle_lock);
        return;
    }
    /*
     * Low-level providers record a failure before the frozen algorithm
     * finishes.  Suppressed policy requests return ENXIO, which must never
     * replace that first native error or notify the supplier repeatedly.
     * The active lease and owned engine lock protect this child access.
     */
    if (sc->sc_btc.first_error != 0)
        error = sc->sc_btc.first_error;
    if (ctx->provider_error == 0) {
        ctx->provider_error = error;
        notify = true;
    } else
        error = ctx->provider_error;
    mutex_exit(&o->lifecycle_lock);
    rtwn8723be_btc_native_provider_error(sc, error);
    if (notify)
        ctx->ports.fault(sc, error);
}

static const struct rtwn8723be_btc_policy_ops runtime_policy_ops = {
    .snapshot = runtime_snapshot, .clock_msec = runtime_clock,
    .aggregate_apply = runtime_aggregate, .lps_enter = runtime_lps_enter,
    .lps_leave = runtime_lps_leave, .bt_query = runtime_bt_query,
    .fault = runtime_policy_fault,
};

static int
runtime_btc_acquire(void *arg, struct rtwn8723be_softc *sc)
{
    return arg == sc ? runtime_io_acquire(sc, R23BE_IO_BTC) : EINVAL;
}
static bool
runtime_btc_ready(void *arg, struct rtwn8723be_softc *sc)
{
    return arg == sc && runtime_io_ready(sc, R23BE_IO_BTC);
}
static void
runtime_btc_release(void *arg, struct rtwn8723be_softc *sc, int error)
{
    int fault_error;

    KASSERT(arg == sc);
    (void)error; /* The caller keeps its own validation/execution result. */
    /*
     * Async enqueue can publish a native fault after event validation.
     * Snapshot that first fault, never attribute a per-call validation
     * result to a separately observed queue fault.  The active lease
     * retains this child; drop its queue lock before broker release.
     */
    mutex_enter(&sc->sc_btc.queue_lock);
    fault_error = sc->sc_btc.faulted ? sc->sc_btc.last_error : 0;
    mutex_exit(&sc->sc_btc.queue_lock);
    runtime_io_release(sc, fault_error);
}

static const struct rtwn8723be_btc_native_owner runtime_btc_owner = {
    .acquire = runtime_btc_acquire, .ready = runtime_btc_ready,
    .release = runtime_btc_release,
};

static int
runtime_bind_lowlevel(void *arg, struct btc_coexist *btc)
{
    return rtwn8723be_btc_native_seed_lowlevel(btc, arg);
}
static int
runtime_bind_policy(void *arg, struct btc_coexist *btc)
{
    struct rtwn8723be_softc *sc = arg;
    return rtwn8723be_btc_policy_bind(btc,
        &sc->sc_runtime_owner.context->policy);
}

int
rtwn8723be_netbsd_bt_prepare(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime_context *ctx;
    struct rtwn8723be_runtime_owner *o;
    struct rtwn8723be_btc_context_identity identity;
    struct rtwn8723be_btc_context_binders binders;
    struct btc_coexist btc;
    bool owned;
    int error;

    if (sc == NULL)
        return EINVAL;
    if (!runtime_thread_ok())
        return EWOULDBLOCK;
    o = &sc->sc_runtime_owner;
    if (!o->initialized)
        return ENXIO;
    if (runtime_caller_locks_held(sc))
        return EBUSY;
    mutex_enter(&o->lifecycle_lock);
    ctx = o->context;
    owned = !o->closing && o->operation == R23BE_RUNTIME_START &&
        o->operation_lwp == curlwp && o->io_depth == 0 &&
        ctx != NULL && ctx->providers_configured &&
        ctx->policy.initialized && ctx->pending_btc == 0 &&
        !ctx->btc_prepared && ctx->provider_error == 0;
    mutex_exit(&o->lifecycle_lock);
    if (!owned || !runtime_bridge_owned(sc, ctx) ||
        !sc->sc_mapped || !sc->sc_core_initialized ||
        !sc->sc_rings_allocated ||
        sc->sc_linux.stage != R23BE_STAGE_BT_PREPARE ||
        sc->sc_linux.started || sc->sc_hal_started ||
        !sc->sc_bt_ant_valid || !sc->sc_package_valid ||
        sc->sc_btc.initialized)
        return EAGAIN;
    memset(&identity, 0, sizeof(identity));
    identity.adapter = sc;
    identity.identity_valid = true; /* actual parsed flags checked above */
    identity.hwpg_bt_present = sc->sc_btcoexist;
    identity.raw_ant_num = sc->sc_btdm_ant_num;
    identity.single_ant_path = sc->sc_single_ant_path;
    identity.package_type = sc->sc_package_type;
    binders.lowlevel.bind = runtime_bind_lowlevel;
    binders.lowlevel.arg = sc;
    binders.policy.bind = runtime_bind_policy;
    binders.policy.arg = sc;
    error = rtwn8723be_btc_context_build(&btc, &identity, &binders);
    if (error != 0)
        return error;
    error = rtwn8723be_btc_native_init(sc, &btc, &runtime_btc_owner, sc);
    if (error == 0) {
        mutex_enter(&o->lifecycle_lock);
        ctx->btc_prepared = true;
        mutex_exit(&o->lifecycle_lock);
    }
    return error;
}


int
rtwn8723be_runtime_btc_stop_ready(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_owner *o;
    struct rtwn8723be_runtime_context *ctx;
    bool ready;
    if (sc == NULL)
        return EINVAL;
    if (!runtime_thread_ok())
        return EWOULDBLOCK;
    o = &sc->sc_runtime_owner;
    if (!o->initialized || runtime_caller_locks_held(sc))
        return EBUSY;
    mutex_enter(&o->lifecycle_lock);
    ctx = o->context;
    ready = !o->closing && o->operation == R23BE_RUNTIME_STOP &&
        o->operation_lwp == curlwp && o->io_depth == 0 &&
        ctx != NULL && ctx->btc_prepared && ctx->pending_btc == 0 &&
        sc->sc_linux.stage == R23BE_STAGE_STOPPING && sc->sc_linux.started;
    /* The STOP claim pins this child; inspect its locks only after admission. */
    if (ready)
        ready = sc->sc_btc.initialized &&
            sc->sc_btc.owner == &runtime_btc_owner &&
            sc->sc_btc.owner_arg == sc &&
            !mutex_owned(&sc->sc_btc.engine_lock);
    mutex_exit(&o->lifecycle_lock);
    return ready ? 0 : EBUSY;
}

/* Called only after genuine HALT/fini, outside all child/IO locks. */
int
rtwn8723be_runtime_btc_retire(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_owner *o;
    struct rtwn8723be_runtime_context *ctx;
    int error;

    if (sc == NULL || !runtime_thread_ok())
        return EINVAL;
    o = &sc->sc_runtime_owner;
    if (!o->initialized || runtime_caller_locks_held(sc))
        return EBUSY;
    mutex_enter(&o->lifecycle_lock);
    ctx = o->context;
    if (o->closing || o->operation != R23BE_RUNTIME_STOP ||
        o->operation_lwp != curlwp || o->io_depth != 0 ||
        ctx == NULL || !ctx->btc_prepared || ctx->pending_btc != 0 ||
        sc->sc_linux.stage != R23BE_STAGE_STOPPING ||
        !sc->sc_linux.started || sc->sc_btc.initialized) {
        mutex_exit(&o->lifecycle_lock);
        return EBUSY;
    }
    mutex_exit(&o->lifecycle_lock);
    /* Core owns final MP storage destruction; never invent activation. */
    error = rtwn8723be_btc_mp_native_stop(sc);
    if (error != 0)
        return error;
    mutex_enter(&o->lifecycle_lock);
    ctx->btc_prepared = false;
    /* The DM/thermal and policy aggregation histories remain device-owned. */
    mutex_exit(&o->lifecycle_lock);
    return 0;
}

static bool
runtime_dm_ready(void *arg)
{
    return runtime_io_ready(arg, R23BE_IO_DM);
}
static int
runtime_dm_read(void *arg, uint32_t reg, uint32_t mask, uint32_t *value)
{
    struct rtwn8723be_softc *sc = arg;
    if (!runtime_dm_ready(sc))
        return ENXIO;
    if (value == NULL ||
        !((reg == R23BE_DM_AGC_REG && mask == R23BE_DM_AGC_MASK) ||
          (reg == R23BE_DM_ATC_REG && mask == R23BE_DM_ATC_MASK)) ||
        reg > sc->sc_mapsize || sc->sc_mapsize - reg < sizeof(uint32_t))
        return EINVAL;
    *value = rtwn8723be_netbsd_get_bbreg(sc, reg, mask);
    return 0;
}
int
rtwn8723be_netbsd_dm_init(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime_context *ctx;
    const struct rtwn8723be_dm_io io = {
        .ready = runtime_dm_ready, .read_bb = runtime_dm_read,
    };
    int error;

    error = runtime_io_acquire(sc, R23BE_IO_DM);
    if (error != 0)
        return error;
    ctx = sc->sc_runtime_owner.context;
    error = rtwn8723be_dm_init(&ctx->dm, &io, sc, sc->sc_xtal_cap);
    runtime_io_release(sc, error);
    return error;
}

static bool
runtime_private_publication_present(struct rtwn8723be_runtime_context *ctx)
{
    return ctx != NULL && (ctx->pending_btc != 0 || ctx->btc_prepared ||
        ctx->io_lwp != NULL || ctx->io_kind != R23BE_IO_NONE ||
        ctx->io_giant_count != 0 || ctx->rf_owned ||
        ctx->dp.prepared || ctx->dp.sc != NULL ||
        ctx->dp.rx.arg != NULL || ctx->dp.rx.frame != NULL ||
        ctx->dp.rx.c2h != NULL || ctx->dp.tx_complete != NULL ||
        ctx->dp.tx_complete_arg != NULL || ctx->dp.tx_enabled ||
        ctx->dp.stop_pending || ctx->dp.tx_callback_active != 0 ||
        ctx->dp.rx_callback_active != 0 || ctx->dp.tx_start_active != 0 ||
        ctx->rx.net != NULL || ctx->rx.dispatch.arg != NULL ||
        ctx->rx.dispatch.frame != NULL || ctx->rx.dispatch.c2h != NULL ||
        ctx->rx.firmware.arg != NULL || ctx->rx.firmware.tx_report != NULL ||
        ctx->rx.firmware.ra_report != NULL ||
        ctx->rx.firmware.bt_info != NULL || ctx->rx.firmware.bt_mp != NULL);
}

int
rtwn8723be_runtime_owner_fini(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_owner *owner;
    struct rtwn8723be_runtime_context *ctx;

    if (sc == NULL)
        return EINVAL;
    if (!runtime_thread_ok())
        return EWOULDBLOCK;
    owner = &sc->sc_runtime_owner;
    /*
     * An inconsistent non-NULL context with initialized=false is retained
     * without dereferencing it. Check external owners in release builds
     * before the outer context can destroy IRQ/RF locks or lose storage.
     */
    if (!owner->initialized) {
        if (runtime_publication_present(sc) ||
            sc->sc_calibration_owner != NULL ||
            sc->sc_calibration_owner_arg != NULL ||
            sc->sc_hw_disable_owner != NULL ||
            sc->sc_hw_disable_owner_arg != NULL ||
            owner->context != NULL || owner->io_depth != 0 ||
            owner->operation != R23BE_RUNTIME_NONE ||
            owner->operation_lwp != NULL || owner->closing)
            return EBUSY;
        return runtime_caller_locks_held(sc) ? EBUSY : 0;
    }
    if (runtime_caller_locks_held(sc) ||
        !mutex_tryenter(&owner->lifecycle_lock))
        return EBUSY;
    if (owner->closing || owner->io_depth != 0 ||
        owner->operation != R23BE_RUNTIME_NONE ||
        owner->operation_lwp != NULL ||
        runtime_publication_present(sc) ||
        sc->sc_calibration_owner != NULL ||
        sc->sc_calibration_owner_arg != NULL ||
        sc->sc_hw_disable_owner != NULL ||
        sc->sc_hw_disable_owner_arg != NULL ||
        runtime_private_publication_present(owner->context)) {
        mutex_exit(&owner->lifecycle_lock);
        return EBUSY;
    }
    owner->closing = true;
    owner->operation = R23BE_RUNTIME_RETIRE;
    owner->operation_lwp = curlwp;
    ctx = owner->context;
    owner->context = NULL;
    mutex_exit(&owner->lifecycle_lock);
    /* External detach excludes all new callers before mutex destruction. */
    if (ctx != NULL) {
        rtwn8723be_btc_policy_fini(&ctx->policy);
        kmem_free(ctx, sizeof(*ctx));
    }
    mutex_destroy(&owner->io_lock);
    mutex_destroy(&owner->lifecycle_lock);
    owner->initialized = false;
    owner->closing = false;
    owner->operation = R23BE_RUNTIME_NONE;
    owner->operation_lwp = NULL;
    return 0;
}
