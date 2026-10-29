/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Optional NetBSD SOFTINT_NET bridge for the existing PCI IRQ dispatcher,
 * source-based RX drain and TX enqueue/reclaim implementations.
 * This is NOT the missing net80211 or H2C implementation.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <sys/mutex.h>

#include "rtwn8723be_datapath.h"

static void
rtwn8723be_dp_rx(void *arg)
{
    struct rtwn8723be_datapath *dp = arg;
    size_t delivered = 0;
    int error;

    if (dp == NULL || !dp->prepared || dp->sc == NULL)
        return;

    /*
     * The IRQ softint borrows the DMA rings and frame/C2H handlers.
     * Acquire one RX-drain lifetime reference under the SAME TX/STOPPING
     * serializer before accessing DMA or calling a borrowed consumer.
     * A STOP that overtakes a queued softint leaves the ring untouched.
     */
    mutex_enter(&dp->tx_lock);
    if (!dp->tx_enabled || dp->sc->sc_datapath != dp ||
        dp->sc->sc_irq_arg != dp || !dp->sc->sc_irq_dispatch_ready ||
        !dp->sc->sc_linux.started || !dp->sc->sc_linux.fw_ready ||
        dp->sc->sc_linux.stage != R23BE_STAGE_RUNNING ||
        dp->rx.frame == NULL || dp->rx.c2h == NULL) {
        mutex_exit(&dp->tx_lock);
        return;
    }
    dp->rx_callback_active++;
    mutex_exit(&dp->tx_lock);

    /*
     * Never hold the TX spin mutex across RX DMA and net80211 callbacks.
     * RX ring OWN rearm and borrowed buffers remain the native drain's
     * responsibility; the outer IRQ owner must still drain softint.
     */
    error = rtwn8723be_rx_native_drain(dp->sc, &dp->rx, &delivered);

    mutex_enter(&dp->tx_lock);
    dp->rx_delivered += delivered;
    if (error != 0 && dp->rx_error == 0)
        dp->rx_error = error;
    KASSERT(dp->rx_callback_active != 0);
    dp->rx_callback_active--;
    mutex_exit(&dp->tx_lock);
}

static void
rtwn8723be_dp_tx_done(void *arg, unsigned int qid)
{
    struct rtwn8723be_datapath *dp = arg;
    void (*notify)(void *, unsigned int, size_t) = NULL;
    void *notify_arg = NULL;
    size_t reclaimed = 0;
    int error;

    if (dp == NULL || !dp->prepared ||
        qid >= RTWN8723BE_TX_QUEUE_COUNT)
        return;

    /* Serialize ring consumer against concurrent ifnet send producer. */
    mutex_enter(&dp->tx_lock);
    /*
     * A late softint after STOPPING must not DMA-sync a retired ring or
     * wake net80211. Leave remaining descriptors to the explicit device
     * quiesce/recovery owner; never reclaim speculatively after stop.
     */
    if (!dp->tx_enabled || dp->sc == NULL ||
        dp->sc->sc_datapath != dp || dp->sc->sc_irq_arg != dp ||
        !dp->sc->sc_linux.started || !dp->sc->sc_linux.fw_ready ||
        dp->sc->sc_linux.stage != R23BE_STAGE_RUNNING) {
        mutex_exit(&dp->tx_lock);
        return;
    }
    error = rtwn8723be_tx_native_reclaim(dp->sc, qid, &reclaimed);
    if (error != 0 && dp->tx_error == 0)
        dp->tx_error = error;
    dp->tx_reclaimed += reclaimed;
    if (error == 0 && reclaimed != 0 && dp->tx_complete != NULL) {
        /*
         * Publish a lifetime reference BEFORE releasing the TX lock.
         * A concurrent unprepare may not retire the callback or destroy
         * this lock until the externally executing callback returns.
         */
        dp->tx_callback_active++;
        notify = dp->tx_complete;
        notify_arg = dp->tx_complete_arg;
    }
    mutex_exit(&dp->tx_lock);

    /* Never invoke a reentrant net80211 completion under the TX lock. */
    if (notify != NULL) {
        notify(notify_arg, qid, reclaimed);
        mutex_enter(&dp->tx_lock);
        KASSERT(dp->tx_callback_active != 0);
        dp->tx_callback_active--;
        mutex_exit(&dp->tx_lock);
    }
}

