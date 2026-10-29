#!/usr/bin/env python3
"""Strict host test of the exact native C2H RX adapter function body.

Extracts the committed NetBSD function into a standalone C11/UBSan harness
with mock packet metadata. This does not validate kernel ABI, bus_dma or HP.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "src/rtwn8723be_c2h_native.c").read_text()
anchor = "\nint\nrtwn8723be_c2h_native_receive("
if source.count(anchor) != 1:
    raise AssertionError("missing or duplicated native C2H RX adapter")
fragment = "int\nrtwn8723be_c2h_native_receive(" + source.split(anchor, 1)[1]
start = fragment.index("{")
level, stop = 0, None
for idx in range(start, len(fragment)):
    if fragment[idx] == "{":
        level += 1
    elif fragment[idx] == "}":
        level -= 1
        if level == 0:
            stop = idx + 1
            break
if stop is None:
    raise AssertionError("unbalanced native RX adapter")
fragment = fragment[:stop]
prologue = r"""
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include "rtwn8723be_c2h.h"
enum rtwn8723be_rx_kind { RTWN8723BE_RX_FRAME, RTWN8723BE_RX_C2H };
struct rtwn8723be_rx_packet {
    enum rtwn8723be_rx_kind kind;
    size_t packet_length;
    int crc_error, icv_error;
    size_t packet_offset, c2h_payload_offset, c2h_payload_length;
    uint8_t c2h_id, c2h_seq;
};
"""
epilogue = r"""
static unsigned calls;
static int report(void *arg, const struct rtwn8723be_c2h_event *e)
{
    (void)arg;
    assert(e->tx_report_valid && e->tx_report_sequence == 0x52);
    calls++;
    return 0;
}
int main(void)
{
    uint8_t raw[] = {3, 41, 0xc3, 0x19, 0x7f, 0, 0, 0, 0x52};
    struct rtwn8723be_c2h_handlers handlers = {.tx_report = report};
    struct rtwn8723be_rx_packet p = {
        .kind = RTWN8723BE_RX_C2H, .packet_length = sizeof(raw),
        .packet_offset = 40, .c2h_payload_offset = 42,
        .c2h_payload_length = sizeof(raw)-2,
        .c2h_id = 3, .c2h_seq = 41
    };
    assert(rtwn8723be_c2h_native_receive(&handlers,raw,sizeof(raw),&p)
           == 0 && calls == 1);
    p.c2h_seq++;
    assert(rtwn8723be_c2h_native_receive(&handlers,raw,sizeof(raw),&p)
           == EINVAL);
    p.c2h_seq--;
    p.crc_error = 1;
    assert(rtwn8723be_c2h_native_receive(&handlers,raw,sizeof(raw),&p)
           == EINVAL);
    p.crc_error = 0;
    p.c2h_payload_offset++;
    assert(rtwn8723be_c2h_native_receive(&handlers,raw,sizeof(raw),&p)
           == EINVAL);
    p.c2h_payload_offset--;
    p.kind = RTWN8723BE_RX_FRAME;
    assert(rtwn8723be_c2h_native_receive(&handlers,raw,sizeof(raw),&p)
           == EINVAL);
    p.kind = RTWN8723BE_RX_C2H;
    handlers.tx_report = NULL;
    assert(rtwn8723be_c2h_native_receive(&handlers,raw,sizeof(raw),&p)
           == ENOSYS);
    assert(rtwn8723be_c2h_native_receive(NULL,raw,sizeof(raw),&p)
           == EINVAL);
    assert(calls == 1);
    puts("RTL_NATIVE_C2H_RX_BOUNDARY_HOST_C11_UBSAN_OK");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-c2h-native-") as tmp:
    path = Path(tmp)
    harness = path / "native_harness.c"
    binary = path / "native_harness"
    harness.write_text(prologue + fragment + epilogue)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=undefined", "-fno-sanitize-recover=all",
         "-I", str(ROOT / "src"),
         str(ROOT / "src/rtwn8723be_c2h.c"),
         str(harness), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
