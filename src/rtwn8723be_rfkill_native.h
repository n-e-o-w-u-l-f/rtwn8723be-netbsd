/* SPDX-License-Identifier: GPL-2.0 */
/*
 * RTL8723BE RF-kill polling thread/callout resource owner.
 * Source reference: pinned rtlwifi/base.c:rtl_init_rfkill() and
 * NetBSD 11 sys/callout.h / sys/workqueue.h. No fake radio status.
 */
#ifndef _RTWN8723BE_RFKILL_NATIVE_H_
#define _RTWN8723BE_RFKILL_NATIVE_H_

#include <sys/types.h>
#include <sys/mutex.h>
#include <sys/callout.h>
#include <sys/workqueue.h>

struct rtwn8723be_softc;

struct rtwn8723be_rfkill_native {
    kmutex_t lock;                 /* IPL_SOFTNET, protects all worker state */
    callout_t timer;               /* softclock: enqueue ONLY, no MMIO */
    struct workqueue *wq;          /* real NetBSD kernel thread context */
    struct work poll_work;
    bool initialized;
    bool active;
    bool work_queued;
    bool last_valid;
    bool last_radio_on;
    unsigned int samples;
    int last_error;
};

/*
 * Only valid after net80211 registration and before IRQ establishment,
 * matching Linux rtl_pci_probe() -> rtl_init_rfkill().  The owner must
 * call fini and drain both the callout and worker BEFORE PCI BAR unmap,
 * RF-PS lock destruction or ieee80211_ifdetach().
 *
 * These methods are intentionally NOT connected to sc_linux.ops until
 * complete reverse-order probe rollback and net80211 radio-state
 * notification/stop have been proven.
 */
int rtwn8723be_rfkill_native_init(void *);
int rtwn8723be_rfkill_native_fini(struct rtwn8723be_softc *);

#endif /* _RTWN8723BE_RFKILL_NATIVE_H_ */
