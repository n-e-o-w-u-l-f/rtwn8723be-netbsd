/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_TX_NATIVE_H_
#define _RTWN8723BE_TX_NATIVE_H_

#include <sys/types.h>
#include <sys/mbuf.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_tx_desc.h"

/*
 * Native old-TRX DMA queue/reclaim (Linux rtlwifi/pci.c:rtl_pci_tx).
 *
 * The caller owns the mbuf on failure; the ring owns it after success.
 * The caller MUST serialize enqueue against IRQ/softint completion, stop,
 * reset and detach with an IPL_NET-compatible TX lock. No NetBSD ifnet
 * callback may invoke this adapter before lifecycle/locking closure.
 *
 * The current ring uses one DMA segment: callers must linearize chained
 * mbufs BEFORE calling this function; EFBIG is returned otherwise.
 */
int rtwn8723be_tx_native_enqueue(struct rtwn8723be_softc *,
    unsigned int qid, struct mbuf *,
    const struct rtwn8723be_tx_params *, bool command);
/* Additional net80211 owner is held by this TX slot until POSTWRITE
 * and DMAMAP unload; release callback receives the mbuf and whether DMA
 * completed. The caller retains both ownerships on enqueue failure. */
int rtwn8723be_tx_native_enqueue_owned(struct rtwn8723be_softc *,
    unsigned int qid, struct mbuf *,
    const struct rtwn8723be_tx_params *, bool command,
    void *, void (*)(void *, struct mbuf *, bool));

/* Bounded preparation primitive; not yet wired to net80211 fragmentation.
 * The caller holds the TX lock across this entire synchronous operation,
 * supplies distinct already encrypted/linearized mbufs (m_nextpkt detached),
 * and retains all mbuf/node/report ownership on failure. Success transfers
 * every entry to the ring. No callback is invoked during preparation/abort.
 * Workspace must be caller-owned storage, not a large kernel-stack array;
 * it must not alias ring/frame storage or be shared by concurrent calls.
 * This bound is an adapter limit, not a claim of arbitrary batch support.
 */
#define RTWN8723BE_TX_BATCH_MAX 16U
struct rtwn8723be_tx_batch_frame {
    struct mbuf *m;
    struct rtwn8723be_tx_params params;
    void *owner;
    void (*release)(void *, struct mbuf *, bool);
};
struct rtwn8723be_tx_batch_workspace {
    struct rtwn8723be_tx_desc desc[RTWN8723BE_TX_BATCH_MAX];
};
int rtwn8723be_tx_native_enqueue_batch(struct rtwn8723be_softc *,
    const struct rtwn8723be_tx_batch_frame *, unsigned int,
    struct rtwn8723be_tx_batch_workspace *);

/*
 * Reclaim completed OWN-cleared descriptors, release bus_dmamaps/mbufs,
 * and report completion count; caller holds the same TX lock.
 */
int rtwn8723be_tx_native_reclaim(struct rtwn8723be_softc *,
    unsigned int qid, size_t *);

/*
 * Linux reserved-page (H2C join-report) uses beacon descriptor slot zero;
 * no IRQ reclaim is assumed. These functions require caller TX locking.
 * On enqueue failure caller retains mbuf and node; successful completion
 * releases them once after DMA POSTWRITE/unload through the callback.
 */
int rtwn8723be_tx_native_enqueue_reserved(struct rtwn8723be_softc *,
    struct mbuf *, const struct rtwn8723be_tx_params *,
    void *, void (*)(void *, struct mbuf *, bool));
int rtwn8723be_tx_native_reclaim_reserved(struct rtwn8723be_softc *,
    size_t *);

#endif
