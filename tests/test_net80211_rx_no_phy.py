#!/usr/bin/env python3
"""Compile the actual net80211 RX callback with only its NetBSD types mocked.

This tests callback ownership/validation/fallback in isolation, not native
kernel compilation, DMA safety, registration, or live WLAN association.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "src" / "rtwn8723be_net80211.c").read_text()
anchor = "\nint\nrtwn8723be_net80211_rx_frame("
if text.count(anchor) != 1:
    raise AssertionError("net80211 receive handler missing or duplicated")
fragment = text.split(anchor, 1)[1]
fragment = "int\nrtwn8723be_net80211_rx_frame(" + fragment
start = fragment.index("{")
depth = 0
stop = None
for i in range(start, len(fragment)):
    if fragment[i] == "{":
        depth += 1
    elif fragment[i] == "}":
        depth -= 1
        if depth == 0:
            stop = i + 1
            break
if stop is None:
    raise AssertionError("unbalanced handler braces")
fragment = fragment[:stop]

prologue = r"""
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
enum rtwn8723be_rx_kind { RTWN8723BE_RX_FRAME, RTWN8723BE_RX_C2H };
struct rtwn8723be_rx_packet {
    enum rtwn8723be_rx_kind kind;
    size_t packet_length;
    int rssi_dbm;
    int rssi_valid;
    int crc_error;
    int icv_error;
};
struct rtwn8723be_net80211 { int registered; };
static int calls, last_rssi;
static const uint8_t *last_frame;
static size_t last_len;
static int rtwn8723be_net80211_input(struct rtwn8723be_net80211 *n,
    const uint8_t *frame, size_t length, int rssi_dbm)
{
    assert(n->registered);
    calls++;
    last_rssi = rssi_dbm;
    last_frame = frame;
    last_len = length;
    return 0;
}
"""
epilogue = r"""
int main(void)
{
    uint8_t frame[24] = {0};
    struct rtwn8723be_net80211 n = {1};
    struct rtwn8723be_rx_packet p;
    memset(&p, 0, sizeof(p));
    p.kind = RTWN8723BE_RX_FRAME;
    p.packet_length = sizeof(frame);

    p.rssi_valid = 1;
    p.rssi_dbm = -71;
    assert(rtwn8723be_net80211_rx_frame(&n, frame, sizeof(frame),
        &p) == 0);
    assert(calls == 1 && last_rssi == -71 &&
        last_frame == frame && last_len == sizeof(frame));

    p.rssi_valid = 0;
    assert(rtwn8723be_net80211_rx_frame(&n, frame, sizeof(frame),
        &p) == 0);
    assert(calls == 2 && last_rssi == 0); /* NetBSD no-PHY fallback. */

    p.crc_error = 1;
    assert(rtwn8723be_net80211_rx_frame(&n, frame, sizeof(frame),
        &p) == EINVAL);
    p.crc_error = 0;
    p.icv_error = 1;
    assert(rtwn8723be_net80211_rx_frame(&n, frame, sizeof(frame),
        &p) == EINVAL);
    p.icv_error = 0;
    p.kind = RTWN8723BE_RX_C2H;
    assert(rtwn8723be_net80211_rx_frame(&n, frame, sizeof(frame),
        &p) == EINVAL);
    p.kind = RTWN8723BE_RX_FRAME;
    assert(rtwn8723be_net80211_rx_frame(&n, frame, 23, &p) == EINVAL);
    assert(rtwn8723be_net80211_rx_frame(&n, NULL,
        sizeof(frame), &p) == EINVAL);
    assert(rtwn8723be_net80211_rx_frame(NULL, frame,
        sizeof(frame), &p) == EINVAL);
    assert(rtwn8723be_net80211_rx_frame(&n, frame,
        sizeof(frame), NULL) == EINVAL);
    assert(calls == 2);
    puts("RTL_NET80211_RX_FALLBACK_C11_OK");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-n80211-rx-") as tmp:
    source = Path(tmp) / "rx_test.c"
    binary = Path(tmp) / "rx_test"
    source.write_text(prologue + fragment + epilogue)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
         "-pedantic", "-fsanitize=undefined", "-fno-sanitize-recover=all",
         str(source), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
