/* SPDX-License-Identifier: GPL-2.0
 * Source-order BB, optional PG and AGC stages of the pinned Linux
 * rtl8723be/phy.c:_rtl8723be_phy_bb8723b_config_parafile().
 */
#include <sys/types.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#include "rtwn8723be_phy_bb_sequence.h"

int
rtwn8723be_phy_bb_sequence(void *ctx,
    const struct rtwn8723be_bb_sequence_ops *ops,
    bool efuse_autoload_ok, bool *cck_high_power)
{
    int error, pg_error = 0;
    bool high_power;

    if (ctx == NULL || ops == NULL || cck_high_power == NULL ||
        ops->select_antenna == NULL || ops->write_bb == NULL ||
        ops->init_txpower == NULL || ops->convert_txpower == NULL ||
        ops->write_agc == NULL || ops->read_cck_high_power == NULL)
        return EINVAL;
    /* Missing required PG implementation must fail BEFORE changing MMIO. */
    if (efuse_autoload_ok && ops->store_pg == NULL)
        return ENOSYS;

    error = ops->select_antenna(ctx);
    if (error != 0)
        return error;
    error = rtwn8723be_phy_run_bb(ctx, ops->write_bb);
    if (error != 0)
        return error;
    error = ops->init_txpower(ctx);
    if (error != 0)
        return error;
    if (efuse_autoload_ok)
        pg_error = rtwn8723be_phy_run_pg(ctx, ops->store_pg);
    /* Linux converts the power tables before examining the PG result. */
    error = ops->convert_txpower(ctx);
    if (pg_error != 0)
        return pg_error;
    if (error != 0)
        return error;
    error = rtwn8723be_phy_run_agc(ctx, ops->write_agc);
    if (error != 0)
        return error;
    error = ops->read_cck_high_power(ctx, &high_power);
    if (error != 0)
        return error;
    *cck_high_power = high_power;
    return 0;
}
