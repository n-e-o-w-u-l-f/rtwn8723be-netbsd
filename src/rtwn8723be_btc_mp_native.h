/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_BTC_MP_NATIVE_H_
#define _RTWN8723BE_BTC_MP_NATIVE_H_

#include <sys/types.h>
#include <sys/mutex.h>
#include <sys/condvar.h>

#include "rtwn8723be_btc_mp.h"
#include "rtwn8723be_c2h.h"

#define R23BE_BT_MP_H2C_ID 0x67U
#define R23BE_BT_MP_WAIT_MS 200U

struct rtwn8723be_softc;

struct rtwn8723be_btc_mp_native {
    kmutex_t lock; /* adaptive IPL_SOFTNET: thread and RX softint */
    kcondvar_t reply_cv;
    kcondvar_t drained_cv;
    struct rtwn8723be_btc_mp_reply reply; /* owns values, never RX bytes */
    uint8_t expected_sequence;
    uint64_t firmware_generation; /* MCU handshake, not a wire nonce */
    bool initialized;
    bool active;
    bool faulted;
    bool busy;
    bool pending;
    bool done;
    bool cancelled;
};

/* All entry points require a live softc. The lifecycle owner serializes
 * init/activate/fini and excludes new users before destroying storage.
 * receive may run in SOFTINT_NET, never in a hard interrupt. All other
 * entry points require a sleepable thread, with no spin locks held.
 */
int rtwn8723be_btc_mp_native_init(struct rtwn8723be_softc *);
/* Only after a REAL MCU restart/ready handshake AND old RX/IRQ drain.
 * IRQ-disabled/pending checks cannot establish the RX drain themselves.
 * This hook remains unbound until the full initialization/recovery owner
 * supplies that ordering; timeout must never be cleared by a retry.
 */
int rtwn8723be_btc_mp_native_activate(struct rtwn8723be_softc *);
/* Frozen consumers wait 200 ms; false preserves send-without-wait mode.
 * Copy the command before encoding. On error, output is unchanged.
 * One request per device: another concurrent request returns EBUSY.
 * A timeout, uncertain send, or no-wait submission quarantines the
 * channel: fixed opcode sequences cannot identify a late older reply.
 */
int rtwn8723be_btc_mp_native_request(struct rtwn8723be_softc *, uint8_t,
    const uint8_t *, size_t, bool, struct rtwn8723be_btc_mp_reply *);
int rtwn8723be_btc_mp_native_receive(struct rtwn8723be_softc *,
    const struct rtwn8723be_c2h_event *);
/* Exact callback ABI for rtwn8723be_c2h_handlers.bt_mp. No activation
 * or lifetime acquisition is implicit; the RX/lifecycle owner provides it.
 */
int rtwn8723be_btc_mp_native_c2h(void *,
    const struct rtwn8723be_c2h_event *);
/* stop cancels and drains the submitting/waiting request BEFORE H2C,
 * firmware or DMA resources can be released. Owner then drains RX/IRQs
 * and excludes all other entry points before fini destroys mutex/CVs.
 */
int rtwn8723be_btc_mp_native_stop(struct rtwn8723be_softc *);
int rtwn8723be_btc_mp_native_fini(struct rtwn8723be_softc *);

#endif
