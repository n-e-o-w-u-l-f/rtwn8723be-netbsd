/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_RX_BINDING_H_
#define _RTWN8723BE_RX_BINDING_H_

#include "rtwn8723be_c2h_native.h"
#include "rtwn8723be_net80211.h"

/*
 * One stable callback argument shared by the RX ring's frame and C2H
 * callbacks. The owning PCI/net80211 adapter keeps this storage live until
 * IRQ + softint have been fully disestablished and RX has stopped.
 * This function does NOT activate DMA, register net80211 or start hardware.
 */
struct rtwn8723be_rx_binding {
    struct rtwn8723be_net80211 *net;
    struct rtwn8723be_c2h_handlers firmware;
    struct rtwn8723be_rx_dispatch dispatch;
};

int rtwn8723be_rx_binding_init(struct rtwn8723be_rx_binding *,
    struct rtwn8723be_net80211 *,
    const struct rtwn8723be_c2h_handlers *);

#endif
