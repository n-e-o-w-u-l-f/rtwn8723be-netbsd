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

    if (!dp->prepared || dp->rx.frame == NULL || dp->rx.c2h == NULL)
        return;

    /*
     * RX DMA drain re-arms OWN after each callback. The packet pointer
     * cannot be retained by the frame/C2H consumer.
     */
    error = rtwn8723be_rx_native_drain(dp->sc, &dp->rx, &delivered);
    dp->rx_delivered += delivered;
    if (error != 0 && dp->rx_error == 0)
        dp->rx_error = error;
}

static void
rtwn8723be_dp_tx_done(void *arg, unsigned int qid)
{
    struct rtwn8723be_datapath *dp = arg;
    size_t reclaimed = 0;
    int error;

    if (!dp->prepared || qid >= RTWN8723BE_TX_QUEUE_COUNT)
        return;

    /* Serialize ring consumer against concurrent ifnet send producer. */
    mutex_enter(&dp->tx_lock);
    error = rtwn8723be_tx_native_reclaim(dp->sc, qid, &reclaimed);
    if (error != 0 && dp->tx_error == 0)
        dp->tx_error = error;
    dp->tx_reclaimed += reclaimed;
    mutex_exit(&dp->tx_lock);

    /* Caller may wake a stopped net80211 queue outside the TX spin lock. */
    if (reclaimed != 0 && dp->tx_complete != NULL)
        dp->tx_complete(dp->tx_complete_arg, qid, reclaimed);
}

int
rtwn8723be_datapath_prepare(struct rtwn8723be_datapath *dp,
    struct rtwn8723be_softc *sc,
    const struct rtwn8723be_rx_dispatch *rx,
    void (*tx_complete)(void *, unsigned int, size_t),
    void *tx_complete_arg)
{
    struct rtwn8723be_irq_dispatch irq;

    if (dp == NULL || sc == NULL || rx == NULL ||
        rx->frame == NULL || rx->c2h == NULL)
        return EINVAL;
    /* dp storage must be zero-initialized by its owning attach path. */
    if (dp->prepared || sc->sc_irq_dispatch_ready ||
        sc->sc_ih != NULL || sc->sc_soft_ih != NULL)
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

    memset(&irq, 0, sizeof(irq));
    irq.rx = rtwn8723be_dp_rx;
    irq.tx_done = rtwn8723be_dp_tx_done;
    rtwn8723be_netbsd_irq_set_dispatch(sc, &irq, dp);
    return 0;
}

int
rtwn8723be_datapath_start(struct rtwn8723be_datapath *dp)
{
    struct rtwn8723be_softc *sc;

    if (dp == NULL || !dp->prepared || dp->sc == NULL)
        return EINVAL;
    sc = dp->sc;
    if (!sc->sc_linux.started ||
        sc->sc_linux.stage != R23BE_STAGE_RUNNING ||
        !sc->sc_linux.fw_ready ||
        !sc->sc_irq_dispatch_ready || sc->sc_ih == NULL ||
        !sc->sc_mapped || !sc->sc_rings_allocated)
        return EAGAIN;

    mutex_enter(&dp->tx_lock);
    dp->tx_enabled = true;
    mutex_exit(&dp->tx_lock);
    return 0;
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

    if (dp == NULL || !dp->prepared || dp->sc == NULL)
        return EINVAL;
    sc = dp->sc;

    /* Unbind only after the hardware and NetBSD softint are both quiesced. */
    if (dp->tx_enabled || sc->sc_irq_enabled ||
        sc->sc_ih != NULL || sc->sc_soft_ih != NULL ||
        sc->sc_pihp != NULL)
        return EBUSY;
    rtwn8723be_netbsd_irq_set_dispatch(sc, NULL, NULL);
    mutex_destroy(&dp->tx_lock);
    memset(dp, 0, sizeof(*dp));
    return 0;
}

int
rtwn8723be_datapath_enqueue(struct rtwn8723be_datapath *dp,
    unsigned int qid, struct mbuf *m,
    const struct rtwn8723be_tx_params *p, bool command)
{
    int error;

    if (dp == NULL || !dp->prepared || dp->sc == NULL ||
        m == NULL || p == NULL)
        return EINVAL;
    mutex_enter(&dp->tx_lock);
    if (!dp->tx_enabled || !dp->sc->sc_linux.started ||
        !dp->sc->sc_linux.fw_ready)
        error = EAGAIN;
    else
        error = rtwn8723be_tx_native_enqueue(dp->sc,
            qid, m, p, command);
    mutex_exit(&dp->tx_lock);
    return error;
}
