/* SPDX-License-Identifier: GPL-2.0
 * Frozen Linux rtl8723be/rf.c:_rtl8723be_phy_rf6052_config_parafile().
 *
 * One selected RF path at a time; caller derives count from actual RF type,
 * holds RF lock and owns mapped/powered BB resources. Path B does not require
 * a Radio-A table and may pass initialize=NULL, exactly as in Linux.
 * All paths restore saved RFENV even when table/setup reports a failure.
 */
#include <sys/types.h>
#include "rtwn8723be_os_compat.h"
#include "rtwn8723be_rf_path.h"

#define RFPGA0_XAB_RFINTERFACESW 0x870U
#define RFPGA0_XA_RFINTERFACEOE 0x860U
#define RFPGA0_XB_RFINTERFACEOE 0x864U
#define RFPGA0_XA_HSSIPARAMETER2 0x824U
#define RFPGA0_XB_HSSIPARAMETER2 0x82cU
#define BRFSI_RFENV 0x10U
#define B3WIREADDREAALENGTH 0x400U
#define B3WIREDATALENGTH 0x800U

static int
rf_set_bb_mask(const struct rtwn8723be_rf_serial_ctx *ctx,
    uint32_t reg, uint32_t mask, uint32_t value)
{
    uint32_t full;
    unsigned int shift = 0;
    int error;

    error = ctx->io->read_bb(ctx->dev, reg, &full);
    if (error != 0)
        return error;
    while ((mask & (1U << shift)) == 0)
        shift++;
    full = (full & ~mask) | (value << shift);
    return ctx->io->write_bb(ctx->dev, reg, full);
}

int
rtwn8723be_rf_path_configure(
    const struct rtwn8723be_rf_serial_ctx *ctx,
    unsigned int path, rtwn8723be_rf_path_init_fn initialize,
    void *initialize_arg)
{
    uint32_t rfintfo, hssi2, rfenv_mask, saved_env, value;
    int error, restore_error;

    if (ctx == NULL || ctx->io == NULL ||
        path > RTWN8723BE_RF_PATH_B ||
        (path == RTWN8723BE_RF_PATH_A && initialize == NULL))
        return EINVAL;
    if (ctx->io->ready == NULL || ctx->io->read_bb == NULL ||
        ctx->io->write_bb == NULL || ctx->io->delay_us == NULL)
        return EINVAL;
    if (!ctx->io->ready(ctx->dev))
        return ENXIO;

    rfintfo = path == RTWN8723BE_RF_PATH_A ?
        RFPGA0_XA_RFINTERFACEOE : RFPGA0_XB_RFINTERFACEOE;
    hssi2 = path == RTWN8723BE_RF_PATH_A ?
        RFPGA0_XA_HSSIPARAMETER2 : RFPGA0_XB_HSSIPARAMETER2;
    rfenv_mask = path == RTWN8723BE_RF_PATH_A ?
        BRFSI_RFENV : BRFSI_RFENV << 16;

    error = ctx->io->read_bb(ctx->dev, RFPGA0_XAB_RFINTERFACESW, &value);
    if (error != 0)
        return error;
    saved_env = (value & rfenv_mask) != 0 ? 1U : 0U;

    /* rfintfe is the upper half of the same A/B path-specific OE register. */
    error = rf_set_bb_mask(ctx, rfintfo, BRFSI_RFENV << 16, 1);
    if (error != 0)
        goto restore;
    ctx->io->delay_us(ctx->dev, 1);

    error = rf_set_bb_mask(ctx, rfintfo, BRFSI_RFENV, 1);
    if (error != 0)
        goto restore;
    ctx->io->delay_us(ctx->dev, 1);

    error = rf_set_bb_mask(ctx, hssi2, B3WIREADDREAALENGTH, 0);
    if (error != 0)
        goto restore;
    ctx->io->delay_us(ctx->dev, 1);

    error = rf_set_bb_mask(ctx, hssi2, B3WIREDATALENGTH, 0);
    if (error != 0)
        goto restore;
    ctx->io->delay_us(ctx->dev, 1);

    error = initialize == NULL ? 0 : initialize(initialize_arg, path);

restore:
    /* Reference restores rfintfs after Radio-A/B even when it failed. */
    restore_error = rf_set_bb_mask(ctx, RFPGA0_XAB_RFINTERFACESW,
        rfenv_mask, saved_env);
    if (restore_error != 0)
        return restore_error;
    return error;
}
