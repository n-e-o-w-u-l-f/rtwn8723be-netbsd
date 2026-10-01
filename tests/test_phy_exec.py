#!/usr/bin/env python3
"""Strict C tests of the ACTUAL reference-derived PHY interpreter source.

Tests Linux IF/ELSEIF/ELSE/ENDIF, negative-token no-op, PCI/USB, board
amplifier matching, BB/AGC/PG exact ordering, early I/O failures and Radio-A.
No claim of RF serial access, NetBSD build or physical hardware behavior.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = r'''
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <assert.h>
#include <string.h>
#include "rtwn8723be_phy_exec.c"

struct trace {
    unsigned count;
    uint32_t first_reg, first_val, last_reg, last_val;
    int fail_at;
};

static int capture(void *arg, uint32_t reg, uint32_t val)
{
    struct trace *t = arg;
    t->count++;
    if (t->count == 1) {
        t->first_reg = reg;
        t->first_val = val;
    }
    t->last_reg = reg;
    t->last_val = val;
    if (t->fail_at > 0 && t->count == (unsigned)t->fail_at)
        return EIO;
    return 0;
}

static int capture_pg(void *arg, const struct rtwn8723be_pg_entry *entry)
{
    struct trace *t = arg;
    assert(entry->band == 0 && entry->path == 0 && entry->txnum == 0);
    t->count++;
    if (t->count == 1) {
        t->first_reg = entry->reg;
        t->first_val = entry->value;
    }
    t->last_reg = entry->reg;
    t->last_val = entry->value;
    return 0;
}

int main(void)
{
    struct trace t = {0};
    struct rtwn8723be_phy_identity id = {0};
    const struct rtwn8723be_init_pair branch[] = {
        {0x80000100U, 0}, {0x020, 0x111},
        {0x90000200U, 0}, {0x024, 0x222},
        {0xa0000000U, 0}, {0x028, 0x333},
        {0x40000000U, 0}, /* Linux negative token: no-op */
        {0xb0000000U, 0}, {0x02c, 0x444}
    };
    const struct rtwn8723be_init_pair amp[] = {
        {0x80000101U, 0x55}, {0x050, 0x555},
        {0xa0000000U, 0}, {0x054, 0x777},
        {0xb0000000U, 0}
    };
    assert(RTWN8723BE_PHY_TABLE_COUNT == 193);
    assert(RTWN8723BE_AGC_TABLE_COUNT == 131);
    assert(RTWN8723BE_PG_TABLE_COUNT == 6);
    assert(RTWN8723BE_RADIO_A_TABLE_COUNT == 136);
    assert(rtwn8723be_phy_run_bb(&t, capture) == 0);
    assert(t.count == 193 && t.first_reg == 0x800);
    assert(t.first_val == 0x80040000U);
    assert(t.last_reg == 0x800 && t.last_val == 0x83040000U);
    memset(&t, 0, sizeof(t));
    assert(rtwn8723be_phy_run_agc(&t, capture) == 0);
    assert(t.count == 131 && t.first_reg == 0xc78);
    assert(t.last_reg == 0x824 && t.last_val == 0x00390204U);
    memset(&t, 0, sizeof(t));
    assert(rtwn8723be_phy_run_pg(&t, capture_pg) == 0);
    assert(t.count == 6 && t.first_reg == 0xe08);
    assert(t.last_reg == 0xe14 && t.last_val == 0x26303436U);
    assert(rtwn8723be_phy_run_pg(&t, NULL) == EINVAL);

    id.pci_interface = true;
    assert(rtwn8723be_phy_check_positive(&id, 0x80000100U, 0));
    assert(!rtwn8723be_phy_check_positive(&id, 0x80000200U, 0));
    memset(&t, 0, sizeof(t));
    assert(rtwn8723be_phy_run_pairs(branch, 9, &id, &t, capture) == 0);
    assert(t.count == 2 && t.first_reg == 0x020 && t.last_reg == 0x02c);

    id.pci_interface = false;
    memset(&t, 0, sizeof(t));
    assert(rtwn8723be_phy_run_pairs(branch, 9, &id, &t, capture) == 0);
    assert(t.count == 2 && t.first_reg == 0x024 && t.last_reg == 0x02c);

    id.pci_interface = true;
    id.board_type = (1U << 4);
    id.type_glna = 0x55;
    assert(rtwn8723be_phy_check_positive(&id, 0x80000101U, 0x55));
    assert(!rtwn8723be_phy_check_positive(&id, 0x80000101U, 0x56));
    memset(&t, 0, sizeof(t));
    assert(rtwn8723be_phy_run_pairs(amp, 5, &id, &t, capture) == 0);
    assert(t.count == 1 && t.last_val == 0x555);
    id.type_glna = 0x56;
    memset(&t, 0, sizeof(t));
    assert(rtwn8723be_phy_run_pairs(amp, 5, &id, &t, capture) == 0);
    assert(t.count == 1 && t.last_val == 0x777);

    id.board_type = 0;
    id.type_glna = 0;
    id.package_type = 2;
    id.cut_version = 3;
    assert(rtwn8723be_phy_check_positive(&id, 0x83002100U, 0));
    assert(!rtwn8723be_phy_check_positive(&id, 0x83003100U, 0));
    assert(!rtwn8723be_phy_check_positive(&id, 0x84002100U, 0));

    memset(&t, 0, sizeof(t));
    assert(rtwn8723be_phy_run_radio_a(&id, &t, capture) == 0);
    assert(t.count > 0 && t.count < RTWN8723BE_RADIO_A_TABLE_COUNT);
    assert(rtwn8723be_phy_run_radio_a(NULL, &t, capture) == EINVAL);

    memset(&t, 0, sizeof(t));
    t.fail_at = 2;
    assert(rtwn8723be_phy_run_bb(&t, capture) == EIO && t.count == 2);
    assert(rtwn8723be_phy_run_bb(&t, NULL) == EINVAL);
    puts("PHY_INTERPRETER_C_TESTS_OK: BB193 AGC131 PG6 RF conditional branches and error paths");
    return 0;
}
'''


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "test.c"
        exe = Path(tmp) / "test"
        src.write_text(PROGRAM)
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-I", str(ROOT / "src"), str(src), "-o", str(exe),
        ], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
