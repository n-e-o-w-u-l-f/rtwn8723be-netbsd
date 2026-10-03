/* SPDX-License-Identifier: GPL-2.0 */
#include <errno.h>
#include <stddef.h>
#include "rtwn8723be_package.h"

uint8_t
rtwn8723be_package_decode(uint8_t physical)
{
    switch (physical & 0x07U) {
    case 4:
        return RTWN8723BE_PACKAGE_TFBGA79;
    case 5:
        return RTWN8723BE_PACKAGE_TFBGA90;
    case 6:
        return RTWN8723BE_PACKAGE_QFN68;
    case 7:
        return RTWN8723BE_PACKAGE_TFBGA80;
    default:
        return RTWN8723BE_PACKAGE_DEFAULT;
    }
}

/*
 * Callbacks must access the PHYSICAL EFUSE address, not the logical shadow.
 * Unlike Linux's void power callbacks, this adapter propagates failures.
 * On read failure the output remains Linux's default, but the caller receives
 * an error and may not treat the device identity as validated. Power-off is
 * attempted on every path after a power-on attempt; preserve the first error.
 */
int
rtwn8723be_package_read(void *ctx, rtwn8723be_package_power_fn power,
    rtwn8723be_package_read_fn read_byte, uint8_t *package)
{
    uint8_t physical = 0;
    int error, off_error;

    if (package == NULL || power == NULL || read_byte == NULL)
        return EINVAL;
    *package = RTWN8723BE_PACKAGE_DEFAULT;

    error = power(ctx, true);
    if (error != 0) {
        (void)power(ctx, false);
        return error;
    }
    error = read_byte(ctx, RTWN8723BE_PACKAGE_EFUSE_ADDRESS, &physical);
    off_error = power(ctx, false);
    if (error != 0)
        return error;
    if (off_error != 0)
        return off_error;

    *package = rtwn8723be_package_decode(physical);
    return 0;
}
