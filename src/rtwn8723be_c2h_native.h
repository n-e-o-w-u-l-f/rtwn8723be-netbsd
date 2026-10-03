/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_C2H_NATIVE_H_
#define _RTWN8723BE_C2H_NATIVE_H_

#include "rtwn8723be_c2h.h"
#include "rtwn8723be_rx_native.h"

/*
 * Supply this to rtwn8723be_rx_dispatch.c2h with dispatch.arg pointing to
 * a context that embeds these event handlers. The frame path uses the
 * same dispatch.arg and MUST have its own compatible owning context.
 *
 * A caller can instead use rtwn8723be_c2h_native_receive() from an
 * owning wrapper with independently selected RX frame and C2H contexts.
 * This adapter does not automatically establish IRQs or register net80211.
 */
int rtwn8723be_c2h_native_receive(
    const struct rtwn8723be_c2h_handlers *,
    const uint8_t *, size_t, const struct rtwn8723be_rx_packet *);

#endif
