#!/usr/bin/env python3
"""Extract and exercise the actual RX DMA slot guard with strict host C.

This is a source-contract and isolated-branch regression, not a native
NetBSD object build, bus_dma integration test, or hardware validation.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "src/rtwn8723be_rx_native.c").read_text()
slot_anchor = "if (slot->map == NULL ||"
if src.count(slot_anchor) != 1:
    raise AssertionError("RX slot preflight is missing or ambiguous")
guard = slot_anchor + src.split(slot_anchor, 1)[1].split("return EIO;", 1)[0] + "return EIO;"
for required in (
    "slot->map->dm_nsegs != 1",
    "slot->m == NULL",
    "slot->m->m_len < RTWN8723BE_RX_BUFFER_SIZE",
    "slot->map->dm_mapsize < RTWN8723BE_RX_BUFFER_SIZE",
    "slot->map->dm_segs[0].ds_len <",
    "slot->map->dm_segs[0].ds_addr >",
    "(RTWN8723BE_RX_BUFFER_SIZE - 1U)",
):
    if required not in guard:
        raise AssertionError("missing RX DMA bound: " + required)

ring_guard = "ring->desc_dma.size < (bus_size_t)ring->count *"
if src.count(ring_guard) != 1 or src.index(ring_guard) > src.index(
    "rtwn8723be_f16_1_dma_sync_for_cpu("
):
    raise AssertionError("descriptor ring must be checked before DMA sync")
if "sizeof(*descs)" not in src[
    src.index(ring_guard):src.index(ring_guard) + 100
]:
    raise AssertionError("descriptor capacity must use actual stride")

prefix = r"""
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#define RTWN8723BE_RX_BUFFER_SIZE 9100U
#define RTWN8723BE_DMA_MAXADDR UINT32_MAX
/* Host model of NetBSD bus_addr_t; native ABI is not tested here. */
typedef uint64_t bus_addr_t;
struct segment { uint64_t ds_addr; size_t ds_len; };
struct dma_map { unsigned dm_nsegs; size_t dm_mapsize;
                 struct segment dm_segs[1]; };
struct mbuf { size_t m_len; };
struct dma_slot { struct dma_map *map; struct mbuf *m; };
static int valid(const struct dma_slot *slot)
{
"""
suffix = r"""
    return 0;
}
int main(void)
{
    struct dma_map map = {0};
    struct mbuf mbuf = {0};
    struct dma_slot slot = {0};

    assert(valid(&slot) == EIO); /* no DMA map */
    slot.map = &map;
    assert(valid(&slot) == EIO); /* no mapped segment */
    map.dm_nsegs = 1;
    assert(valid(&slot) == EIO); /* no mbuf */
    slot.m = &mbuf;
    assert(valid(&slot) == EIO); /* undersized mbuf */
    mbuf.m_len = RTWN8723BE_RX_BUFFER_SIZE;
    assert(valid(&slot) == EIO); /* zero mapped length */
    map.dm_mapsize = RTWN8723BE_RX_BUFFER_SIZE - 1;
    assert(valid(&slot) == EIO); /* map one byte too short */
    map.dm_mapsize = RTWN8723BE_RX_BUFFER_SIZE;
    assert(valid(&slot) == EIO); /* zero segment length */
    map.dm_segs[0].ds_len = RTWN8723BE_RX_BUFFER_SIZE - 1;
    assert(valid(&slot) == EIO); /* segment one byte too short */
    map.dm_segs[0].ds_len = RTWN8723BE_RX_BUFFER_SIZE;
    map.dm_segs[0].ds_addr = (uint64_t)UINT32_MAX + 1U;
    assert(valid(&slot) == EIO); /* device cannot address buffer */
    map.dm_segs[0].ds_addr = UINT32_MAX;
    assert(valid(&slot) == EIO); /* start fits, end crosses boundary */
    map.dm_segs[0].ds_addr = UINT32_MAX -
        (RTWN8723BE_RX_BUFFER_SIZE - 1U);
    assert(valid(&slot) == 0); /* exact highest legal 32-bit span */
    map.dm_segs[0].ds_addr++;
    assert(valid(&slot) == EIO); /* one byte beyond legal span */
    map.dm_segs[0].ds_addr--;
    map.dm_mapsize++;
    map.dm_segs[0].ds_len++;
    assert(valid(&slot) == 0); /* larger map/segment still valid */
    puts("RTL_RX_DMA_BOUNDS_HOST_C11_UBSAN_OK");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-rx-dma-") as tmp:
    base = Path(tmp)
    source = base / "guard.c"
    output = base / "guard"
    source.write_text(prefix + guard + suffix)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-pedantic", "-fsanitize=undefined",
        "-fno-sanitize-recover=all",
        str(source), "-o", str(output),
    ], check=True)
    subprocess.run([str(output)], check=True)
