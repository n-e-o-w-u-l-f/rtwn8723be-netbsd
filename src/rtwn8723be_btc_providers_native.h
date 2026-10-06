/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_BTC_PROVIDERS_NATIVE_H_
#define _RTWN8723BE_BTC_PROVIDERS_NATIVE_H_

#include "rtwn8723be_btc_linux_types.h"

struct rtwn8723be_softc;

/*
 * Seed only providers whose frozen Linux semantics map directly to existing
 * NetBSD MMIO/BB/RF/H2C primitives.  This does NOT make the coexistence
 * context complete and must not be used as evidence that bt_prepare can bind.
 */
int rtwn8723be_btc_native_seed_lowlevel(struct btc_coexist *,
    struct rtwn8723be_softc *);

#endif
