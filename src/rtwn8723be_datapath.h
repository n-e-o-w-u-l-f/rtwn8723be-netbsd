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
    bool prepared;
    bool tx_enabled;
    /* Latches a denied STOP until all borrowed callbacks return/retry. */
    bool stop_pending;
    /*
     * Number of external TX completion callbacks executing after the
     * tx_lock release. Increment before publication; decrement only after
     * callback returns. Protected exclusively by tx_lock (IPL_NET).
     */
    unsigned int tx_callback_active;
    /* Active net80211 if_start method calls after releasing TX mutex. */
    unsigned int tx_start_active;
    /* In-progress RX ring drains and borrowed frame/C2H callbacks. */
    unsigned int rx_callback_active;
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

/*
 * Read-only, IPL_NET-serialized RUNNING/owner gate for net80211's
 * IFF_RUNNING publication and advisory if_start preflight. A successful
 * snapshot does not replace the actual TX enqueue lock/lifetime owner.
 */
bool rtwn8723be_datapath_running_ready(struct rtwn8723be_datapath *);

/*
 * Atomically lease the RUNNING TX/net80211 owner across the external
 * if_start/tx_start callback. No callback is invoked under IPL_NET.
 * The caller must pair a successful acquire with an eventual release.
 */
bool rtwn8723be_datapath_tx_start_begin(struct rtwn8723be_datapath *);
void rtwn8723be_datapath_tx_start_end(struct rtwn8723be_datapath *);

/*
 * Atomically closes TX and transitions the actual Linux lifecycle from
 * RUNNING to STOPPING under the same IPL_NET lock as ring enqueue/reclaim.
 * Refuses the transition while RX drain, TX completion or net80211
 * TX start method is executing.
 * Does NOT drain softint or free outstanding mbufs; lifecycle owns those.
 */
int rtwn8723be_datapath_begin_stop(struct rtwn8723be_datapath *,
    struct rtwn8723be_linux_state *);

/*
 * A previously rejected, quiescence-delayed STOP can be reattempted from
 * an already DOWN ifnet without restoring IFF_RUNNING. Snapshot owner,
 * stage and stop_pending under the same IPL_NET TX serializer.
 */
bool rtwn8723be_datapath_stop_retry_ready(struct rtwn8723be_datapath *);

/* Disables new TX; caller must quiesce/disestablish IRQ independently. */
void rtwn8723be_datapath_stop(struct rtwn8723be_datapath *);

/*
 * Requires IRQ and softint fully DIS-ESTABLISHED, plus no concurrent
 * ifnet entry, before clearing callbacks/destroying the TX lock.
 * Also returns EBUSY while RX drain, an external TX-completion callback,
 * or net80211 TX start method holds a published reference; drain/retry must occur OUTSIDE IPL_NET.
 */
int rtwn8723be_datapath_unprepare(struct rtwn8723be_datapath *);

int rtwn8723be_datapath_enqueue(struct rtwn8723be_datapath *,
    unsigned int, struct mbuf *, struct ieee80211_node *,
    const struct rtwn8723be_tx_params *, bool command);

/*
 * Pre-encapsulated contiguous 802.11 MPDU. Caller supplies an already
 * referenced node and rate policy. For protected frames,
 * sw_crypto_complete is true ONLY after ieee80211_crypto_encap succeeded.
 * Returns 0 only after DMA consumes m + ni; otherwise caller retains both.
 * This is NOT a complete if_start management/data queue consumer.
 */
int rtwn8723be_datapath_enqueue_80211(struct rtwn8723be_datapath *,
    struct mbuf *, struct ieee80211_node *, bool sw_crypto_complete,
    const struct rtwn8723be_tx_params *);

#endif
