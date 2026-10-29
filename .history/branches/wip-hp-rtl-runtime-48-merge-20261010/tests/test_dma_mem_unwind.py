#!/usr/bin/env python3
"""Compile the production DMA-unwind function with strict mocked NetBSD bus_dma.

Host-side failure injection only: no NetBSD kernel object or physical DMA test.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/rtwn8723be_f16_1_dma.c").read_text()
START = "void\nrtwn8723be_f16_1_dma_mem_free("
END = "\nvoid\nrtwn8723be_f16_1_dma_sync_for_device("
assert SOURCE.count(START) == 1 and SOURCE.count(END) == 1
body = SOURCE[SOURCE.index(START):SOURCE.index(END, SOURCE.index(START))]
assert "dma->map->dm_mapsize != 0" in body
assert body.index("dma->map->dm_mapsize != 0") < body.index("bus_dmamap_sync(")
assert body.index("bus_dmamap_unload(") < body.index("bus_dmamem_unmap(")

PRELUDE = r"""
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef void *bus_dma_tag_t;
typedef uint64_t bus_addr_t;
typedef size_t bus_size_t;
typedef struct { bus_addr_t ds_addr; bus_size_t ds_len; } bus_dma_segment_t;
struct dma_map {
    bus_size_t dm_mapsize;
    int dm_nsegs;
};
typedef struct dma_map *bus_dmamap_t;
struct rtwn8723be_dma_mem {
    bus_dmamap_t map;
    void *kva;
    bus_dma_segment_t seg;
    int nsegs;
    bus_addr_t paddr;
    bus_size_t size;
};
#define BUS_DMASYNC_POSTREAD 1
#define BUS_DMASYNC_POSTWRITE 2
static char events[16];
static unsigned n;
static void record(char c) { assert(n < sizeof(events)); events[n++] = c; }
static void bus_dmamap_sync(bus_dma_tag_t t, bus_dmamap_t m,
                            bus_addr_t o, bus_size_t l, int ops)
{
    (void)t;
    assert(m != NULL && m->dm_mapsize != 0);
    assert(o == 0 && l == m->dm_mapsize);
    assert(ops == (BUS_DMASYNC_POSTREAD | BUS_DMASYNC_POSTWRITE));
    record('s');
}
static void bus_dmamap_unload(bus_dma_tag_t t, bus_dmamap_t m)
{ (void)t; assert(m != NULL && m->dm_mapsize != 0); record('l'); m->dm_mapsize = 0; m->dm_nsegs = 0; }
static void bus_dmamem_unmap(bus_dma_tag_t t, void *k, bus_size_t s)
{ (void)t; assert(k != NULL && s == 128); record('u'); }
static void bus_dmamem_free(bus_dma_tag_t t, bus_dma_segment_t *s, int nsegs)
{ (void)t; assert(s != NULL && nsegs == 1); record('f'); }
static void bus_dmamap_destroy(bus_dma_tag_t t, bus_dmamap_t m)
{ (void)t; assert(m != NULL); record('d'); }
"""

MAIN = r"""
static void exercise(bus_dmamap_t map, int mapped_kva, int allocated,
                     size_t mapsize, const char *expected)
{
    static int backing;
    struct rtwn8723be_dma_mem dma = {0};
    if (map != NULL) {
        map->dm_mapsize = mapsize;
        map->dm_nsegs = mapsize != 0 ? 1 : 0;
    }
    dma.map = map;
    dma.kva = mapped_kva ? &backing : NULL;
    dma.nsegs = allocated ? 1 : 0;
    dma.paddr = 0x1000;
    dma.size = 128;
    n = 0;
    memset(events, 0, sizeof(events));
    rtwn8723be_f16_1_dma_mem_free(NULL, &dma);
    assert(n == strlen(expected) && memcmp(events, expected, n) == 0);
    assert(dma.map == NULL && dma.kva == NULL && dma.nsegs == 0);
    assert(dma.paddr == 0 && dma.size == 0);
}
int main(void)
{
    struct dma_map map;
    exercise(NULL, 0, 0, 0, "");       /* no handle */
    exercise(&map, 0, 0, 0, "d");       /* created map only */
    exercise(&map, 0, 1, 0, "fd");      /* allocated DMA memory */
    exercise(&map, 1, 1, 0, "ufd");     /* KVA valid; map load failed */
    exercise(&map, 1, 1, 128, "slufd");/* normal loaded DMA map */
    exercise(&map, 1, 1, 64, "slufd"); /* synchronize actual map size */
    puts("RTL_DMA_UNWIND_C11_UBSAN_OK cases=6");
    return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="rtl-dma-unwind-") as tmp:
    c = Path(tmp) / "unwind.c"
    exe = Path(tmp) / "unwind"
    c.write_text(PRELUDE + "\n" + body + "\n" + MAIN)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all",
                    str(c), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
