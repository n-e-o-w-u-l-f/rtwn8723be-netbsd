#!/usr/bin/env python3
"""Compile the real TX encoder in strict C11/UBSan; NOT NetBSD/HP proof."""
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
#include "rtwn8723be_tx_desc.h"

static uint8_t d[64];
static uint32_t dw(unsigned n)
{
    const uint8_t *p = d + n * 4U;
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
        ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static struct rtwn8723be_tx_params valid(void)
{
    struct rtwn8723be_tx_params p;
    memset(&p, 0, sizeof(p));
    p.packet_len = p.buffer_len = 100;
    p.buffer_dma = 0x12345678U;
    p.next_desc_dma = 0x10000040U;
    p.first_segment = p.last_segment = true;
    p.fw_queue = RTWN8723BE_TX_FW_VI;
    p.rateid = 3;
    p.macid = 7;
    p.hw_rate = 0x12;
    p.rts_rate = 0xb;
    p.rts_sc = 2;
    p.security = 3;
    p.ampdu_density = 5;
    p.subcarrier = 3;
    p.seq = 0xabc;
    p.qos_data = p.ampdu = p.short_gi_or_preamble = true;
    p.rts_enable = p.rts_short = p.nav_use_hdr = true;
    p.use_driver_rate = p.disable_rate_fallback = p.rdg = true;
    p.data_bw_40 = true;
    return p;
}
int main(void)
{
    struct rtwn8723be_tx_params p = valid();
    unsigned i, count = 0;

    memset(d, 0xa5, sizeof(d));
    assert(rtwn8723be_tx_encode(&p, d, sizeof(d)) == 0);
    assert(dw(0) == (100U | (40U << 16) | (1U << 26) |
        (1U << 27)));
    assert(dw(1) == (7U | (5U << 8) | (3U << 16) |
        (3U << 22)));
    assert(dw(2) == ((1U << 12) | (1U << 13) | (5U << 20)));
    assert(dw(3) == ((0x14U << 17) | (1U << 12) |
        (1U << 15) | (1U << 10) | (1U << 8)));
    assert(dw(4) == (0x12U | (31U << 8) |
        (15U << 13) | (11U << 24)));
    assert(dw(5) == ((1U << 4) | (1U << 5) |
        (1U << 12) | (2U << 13) | 3U));
    assert(dw(7) == 100 && dw(8) == 0 &&
        dw(9) == (0xabcU << 12));
    assert(dw(10) == 0x12345678U && dw(12) == 0x10000040U);
    assert((dw(0) & (1U << 31)) == 0); /* OWN requires later DMA sync */
    assert(dw(6) == 0 && dw(11) == 0 && dw(13) == 0 &&
        dw(14) == 0 && dw(15) == 0);

    p = valid();
    p.first_segment = false;
    p.last_segment = false;
    p.qos_data = false;
    assert(rtwn8723be_tx_encode(&p, d, sizeof(d)) == 0);
    assert(dw(0) == 0 && dw(2) == (1U << 17));
    assert(dw(7) == 100 && dw(8) == (1U << 15));
    assert(dw(10) == p.buffer_dma && dw(12) == p.next_desc_dma);

    p = valid();
    p.buffer_len = 108;  /* 8-byte early-mode header */
    assert(rtwn8723be_tx_encode(&p, d, sizeof(d)) == 0);
    assert(((dw(0) >> 16) & 255U) == 48U);
    assert(((dw(1) >> 24) & 31U) == 1U);
    assert(dw(7) == 108 && (dw(0) & 0xffffU) == 100U);

    assert(rtwn8723be_tx_encode_command(60, 0x1000U,
        0x2000U, d, sizeof(d)) == 0);
    assert(dw(0) == (60U | (40U << 16) |
        (1U << 26) | (1U << 27)));
    assert(dw(1) == (0x10U << 8) && dw(2) == 0 &&
        dw(3) == (1U << 8) && dw(4) == 0);
    assert(dw(7) == 60 && dw(10) == 0x1000U &&
        dw(12) == 0x2000U && !(dw(0) & (1U << 31)));

    p = valid();
    memset(d, 0x5a, sizeof(d));
    p.next_desc_dma++;
    assert(rtwn8723be_tx_encode(&p, d, sizeof(d)) == EINVAL);
    for (i = 0; i < sizeof(d); i++)
        assert(d[i] == 0x5a);

    p = valid();
    p.security = 2;
    assert(rtwn8723be_tx_encode(&p, d, sizeof(d)) == EINVAL);
    p = valid();
    p.buffer_len = 109;
    assert(rtwn8723be_tx_encode(&p, d, sizeof(d)) == EINVAL);
    p = valid();
    p.buffer_len = 9101;
    assert(rtwn8723be_tx_encode(&p, d, sizeof(d)) == EINVAL);
    p = valid();
    p.fw_queue = 32;
    assert(rtwn8723be_tx_encode(&p, d, sizeof(d)) == EINVAL);
    assert(rtwn8723be_tx_encode(NULL, d, sizeof(d)) == EINVAL);
    assert(rtwn8723be_tx_encode(&p, NULL, sizeof(d)) == EINVAL);
    assert(rtwn8723be_tx_encode(&p, d, 39) == EINVAL);
    assert(rtwn8723be_tx_encode_command(0, 0x1000U,
        0x2000U, d, sizeof(d)) == EINVAL);

    for (i = 0; i < 32; i++) {
        p = valid();
        p.fw_queue = (uint8_t)i;
        assert(rtwn8723be_tx_encode(&p, d, sizeof(d)) == 0);
        assert(((dw(1) >> 8) & 31U) == i);
        count++;
    }
    printf("RTL_TX_DESC_C11_OK: golden data/command, "
        "fragments, early-mode, all %u QSEL, guards, OWN=0\\n", count);
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="r23be-tx-") as tmp:
    source = Path(tmp) / "test_tx.c"
    exe = Path(tmp) / "test_tx"
    source.write_text(HARNESS)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
         "-pedantic", "-fsanitize=undefined",
         "-fno-sanitize-recover=all",
         "-I", str(ROOT / "src"),
         str(ROOT / "src/rtwn8723be_tx_desc.c"),
         str(source), "-o", str(exe)],
        check=True,
    )
    subprocess.run([str(exe)], check=True)
