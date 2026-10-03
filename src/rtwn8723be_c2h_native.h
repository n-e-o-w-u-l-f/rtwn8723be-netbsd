/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_C2H_NATIVE_H_
#define _RTWN8723BE_C2H_NATIVE_H_

#include "rtwn8723be_c2h.h"
#include "rtwn8723be_rx_native.h"

/*
 * rtwn8723be_c2h_native_receive() is the typed implementation, NOT a
 * rtwn8723be_rx_dispatch.c2h function pointer (their first arguments
 * differ). Use rtwn8723be_rx_binding_init() for the shared frame/C2H
 * callback argument or a correctly typed owning wrapper.
 * This adapter does not establish IRQs or register net80211.
 */
int rtwn8723be_c2h_native_receive(
    const struct rtwn8723be_c2h_handlers *,
    const uint8_t *, size_t, const struct rtwn8723be_rx_packet *);

#endif
