/* SPDX-License-Identifier: GPL-2.0 */
#include "rtwn8723be_os_compat.h"
#include "rtwn8723be_oem.h"

bool
rtwn8723be_is_hp_oem_default_branch(
    const struct rtwn8723be_oem_probe *id)
{
    if (id == NULL || !id->eeprom_valid ||
        !id->initial_oem_is_default ||
        id->eeprom_customer_id != RTWN8723BE_EEPROM_CID_DEFAULT)
        return false;

    return id->eeprom_device_id == 0x8176U &&
        id->eeprom_subvendor_id == 0x103cU &&
        id->eeprom_subdevice_id == 0x1629U;
}