int
rtwn8723be_datapath_prepare(struct rtwn8723be_datapath *dp,
    struct rtwn8723be_softc *sc,
    const struct rtwn8723be_rx_dispatch *rx,
    void (*tx_complete)(void *, unsigned int, size_t),
    void *tx_complete_arg)
{
    struct rtwn8723be_irq_dispatch irq;
    int error;

    if (dp == NULL || sc == NULL || rx == NULL ||
        rx->frame == NULL || rx->c2h == NULL)
        return EINVAL;
    /* dp storage must be zero-initialized by its owning attach path. */
    if (dp->prepared || sc->sc_datapath != NULL ||
        sc->sc_irq_dispatch_ready || sc->sc_irq_arg != NULL ||
        sc->sc_irq_dispatch.rx != NULL ||
        sc->sc_irq_dispatch.tx_done != NULL ||
        sc->sc_irq_dispatch.power_event != NULL ||
        sc->sc_ih != NULL || sc->sc_soft_ih != NULL ||
        sc->sc_pihp != NULL)
        return EBUSY;
    if (!sc->sc_core_initialized || !sc->sc_rings_allocated ||
        sc->sc_dmat == NULL || !sc->sc_dma_32bit)
        return ENXIO;

    memset(dp, 0, sizeof(*dp));
    dp->sc = sc;
    dp->rx = *rx;
    dp->tx_complete = tx_complete;
    dp->tx_complete_arg = tx_complete_arg;
    mutex_init(&dp->tx_lock, MUTEX_DEFAULT, IPL_NET);
    dp->prepared = true;
    /* Publish owner before IRQ dispatch; never leave an orphan TX mutex. */
    sc->sc_datapath = dp;

    memset(&irq, 0, sizeof(irq));
    irq.rx = rtwn8723be_dp_rx;
    irq.tx_done = rtwn8723be_dp_tx_done;
    error = rtwn8723be_netbsd_irq_set_dispatch(sc, &irq, dp);
    if (error != 0) {
        /* Publication failed: no callback owns the native TX mutex. */
        sc->sc_datapath = NULL;
        dp->prepared = false;
        mutex_destroy(&dp->tx_lock);
        memset(dp, 0, sizeof(*dp));
        return error;
    }
    return 0;
}

int
rtwn8723be_datapath_start(struct rtwn8723be_datapath *dp)
{
    struct rtwn8723be_softc *sc;
    int error = 0;

    if (dp == NULL || !dp->prepared || dp->sc == NULL)
        return EINVAL;
    sc = dp->sc;

    /*
     * Validate owner and runtime state under the SAME lock that publishes
     * tx_enabled and serializes descriptor enqueue and reclaim. A STOP
     * or owner transition before mutex acquisition must not reenable TX
     * using the stale pre-lock snapshot.
     *
     * The external runtime owner still must serialize its STOPPING state
     * transition with this mutex; this check does not invent that owner.
     */
    mutex_enter(&dp->tx_lock);
    if (sc->sc_datapath != dp || sc->sc_irq_arg != dp ||
        dp->stop_pending)
        error = EBUSY;
    else if (!sc->sc_linux.started ||
        sc->sc_linux.stage != R23BE_STAGE_RUNNING ||
        !sc->sc_linux.fw_ready ||
        !sc->sc_irq_dispatch_ready || sc->sc_ih == NULL ||
        !sc->sc_mapped || !sc->sc_rings_allocated)
        error = EAGAIN;
    else
        dp->tx_enabled = true;
    mutex_exit(&dp->tx_lock);
    return error;
}

/*
 * Net80211 may publish IFF_RUNNING only after the actual datapath bridge
 * has been started and the IRQ, DMA and Linux RUNNING owners still match.
 * This is a snapshot, NOT a lifetime lease: enqueue and STOPPING continue
 * to recheck their own admission under this same TX serializer.
 */
bool
rtwn8723be_datapath_running_ready(struct rtwn8723be_datapath *dp)
{
    struct rtwn8723be_softc *sc;
    bool ready;

    if (dp == NULL || !dp->prepared || dp->sc == NULL)
        return false;
    sc = dp->sc;
    mutex_enter(&dp->tx_lock);
    ready = dp->tx_enabled && !dp->stop_pending &&
        sc->sc_datapath == dp && sc->sc_irq_arg == dp &&
        sc->sc_irq_dispatch_ready && sc->sc_ih != NULL &&
        sc->sc_mapped && sc->sc_rings_allocated &&
        sc->sc_linux.started && sc->sc_linux.fw_ready &&
        sc->sc_linux.stage == R23BE_STAGE_RUNNING;
    mutex_exit(&dp->tx_lock);
    return ready;
}

