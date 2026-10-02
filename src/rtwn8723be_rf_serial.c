/* SPDX-License-Identifier: GPL-2.0
 * Exact 8-bit-address / 20-bit-data RF serial transactions from frozen Linux
 * rtl8723com/phy_common.c:rtl8723_phy_rf_serial_read/write() and
 * rtl8723be/phy.c:rtl8723be_phy_set_rf_reg(), _rtl8723be_config_rf_reg().
 * The platform adapter provides already serialized, full-width BB access;
 * the caller holds the RF lock and manages MMIO/power/recovery lifetime.
 */
#include <sys/types.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#include "rtwn8723be_rf_serial.h"

#define RF_A_HSSI2 0x824U
#define RF_B_HSSI2 0x82cU
#define RF_A_HSSI1 0x820U
#define RF_B_HSSI1 0x828U
#define RF_A_3WIRE 0x840U
#define RF_B_3WIRE 0x844U
#define RF_A_LSSI_RB 0x8a0U
#define RF_B_LSSI_RB 0x8a4U
#define RF_A_PI_RB 0x8b8U
#define RF_B_PI_RB 0x8bcU
#define RF_LSSI_READ_ADDRESS 0x7f800000U
#define RF_LSSI_READ_EDGE 0x80000000U

static int
rf_check(const struct rtwn8723be_rf_serial_ctx *ctx, unsigned int path,
    bool read_required, bool delay_required)
{
    const struct rtwn8723be_rf_serial_io *io;

    if (ctx == NULL || ctx->io == NULL ||
        path > RTWN8723BE_RF_PATH_B)
        return EINVAL;
    io = ctx->io;
    if (io->ready == NULL || io->write_bb == NULL ||
        (read_required && io->read_bb == NULL) ||
        (delay_required && io->delay_us == NULL))
        return EINVAL;
    if (!io->ready(ctx->dev))
        return ENXIO;
    return 0;
}

int
rtwn8723be_rf_serial_write(const struct rtwn8723be_rf_serial_ctx *ctx,
    unsigned int path, uint32_t reg, uint32_t value)
{
    uint32_t packed;
    int error;

    error = rf_check(ctx, path, false, false);
    if (error != 0)
        return error;

    packed = (((reg & 0xffU) << 20) |
        (value & RTWN8723BE_RF_FULL_MASK)) & 0x0fffffffU;
    return ctx->io->write_bb(ctx->dev,
        path == RTWN8723BE_RF_PATH_A ? RF_A_3WIRE : RF_B_3WIRE, packed);
}

int
rtwn8723be_rf_serial_read(const struct rtwn8723be_rf_serial_ctx *ctx,
    unsigned int path, uint32_t reg, uint32_t *value)
{
    uint32_t tmplong, tmplong2, rfpi_enable, readback;
    uint32_t hssi2, hssi1, rb, rbpi;
    int error;

    if (value == NULL)
        return EINVAL;
    error = rf_check(ctx, path, true, true);
    if (error != 0)
        return error;

    hssi2 = path == RTWN8723BE_RF_PATH_A ? RF_A_HSSI2 : RF_B_HSSI2;
    hssi1 = path == RTWN8723BE_RF_PATH_A ? RF_A_HSSI1 : RF_B_HSSI1;
    rb = path == RTWN8723BE_RF_PATH_A ? RF_A_LSSI_RB : RF_B_LSSI_RB;
    rbpi = path == RTWN8723BE_RF_PATH_A ? RF_A_PI_RB : RF_B_PI_RB;

    error = ctx->io->read_bb(ctx->dev, RF_A_HSSI2, &tmplong);
    if (error != 0)
        return error;
    tmplong2 = tmplong;
    if (path == RTWN8723BE_RF_PATH_B) {
        error = ctx->io->read_bb(ctx->dev, hssi2, &tmplong2);
        if (error != 0)
            return error;
    }

    tmplong2 = (tmplong2 & ~RF_LSSI_READ_ADDRESS) |
        ((reg & 0xffU) << 23) | RF_LSSI_READ_EDGE;
    error = ctx->io->write_bb(ctx->dev, RF_A_HSSI2,
        tmplong & ~RF_LSSI_READ_EDGE);
    if (error != 0)
        return error;
    error = ctx->io->write_bb(ctx->dev, hssi2, tmplong2);
    if (error != 0)
        return error;
    error = ctx->io->write_bb(ctx->dev, RF_A_HSSI2,
        tmplong | RF_LSSI_READ_EDGE);
    if (error != 0)
        return error;

    ctx->io->delay_us(ctx->dev, 120);
    error = ctx->io->read_bb(ctx->dev, hssi1, &rfpi_enable);
    if (error != 0)
        return error;
    error = ctx->io->read_bb(ctx->dev,
        (rfpi_enable & (1U << 8)) != 0 ? rbpi : rb, &readback);
    if (error != 0)
        return error;
    *value = readback & RTWN8723BE_RF_FULL_MASK;
    return 0;
}

int
rtwn8723be_rf_masked_write(const struct rtwn8723be_rf_serial_ctx *ctx,
    unsigned int path, uint32_t reg, uint32_t mask, uint32_t value)
{
    uint32_t original;
    unsigned int shift = 0;
    int error;

    if (mask == 0 || (mask & ~RTWN8723BE_RF_FULL_MASK) != 0)
        return EINVAL;
    if (mask == RTWN8723BE_RF_FULL_MASK)
        return rtwn8723be_rf_serial_write(ctx, path, reg, value);

    error = rtwn8723be_rf_serial_read(ctx, path, reg, &original);
    if (error != 0)
        return error;
    while ((mask & (1U << shift)) == 0)
        shift++;

    /* Match Linux's shifted input semantics; final serial write masks to 20b. */
    original = (original & ~mask) | (value << shift);
    return rtwn8723be_rf_serial_write(ctx, path, reg, original);
}

int
rtwn8723be_rf_radio_a_apply(void *arg, uint32_t reg, uint32_t value)
{
    const struct rtwn8723be_rf_serial_ctx *ctx = arg;
    int error;

    error = rf_check(ctx, RTWN8723BE_RF_PATH_A, false, true);
    if (error != 0)
        return error;
    if (reg == 0xfeU || reg == 0xffeU) {
        ctx->io->delay_us(ctx->dev, 50000);
        return 0;
    }

    error = rtwn8723be_rf_serial_write(ctx, RTWN8723BE_RF_PATH_A,
        reg, value);
    if (error != 0)
        return error;
    ctx->io->delay_us(ctx->dev, 1);
    return 0;
}
