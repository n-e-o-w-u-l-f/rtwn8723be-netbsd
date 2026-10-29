/* SPDX-License-Identifier: GPL-2.0 */
/* Portable Linux halbtc_get()/halbtc_set() policy translation. */
#ifndef _RTWN8723BE_BTC_POLICY_H_
#define _RTWN8723BE_BTC_POLICY_H_

#include "rtwn8723be_btc_linux_types.h"

/*
 * A whole-driver NetBSD owner supplies this coherent view while it holds the
 * real state producer.  These are the exact Wi-Fi-side values consumed by
 * the frozen Linux halbtc_get() decisions; no synthetic connection or power
 * state is stored in the policy itself.
 */
struct rtwn8723be_btc_wifi_snapshot {
    bool station_linked;
    bool any_client_connected;
    bool busy;
    bool scanning;
    bool linking;
    bool in_4way;
    bool under_5g;
    bool ap_mode;
    bool encryption_enabled;
    bool under_b_mode;
    int32_t rssi;
    uint32_t bandwidth;
    uint32_t traffic_direction;
    uint32_t firmware_version;
    uint8_t dot11_channel;
    uint8_t ap_count;
};

enum rtwn8723be_btc_policy_bt_query {
    R23BE_BTC_POLICY_BT_PATCH_VERSION,
    R23BE_BTC_POLICY_BT_DEVICE_INFO,
    R23BE_BTC_POLICY_BT_FORBIDDEN_SLOT,
};

/*
 * Every callback is mandatory.  snapshot and the action callbacks belong to
 * the future, serialized whole-driver owner; they are deliberately not
 * replaced with cached or guessed values.  fault marks the enclosing native
 * BTC owner failed when a fallible NetBSD operation cannot preserve Linux's
 * void/scalar provider ABI.
 */
struct rtwn8723be_btc_policy_ops {
    int (*snapshot)(void *, struct rtwn8723be_btc_wifi_snapshot *);
    int (*clock_msec)(void *, uint64_t *);
    int (*aggregate_apply)(void *, const struct btc_bt_info *);
    int (*lps_enter)(void *);
    int (*lps_leave)(void *);
    int (*bt_query)(void *, struct btc_coexist *,
        enum rtwn8723be_btc_policy_bt_query, uint32_t *);
    void (*fault)(void *, int);
};

/*
 * This is per-device state.  Linux used one file-static aggregation timestamp;
 * the NetBSD adaptation keeps the same 8-second decision per device so two
 * adapters cannot suppress one another's aggregation recovery.
 */
struct rtwn8723be_btc_policy {
    const struct rtwn8723be_btc_policy_ops *ops;
    void *arg;
    uint64_t aggregate_last_msec;
    bool initialized;
};

int rtwn8723be_btc_policy_init(struct rtwn8723be_btc_policy *,
    const struct rtwn8723be_btc_policy_ops *, void *);
void rtwn8723be_btc_policy_fini(struct rtwn8723be_btc_policy *);

/*
 * result is the frozen provider's boolean return.  A nonzero C return is a
 * fallible-owner failure and has already been reported through fault().
 */
int rtwn8723be_btc_policy_get(struct rtwn8723be_btc_policy *,
    struct btc_coexist *, u8, void *, bool *);
int rtwn8723be_btc_policy_set(struct rtwn8723be_btc_policy *,
    struct btc_coexist *, u8, void *, bool *);

/* Install the two high-level callback providers into an otherwise complete
 * coexistence context.  This does not initialize, register or start hardware.
 */
int rtwn8723be_btc_policy_bind(struct btc_coexist *,
    struct rtwn8723be_btc_policy *);

#endif /* _RTWN8723BE_BTC_POLICY_H_ */
