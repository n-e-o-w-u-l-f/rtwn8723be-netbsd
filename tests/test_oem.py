#!/usr/bin/env python3
"""Host-C regression for the production RTL8723BE HP OEM default-branch predicate.

The default-branch constants come from frozen Linux
fd179f8a05be3ccae366b9b96e176b51fbe54aab rtl8723be/hw.c and reg.h.
Does not validate the complete OEM classifier, firmware or hardware RF writes.
"""
from pathlib import Path
import argparse
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

TEST = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "rtwn8723be_oem.h"

int main(void)
{
    struct rtwn8723be_oem_probe id = {
        .eeprom_valid = true,
        .initial_oem_is_default = true,
        .eeprom_customer_id = RTWN8723BE_EEPROM_CID_DEFAULT,
        .eeprom_device_id = 0x8176,
        .eeprom_subvendor_id = 0x103c,
        .eeprom_subdevice_id = 0x1629
    };
    assert(!rtwn8723be_is_hp_oem_default_branch(NULL));
    assert(rtwn8723be_is_hp_oem_default_branch(&id));

    /* The HP model and PCI IDs do not establish EEPROM/OEM identity. */
    id.eeprom_device_id = 0xb723;
    assert(!rtwn8723be_is_hp_oem_default_branch(&id));
    id.eeprom_device_id = 0x8176;
    id.eeprom_subdevice_id = 0x81c1;
    assert(!rtwn8723be_is_hp_oem_default_branch(&id));
    id.eeprom_subdevice_id = 0x1629;

    id.eeprom_valid = false;
    assert(!rtwn8723be_is_hp_oem_default_branch(&id));
    id.eeprom_valid = true;
    id.initial_oem_is_default = false;
    assert(!rtwn8723be_is_hp_oem_default_branch(&id));
    id.initial_oem_is_default = true;
    id.eeprom_customer_id = 4;
    assert(!rtwn8723be_is_hp_oem_default_branch(&id));
    id.eeprom_customer_id = RTWN8723BE_EEPROM_CID_DEFAULT;

    /* Exact 16-bit DID, SVID, SMID equality, including immediate neighbors. */
    for (unsigned i = 0; i < 65536; i++) {
        id.eeprom_device_id = (uint16_t)i;
        assert(rtwn8723be_is_hp_oem_default_branch(&id) == (i == 0x8176U));
    }
    id.eeprom_device_id = 0x8176;
    for (unsigned i = 0; i < 65536; i++) {
        id.eeprom_subvendor_id = (uint16_t)i;
        assert(rtwn8723be_is_hp_oem_default_branch(&id) == (i == 0x103cU));
    }
    id.eeprom_subvendor_id = 0x103c;
    for (unsigned i = 0; i < 65536; i++) {
        id.eeprom_subdevice_id = (uint16_t)i;
        assert(rtwn8723be_is_hp_oem_default_branch(&id) == (i == 0x1629U));
    }
    puts("RTL_OEM_HP_C_TESTS_OK: 196608 ID checks, default, invalid and PCI mismatch");
    return 0;
}
"""


def validate_linux(tree: Path):
    root = tree / "drivers/net/wireless/realtek/rtlwifi/rtl8723be"
    hw = (root / "hw.c").read_text()
    reg = (root / "reg.h").read_text()
    start = hw.index("static void _rtl8723be_read_adapter_info(")
    end = hw.index("static void _rtl8723be_hal_customized_behavior(", start)
    src = hw[start:end]
    assert "if (rtlhal->oem_id == RT_CID_DEFAULT)" in src
    assert "switch (rtlefuse->eeprom_oemid)" in src
    assert "case EEPROM_CID_DEFAULT:" in src
    assert "rtlefuse->eeprom_did == 0x8176" in src
    assert "rtlefuse->eeprom_svid == 0x103C" in src
    assert "rtlefuse->eeprom_smid == 0x1629" in src
    assert "rtlhal->oem_id = RT_CID_819X_HP;" in src
    assert "#define EEPROM_CID_DEFAULT" in reg
    print("LINUX_OEM_HP_SOURCE_PIN_OK")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--linux-tree", type=Path)
    args = parser.parse_args()
    if args.linux_tree is not None:
        validate_linux(args.linux_tree)
    with tempfile.TemporaryDirectory() as directory:
        src = Path(directory) / "oem_test.c"
        exe = Path(directory) / "oem_test"
        src.write_text(TEST)
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-fsanitize=undefined", "-fno-sanitize-recover=all",
            "-I", str(ROOT / "src"), str(ROOT / "src/rtwn8723be_oem.c"),
            str(src), "-o", str(exe)
        ], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
