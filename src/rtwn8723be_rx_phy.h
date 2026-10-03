/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_RX_PHY_H_
#define _RTWN8723BE_RX_PHY_H_
#include <stddef.h>
#include <stdint.h>

/*
 * Portable RTL8723BE RSSI extraction from the Linux phy_status_rpt.
 * The raw 32-byte RX descriptor and mapped RX buffer have already
 * completed BUS_DMASYNC_POSTREAD. This does not synthesize a value when
 * PHYST is absent. The native frame adapter preserves rssi_valid=false
 * and follows pinned NetBSD if_rtwn.c by passing the framework's
 * existing zero fallback; this is NOT a measured 0 dBm reading.
 */
int rtwn8723be_rx_phy_rssi(const uint8_t *desc, size_t desc_size,
    const uint8_t *buffer, size_t buffer_size, int *rssi_dbm);

#endif
