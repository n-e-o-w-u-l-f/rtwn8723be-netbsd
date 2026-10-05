/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_ASPM_NATIVE_H_
#define _RTWN8723BE_ASPM_NATIVE_H_
#include "rtwn8723be_os_compat.h"
/* Serialized pre-IRQ Linux fd179f8a PCIe ePHY/DBI transactions. */
int rtwn8723be_netbsd_dbi_read(void *, uint16_t, uint8_t *);
int rtwn8723be_netbsd_dbi_write(void *, uint16_t, uint8_t);
int rtwn8723be_netbsd_mdio_read(void *, uint8_t, uint16_t *);
int rtwn8723be_netbsd_mdio_write(void *, uint8_t, uint16_t);
int rtwn8723be_netbsd_enable_aspm_backdoor(void *);
#endif
