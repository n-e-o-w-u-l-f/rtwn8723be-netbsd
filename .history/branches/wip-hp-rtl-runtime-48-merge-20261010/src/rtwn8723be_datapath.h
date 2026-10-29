/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_DATAPATH_H_
#define _RTWN8723BE_DATAPATH_H_

#include <sys/types.h>
#include <sys/mutex.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_rx_native.h"
#include "rtwn8723be_tx_native.h"

/*
 * Binds the existing SOFTINT_NET interrupt dispatch to both ring consumers
 * and provides one IPL_NET TX serializer shared by send and TX-completion.
 *
 * Prepared != running. The caller supplies real net80211 frame and C2H
 * consumers and must complete all lifecycle and unwind gates BEFORE
 * enabling hardware interrupts. The RX consumers must COPY borrowed data
 * before returning; no callback is permitted to retain a DMA ring mbuf.
 */
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_rx_dispatch rx;
    kmutex_t tx_lock;
    /* Per-device scratch, serialized by tx_lock; no ownership survives a
     * batch return. Embedded in the heap-allocated runtime, not TX stack.
     */
    struct rtwn8723be_tx_batch_workspace batch_workspace;
    bool prepared;
    bool tx_enabled;
    int rx_error;
    int tx_error;
    uint64_t rx_delivered;
    uint64_t tx_reclaimed;
    void (*tx_complete)(void *, unsigned int, size_t);
    void *tx_complete_arg;
};

/* At most one prepared bridge per softc; caller owns bridge storage. */
int rtwn8723be_datapath_prepare(struct rtwn8723be_datapath *,
    struct rtwn8723be_softc *,
    const struct rtwn8723be_rx_dispatch *,
    void (*)(void *, unsigned int, size_t), void *);

/* May only transition to active AFTER Linux lifecycle marked RUNNING. */
int rtwn8723be_datapath_start(struct rtwn8723be_datapath *);

/* Disables new TX; caller must quiesce/disestablish IRQ independently. */
void rtwn8723be_datapath_stop(struct rtwn8723be_datapath *);

/*
 * Requires IRQ and softint fully DIS-ESTABLISHED, plus no concurrent
 * ifnet entry, before clearing callbacks/destroying the TX lock.
 */
int rtwn8723be_datapath_unprepare(struct rtwn8723be_datapath *);

int rtwn8723be_datapath_enqueue(struct rtwn8723be_datapath *,
    unsigned int, struct mbuf *, const struct rtwn8723be_tx_params *,
    bool command);
/* Transfers owner only after successful DMA publication; report callback
 * is invoked once under dp->tx_lock with a borrowed mbuf. */
int rtwn8723be_datapath_enqueue_owned(struct rtwn8723be_datapath *,
    unsigned int, struct mbuf *, const struct rtwn8723be_tx_params *, bool,
    void *, void (*)(void *, struct mbuf *, bool));
int rtwn8723be_datapath_enqueue_owned_notify(struct rtwn8723be_datapath *,
    unsigned int, struct mbuf *, const struct rtwn8723be_tx_params *, bool,
    void *, void (*)(void *, struct mbuf *, bool),
    void (*)(void *, const struct mbuf *), void *);
/* BE-only batch of already encrypted/linearized frames. Same owner-transfer
 * rule as native batch: all on success, none on failure. After success,
 * accepted borrows each mbuf under tx_lock, before reclaim can free it;
 * it must not free/retain packets, reenter TX, or change frame storage.
 * Caller excludes unprepare and retains frame-array storage for the call.
 * This is not yet connected to net80211's fail-closed fragment producer.
 */
int rtwn8723be_datapath_enqueue_batch_notify(struct rtwn8723be_datapath *,
    const struct rtwn8723be_tx_batch_frame *, unsigned int,
    void (*)(void *, const struct mbuf *), void *);
int rtwn8723be_datapath_tx_check(struct rtwn8723be_datapath *, unsigned int);
/*
 * Preflight a fragmented MSDU while the sole ifnet producer holds its lock.
 * Verifies contiguous CPU-owned BE slots; this is NOT a reservation or a
 * guarantee that every later per-fragment DMA load/encode will succeed.
 */
int rtwn8723be_datapath_tx_check_slots(struct rtwn8723be_datapath *,
    unsigned int, unsigned int);

#endif
