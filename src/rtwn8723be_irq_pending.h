/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Source-shared pending-IRQ ledger for RTL8723BE hard IRQ / SOFTINT_NET.
 *
 * The caller MUST hold sc_irq_lock (IPL_NET) for record, take and clear.
 * No separate atomic or volatile read makes the hardware/stop ownership
 * safe without that common lock. An IRQ is delivered only while the
 * lifecycle has explicitly requested interrupts and RX/TX dispatch exists.
 */
#ifndef _RTWN8723BE_IRQ_PENDING_H_
#define _RTWN8723BE_IRQ_PENDING_H_

#include "rtwn8723be_os_compat.h"

static inline bool
rtwn8723be_irq_pending_record(volatile uint32_t pending[2],
    bool requested, bool dispatch_ready, uint32_t inta, uint32_t intb)
{
    if (pending == NULL || !requested || !dispatch_ready ||
        (inta | intb) == 0)
        return false;
    pending[0] |= inta;
    pending[1] |= intb;
    return true;
}

static inline bool
rtwn8723be_irq_pending_take(volatile uint32_t pending[2],
    bool requested, bool dispatch_ready, uint32_t *inta, uint32_t *intb)
{
    uint32_t a, b;

    if (pending == NULL || inta == NULL || intb == NULL)
        return false;
    a = pending[0];
    b = pending[1];
    pending[0] = 0;
    pending[1] = 0;

    /*
     * After STOP begins, stale work is retired without dereferencing
     * callback pointers or allowing a late softint to re-open hardware.
     */
    if (!requested || !dispatch_ready) {
        *inta = 0;
        *intb = 0;
        return false;
    }
    *inta = a;
    *intb = b;
    return (a | b) != 0;
}

static inline void
rtwn8723be_irq_pending_clear(volatile uint32_t pending[2])
{
    if (pending != NULL) {
        pending[0] = 0;
        pending[1] = 0;
    }
}

#endif /* _RTWN8723BE_IRQ_PENDING_H_ */
