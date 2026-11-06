/* SPDX-License-Identifier: GPL-2.0
 * RTL8723BE: source-pinned HP OEM selection predicate.
 * Linux rtl8723be/hw.c:_rtl8723be_read_adapter_info(), frozen
 * fd179f8a05be3ccae366b9b96e176b51fbe54aab and Linux v7.2.
 */
#ifndef _RTWN8723BE_OEM_H_
#define _RTWN8723BE_OEM_H_

#include "rtwn8723be_os_compat.h"

/* The Linux EEPROM_CID_DEFAULT branch has value zero. */
#define RTWN8723BE_EEPROM_CID_DEFAULT 0x00U

struct rtwn8723be_oem_probe {
    bool eeprom_valid;
    bool initial_oem_is_default;
    uint8_t eeprom_customer_id;
    uint16_t eeprom_device_id;
    uint16_t eeprom_subvendor_id;
    uint16_t eeprom_subdevice_id;
};

/*
 * Recognize only Linux's DEFAULT -> HP branch. This is not the complete
 * OEM classifier and MUST NOT directly enable the HP-only RF 0x52 write:
 * the caller must first resolve the full OEM identity and validate the
 * remaining PHY identity and powered RF lifetime.
 * Values are decoded EEPROM IDs, never inferred from the PCI subsystem,
 * machine model, or a default-filled/incompletely read EFUSE map.
 */
bool rtwn8723be_is_hp_oem_default_branch(
    const struct rtwn8723be_oem_probe *);

#endif /* _RTWN8723BE_OEM_H_ */
