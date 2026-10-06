/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_HW_DISABLE_NATIVE_H_
#define _RTWN8723BE_HW_DISABLE_NATIVE_H_
#include "rtwn8723be_hw_disable.h"
struct rtwn8723be_softc;

/*
 * Real stop owner excludes detach/MMIO unmap, power, channel and RF/DM work;
 * drains IRQ/softint, BTC notifications and H2C users before granting access.
 * It publishes actual RF reason, unload flag and MAC/RF-PS state at acquire.
 * release publishes partial NOLINK/HALT_NIC state and always drops the hold.
 * No owner is supplied or inferred from EFUSE by this candidate.
 */
struct rtwn8723be_hw_disable_owner {
    int (*acquire)(void *, struct rtwn8723be_softc *,
        struct rtwn8723be_hw_disable_inputs *,
        struct rtwn8723be_hw_disable_state *);
    bool (*ready)(void *, struct rtwn8723be_softc *);
    void (*release)(void *, struct rtwn8723be_softc *,
        const struct rtwn8723be_hw_disable_state *, int);
};
int rtwn8723be_netbsd_hw_disable(void *);
#endif
