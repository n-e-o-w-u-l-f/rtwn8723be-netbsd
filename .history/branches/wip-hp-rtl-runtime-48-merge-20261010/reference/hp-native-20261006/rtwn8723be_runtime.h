/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_RUNTIME_H_
#define _RTWN8723BE_RUNTIME_H_
#include <sys/mutex.h>
#include <sys/condvar.h>
#include <sys/workqueue.h>
#include <sys/callout.h>
#include "rtwn8723be_net80211.h"
#include "rtwn8723be_datapath.h"
#include "rtwn8723be_net80211_tx.h"
#include "rtwn8723be_reserved_native.h"
#include "rtwn8723be_dm_native.h"
#include "rtwn8723be_channel_native.h"
#include "rtwn8723be_media_native.h"
#include "rtwn8723be_btc_provider_native.h"

#define R23BE_RUNTIME_QUEUE 32U
enum rtwn8723be_runtime_job_kind {
    R23BE_RUNTIME_STATE, R23BE_RUNTIME_WATCHDOG, R23BE_RUNTIME_SCAN,
    R23BE_RUNTIME_QUIESCE
};
struct rtwn8723be_runtime_job {
    enum rtwn8723be_runtime_job_kind kind;
    enum ieee80211_state state;
    int arg;
    uint64_t generation;
};
struct rtwn8723be_runtime_scan_entry {
    struct rtwn8723be_runtime_scan_entry *next;
    uint32_t age;
    uint8_t bssid[6];
};

struct rtwn8723be_runtime {
    /* Thread-only transition mutex; never held while waiting for this work. */
    kmutex_t lifecycle_lock;
    /* Sleepable RF/DM/MMIO owner, always before the BTC engine mutex. */
    kmutex_t io_lock;
    kmutex_t queue_lock; /* IPL_SOFTNET copied jobs / admission */
    kmutex_t stats_lock; /* IPL_SOFTNET actual RX/TX producers */
    struct workqueue *workqueue;
    struct work work;
    struct lwp *worker;
    struct callout watchdog, scan;
    struct rtwn8723be_runtime_job jobs[R23BE_RUNTIME_QUEUE];
    unsigned int head, count;
    bool scheduled, jobs_enabled, initialized, closing, faulted;
    bool rf_on, rf_state_valid, rfkill_valid, radio_blocked, unloading;
    bool mcu_rx_drained, fw_in_ps, in_lps, report_linked;
    bool rfkill_polling, shutdown_active, poweroff_verified;
    bool resume_up;
    bool transition;
    unsigned int io_depth;
    uint64_t generation, rx_generation;
    int first_error, shutdown_error;
    int (*newstate)(struct ieee80211com *, enum ieee80211_state, int);
    struct rtwn8723be_net80211 net;
    struct rtwn8723be_datapath datapath;
    struct rtwn8723be_net80211_tx tx;
    struct rtwn8723be_reserved_native reserved;
    struct rtwn8723be_dm_native dm;
    struct rtwn8723be_dm_rx_state rx;
    struct rtwn8723be_channel_state channel;
    struct rtwn8723be_media_state media;
    struct rtwn8723be_eeprom_txpower txpower;
    struct rtwn8723be_btc_wifi_state wifi;
    struct rtwn8723be_dm_rate_inputs rates;
    struct rtwn8723be_thermal_inputs thermal;
    struct rtwn8723be_runtime_scan_entry *scan_entries;
    uint32_t scan_count;
    uint32_t rx_period, tx_period, rx_history[4], tx_history[4];
    uint32_t linked_periods, roam_periods;
    uint64_t rx_bytes, tx_bytes, last_special_tick, in_4way_tick;
    uint64_t aggregate_tick;
    uint32_t edca_be;
    uint8_t slot_time;
};

int rtwn8723be_runtime_init(struct rtwn8723be_softc *);
int rtwn8723be_runtime_fini(struct rtwn8723be_softc *);
int rtwn8723be_runtime_register(void *);
int rtwn8723be_runtime_rfkill_init(void *);
int rtwn8723be_runtime_bt_prepare(void *);
int rtwn8723be_runtime_bt_hw_init(void *);
int rtwn8723be_runtime_dm_init(void *);
int rtwn8723be_runtime_bt_halt(void *);
int rtwn8723be_runtime_wait_rf(void *);
int rtwn8723be_runtime_btc_event(struct rtwn8723be_softc *,
    enum rtwn8723be_btc_event_kind, uint8_t);
int rtwn8723be_runtime_start(struct rtwn8723be_softc *);
int rtwn8723be_runtime_stop(struct rtwn8723be_softc *);
int rtwn8723be_runtime_unregister(struct rtwn8723be_softc *);
int rtwn8723be_runtime_io_enter(struct rtwn8723be_softc *);
void rtwn8723be_runtime_io_exit(struct rtwn8723be_softc *);
void rtwn8723be_runtime_poweroff(struct rtwn8723be_softc *, int);
bool rtwn8723be_runtime_mcu_prepared(struct rtwn8723be_softc *);
bool rtwn8723be_runtime_poweroff_verified(struct rtwn8723be_softc *);
void rtwn8723be_runtime_tx_produce(struct rtwn8723be_softc *,
    const uint8_t *, size_t, uint8_t);
int rtwn8723be_runtime_suspend(struct rtwn8723be_softc *);
int rtwn8723be_runtime_resume(struct rtwn8723be_softc *);
#endif
