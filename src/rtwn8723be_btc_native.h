/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _R23BE_BTC_NATIVE_H_
#define _R23BE_BTC_NATIVE_H_
#include <sys/types.h>
#include <sys/mutex.h>
#include <sys/condvar.h>
#include <sys/workqueue.h>
#include "rtwn8723be_btc_engine.h"

struct rtwn8723be_softc;
struct rtwn8723be_c2h_event;

/* This is the real runtime RF/DM/MMIO lifetime, supplied by the whole-driver
 * owner. It must exclude channel/PM/unmap and support sleepable H2C/MP waits.
 * EFUSE presence, IRQ-disabled flags and callback-counts are not this owner.
 */
struct rtwn8723be_btc_native_owner {
    int (*acquire)(void *, struct rtwn8723be_softc *);
    bool (*ready)(void *, struct rtwn8723be_softc *);
    void (*release)(void *, struct rtwn8723be_softc *, int);
};

#define R23BE_BTC_QUEUE_SIZE 32U
struct rtwn8723be_btc_native {
    kmutex_t queue_lock; /* IPL_SOFTNET, copied RX events and admission */
    kmutex_t engine_lock; /* IPL_NONE, all algorithm/history accesses */
    kcondvar_t calls_cv;
    struct workqueue *workqueue;
    struct lwp *worker;
    struct work work;
    struct rtwn8723be_btc_state engine;
    struct rtwn8723be_btc_event events[R23BE_BTC_QUEUE_SIZE];
    const struct rtwn8723be_btc_native_owner *owner;
    void *owner_arg;
    unsigned int head, count, calls;
    int first_error, last_error;
    bool initialized, closing, events_enabled, scheduled, faulted, halted;
};

/* Storage/activation/fini are serialized by the external lifecycle owner.
 * Full providers, actual parsed board/context and real owner are mandatory.
 * This module is built but remains unbound to start/stop until those exist.
 */
int rtwn8723be_btc_native_init(struct rtwn8723be_softc *,
    const struct btc_coexist *, const struct rtwn8723be_btc_native_owner *, void *);
int rtwn8723be_btc_native_execute(struct rtwn8723be_softc *,
    const struct rtwn8723be_btc_event *);
int rtwn8723be_btc_native_enable_events(struct rtwn8723be_softc *);
int rtwn8723be_btc_native_enqueue(struct rtwn8723be_softc *,
    const struct rtwn8723be_btc_event *);
int rtwn8723be_btc_native_c2h_info(void *, const struct rtwn8723be_c2h_event *);
/* Providers call these ONLY from their serialized algorithm invocation.
 * Record the first IO/firmware/OS failure; later providers must decline IO.
 * Partial source effects remain retained, and the device is quarantined.
 */
bool rtwn8723be_btc_native_provider_ready(struct rtwn8723be_softc *);
void rtwn8723be_btc_native_provider_error(struct rtwn8723be_softc *, int);
/* Close admission, drain copied notifications and synchronous callers before
 * HALT or firmware/H2C/RX resource release. Calling from the worker is forbidden.
 */
int rtwn8723be_btc_native_stop(struct rtwn8723be_softc *);
int rtwn8723be_btc_native_fini(struct rtwn8723be_softc *);
/* WIP runtime owner: may retire only after verified poweroff and IRQ drain. */
int rtwn8723be_btc_native_retire(struct rtwn8723be_softc *);
/* Real RTL8723BE BTC init_hw_config -> init_coex_dm phase, fail-closed.
 * Requires the complete owner/context established by bt_prepare.
 */
int rtwn8723be_netbsd_bt_hw_init(void *);
int rtwn8723be_netbsd_bt_halt_deinit(void *);
#endif