/*
 * The net80211 if_start callback is external and may reenter the STOP
 * controller. Unlike a read-only RUNNING snapshot, this reference remains
 * published throughout the whole external tx_start call. STOP must first
 * close TX admission and return EBUSY; it may not enter STOPPING while a
 * caller still borrows its ifnet/PCI bridge. No waiting under IPL_NET.
 */
bool
rtwn8723be_datapath_tx_start_begin(struct rtwn8723be_datapath *dp)
{
    struct rtwn8723be_softc *sc;
    bool ready;

    if (dp == NULL || !dp->prepared || dp->sc == NULL)
        return false;
    sc = dp->sc;
    mutex_enter(&dp->tx_lock);
    ready = dp->tx_enabled && !dp->stop_pending &&
        sc->sc_datapath == dp && sc->sc_irq_arg == dp &&
        sc->sc_irq_dispatch_ready && sc->sc_ih != NULL &&
        sc->sc_mapped && sc->sc_rings_allocated &&
        sc->sc_linux.started && sc->sc_linux.fw_ready &&
        sc->sc_linux.stage == R23BE_STAGE_RUNNING;
    if (ready)
        dp->tx_start_active++;
    mutex_exit(&dp->tx_lock);
    return ready;
}

void
rtwn8723be_datapath_tx_start_end(struct rtwn8723be_datapath *dp)
{
    KASSERT(dp != NULL && dp->prepared && dp->sc != NULL);
    mutex_enter(&dp->tx_lock);
    KASSERT(dp->tx_start_active != 0);
    dp->tx_start_active--;
    mutex_exit(&dp->tx_lock);
}

/*
 * A complete RUNNING hardware owner must close TX descriptor admission
 * and enter STOPPING as ONE transition. The stage is shared with the
 * Linux-order stop controller, which will subsequently disable IRQ and
 * unwind hardware. The outer lifecycle owns softint/callback draining.
 */
int
rtwn8723be_datapath_begin_stop(struct rtwn8723be_datapath *dp,
    struct rtwn8723be_linux_state *state)
{
    struct rtwn8723be_softc *sc;
    int error = 0;

    if (dp == NULL || !dp->prepared || dp->sc == NULL || state == NULL)
        return EINVAL;
    sc = dp->sc;
    if (state != &sc->sc_linux)
        return EINVAL;

    mutex_enter(&dp->tx_lock);
    if (sc->sc_datapath != dp || sc->sc_irq_arg != dp ||
        !sc->sc_irq_dispatch_ready)
        error = EBUSY;
    else if (!state->started || !state->fw_ready ||
        state->stage != R23BE_STAGE_RUNNING) {
        /* Even an inconsistent owner must not retain TX admission. */
        dp->tx_enabled = false;
        error = EAGAIN;
    } else if (dp->rx_callback_active != 0 ||
        dp->tx_callback_active != 0 || dp->tx_start_active != 0) {
        /*
         * Do not begin destructive hardware STOP with borrowed RX DMA
         * or external TX-completion callbacks still executing. Close
         * fresh admissions, retain RUNNING ownership, and report EBUSY
         * for an external sleepable/drain-and-retry controller.
         */
        dp->tx_enabled = false;
        dp->stop_pending = true;
        error = EBUSY;
    } else {
        dp->tx_enabled = false;
        state->stage = R23BE_STAGE_STOPPING;
        dp->stop_pending = false;
    }
    mutex_exit(&dp->tx_lock);
    return error;
}

/*
 * Called by net80211 SIOCSIFFLAGS when IFF_UP and IFF_RUNNING are both
 * clear: a first DOWN may have been refused with EBUSY because a borrowed
 * RX DMA or external TX completion still held its lifetime reference.
 * Read stop_pending under the same IPL_NET mutex as begin_stop/start.
 *
 * This is only a retry admission snapshot; the actual begin_stop callback
 * must recheck all owners and activity atomically. It does not perform
 * any hardware operation, wait, or change the logical ifnet flags.
 */
bool
rtwn8723be_datapath_stop_retry_ready(struct rtwn8723be_datapath *dp)
{
    struct rtwn8723be_softc *sc;
    bool ready;

    if (dp == NULL || !dp->prepared || dp->sc == NULL)
        return false;
    sc = dp->sc;
    mutex_enter(&dp->tx_lock);
    ready = dp->stop_pending && !dp->tx_enabled &&
        sc->sc_datapath == dp && sc->sc_irq_arg == dp &&
        sc->sc_irq_dispatch_ready && sc->sc_linux.started &&
        sc->sc_linux.stage == R23BE_STAGE_RUNNING;
    mutex_exit(&dp->tx_lock);
    return ready;
}

