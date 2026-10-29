#!/usr/bin/env python3
"""Verify exact frozen Linux PHY table import and isolated C table integrity.

This test does NOT execute PHY/RF programming, validate the RF condition
interpreter, build the NetBSD kernel, or establish WLAN hardware readiness.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINUX = Path(os.environ.get("RTWN8723BE_LINUX_TREE",
                         "/opt/ChatGPT/hp-driver-port/linux"))
HEADER = ROOT / "src/rtwn8723be_phy_tables.h"
CC_TEST = r"""
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#include "rtwn8723be_phy_tables.h"
int main(void)
{
    unsigned conditional = 0;
    assert(RTWN8723BE_PHY_TABLE_COUNT == 193);
    assert(RTWN8723BE_AGC_TABLE_COUNT == 131);
    assert(RTWN8723BE_PG_TABLE_COUNT == 6);
    assert(RTWN8723BE_RADIO_A_TABLE_COUNT == 136);
    assert(rtwn8723be_phy_table[0].reg == 0x800);
    assert(rtwn8723be_phy_table[192].reg == 0x800);
    assert(rtwn8723be_agc_table[0].reg == 0xc78);
    assert(rtwn8723be_pg_table[0].reg == 0xe08);
    for (unsigned i = 0; i < RTWN8723BE_RADIO_A_TABLE_COUNT; i++)
        if ((rtwn8723be_radio_a_table[i].reg & 0xc0000000U) != 0)
            conditional++;
    assert(conditional == 16);
    puts("PHY_TABLE_C_TESTS_OK: 193 BB 131 AGC 6 PG 136 RF; 16 RF conditions");
    return 0;
}
"""


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        generated = directory / "phy_tables.h"
        subprocess.run([
            "python3", str(ROOT / "tools/generate_phy_tables.py"),
            "--linux-tree", str(LINUX), "--out", str(generated),
        ], check=True)
        if generated.read_bytes() != HEADER.read_bytes():
            raise AssertionError("tracked PHY tables differ from frozen Linux")
        print("PHY_TABLE_BYTE_MATCH_OK")
        src = directory / "test.c"
        exe = directory / "phy_test"
        src.write_text(CC_TEST)
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-I", str(ROOT / "src"), str(src), "-o", str(exe),
        ], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
