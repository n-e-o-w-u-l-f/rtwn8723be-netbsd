/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_C2H_H_
#define _RTWN8723BE_C2H_H_

#include "rtwn8723be_os_compat.h"

/* Frozen Linux rtlwifi/wifi.h: enum rtl_c2h_evt_v1 and C2H_DATA_OFFSET. */
enum rtwn8723be_c2h_kind {
    R23BE_C2H_DEBUG = 0,
    R23BE_C2H_LOOPBACK = 1,
    R23BE_C2H_TXBF = 2,
    R23BE_C2H_TX_REPORT = 3,
    R23BE_C2H_BT_INFO = 9,
    R23BE_C2H_BT_MP = 11,
    R23BE_C2H_RA_REPORT = 12,
    R23BE_C2H_FW_SWITCH_CHANNEL = 0x10,
    R23BE_C2H_IQK_FINISH = 0x11,
    R23BE_C2H_EXT_V2 = 0xff
};

struct rtwn8723be_c2h_event {
    uint8_t id;
    uint8_t sequence;
    const uint8_t *payload; /* Borrowed: valid only during RX callback. */
    size_t payload_length;
    bool recognized;
    bool fast; /* Linux rtl_c2h_fast_cmd(): C2H_BT_MP only. */
    bool tx_report_valid;
    uint8_t tx_report_sequence;
    uint8_t tx_report_status;
    uint8_t tx_report_retry;
};

/*
 * Decode the 2-byte firmware C2H envelope and v1 TX report fields.
 * This function only reads caller-owned data; it does NOT store a borrowed
 * RX pointer, access DMA, acknowledge firmware, or dispatch asynchronous
 * work. Unsupported v2 envelopes are returned as recognized but opaque.
 */
int rtwn8723be_c2h_decode(const uint8_t *, size_t,
    struct rtwn8723be_c2h_event *);


/*
 * Synchronous host-side C2H consumers. The callbacks receive borrowed
 * DMA-backed payload pointers; they MUST copy data if deferring work.
 * Event-specific callbacks are mandatory to process their respective
 * events. Do not acknowledge a TX report or BT event without a consumer.
 * The caller serializes against stop/detach and firmware state reset.
 */
struct rtwn8723be_c2h_handlers {
    void *arg;
    int (*tx_report)(void *, const struct rtwn8723be_c2h_event *);
    int (*ra_report)(void *, const struct rtwn8723be_c2h_event *);
    int (*bt_info)(void *, const struct rtwn8723be_c2h_event *);
    int (*bt_mp)(void *, const struct rtwn8723be_c2h_event *);
};

/*
 * Validate and route a raw C2H event from the already DMA-synchronized RX
 * buffer; return ENOSYS for a required but absent event handler, EMSGSIZE
 * for malformed v1 TX reports. Opaque v2 events remain EOPNOTSUPP.
 * Debug, loopback, TXBF and unknown events match pinned Linux's no-op
 * logging behavior without fabricated hardware state changes.
 */
int rtwn8723be_c2h_route(const uint8_t *, size_t,
    const struct rtwn8723be_c2h_handlers *);

#endif
