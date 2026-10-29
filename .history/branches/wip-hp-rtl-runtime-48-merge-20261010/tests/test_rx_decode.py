#!/usr/bin/env python3
"""Compile the committed production RX decoder; no native NetBSD claim."""
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
#include "rtwn8723be_rx_decode.h"

static uint8_t desc[32], data[9100];
static struct rtwn8723be_rx_packet pkt;
static void set_dw(unsigned n, uint32_t v)
{
    unsigned i;
    for (i = 0; i < 4; i++)
        desc[n * 4U + i] = (uint8_t)(v >> (8U * i));
}
static void clear(void)
{
    memset(desc, 0, sizeof(desc));
    memset(data, 0, sizeof(data));
    memset(&pkt, 0x5a, sizeof(pkt));
}
static int decode(size_t len)
{
    return rtwn8723be_rx_decode(desc, sizeof(desc), data, len, &pkt);
}
int main(void)
{
    unsigned drv, shift, tested = 0;
    clear();
    set_dw(0, 24U | (1U << 16) | (2U << 24));
    set_dw(1, 13U);
    set_dw(3, 7U);
    assert(decode(sizeof(data)) == 0);
    assert(pkt.kind == RTWN8723BE_RX_FRAME);
    assert(pkt.packet_offset == 10 && pkt.packet_length == 24);
    assert(pkt.mac_id == 13 && pkt.rate == 7);
    assert(pkt.c2h_payload_length == 0 && !pkt.crc_error);

    clear();
    set_dw(0, 5U | (2U << 16) | (1U << 24));
    set_dw(2, 1U << 28);
    data[17] = 9;
    data[18] = 42;
    data[19] = 0xaa;
    assert(decode(sizeof(data)) == 0);
    assert(pkt.kind == RTWN8723BE_RX_C2H);
    assert(pkt.c2h_id == 9 && pkt.c2h_seq == 42);
    assert(pkt.c2h_payload_offset == 19 &&
        pkt.c2h_payload_length == 3);

    clear();
    set_dw(0, 4U | (1U << 31));
    assert(decode(sizeof(data)) == EAGAIN);
    assert(pkt.packet_length == 0);

    clear();
    set_dw(0, 1U);
    set_dw(2, 1U << 28);
    assert(decode(sizeof(data)) == EMSGSIZE);
    assert(pkt.packet_length == 0);

    clear();
    assert(decode(sizeof(data)) == EMSGSIZE);
    set_dw(0, 20U | (15U << 16) | (3U << 24));
    assert(decode(120) == EMSGSIZE);
    assert(decode(144) == 0);
    assert(pkt.packet_offset == 123 && pkt.packet_length == 20);

    clear();
    set_dw(0, 2U | (1U << 14) | (1U << 15) | (1U << 27));
    assert(decode(sizeof(data)) == 0);
    assert(pkt.crc_error && pkt.icv_error &&
        pkt.software_decryption);

    assert(rtwn8723be_rx_decode(NULL, sizeof(desc), data,
        sizeof(data), &pkt) == EINVAL);
    assert(rtwn8723be_rx_decode(desc, 31, data,
        sizeof(data), &pkt) == EINVAL);
    assert(rtwn8723be_rx_decode(desc, sizeof(desc), data,
        sizeof(data) + 1, &pkt) == EINVAL);

    for (drv = 0; drv < 16; drv++) {
        for (shift = 0; shift < 4; shift++) {
            size_t off = drv * 8U + shift;
            clear();
            set_dw(0, (uint32_t)(9100U - off) |
                (drv << 16) | (shift << 24));
            assert(decode(sizeof(data)) == 0);
            assert(pkt.packet_offset == off);
            assert(pkt.packet_length == 9100U - off);
            tested++;
        }
    }
    printf("RX_DECODE_C11_OK: %u drvinfo/shift edges, frame, "
        "C2H, OWN, truncation, CRC/ICV, null/size guards\\n", tested);
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="r23be-rx-") as tmp:
    source = Path(tmp) / "rx_test.c"
    program = Path(tmp) / "rx_test"
    source.write_text(HARNESS)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
         "-pedantic", "-fsanitize=undefined",
         "-fno-sanitize-recover=all",
         "-I", str(ROOT / "src"),
         str(ROOT / "src/rtwn8723be_rx_decode.c"), str(source),
         "-o", str(program)],
        check=True,
    )
    subprocess.run([str(program)], check=True)
