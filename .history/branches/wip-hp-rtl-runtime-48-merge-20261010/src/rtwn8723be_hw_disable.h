/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_HW_DISABLE_H_
#define _RTWN8723BE_HW_DISABLE_H_
#include "rtwn8723be_os_compat.h"

struct rtwn8723be_hw_disable_state {
    uint8_t bcn_ctrl, mac_link_state;
    uint32_t cur_ps_level;
    bool poweroff_attempted, powered_off;
    int last_error, poweroff_error;
};
struct rtwn8723be_hw_disable_inputs {
    /* Real MAC/RF-PS state, unload flag and exclusion supplied by owner. */
    bool state_valid, rf_idle, driver_is_goingto_unload;
    uint32_t rfoff_reason;
    bool led_opendrain;
    uint8_t led_pin;
};
struct rtwn8723be_hw_disable_io {
    bool (*ready)(void *);
    int (*read_1)(void *, uint32_t, uint8_t *);
    int (*write_1)(void *, uint32_t, uint8_t);
    /* Existing real pinned poweroff engine, under this same lifetime hold. */
    int (*poweroff)(void *);
};

/*
 * Exact pinned card-disable media/LED/PS sequence. Real BTC HAL capability
 * returns true in this pin, so this function never clears the IQK cache.
 * Caller holds lifetime and MAC/RF-PS exclusion after IRQ/DM/RF quiescence.
 * Poweroff is attempted after a fallible media/LED failure while lifetime
 * remains held. It cannot be rolled back; partial completion is reported.
 */
int rtwn8723be_hw_disable(const struct rtwn8723be_hw_disable_io *, void *,
    struct rtwn8723be_hw_disable_state *,
    const struct rtwn8723be_hw_disable_inputs *);
#endif
