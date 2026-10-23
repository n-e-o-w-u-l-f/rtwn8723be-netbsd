#!/usr/bin/env python3
"""Compile actual RTL descriptor allocator/free with failure-injected bus_dma mocks.

Read-only source extraction; temporary host C11+UBSan test, NOT a NetBSD
kernel or physical PCI DMA test. Source must come from the active RTL tree.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/rtwn8723be_f16_1_dma.c").read_text(encoding="utf-8")
ALLOC = "int\nrtwn8723be_f16_1_dma_mem_alloc("
FREE = "\nvoid\nrtwn8723be_f16_1_dma_mem_free("
AFTER = "\nvoid\nrtwn8723be_f16_1_dma_sync_for_device("
assert SOURCE.count(ALLOC) == SOURCE.count(FREE) == SOURCE.count(AFTER) == 1
start = SOURCE.index(ALLOC)
end = SOURCE.index(AFTER, SOURCE.index(FREE))
body = SOURCE[start:end]
assert "bus_dmamap_unload(dmat, dma->map);\n        goto fail;" in body
assert "dma->map->dm_mapsize != 0" in body

PRELUDE = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void *bus_dma_tag_t;
typedef uint64_t bus_addr_t;
typedef size_t bus_size_t;
typedef struct { bus_addr_t ds_addr; bus_size_t ds_len; } bus_dma_segment_t;
struct dma_map {
    bus_size_t dm_mapsize;
    int dm_nsegs;
    bus_dma_segment_t dm_segs[1];
    bool loaded;
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
#define BUS_DMA_WAITOK 1
#define BUS_DMA_ALLOCNOW 2
#define BUS_DMASYNC_PREREAD 4
#define BUS_DMASYNC_PREWRITE 8
#define BUS_DMASYNC_POSTREAD 16
#define BUS_DMASYNC_POSTWRITE 32
enum fault { OK, BAD_SEGMENTS, BAD_MAPSIZE, BAD_SEG_LENGTH,
    BAD_DMA32, FAIL_CREATE, FAIL_ALLOC, FAIL_MAP, FAIL_LOAD };
static enum fault injected;
static char events[32];
static unsigned n;
static char backing[128];
static void record(char c) { assert(n < sizeof(events)); events[n++] = c; }
static int bus_dmamap_create(bus_dma_tag_t t, bus_size_t size, int nseg,
    bus_size_t maxsz, bus_size_t boundary, int flags, bus_dmamap_t *out)
{
    (void)t;
    assert(size == 128 && nseg == 1 && maxsz == 128 && boundary == 0);
    assert(flags == (BUS_DMA_WAITOK | BUS_DMA_ALLOCNOW));
    record('C');
    if (injected == FAIL_CREATE) return ENOMEM;
    *out = calloc(1, sizeof(**out));
    assert(*out != NULL);
    return 0;
}
static int bus_dmamem_alloc(bus_dma_tag_t t, bus_size_t size,
    bus_size_t align, bus_size_t boundary, bus_dma_segment_t *seg,
    int capacity, int *nsegs, int flags)
{
    (void)t;
    assert(size == 128 && align == 256 && boundary == 0);
    assert(capacity == 1 && flags == BUS_DMA_WAITOK);
    record('A');
    if (injected == FAIL_ALLOC) return ENOMEM;
    seg->ds_addr = UINT64_C(0x1000);
    seg->ds_len = size;
    *nsegs = 1;
    return 0;
}
static int bus_dmamem_map(bus_dma_tag_t t, bus_dma_segment_t *seg,
    int nsegs, bus_size_t size, void **kva, int flags)
{
    (void)t;
    assert(seg != NULL && nsegs == 1 && size == 128 && flags == BUS_DMA_WAITOK);
    record('M');
    if (injected == FAIL_MAP) return ENOMEM;
    *kva = backing;
    return 0;
}
static int bus_dmamap_load(bus_dma_tag_t t, bus_dmamap_t map,
    void *buf, bus_size_t size, void *p, int flags)
{
    (void)t; (void)p;
    assert(map != NULL && buf == backing && size == 128 && flags == BUS_DMA_WAITOK);
    record('L');
    if (injected == FAIL_LOAD) return EIO;
    map->loaded = true;
    map->dm_mapsize = injected == BAD_MAPSIZE ? 64 : size;
    map->dm_nsegs = injected == BAD_SEGMENTS ? 2 : 1;
    map->dm_segs[0].ds_len = injected == BAD_SEG_LENGTH ? 64 : size;
    map->dm_segs[0].ds_addr = injected == BAD_DMA32 ? UINT64_C(0x100000000) : UINT64_C(0x1000);
    return 0;
}
static bool rtwn8723be_dma32_range_valid(bus_addr_t addr, bus_size_t size)
{
    return size != 0 && addr <= UINT32_MAX && size - 1 <= UINT32_MAX - addr;
}
static void bus_dmamap_sync(bus_dma_tag_t t, bus_dmamap_t map,
    bus_addr_t offset, bus_size_t length, int flags)
{
    (void)t;
    assert(map != NULL && map->loaded && offset == 0);
    assert(length == map->dm_mapsize);
    if (flags == (BUS_DMASYNC_PREREAD | BUS_DMASYNC_PREWRITE)) record('P');
    else { assert(flags == (BUS_DMASYNC_POSTREAD | BUS_DMASYNC_POSTWRITE)); record('Q'); }
}
static void bus_dmamap_unload(bus_dma_tag_t t, bus_dmamap_t map)
{
    (void)t;
    assert(map != NULL && map->loaded);
    record('U');
    map->loaded = false;
    map->dm_mapsize = 0;
    map->dm_nsegs = 0;
}
static void bus_dmamem_unmap(bus_dma_tag_t t, void *kva, bus_size_t size)
{ (void)t; assert(kva == backing && size == 128); record('V'); }
static void bus_dmamem_free(bus_dma_tag_t t, bus_dma_segment_t *seg, int nsegs)
{ (void)t; assert(seg != NULL && nsegs == 1); record('F'); }
static void bus_dmamap_destroy(bus_dma_tag_t t, bus_dmamap_t map)
{ (void)t; assert(map != NULL && !map->loaded); record('D'); free(map); }
void rtwn8723be_f16_1_dma_mem_free(bus_dma_tag_t, struct rtwn8723be_dma_mem *);
'''
MAIN = r'''
static void exercise(enum fault f, int expected_error, const char *expected)
{
    struct rtwn8723be_dma_mem dma = {0};
    injected = f;
    n = 0;
    memset(events, 0, sizeof(events));
    int rc = rtwn8723be_f16_1_dma_mem_alloc((void *)1, &dma, 128, 256);
    assert(rc == expected_error);
    if (rc == 0) {
        assert(dma.map != NULL && dma.map->loaded);
        assert(dma.kva == backing && dma.nsegs == 1 && dma.size == 128);
        assert(dma.paddr == UINT64_C(0x1000));
        rtwn8723be_f16_1_dma_mem_free((void *)1, &dma);
    }
    assert(n == strlen(expected) && memcmp(events, expected, n) == 0);
    assert(dma.map == NULL && dma.kva == NULL && dma.nsegs == 0);
    assert(dma.paddr == 0 && dma.size == 0);
}
int main(void)
{
    exercise(OK, 0, "CAMLPQUVFD");
    exercise(BAD_SEGMENTS, EFBIG, "CAMLUVFD");
    exercise(BAD_MAPSIZE, EFBIG, "CAMLUVFD");
    exercise(BAD_SEG_LENGTH, EFBIG, "CAMLUVFD");
    exercise(BAD_DMA32, EFBIG, "CAMLUVFD");
    exercise(FAIL_CREATE, ENOMEM, "C");
    exercise(FAIL_ALLOC, ENOMEM, "CAD");
    exercise(FAIL_MAP, ENOMEM, "CAMFD");
    exercise(FAIL_LOAD, EIO, "CAMLVFD");
    puts("RTL_DMA_ALLOC_UNWIND_C11_UBSAN_OK cases=9");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtl-dma-alloc-") as tmp:
    source_file = Path(tmp) / "unwind.c"
    executable = Path(tmp) / "unwind"
    source_file.write_text(PRELUDE + "\n" + body + "\n" + MAIN, encoding="utf-8")
    compiler = os.environ.get("CC", "cc")
    subprocess.run([compiler, "-v", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                    str(source_file), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
