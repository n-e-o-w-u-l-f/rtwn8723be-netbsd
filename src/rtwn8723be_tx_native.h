/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_TX_NATIVE_H_
#define _RTWN8723BE_TX_NATIVE_H_

#include <sys/types.h>
#include <sys/mbuf.h>
struct ieee80211_node;
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_tx_desc.h"

/*
 * Native old-TRX DMA queue/reclaim (Linux rtlwifi/pci.c:rtl_pci_tx).
 *
 * The caller owns BOTH mbuf and referenced net80211 node on failure;
 * the TX ring owns BOTH after successful descriptor/DMA publication.
 * The node must be referenced by the caller; do not take a second ref.
 * The node is freed only after DMA POSTWRITE/unload on reclaim/reset/free.
 * NULL nodes are forbidden for normal 802.11 frame TX.
 * The caller MUST serialize enqueue against IRQ/softint completion, stop,
 * reset and detach with an IPL_NET-compatible TX lock. No NetBSD ifnet
 * callback may invoke this adapter before lifecycle/locking closure.
 *
 * The current ring uses one DMA segment: callers must linearize chained
 * mbufs BEFORE calling this function; EFBIG is returned otherwise.
 */
int rtwn8723be_tx_native_enqueue(struct rtwn8723be_softc *,
    unsigned int qid, struct mbuf *, struct ieee80211_node *,
    const struct rtwn8723be_tx_params *, bool command);

/*
 * Reclaim completed OWN-cleared descriptors, release bus_dmamaps/mbufs,
 * and report completion count; caller holds the same TX lock.
 */
int rtwn8723be_tx_native_reclaim(struct rtwn8723be_softc *,
    unsigned int qid, size_t *);

#endif
