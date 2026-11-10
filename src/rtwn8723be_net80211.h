/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_NET80211_H_
#define _RTWN8723BE_NET80211_H_

#include <sys/types.h>
#include "rtwn8723be_os_compat.h"
#include "rtwn8723be_rx_decode.h"
#include "rtwn8723be_tx_desc.h"

/* The public lifecycle declaration layer owns no PCI softc definition. */
struct rtwn8723be_softc;
struct ifnet;
struct mbuf;
struct ieee80211_node;
struct ieee80211com;
struct ieee80211_channel;

/*
 * NetBSD 11 ifnet/net80211 glue, independent of native PCI attach.
 *
 * Hardware methods MUST implement real lifecycle/PHY/channel/security,
 * serialization, net80211 TX framing and recovery. Supplying a no-op
 * merely to register an ifnet violates the full port contract.
 *
 * A NULL tx_start selects the real native management/data queue consumer.
 * A supplied method must preserve the same frame/node/lifetime contract.
 */
struct rtwn8723be_net80211_methods {
    int (*hw_start)(struct rtwn8723be_softc *);
    int (*hw_stop)(struct rtwn8723be_softc *);
    void (*tx_start)(struct rtwn8723be_softc *, struct ifnet *);
};

struct rtwn8723be_net80211 {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_net80211_methods methods;
    bool registered;
    /*
     * Legacy non-MPSAFE ifnet and NET softint serialize these fields with
     * the kernel lock and splnet. Never perform crypto/callbacks under
     * datapath tx_lock. The existing TX-start lease excludes hardware STOP.
     */
    bool tx_busy;
    bool tx_again;
    struct mbuf *tx_pending_m;
    struct ieee80211_node *tx_pending_ni;
    struct rtwn8723be_tx_params tx_pending_rate;
    uint64_t tx_key_epoch;
    uint64_t tx_pending_key_epoch;
    unsigned int tx_key_update_depth;
    void (*tx_key_begin_saved)(struct ieee80211com *);
    void (*tx_key_end_saved)(struct ieee80211com *);
    struct ieee80211_channel *tx_pending_channel;
    uint16_t tx_pending_channel_freq;
    uint16_t tx_pending_channel_flags;
    uint16_t tx_pending_defkey;
    int tx_pending_state;
    int tx_pending_mode;
    uint32_t tx_pending_security_flags;
    uint8_t tx_pending_bssid[6];
};

/*
 * Real native TX method; if_start holds the datapath TX-start lifetime lease.
 * Completion is called outside its TX mutex under the completion lease.
 * tx_owner is a nonblocking, callback-free exact owner lookup.
 */
void rtwn8723be_net80211_tx_start(struct rtwn8723be_softc *, struct ifnet *);
void rtwn8723be_net80211_tx_complete(void *, unsigned int, size_t);
struct rtwn8723be_net80211 *rtwn8723be_net80211_tx_owner(
    struct rtwn8723be_softc *);

int rtwn8723be_net80211_register(struct rtwn8723be_net80211 *,
    struct rtwn8723be_softc *,
    const struct rtwn8723be_net80211_methods *);
/* Return hardware-stop failure: caller must retain softc/PCI resources. */
int rtwn8723be_net80211_unregister(struct rtwn8723be_net80211 *);

/*
 * Copy a borrowed, already DMA-synchronized and CRC/ICV-validated frame
 * before passing it to the NetBSD stack. rssi_dbm must be computed from
 * actual receive PHY metadata, NOT an invented constant. C2H packets
 * MUST NOT be passed through this function.
 */
int rtwn8723be_net80211_input(struct rtwn8723be_net80211 *,
    const uint8_t *, size_t, int rssi_dbm);

/*
 * RX-ring callback: routes a copied frame into the NetBSD 802.11 stack.
 * Measured RSSI comes from RTL8723BE PHY metadata; for frames without
 * valid PHY metadata, pass the pinned NetBSD if_rtwn.c fallback RSSI
 * value zero, without marking it as a measured 0 dBm signal.
 * Full network/runtime acceptance remains subject to native testing.
 */
int rtwn8723be_net80211_rx_frame(void *, const uint8_t *, size_t,
    const struct rtwn8723be_rx_packet *);

#endif
