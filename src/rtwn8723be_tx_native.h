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

/*
 * Reclaim completed OWN-cleared descriptors, release bus_dmamaps/mbufs,
 * and report completion count; caller holds the same TX lock.
 */
int rtwn8723be_tx_native_reclaim(struct rtwn8723be_softc *,
    unsigned int qid, size_t *);

#endif
