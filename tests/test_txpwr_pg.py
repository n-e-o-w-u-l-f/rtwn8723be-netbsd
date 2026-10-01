#!/usr/bin/env python3
"""Strict production-C verification of frozen Linux RTL8723BE PHY-PG staging.

Uses the real source-pinned six-entry PG table and actual table iterator.
No hardware/MMIO/NetBSD-kernel/runtime claim is made by this host test.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINUX = (Path("/opt/ChatGPT/hp-driver-port/linux") /
         "drivers/net/wireless/realtek/rtlwifi/rtl8723be/phy.c")

PROGRAM = r"""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_txpwr_pg.h"
#include "rtwn8723be_phy_tables.h"

int main(void)
{
    struct rtwn8723be_txpwr_pg_state s;
    struct rtwn8723be_pg_entry p;

    rtwn8723be_txpwr_pg_reset(&s);
    assert(rtwn8723be_txpwr_pg_store(NULL, NULL) == EINVAL);
    p = (struct rtwn8723be_pg_entry){ .band=2, .reg=0xe00 };
    assert(rtwn8723be_txpwr_pg_store(&s, &p) == EINVAL);
    p = (struct rtwn8723be_pg_entry){ .band=0, .path=4, .reg=0xe00 };
    assert(rtwn8723be_txpwr_pg_store(&s, &p) == EINVAL);
    p = (struct rtwn8723be_pg_entry){ .band=0, .txnum=4, .reg=0xe00 };
    assert(rtwn8723be_txpwr_pg_store(&s, &p) == EINVAL);

    assert(rtwn8723be_phy_run_pg(&s, rtwn8723be_txpwr_pg_store) == 0);
    assert(s.offset[0][0][0][0] == 0x40424444U);
    assert(s.offset[0][0][0][1] == 0x28323638U);
    assert(s.offset[0][0][0][2] == 0x00003800U);
    assert(s.offset[0][0][0][3] == 0x32343600U);
    assert(s.offset[0][0][0][4] == 0x38404244U);
    assert(s.offset[0][0][0][5] == 0x26303436U);

    rtwn8723be_txpwr_pg_convert(&s);
    assert(s.base24[0][0][0] == 32); /* 0x32: CCK */
    assert(s.base24[0][0][1] == 28); /* 0x28: OFDM */
    assert(s.base24[0][0][2] == 26); /* 0x26: MCS0-7 */
    assert(s.base24[0][1][3] == 0);  /* no MCS8-15 PG entry */
    assert(s.offset[0][0][0][0] == 0x0c0e1010U);
    assert(s.offset[0][0][0][1] == 0x0004080aU);
    assert(s.offset[0][0][0][2] == 0x00000600U);
    assert(s.offset[0][0][0][3] == 0x00020400U);
    assert(s.offset[0][0][0][4] == 0x0c0e1012U);
    assert(s.offset[0][0][0][5] == 0x0004080aU);

    /* Linux extracts path-B bases, but converts path-A offsets ONLY. */
    rtwn8723be_txpwr_pg_reset(&s);
    p = (struct rtwn8723be_pg_entry){
        .band=0, .path=1, .txnum=0, .reg=0x86c,
        .mask=0xffffffffU, .value=0x32343635U };
    assert(rtwn8723be_txpwr_pg_store(&s, &p) == 0);
    p.reg=0x834; p.value=0x41424344U;
    assert(rtwn8723be_txpwr_pg_store(&s, &p) == 0);
    p.reg=0x848; p.value=0x31323334U;
    assert(rtwn8723be_txpwr_pg_store(&s, &p) == 0);
    p.txnum=1; p.reg=0x868; p.value=0x40414243U;
    assert(rtwn8723be_txpwr_pg_store(&s, &p) == 0);
    rtwn8723be_txpwr_pg_convert(&s);
    assert(s.base24[1][0][0] == 35);
    assert(s.base24[1][0][1] == 41);
    assert(s.base24[1][0][2] == 31);
    assert(s.base24[1][1][3] == 40);
    assert(s.offset[0][1][0][3] == 0x32343635U);
    assert(s.offset[0][1][0][1] == 0x41424344U);
    assert(s.offset[0][1][0][5] == 0x31323334U);
    assert(s.offset[0][1][1][7] == 0x40414243U);

    /* Linux's conversion uses the *absolute* difference, not signed dBm. */
    s.offset[0][0][0][1] = 0x28303050U; /* OFDM base 28 */
    rtwn8723be_txpwr_pg_convert(&s);
    assert(s.offset[0][0][0][1] == 0x00020216U);

    /* Linux's 12-section register fallback and raw-data storage. */
    p = (struct rtwn8723be_pg_entry){
        .band=1, .path=3, .txnum=3, .reg=0xc4c,
        .mask=0U, .value=0x12345678U };
    assert(rtwn8723be_txpwr_pg_store(&s, &p) == 0);
    assert(s.offset[1][3][3][11] == 0x12345678U);
    rtwn8723be_txpwr_pg_reset(&s);
    assert(s.offset[1][3][3][11] == 0U && s.base24[1][0][0] == 0U);
    puts("TXPWR_PG_C_TESTS_OK: six Linux records, CCK/OFDM/MCS bases, RF-A conversion, path-B preservation");
    return 0;
}
"""


def main():
    original = LINUX.read_text()
    for symbol in ("_rtl8723be_get_rate_section_index(",
                   "_rtl8723be_phy_store_txpower_by_rate_base(",
                   "_phy_convert_txpower_dbm_to_relative_value(",
                   "_rtl8723be_phy_convert_txpower_dbm_to_relative_value(",
                   "for (path = RF90_PATH_A; path <= RF90_PATH_B; ++path)",
                   "u8 base = 0, rfpath = RF90_PATH_A"):
        if symbol not in original:
            raise AssertionError("frozen Linux PHY-PG source changed: " + symbol)
    with tempfile.TemporaryDirectory() as td:
        source = Path(td) / "test.c"
        exe = Path(td) / "test"
        source.write_text(PROGRAM)
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-I", str(ROOT / "src"), str(source),
             str(ROOT / "src/rtwn8723be_txpwr_pg.c"),
             str(ROOT / "src/rtwn8723be_phy_exec.c"),
             "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
