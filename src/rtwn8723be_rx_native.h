/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_RX_NATIVE_H_
#define _RTWN8723BE_RX_NATIVE_H_

#include <sys/types.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_rx_decode.h"

/*
 * A callback sees a BORROWED, DMA-synchronized frame, valid only during
 * this call. It must copy the frame before returning; it must NEVER free
 * or retain the ring's mbuf. Frame ownership/zero-copy belongs to a later
 * complete net80211 adapter.
 *
 * This is a kernel-side ring-drain routine, NOT permission to register
 * the device or enable interrupts while TX, firmware events, rollback,
 * net80211 and lifecycle callbacks remain incomplete.
 */
struct rtwn8723be_rx_dispatch {
    void *arg;
    int (*frame)(void *, const uint8_t *, size_t,
        const struct rtwn8723be_rx_packet *);
    int (*c2h)(void *, const uint8_t *, size_t,
        const struct rtwn8723be_rx_packet *);
};

int rtwn8723be_rx_native_drain(struct rtwn8723be_softc *,
    const struct rtwn8723be_rx_dispatch *, size_t *);

#endif /* _RTWN8723BE_RX_NATIVE_H_ */
