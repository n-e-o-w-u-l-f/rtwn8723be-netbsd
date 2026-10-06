/* SPDX-License-Identifier: GPL-2.0 */
#ifndef BTC_ALGORITHM_MODEL_H
#define BTC_ALGORITHM_MODEL_H
#include "rtwn8723be_btc_engine.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

struct btc_trace { u32 op, a, b, c, d; u8 bytes[16]; };
struct btc_model {
    u8 mmio[65536];
    u32 rf[4][256], bt[5][256], inputs[BTC_GET_MAX];
    struct btc_trace trace[4096];
    unsigned int count;
    struct seq_file sink;
};
void btc_model_init(struct btc_model *, struct btc_coexist *, unsigned int,
    unsigned int, unsigned int);
void btc_model_inputs(struct btc_model *, unsigned int, unsigned int);
struct rtwn8723be_btc_event btc_model_event(unsigned int, unsigned int,
    unsigned int, struct btc_model *);
void btc_model_equal(const struct btc_model *, const struct btc_model *);
void btc_state_equal(const struct rtwn8723be_btc_state *,
    const struct rtwn8723be_btc_state *);
void btc_context_equal(const struct btc_coexist *, const struct btc_coexist *);
void btc_reference_delay(unsigned int);
extern struct btc_coexist *btc_reference_current;
void btc_reference1(struct btc_coexist *, const struct rtwn8723be_btc_event *,
    struct coex_dm_8723b_1ant *, struct coex_sta_8723b_1ant *);
void btc_reference2(struct btc_coexist *, const struct rtwn8723be_btc_event *,
    struct coex_dm_8723b_2ant *, struct coex_sta_8723b_2ant *);
#endif
