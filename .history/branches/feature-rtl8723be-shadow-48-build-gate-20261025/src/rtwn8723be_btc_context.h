/* SPDX-License-Identifier: GPL-2.0 */
/* Pure, atomic construction of a Linux-shaped BTC coexistence context. */
#ifndef _RTWN8723BE_BTC_CONTEXT_H_
#define _RTWN8723BE_BTC_CONTEXT_H_

#include "rtwn8723be_btc_linux_types.h"

/* These are the raw RTL8723BE EFUSE encodings, not antenna counts. */
enum rtwn8723be_btc_raw_ant {
    R23BE_BTC_RAW_ANT_X2 = 0,
    R23BE_BTC_RAW_ANT_X1 = 1,
};

/* A caller must supply a complete, parsed board identity.  Hardware BT
 * presence is deliberately descriptive only: Linux still prepares the
 * coexistence context for Wi-Fi-only RTL8723BE boards. */
struct rtwn8723be_btc_context_identity {
    void *adapter;
    bool identity_valid;
    bool hwpg_bt_present;
    u8 raw_ant_num;
    u8 single_ant_path;
    u8 package_type;
};

/* Binders populate only their respective callback sets in a temporary
 * context.  They must not publish lifecycle state or alter the parsed
 * identity; the builder checks those invariants before publishing output. */
typedef int (*rtwn8723be_btc_context_bind_fn)(void *, struct btc_coexist *);

struct rtwn8723be_btc_context_binder {
    rtwn8723be_btc_context_bind_fn bind;
    void *arg;
};

struct rtwn8723be_btc_context_binders {
    struct rtwn8723be_btc_context_binder lowlevel;
    struct rtwn8723be_btc_context_binder policy;
};

/* Build into a local candidate and publish it to out only after both binders,
 * exact Linux defaults, and the existing complete callback gate succeed. */
int rtwn8723be_btc_context_build(struct btc_coexist *out,
    const struct rtwn8723be_btc_context_identity *identity,
    const struct rtwn8723be_btc_context_binders *binders);

#endif /* _RTWN8723BE_BTC_CONTEXT_H_ */
