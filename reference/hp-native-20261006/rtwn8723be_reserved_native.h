/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_RESERVED_NATIVE_H_
#define _RTWN8723BE_RESERVED_NATIVE_H_

#include "rtwn8723be_datapath.h"

#define RTWN8723BE_RESERVED_SIZE 1024U

/* Actual peer snapshot; pointers remain valid during the pure build call. */
struct rtwn8723be_reserved_peer {
    uint8_t mac[6], bssid[6];
    uint16_t aid, beacon_interval, capability;
    uint8_t channel, erp, dtim_period;
    const uint8_t *ssid;
    size_t ssid_length;
    const uint8_t *rates;
    size_t rate_count;
    const uint8_t *wpa_ie;
    size_t wpa_ie_length;
};

struct rtwn8723be_reserved_native {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_datapath *dp;
    bool initialized, downloading, valid;
    uint64_t firmware_generation;
    uint8_t bssid[6];
    uint16_t aid;
    uint64_t attempts;
    int last_error;
};

/* Frozen 0/2/3/4/6/7 page layout, real legacy BSS fields, no HT/WME IE. */
int rtwn8723be_reserved_build(const struct rtwn8723be_reserved_peer *,
    uint8_t *, size_t, uint8_t locations[5]);
int rtwn8723be_reserved_native_prepare(struct rtwn8723be_reserved_native *,
    struct rtwn8723be_softc *, struct rtwn8723be_datapath *);

/*
 * Caller owns a node reference and serializes runtime state/firmware/stop.
 * Requires a process/workqueue context allowed to wait for the H2C mutex;
 * never call from hard/soft interrupt or while holding an IPL_NET lock.
 * The beacon ring acquires its own node reference only on enqueue success.
 * DMA stays owned on timeout until OWN clears or hardware reset/free.
 */
int rtwn8723be_reserved_native_download(struct rtwn8723be_reserved_native *,
    struct ieee80211_node *);
bool rtwn8723be_reserved_native_ready(const struct rtwn8723be_reserved_native *,
    const struct ieee80211_node *);
int rtwn8723be_reserved_native_invalidate(struct rtwn8723be_reserved_native *);
int rtwn8723be_reserved_native_fini(struct rtwn8723be_reserved_native *);

#endif