void
rtwn8723be_datapath_stop(struct rtwn8723be_datapath *dp)
{
    if (dp != NULL && dp->prepared) {
        mutex_enter(&dp->tx_lock);
        dp->tx_enabled = false;
        mutex_exit(&dp->tx_lock);
    }
}

int
rtwn8723be_datapath_unprepare(struct rtwn8723be_datapath *dp)
{
    struct rtwn8723be_softc *sc;
    int error;

    if (dp == NULL || !dp->prepared || dp->sc == NULL)
        return EINVAL;
    sc = dp->sc;

    /* Unbind only after the hardware and NetBSD softint are both quiesced. */
    if (sc->sc_datapath != dp || sc->sc_irq_arg != dp ||
        !sc->sc_irq_dispatch_ready ||
        sc->sc_irq_dispatch.rx != rtwn8723be_dp_rx ||
        sc->sc_irq_dispatch.tx_done != rtwn8723be_dp_tx_done ||
        sc->sc_irq_dispatch.power_event != NULL)
        return EBUSY;
    if (sc->sc_irq_requested || sc->sc_irq_enabled ||
        sc->sc_ih != NULL || sc->sc_soft_ih != NULL ||
        sc->sc_pihp != NULL)
        return EBUSY;

    /*
     * The actual PCI + softint owner has now drained/disestablished both
     * handlers and no new ifnet entrant may appear. Still refuse to
     * retire this bridge while a previously published external TX
     * completion executes without the TX mutex.
     *
     * Never wait while holding an IPL_NET spin lock: an in-flight
     * completion needs this same mutex to drop its lifetime reference.
     */
    mutex_enter(&dp->tx_lock);
    /*
     * A disabled TX admission gate and drained IRQ handlers are NOT
     * proof that the Linux hardware STOP actually completed. In
     * particular, an interrupted STOPPING phase may still own live
     * firmware/MAC state. Preserve the bridge until real STOPPED or
     * an unstarted, firmware-free probe rollback is established.
     *
     * Pre-RUNNING start failures retain stages beyond PROBED; even
     * when fw_ready is not yet published they require a separate
     * journalled hardware unwind, never a speculative unprepare.
     */
    if (dp->tx_enabled || dp->stop_pending ||
        dp->tx_callback_active != 0 || dp->rx_callback_active != 0 ||
        dp->tx_start_active != 0 ||
        sc->sc_linux.started || sc->sc_linux.fw_ready ||
        sc->sc_linux.mac_func_enable ||
        sc->sc_linux.being_init_adapter ||
        (sc->sc_linux.stage != R23BE_STAGE_STOPPED &&
         sc->sc_linux.stage > R23BE_STAGE_PROBED)) {
        mutex_exit(&dp->tx_lock);
        return EBUSY;
    }
    mutex_exit(&dp->tx_lock);
    /* External lifecycle excludes TX enqueue/softint before lock destroy. */
    error = rtwn8723be_netbsd_irq_set_dispatch(sc, NULL, NULL);
    if (error != 0)
        return error; /* Retain all owner storage on failed unbind. */
    sc->sc_datapath = NULL;
    mutex_destroy(&dp->tx_lock);
    memset(dp, 0, sizeof(*dp));
    return 0;
}

int
rtwn8723be_datapath_enqueue(struct rtwn8723be_datapath *dp,
    unsigned int qid, struct mbuf *m, struct ieee80211_node *ni,
    const struct rtwn8723be_tx_params *p, bool command)
{
    int error;

    if (dp == NULL || !dp->prepared || dp->sc == NULL ||
        m == NULL || ni == NULL || p == NULL)
        return EINVAL;
    mutex_enter(&dp->tx_lock);
    /*
     * RUNNING is a stronger prerequisite than the persistent started/
     * firmware flags: during STOPPING the Linux stop controller has not
     * cleared those bits yet. Never publish another DMA descriptor then.
     * The external lifecycle still owns TX lock lifetime/teardown.
     */
    if (!dp->tx_enabled || dp->sc->sc_datapath != dp ||
        !dp->sc->sc_linux.started || !dp->sc->sc_linux.fw_ready ||
        dp->sc->sc_linux.stage != R23BE_STAGE_RUNNING)
        error = EAGAIN;
    else
        error = rtwn8723be_tx_native_enqueue(dp->sc,
            qid, m, ni, p, command);
    mutex_exit(&dp->tx_lock);
    return error;
}
