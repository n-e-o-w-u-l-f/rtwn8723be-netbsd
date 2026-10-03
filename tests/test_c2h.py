#!/usr/bin/env python3
"""Compile and execute exact repository C2H production C with C11/UBSan."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_c2h.h"

static int seen[4];
static int on_tx(void *arg, const struct rtwn8723be_c2h_event *ev)
{
    (void)arg;
    assert(ev->tx_report_valid && ev->tx_report_sequence == 0x52);
    assert(ev->tx_report_status == 0xc0 && ev->tx_report_retry == 0x3f);
    seen[0]++;
    return 0;
}
static int on_ra(void *arg, const struct rtwn8723be_c2h_event *ev)
{
    (void)arg;
    assert(ev->id == R23BE_C2H_RA_REPORT);
    seen[1]++;
    return 0;
}
static int on_bt_info(void *arg, const struct rtwn8723be_c2h_event *ev)
{
    (void)arg;
    assert(ev->id == R23BE_C2H_BT_INFO && ev->payload_length == 2);
    seen[2]++;
    return 0;
}
static int on_bt_mp(void *arg, const struct rtwn8723be_c2h_event *ev)
{
    (void)arg;
    assert(ev->fast && ev->id == R23BE_C2H_BT_MP);
    seen[3]++;
    return 0;
}

int main(void)
{
    struct rtwn8723be_c2h_event ev;
    uint8_t report[] = {3, 41, 0xc3, 0x19, 0x7f, 0, 0, 0, 0x52};
    uint8_t bt_mp[] = {11, 9, 1};
    uint8_t bt_info[] = {9, 10, 0x22, 0x33};
    uint8_t ra[] = {12, 11};
    uint8_t unknown[] = {0x80, 12, 0x44};
    uint8_t ext_v2[] = {0xff, 13, 0x0f, 0xab};

    assert(rtwn8723be_c2h_decode(report, sizeof(report), &ev) == 0);
    assert(ev.id == R23BE_C2H_TX_REPORT && ev.sequence == 41);
    assert(ev.recognized && !ev.fast && ev.tx_report_valid);
    assert(ev.tx_report_sequence == 0x52);
    assert(ev.tx_report_status == 0xc0);
    assert(ev.tx_report_retry == 0x3f);
    assert(ev.payload == report + 2 && ev.payload_length == 7);

    for (size_t size = 2; size < sizeof(report); size++) {
        assert(rtwn8723be_c2h_decode(report, size, &ev) == EMSGSIZE);
        assert(!ev.tx_report_valid);
    }
    assert(rtwn8723be_c2h_decode(bt_mp, sizeof(bt_mp), &ev) == 0);
    assert(ev.fast && ev.recognized && !ev.tx_report_valid);
    assert(rtwn8723be_c2h_decode(bt_info, sizeof(bt_info), &ev) == 0);
    assert(!ev.fast && ev.recognized && ev.payload_length == 2);
    assert(rtwn8723be_c2h_decode(ra, sizeof(ra), &ev) == 0);
    assert(ev.recognized && ev.payload_length == 0);
    assert(rtwn8723be_c2h_decode(unknown, sizeof(unknown), &ev) == 0);
    assert(!ev.recognized);
    assert(rtwn8723be_c2h_decode(ext_v2, sizeof(ext_v2), &ev) == 0);
    assert(ev.recognized && !ev.tx_report_valid);
    assert(rtwn8723be_c2h_decode(report, 1, &ev) == EMSGSIZE);
    assert(ev.payload == NULL && !ev.recognized);
    assert(rtwn8723be_c2h_decode(NULL, sizeof(report), &ev) == EINVAL);
    assert(rtwn8723be_c2h_decode(report, sizeof(report), NULL) == EINVAL);
    struct rtwn8723be_c2h_handlers handlers = {0};
    handlers.tx_report = on_tx;
    handlers.ra_report = on_ra;
    handlers.bt_info = on_bt_info;
    handlers.bt_mp = on_bt_mp;
    assert(rtwn8723be_c2h_route(report, sizeof(report), &handlers) == 0);
    assert(rtwn8723be_c2h_route(ra, sizeof(ra), &handlers) == 0);
    assert(rtwn8723be_c2h_route(bt_info, sizeof(bt_info), &handlers) == 0);
    assert(rtwn8723be_c2h_route(bt_mp, sizeof(bt_mp), &handlers) == 0);
    assert(seen[0] == 1 && seen[1] == 1 &&
           seen[2] == 1 && seen[3] == 1);

    handlers.tx_report = NULL;
    assert(rtwn8723be_c2h_route(report, sizeof(report), &handlers)
           == ENOSYS);
    handlers.ra_report = NULL;
    assert(rtwn8723be_c2h_route(ra, sizeof(ra), &handlers)
           == ENOSYS);
    handlers.bt_info = NULL;
    assert(rtwn8723be_c2h_route(bt_info, sizeof(bt_info), &handlers)
           == ENOSYS);
    handlers.bt_mp = NULL;
    assert(rtwn8723be_c2h_route(bt_mp, sizeof(bt_mp), &handlers)
           == ENOSYS);
    assert(rtwn8723be_c2h_route(ext_v2, sizeof(ext_v2), &handlers)
           == EOPNOTSUPP);
    assert(rtwn8723be_c2h_route(unknown, sizeof(unknown), &handlers)
           == 0);
    assert(rtwn8723be_c2h_route(report, 2, &handlers) == EMSGSIZE);
    assert(rtwn8723be_c2h_route(report, sizeof(report), NULL) == EINVAL);
    assert(seen[0] == 1 && seen[1] == 1 &&
           seen[2] == 1 && seen[3] == 1);
    puts("RTL_C2H_DECODE_ROUTE_C11_UBSAN_OK");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-c2h-") as tmp:
    path = Path(tmp)
    harness = path / "c2h_harness.c"
    binary = path / "c2h_harness"
    harness.write_text(HARNESS)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=undefined", "-fno-sanitize-recover=all",
         "-I", str(ROOT / "src"),
         str(ROOT / "src/rtwn8723be_c2h.c"),
         str(harness), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
