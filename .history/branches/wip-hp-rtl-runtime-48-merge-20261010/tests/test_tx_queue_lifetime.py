#!/usr/bin/env python3
"""Strict C11/UBSan regression of the actual native TX queue-selection body.

Extracts r23be_tx_queue_check from production C, retaining its real FW
queue enum and the authoritative RTL8723BE hardware queue-number constants.
This is an isolated policy test, not a native NetBSD kernel or hardware test.
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "src/rtwn8723be_tx_native.c").read_text()
header = (ROOT / "src/rtwn8723be_f16_1.h").read_text()
anchor = "static int\nr23be_tx_queue_check("
if source.count(anchor) != 1:
    raise AssertionError("native TX queue check missing or duplicated")
start = source.index(anchor)
end = source.index("\n}\n", start) + 3
production = source[start:end]

queues = (
    "BK", "BE", "VI", "VO", "BEACON", "TXCMD", "MGNT", "HIGH", "HCCA"
)
defines = []
for q in queues:
    symbol = f"RTWN8723BE_{q}_QUEUE"
    matches = re.findall(
        rf"^#define\s+{symbol}\s+(\d+)\s*$", header, re.M
    )
    if len(matches) != 1:
        raise AssertionError("unexpected hardware queue ID: " + symbol)
    defines.append(f"#define {symbol} {matches[0]}")

harness = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include "rtwn8723be_tx_desc.h"
""" + "\n".join(defines) + "\n" + production + r"""
int main(void)
{
    assert(r23be_tx_queue_check(RTWN8723BE_BE_QUEUE,
        RTWN8723BE_TX_FW_BE, false) == 0);
    assert(r23be_tx_queue_check(RTWN8723BE_BK_QUEUE,
        RTWN8723BE_TX_FW_BK, false) == 0);
    assert(r23be_tx_queue_check(RTWN8723BE_VI_QUEUE,
        RTWN8723BE_TX_FW_VI, false) == 0);
    assert(r23be_tx_queue_check(RTWN8723BE_VO_QUEUE,
        RTWN8723BE_TX_FW_VO, false) == 0);
    assert(r23be_tx_queue_check(RTWN8723BE_MGNT_QUEUE,
        RTWN8723BE_TX_FW_MGNT, false) == 0);
    assert(r23be_tx_queue_check(RTWN8723BE_HIGH_QUEUE,
        RTWN8723BE_TX_FW_HIGH, false) == 0);

    /* Missing IRQ reclaim must NEVER publish an owned command/beacon. */
    assert(r23be_tx_queue_check(RTWN8723BE_TXCMD_QUEUE,
        RTWN8723BE_TX_FW_BEACON, true) == EOPNOTSUPP);
    assert(r23be_tx_queue_check(RTWN8723BE_BEACON_QUEUE,
        RTWN8723BE_TX_FW_BEACON, true) == EOPNOTSUPP);
    assert(r23be_tx_queue_check(RTWN8723BE_BEACON_QUEUE,
        RTWN8723BE_TX_FW_BEACON, false) == EOPNOTSUPP);
    assert(r23be_tx_queue_check(RTWN8723BE_TXCMD_QUEUE,
        RTWN8723BE_TX_FW_BEACON, false) == EINVAL);
    assert(r23be_tx_queue_check(RTWN8723BE_HCCA_QUEUE,
        RTWN8723BE_TX_FW_BE, false) == EINVAL);
    assert(r23be_tx_queue_check(RTWN8723BE_BE_QUEUE,
        RTWN8723BE_TX_FW_VO, false) == EINVAL);
    puts("RTL_TX_QUEUE_LIFETIME_C11_OK");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-tx-queue-") as d:
    c = Path(d) / "queue.c"
    exe = Path(d) / "queue"
    c.write_text(harness)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-pedantic", "-fsanitize=undefined",
        "-fno-sanitize-recover=all", "-I", str(ROOT / "src"),
        str(c), "-o", str(exe)
    ], check=True)
    subprocess.run([str(exe)], check=True)
