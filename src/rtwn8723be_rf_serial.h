/* SPDX-License-Identifier: GPL-2.0
 * Portable Linux rtl8723com/phy_common.c RF-serial protocol for RTL8723BE.
 * Frozen Linux reference: fd179f8a05be3ccae366b9b96e176b51fbe54aab.
 *
 * Not a native NetBSD MMIO adapter. Caller must hold its RF lock and
 * guarantee the BB/RF power, ownership and bus-space lifetime prerequisites.
 */
#ifndef _RTWN8723BE_RF_SERIAL_H_
#define _RTWN8723BE_RF_SERIAL_H_
#include <sys/types.h>
#include <stdint.h>
#include <stdbool.h>

#define RTWN8723BE_RF_PATH_A 0U
#define RTWN8723BE_RF_PATH_B 1U
#define RTWN8723BE_RF_FULL_MASK 0x000fffffU

struct rtwn8723be_rf_serial_io {
    bool (*ready)(void *);
    int (*read_bb)(void *, uint32_t, uint32_t *);
    int (*write_bb)(void *, uint32_t, uint32_t);
    void (*delay_us)(void *, unsigned int);
};

struct rtwn8723be_rf_serial_ctx {
    const struct rtwn8723be_rf_serial_io *io;
    void *dev;
};

int rtwn8723be_rf_serial_write(const struct rtwn8723be_rf_serial_ctx *,
    unsigned int path, uint32_t reg, uint32_t value);
int rtwn8723be_rf_serial_read(const struct rtwn8723be_rf_serial_ctx *,
    unsigned int path, uint32_t reg, uint32_t *value);
int rtwn8723be_rf_masked_write(const struct rtwn8723be_rf_serial_ctx *,
    unsigned int path, uint32_t reg, uint32_t mask, uint32_t value);
/* Compatible with rtwn8723be_phy_run_radio_a() table-write callback. */
int rtwn8723be_rf_radio_a_apply(void *, uint32_t reg, uint32_t value);
#endif /* _RTWN8723BE_RF_SERIAL_H_ */
