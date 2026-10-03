/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_NET80211_H_
#define _RTWN8723BE_NET80211_H_

#include <sys/types.h>
#include <stdbool.h>
#include <stdint.h>
#include "rtwn8723be_netbsd.h"

/*
 * NetBSD 11 ifnet/net80211 glue, independent of native PCI attach.
 *
 * Hardware methods MUST implement real lifecycle/PHY/channel/security,
 * serialization, net80211 TX framing and recovery. Supplying a no-op
 * merely to register an ifnet violates the full port contract.
 *
 * tx_start must drain management and normal ifnet queues and ensure each
 * transmitted 802.11 frame owns a node reference until TX completion.
 */
struct rtwn8723be_net80211_methods {
    int (*hw_start)(struct rtwn8723be_softc *);
    void (*hw_stop)(struct rtwn8723be_softc *);
    void (*tx_start)(struct rtwn8723be_softc *, struct ifnet *);
};

struct rtwn8723be_net80211 {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_net80211_methods methods;
    bool registered;
};

int rtwn8723be_net80211_register(struct rtwn8723be_net80211 *,
    struct rtwn8723be_softc *,
    const struct rtwn8723be_net80211_methods *);
void rtwn8723be_net80211_unregister(struct rtwn8723be_net80211 *);

/*
 * Copy a borrowed, already DMA-synchronized and CRC/ICV-validated frame
 * before passing it to the NetBSD stack. rssi_dbm must be computed from
 * actual receive PHY metadata, NOT an invented constant. C2H packets
 * MUST NOT be passed through this function.
 */
int rtwn8723be_net80211_input(struct rtwn8723be_net80211 *,
    const uint8_t *, size_t, int rssi_dbm);

#endif
