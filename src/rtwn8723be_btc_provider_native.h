/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_BTC_PROVIDER_NATIVE_H_
#define _RTWN8723BE_BTC_PROVIDER_NATIVE_H_
#include "rtwn8723be_btc_engine.h"

struct rtwn8723be_softc;

/* A locked snapshot of actual net80211, watchdog, RX-DM and MCU producers.
 * It is not an EEPROM-derived claim that the runtime owner exists. */
struct rtwn8723be_btc_wifi_state {
    bool connected, busy, scanning, linking, in_4way, ap, encrypted, under_b;
    bool under_5g;
    int32_t rssi;
    uint32_t bandwidth, direction, firmware_version, link_status;
    uint8_t channel, ap_count;
};

int rtwn8723be_btc_provider_native_context(struct rtwn8723be_softc *,
    struct btc_coexist *);

/* Native owner adapters called by providers under io -> engine exclusion. */
int rtwn8723be_runtime_btc_snapshot(struct rtwn8723be_softc *,
    struct rtwn8723be_btc_wifi_state *);
int rtwn8723be_runtime_lps(struct rtwn8723be_softc *, bool);
int rtwn8723be_runtime_aggregate(struct rtwn8723be_softc *,
    struct btc_bt_info *);
int rtwn8723be_runtime_read_rf(struct rtwn8723be_softc *, unsigned int,
    uint32_t, uint32_t, uint32_t *);
int rtwn8723be_runtime_write_rf(struct rtwn8723be_softc *, unsigned int,
    uint32_t, uint32_t, uint32_t);
bool rtwn8723be_runtime_io_ready(struct rtwn8723be_softc *);
#endif
