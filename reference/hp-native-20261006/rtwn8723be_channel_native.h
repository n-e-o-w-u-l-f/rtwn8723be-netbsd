/* SPDX-License-Identifier: GPL-2.0 */
/* Frozen Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab. */
#ifndef _RTWN8723BE_CHANNEL_NATIVE_H_
#define _RTWN8723BE_CHANNEL_NATIVE_H_
#include "rtwn8723be_os_compat.h"
#include "rtwn8723be_txpwr_pg.h"

/* Pinned rtlwifi HT_CHANNEL_WIDTH_* and PRIME_CHNL_OFFSET_* values. */
#define R23BE_CHANNEL_BW20 0U
#define R23BE_CHANNEL_BW40 1U
#define R23BE_CHANNEL_SC_NONE 0U
#define R23BE_CHANNEL_SC_LOWER 1U
#define R23BE_CHANNEL_SC_UPPER 2U
#define R23BE_CHANNEL_RATE_COUNT 20U /* CCK, OFDM, MCS0..7: actual 1T1R */

struct rtwn8723be_eeprom_txpower {
    uint8_t cck[2][14];
    uint8_t ht40[2][14];
    int8_t bw20_diff[2][4];
    int8_t bw40_diff[2][4];
    int8_t ofdm_diff[2][4];
    uint8_t regulatory;
    bool valid;
    bool defaults;
    bool bw40_valid;
};

/* Atomic output; short PROM does not publish partial power data. */
int rtwn8723be_eeprom_txpower_parse(struct rtwn8723be_eeprom_txpower *,
    const uint8_t *, size_t, bool autoload_fail);

struct rtwn8723be_channel_state {
    uint32_t rf_chnlval[2];
    uint8_t power_index[R23BE_CHANNEL_RATE_COUNT];
    uint8_t current_channel; /* Linux wide/center channel used for TXpower */
    uint8_t primary_channel;
    uint8_t current_bw;
    uint8_t prime_sc;
    bool rf_valid;
    bool valid;
    bool power_valid;
    bool inprogress;
    bool quarantined;
};

/*
 * Caller holds the real sleepable runtime I/O/lifecycle owner throughout.
 * ready excludes stop, detach, power-off, parallel RF/BTC/DM calibration.
 * Native callbacks MUST enforce that same owner before touching bus_space.
 * channel_access is Linux set_channel_access(), called after the channel
 * RF write and 10ms wait, before the MAC/BB/RF bandwidth callback.
 * ht is false for the current IEEE80211_NO_HT net80211 binding.
 */
struct rtwn8723be_channel_io {
    bool (*ready)(void *);
    int (*read8)(void *, uint32_t, uint8_t *);
    int (*write8)(void *, uint32_t, uint8_t);
    int (*write_bb)(void *, uint32_t, uint32_t, uint32_t);
    int (*write_rf)(void *, unsigned int, uint32_t, uint32_t, uint32_t);
    int (*delay_ms)(void *, unsigned int);
    int (*channel_access)(void *, bool ht);
};

/* Only initialization after RF_CHANNEL_STATE may clear quarantine. */
int rtwn8723be_channel_state_seed(struct rtwn8723be_channel_state *,
    const uint32_t [2], unsigned int rf_paths);
void rtwn8723be_channel_state_invalidate(struct rtwn8723be_channel_state *);

/* Pure per-rate source arithmetic, including Linux u8 wrapping then cap. */
int rtwn8723be_channel_power_indices(const struct rtwn8723be_eeprom_txpower *,
    const struct rtwn8723be_txpwr_pg_state *, unsigned int channel,
    unsigned int bandwidth, uint8_t [R23BE_CHANNEL_RATE_COUNT]);

/*
 * Runs switch_channel -> channel_access -> set_bw_mode in source order.
 * Primary/center conversion matches core.c HT40MINUS/PLUS; a 20MHz caller
 * passes SC_NONE and ht=false. No output state is committed until all
 * operations succeed. Any potentially partial write failure quarantines
 * the state until a full hardware reinitialization reseeds it.
 */
int rtwn8723be_channel_apply(const struct rtwn8723be_channel_io *, void *,
    struct rtwn8723be_channel_state *,
    const struct rtwn8723be_eeprom_txpower *,
    const struct rtwn8723be_txpwr_pg_state *, unsigned int primary_channel,
    unsigned int bandwidth, unsigned int prime_sc, bool ht);

/* Thermal/BTC refresh uses the last committed channel and width. */
int rtwn8723be_channel_txpower_refresh(const struct rtwn8723be_channel_io *,
    void *, struct rtwn8723be_channel_state *,
    const struct rtwn8723be_eeprom_txpower *,
    const struct rtwn8723be_txpwr_pg_state *);
#endif
