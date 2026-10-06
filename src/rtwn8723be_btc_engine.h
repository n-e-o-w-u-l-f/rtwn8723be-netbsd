/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _R23BE_BTC_ENGINE_H_
#define _R23BE_BTC_ENGINE_H_
#include "rtwn8723be_btc_linux_types.h"
#include "rtwn8723be_btc1_types.h"
#include "rtwn8723be_btc2_types.h"
#include "rtwn8723be_btc_history.h"

/* This state, including every former static history, belongs to one device.
 * The native owner serializes all engine calls; C2H must copy and defer BTC
 * notifications to a sleepable worker. MP reply delivery has a separate lock.
 */
struct rtwn8723be_btc_state {
    struct btc_coexist btc;
    struct coex_dm_8723b_1ant dm1;
    struct coex_sta_8723b_1ant sta1;
    struct coex_dm_8723b_2ant dm2;
    struct coex_sta_8723b_2ant sta2;
    struct rtwn8723be_btc_history1 history1;
    struct rtwn8723be_btc_history2 history2;
    bool prepared;
};

enum rtwn8723be_btc_event_kind {
    R23BE_BTC_POWER_ON, R23BE_BTC_PRELOAD, R23BE_BTC_INIT_HW,
    R23BE_BTC_INIT_DM, R23BE_BTC_IPS, R23BE_BTC_LPS,
    R23BE_BTC_SCAN, R23BE_BTC_CONNECT, R23BE_BTC_MEDIA,
    R23BE_BTC_SPECIAL_PACKET, R23BE_BTC_INFO, R23BE_BTC_RF_STATUS,
    R23BE_BTC_HALT, R23BE_BTC_PNP, R23BE_BTC_PERIODIC,
    R23BE_BTC_DISPLAY, R23BE_BTC_EVENT_COUNT
};
#define R23BE_BTC_INFO_MAX 10U
struct rtwn8723be_btc_event {
    enum rtwn8723be_btc_event_kind kind;
    u8 value;
    u8 length;
    u8 info[R23BE_BTC_INFO_MAX]; /* Owns C2H data: no borrowed RX pointer. */
    struct seq_file *diagnostic; /* synchronous DISPLAY only */
};

static inline struct rtwn8723be_btc_state *r23be_btc_state(struct btc_coexist *btc)
{
    return btc->r23be_state;
}
static inline void rtwn8723be_btc_delay(struct btc_coexist *btc, unsigned int ms)
{
    btc->r23be_delay_ms(btc, ms);
}
static inline void rtwn8723be_btc_debug(struct btc_coexist *btc,
    unsigned long component, int level, const char *fmt, ...)
{
    va_list ap;
    /* Optional diagnostic trace, matching Linux's disabled debug path. */
    if (btc->r23be_debug == NULL) return;
    va_start(ap, fmt);
    btc->r23be_debug(btc, component, level, fmt, ap);
    va_end(ap);
}

/* Missing any one of the original27 providers or delay rejects before MMIO.
 * Providers must implement real NetBSD semantics. The source layer cannot
 * establish their lifecycle/state-producer correctness by pointer presence.
 */
int rtwn8723be_btc_callbacks_ready(const struct btc_coexist *);
int rtwn8723be_btc_engine_init(struct rtwn8723be_btc_state *,
    const struct btc_coexist *);
int rtwn8723be_btc_event_validate(const struct rtwn8723be_btc_state *,
    const struct rtwn8723be_btc_event *);
int rtwn8723be_btc_engine_execute(struct rtwn8723be_btc_state *,
    const struct rtwn8723be_btc_event *);
#endif
