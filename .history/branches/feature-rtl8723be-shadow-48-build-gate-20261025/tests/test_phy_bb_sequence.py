#!/usr/bin/env python3
"""Compile the actual BB/PG/AGC sequencer C with an isolated source-order mock.

The mocked table-run functions are deliberately one-record stubs: this test
checks orchestration/failure semantics, not the separately tested real tables,
native NetBSD bus_space, PG conversion, kernel linkage, or physical WLAN.
"""
from pathlib import Path
import argparse
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/rtwn8723be_phy_bb_sequence.c"
INCLUDE = ROOT / "src"
C_TEST = r"""
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_phy_bb_sequence.h"

struct trace { char seen[16]; int n; char fail; };
static int mark(struct trace *t, char what)
{
    t->seen[t->n++] = what;
    return t->fail == what ? EIO : 0;
}
static int ant(void *p) { return mark(p, 'A'); }
static int bb(void *p, uint32_t a, uint32_t b)
{ (void)a; (void)b; return mark(p, 'B'); }
static int pg(void *p, const struct rtwn8723be_pg_entry *entry)
{ (void)entry; return mark(p, 'P'); }
static int init(void *p) { return mark(p, 'I'); }
static int reset_pg(void *p) { return mark(p, 'R'); }
static int convert(void *p) { return mark(p, 'C'); }
static int agc(void *p, uint32_t a, uint32_t b)
{ (void)a; (void)b; return mark(p, 'G'); }
static int cck(void *p, bool *b)
{ *b = true; return mark(p, 'H'); }

/* Table traversal itself is covered by tests/test_phy_exec.py. */
int rtwn8723be_phy_run_bb(void *p, rtwn8723be_phy_write_fn f)
{ return f(p, 0, 0); }
int rtwn8723be_phy_run_pg(void *p, rtwn8723be_phy_pg_fn f)
{ return f(p, NULL); }
int rtwn8723be_phy_run_agc(void *p, rtwn8723be_phy_write_fn f)
{ return f(p, 0, 0); }

int main(void)
{
    struct trace t = {0};
    bool high = false;
    const struct rtwn8723be_bb_sequence_ops ops = {
        .select_antenna = ant, .write_bb = bb, .init_txpower = init,
        .reset_pwrgroup = reset_pg, .store_pg = pg,
        .convert_txpower = convert, .write_agc = agc,
        .read_cck_high_power = cck
    };
    struct rtwn8723be_bb_sequence_ops missing = ops;
    const char *failure;

    assert(rtwn8723be_phy_bb_sequence(&t, &ops, true, &high) == 0);
    assert(strcmp(t.seen, "ABIRPCGH") == 0 && high);
    memset(&t, 0, sizeof(t));
    high = false;
    assert(rtwn8723be_phy_bb_sequence(&t, &ops, false, &high) == 0);
    assert(strcmp(t.seen, "ABICGH") == 0 && high);

    for (failure = "ABIRPCGH"; *failure != 0; failure++) {
        memset(&t, 0, sizeof(t));
        t.fail = *failure;
        high = false;
        assert(rtwn8723be_phy_bb_sequence(&t, &ops, true, &high) == EIO);
        assert(!high);
        if (*failure == 'P')
            assert(strcmp(t.seen, "ABIRPC") == 0);
    }
    memset(&t, 0, sizeof(t));
    missing.store_pg = NULL;
    assert(rtwn8723be_phy_bb_sequence(&t, &missing, true, &high) ==
        ENOSYS && t.n == 0);
    assert(rtwn8723be_phy_bb_sequence(&t, &missing, false, &high) == 0);
    memset(&t, 0, sizeof(t));
    missing = ops;
    missing.reset_pwrgroup = NULL;
    assert(rtwn8723be_phy_bb_sequence(&t, &missing, true, &high) ==
        ENOSYS && t.n == 0);
    assert(rtwn8723be_phy_bb_sequence(&t, &missing, false, &high) == 0);
    assert(rtwn8723be_phy_bb_sequence(NULL, &ops, true, &high) == EINVAL);
    assert(rtwn8723be_phy_bb_sequence(&t, &ops, true, NULL) == EINVAL);
    puts("BB_SEQUENCE_HOST_C_OK: source order, PG skip, errors, preflight");
    return 0;
}
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--linux-tree", type=Path)
    args = parser.parse_args()
    if args.linux_tree is not None:
        source = (args.linux_tree /
                  "drivers/net/wireless/realtek/rtlwifi/rtl8723be/phy.c"
                  ).read_text()
        start = source.index("static bool _rtl8723be_phy_bb8723b_config_parafile(")
        end = source.index("static bool rtl8723be_phy_config_with_headerfile(",
                           start)
        body = source[start:end]
        markers = ("_rtl8723be_phy_config_bb_with_headerfile(hw,",
                   "_rtl8723be_phy_init_tx_power_by_rate(hw);",
                   "if (!rtlefuse->autoload_failflag) {",
                   "rtlphy->pwrgroup_cnt = 0;",
                   "_rtl8723be_phy_config_bb_with_pgheaderfile(hw,",
                   "phy_txpower_by_rate_config(hw);",
                   "BASEBAND_CONFIG_AGC_TAB);",
                   "rtlphy->cck_high_power =")
        positions = [body.index(marker) for marker in markers]
        assert positions == sorted(positions) and len(set(positions)) == len(
            positions)
        print("PINNED_LINUX_BB_PHASE_ORDER_OK")
    with tempfile.TemporaryDirectory() as directory:
        src = Path(directory) / "check.c"
        exe = Path(directory) / "check"
        src.write_text(C_TEST)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-pedantic", "-fsanitize=undefined",
                        "-fno-sanitize-recover=all", "-I", str(INCLUDE),
                        str(SRC), str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

if __name__ == "__main__":
    main()
