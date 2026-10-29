/* SPDX-License-Identifier: GPL-2.0
 * RTL8723BE raw physical EFUSE package identification.
 * Frozen Linux reference: fd179f8a05be3ccae366b9b96e176b51fbe54aab
 * rtl8723be/hw.c:_rtl8723be_read_package_type and rtlwifi/wifi.h.
 */
#ifndef _RTWN8723BE_PACKAGE_H_
#define _RTWN8723BE_PACKAGE_H_

#include "rtwn8723be_os_compat.h"

#define RTWN8723BE_PACKAGE_EFUSE_ADDRESS 0x01fbU

/* Preserve the exact values of Linux enum package_type. */
enum rtwn8723be_package_type {
    RTWN8723BE_PACKAGE_DEFAULT = 0,
    RTWN8723BE_PACKAGE_QFN68 = 1,
    RTWN8723BE_PACKAGE_TFBGA90 = 2,
    RTWN8723BE_PACKAGE_TFBGA80 = 3,
    RTWN8723BE_PACKAGE_TFBGA79 = 4
};

typedef int (*rtwn8723be_package_power_fn)(void *, bool);
typedef int (*rtwn8723be_package_read_fn)(void *, uint16_t, uint8_t *);

uint8_t rtwn8723be_package_decode(uint8_t);
int rtwn8723be_package_read(void *, rtwn8723be_package_power_fn,
    rtwn8723be_package_read_fn, uint8_t *);

#endif /* _RTWN8723BE_PACKAGE_H_ */
