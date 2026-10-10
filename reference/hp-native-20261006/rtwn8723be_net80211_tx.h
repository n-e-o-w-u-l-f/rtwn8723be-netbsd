/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_NET80211_TX_H_
#define _RTWN8723BE_NET80211_TX_H_

#include <sys/types.h>
#include <sys/mutex.h>
#include <sys/callout.h>
#include "rtwn8723be_datapath.h"
#include "rtwn8723be_c2h.h"

#define RTWN8723BE_TX_REPORT_SLOTS 64U
/* Frozen rtlwifi/wifi.h PACKET_DHCP/ARP/EAPOL. */
#define RTWN8723BE_TX_SPECIAL_NONE  0U
#define RTWN8723BE_TX_SPECIAL_DHCP  1U
#define RTWN8723BE_TX_SPECIAL_ARP   2U
#define RTWN8723BE_TX_SPECIAL_EAPOL 3U

struct rtwn8723be_net80211_tx;
struct rtwn8723be_tx_report_ticket {
    struct rtwn8723be_net80211_tx *tx;
    struct ieee80211_node *ni;
    struct mbuf *m; /* Set only AFTER DMA has been unloaded. */
    uint32_t sent_ticks;
    uint8_t sequence;
    uint8_t status;
    uint8_t retry;
    bool in_use;
    bool dma_pending;
    bool terminal;
    bool received;
    bool acked;
    bool cancelled;
};

/* Runtime owner storage; zero-initialize before prepare. */
struct rtwn8723be_net80211_tx {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_datapath *dp;
    /* producer -> datapath TX -> report is the sole nesting order. */
    kmutex_t producer_lock;
    kmutex_t report_lock;
    callout_t report_timeout;
    bool prepared;
    bool enabled;
    bool reports_running;
    void (*accepted)(struct rtwn8723be_softc *, const uint8_t *, size_t,
        uint8_t);
    uint8_t next_sequence;
    unsigned int pending_reports;
    struct rtwn8723be_tx_report_ticket report[RTWN8723BE_TX_REPORT_SLOTS];
    uint64_t reports_sent;
    uint64_t reports_acked;
    uint64_t reports_failed;
    uint64_t reports_timedout;
    uint64_t reports_cancelled;
    uint64_t reports_unmatched;
};

int rtwn8723be_net80211_tx_prepare(struct rtwn8723be_net80211_tx *,
    struct rtwn8723be_softc *, struct rtwn8723be_datapath *);
/* Run only after datapath_start succeeds; no hardware state is inferred. */
int rtwn8723be_net80211_tx_run(struct rtwn8723be_net80211_tx *);
/* Set while stopped; callback copies borrowed data and cannot re-enter TX. */
int rtwn8723be_net80211_tx_set_accepted(struct rtwn8723be_net80211_tx *,
    void (*)(struct rtwn8723be_softc *, const uint8_t *, size_t, uint8_t));
/* Close producer BEFORE datapath_stop and hardware stop/reset. */
void rtwn8723be_net80211_tx_stop(struct rtwn8723be_net80211_tx *);
/*
 * After producer/IRQ rundown, ring reset/free AND if_detach return. The
 * NetBSD if_detach path privately calls if_deferred_start_destroy, which
 * softint_disestablishes the deferred producer before freeing its storage.
 * EBUSY preserves this context while a DMA slot still references a ticket.
 * Calls callout_halt, so the native detach caller must be permitted to wait.
 */
int rtwn8723be_net80211_tx_fini(struct rtwn8723be_net80211_tx *);

/* NetBSD rtwn_start ordering: management first, Ethernet framing next. */
void rtwn8723be_net80211_tx_start(struct rtwn8723be_net80211_tx *,
    struct ifnet *);
/* Datapath completion callback; schedules ifnet restart outside TX lock. */
void rtwn8723be_net80211_tx_complete(void *, unsigned int, size_t);

/* C2H v1 handler: retains special frames until DMA AND air result exist. */
int rtwn8723be_net80211_tx_report(void *,
    const struct rtwn8723be_c2h_event *);

/*
 * Consumes one already framed mbuf and one node reference on ALL returns.
 * Ethernet caller detects EAPOL before net80211/software encryption.
 * Callers hold producer_lock, or have independently excluded start/stop.
 * QoS/HT and non-station transmission are explicitly unsupported here.
 */
int rtwn8723be_net80211_tx_frame(struct rtwn8723be_net80211_tx *,
    struct mbuf *, struct ieee80211_node *, uint8_t special_kind);

#endif
