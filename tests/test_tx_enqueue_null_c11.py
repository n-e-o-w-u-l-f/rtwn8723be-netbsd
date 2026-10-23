#!/usr/bin/env python3
"""Compile the complete production enqueue function against userland DMA mocks.

Run on NetBSD with cc and UBSan. This checks admission/ownership control flow,
not kernel ABI, real bus_dma semantics, locking or hardware acceptance.
"""
import hashlib
import pathlib
import resource
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRELUDE = r"""
#include <sys/endian.h>
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint64_t bus_addr_t;
typedef size_t bus_size_t;
/* Mock constants/layouts deliberately do not constitute a kernel ABI test. */
enum { RTWN8723BE_BK_QUEUE, RTWN8723BE_BE_QUEUE, RTWN8723BE_VI_QUEUE,
 RTWN8723BE_VO_QUEUE, RTWN8723BE_BEACON_QUEUE, RTWN8723BE_MGNT_QUEUE,
 RTWN8723BE_HIGH_QUEUE, RTWN8723BE_TX_QUEUE_COUNT };
enum { RTWN8723BE_TX_FW_BK, RTWN8723BE_TX_FW_BE, RTWN8723BE_TX_FW_VI,
 RTWN8723BE_TX_FW_VO, RTWN8723BE_TX_FW_BEACON, RTWN8723BE_TX_FW_MGNT,
 RTWN8723BE_TX_FW_HIGH };
#define RTWN8723BE_RX_BUFFER_SIZE 4096
#define M_PKTHDR 1
#define BUS_DMA_NOWAIT 1
#define BUS_DMA_WRITE 2
#define BUS_DMASYNC_PREWRITE 4
#define R23BE_TXD0_OWN UINT32_C(0x80000000)
#define R23BE_REG_PCIE_CTRL_REG 0x300
struct map { size_t dm_mapsize; int dm_nsegs;
 struct { size_t ds_len; uint64_t ds_addr; } dm_segs[1]; };
struct mbuf { int m_flags, m_len; struct { int len; } m_pkthdr;
 struct mbuf *m_next, *m_nextpkt; };
struct rtwn8723be_tx_desc { uint32_t d[16]; };
struct dma { void *kva; struct map *map; size_t size; uint64_t paddr; };
struct rtwn8723be_dma_slot { struct map *map; struct mbuf *m;
 void *tx_owner; void (*tx_release)(void *, struct mbuf *, bool); };
struct rtwn8723be_tx_ring { unsigned count, producer, consumer;
 struct rtwn8723be_dma_slot *slot; struct dma desc_dma; };
struct rtwn8723be_softc { bool sc_mapped, sc_rings_allocated, sc_dma_32bit;
 void *sc_dmat; struct rtwn8723be_tx_ring sc_tx_ring[RTWN8723BE_TX_QUEUE_COUNT]; };
struct rtwn8723be_tx_params { unsigned fw_queue; int buffer_len, packet_len;
 uint32_t buffer_dma, next_desc_dma; };
static struct { unsigned cpu, device, load, unload, sync, barrier, write, encode; } calls;
static int load_error;
static bool rtwn8723be_dma32_range_valid(uint64_t a, size_t n)
{ return n != 0 && a <= UINT32_MAX && n - 1 <= UINT32_MAX - a; }
static void rtwn8723be_f16_1_dma_sync_for_cpu(void *t, struct dma *d, size_t o, size_t n)
{ assert(t && d && o + n <= d->size); calls.cpu++; }
static void rtwn8723be_f16_1_dma_sync_for_device(void *t, struct dma *d, size_t o, size_t n)
{ assert(t && d && o + n <= d->size); calls.device++; }
static int bus_dmamap_load_mbuf(void *t, struct map *p, struct mbuf *m, int flags)
{ assert(t && p && m && flags == (BUS_DMA_NOWAIT | BUS_DMA_WRITE)); calls.load++;
 if (load_error) return load_error;
 p->dm_mapsize = m->m_len; p->dm_nsegs = 1;
 p->dm_segs[0].ds_addr = 0x2000; p->dm_segs[0].ds_len = m->m_len; return 0; }
static void bus_dmamap_unload(void *t, struct map *p)
{ assert(t && p); calls.unload++; memset(p, 0, sizeof(*p)); }
static void bus_dmamap_sync(void *t, struct map *p, size_t o, size_t n, int flags)
{ assert(t && p && o == 0 && n == p->dm_mapsize && flags == BUS_DMASYNC_PREWRITE);
 calls.sync++; }
static int rtwn8723be_tx_encode(const struct rtwn8723be_tx_params *p, uint8_t *d, size_t n)
{ assert(p->buffer_dma == 0x2000 && p->next_desc_dma == 0x1040);
 calls.encode++; memset(d, 0, n); return 0; }
static int rtwn8723be_tx_encode_command(int len, uint32_t a, uint32_t next, uint8_t *d, size_t n)
{ (void)len; (void)a; (void)next; (void)d; (void)n; assert(!"unexpected command encoding"); return EINVAL; }
static void membar_producer(void) { calls.barrier++; }
static void rtwn8723be_write_2(struct rtwn8723be_softc *sc, unsigned reg, uint16_t value)
{ assert(sc && reg == R23BE_REG_PCIE_CTRL_REG && value == (1U << RTWN8723BE_BE_QUEUE));
 calls.write++; }
"""
TESTS = r"""
static void release_owner(void *p, struct mbuf *m, bool ok)
{ (void)p; (void)m; (void)ok; assert(!"release during enqueue"); }
int main(int argc, char **argv)
{
 struct rtwn8723be_softc sc = {0}, before;
 struct rtwn8723be_tx_desc desc[2] = {{{0}}}, desc_before[2];
 struct rtwn8723be_dma_slot slot[2] = {{0}}, slot_before[2];
 struct map packet = {0}, packet_before, descriptor = {0};
 struct mbuf m = {0};
 struct rtwn8723be_tx_params p = {RTWN8723BE_TX_FW_BE, 64, 64, 0, 0};
 struct rtwn8723be_tx_ring *r = &sc.sc_tx_ring[RTWN8723BE_BE_QUEUE];
 int test = argc == 2 ? atoi(argv[1]) : -1, expected = EIO, result;
 assert(test >= 0 && test < 11);
 sc.sc_mapped = sc.sc_rings_allocated = sc.sc_dma_32bit = true;
 sc.sc_dmat = &sc;
 r->count = 2; r->slot = slot;
 descriptor.dm_mapsize = sizeof(desc);
 r->desc_dma = (struct dma){desc, &descriptor, sizeof(desc), 0x1000};
 slot[0].map = &packet;
 m.m_flags = M_PKTHDR; m.m_len = m.m_pkthdr.len = 64;
 /* Distinct contents catch accidental descriptor changes on rejected input. */
 desc[0].d[5] = 0x12345678; desc[1].d[7] = 0xabcdef01;
 switch (test) {
 case 0: slot[0].map = NULL; break;
 case 1: sc.sc_dmat = NULL; expected = ENXIO; break;
 case 2: packet.dm_mapsize = 64; break;
 case 3: packet.dm_nsegs = 1; break;
 case 4: slot[0].tx_owner = &sc; break;
 case 5: slot[0].tx_release = release_owner; break;
 case 6: slot[0].m = &m; expected = EBUSY; break;
 case 7: sc.sc_rings_allocated = false; expected = ENXIO; break;
 case 8: r->desc_dma.map = NULL; break;
 case 9: load_error = ENOMEM; expected = ENOMEM; break;
 case 10: expected = 0; break;
 }
 memcpy(&before, &sc, sizeof(sc)); memcpy(desc_before, desc, sizeof(desc));
 memcpy(slot_before, slot, sizeof(slot)); memcpy(&packet_before, &packet, sizeof(packet));
 result = rtwn8723be_tx_native_enqueue_owned(&sc, RTWN8723BE_BE_QUEUE, &m, &p,
     false, NULL, NULL);
 assert(result == expected);
 if (test < 9) {
   const unsigned char *b = (const unsigned char *)&calls;
   for (size_t i = 0; i < sizeof(calls); i++) assert(b[i] == 0);
 }
 if (test != 10) {
   assert(memcmp(&sc, &before, sizeof(sc)) == 0);
   assert(memcmp(desc, desc_before, sizeof(desc)) == 0);
   assert(memcmp(slot, slot_before, sizeof(slot)) == 0);
   assert(memcmp(&packet, &packet_before, sizeof(packet)) == 0);
 }
 if (test == 9) {
   assert(calls.cpu == 1 && calls.load == 1 && calls.device == 1);
   assert(!calls.unload && !calls.sync && !calls.encode && !calls.write && !calls.barrier);
 }
 if (test == 10) {
   assert(calls.cpu == 1 && calls.load == 1 && calls.device == 1 && calls.sync == 1);
   assert(calls.encode == 1 && calls.write == 1 && calls.barrier == 1 && !calls.unload);
   assert(r->producer == 1 && slot[0].m == &m && packet.dm_mapsize == 64);
   assert(le32toh(desc[0].d[0]) & R23BE_TXD0_OWN);
   assert(memcmp(&desc[1], &desc_before[1], sizeof(desc[1])) == 0);
 }
 printf("PASS case %d\n", test);
 return 0;
}
"""

def function(source, marker):
    start = source.index(marker)
    # Function end is a closing brace at column zero in these production files.
    end = source.index("\n}", start) + 2
    return source[start:end]

def replace_once(source, old, new):
    assert source.count(old) == 1, "mutation target changed"
    return source.replace(old, new, 1)

def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    source = (ROOT / "src/rtwn8723be_tx_native.c").read_text()
    body = function(source, "static int\nr23be_tx_queue_check(") + "\n" + function(
        source, "int\nrtwn8723be_tx_native_enqueue_owned(")
    print("production_sha256=" + hashlib.sha256(source.encode()).hexdigest(), flush=True)
    mutants = [
        ("missing_map_guard", replace_once(body, "slot->map == NULL || ", ""), 0, "runtime error"),
        ("late_map_guard", replace_once(body,
            "slot->map == NULL || slot->map->dm_mapsize != 0",
            "slot->map->dm_mapsize != 0 || slot->map == NULL"), 0, "runtime error"),
        ("missing_tag_guard", replace_once(body, " || sc->sc_dmat == NULL", ""), 1, "assertion"),
    ]
    with tempfile.TemporaryDirectory(prefix="rtl-enqueue-c-") as tmp:
        for name, code, case, diagnostic in [("baseline", body, None, None)] + mutants:
            cfile = pathlib.Path(tmp) / (name + ".c")
            binary = pathlib.Path(tmp) / name
            cfile.write_text(PRELUDE + "\n" + code + "\n" + TESTS)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-O1", "-g", "-fsanitize=undefined", "-fno-sanitize-recover=undefined",
                str(cfile), "-o", str(binary)], check=True, timeout=60)
            for n in range(11) if case is None else [case]:
                result = subprocess.run([str(binary), str(n)], text=True,
                    capture_output=True, timeout=10)
                if case is None:
                    if result.returncode:
                        raise AssertionError(result.stdout + result.stderr)
                    print(result.stdout.strip(), flush=True)
                else:
                    assert result.returncode != 0, name + " survived"
                    assert diagnostic in result.stderr.lower(), (name, result.stderr)
                    print("KILLED " + name + ": " + result.stderr.splitlines()[0], flush=True)
    print("PASS: 11 native C cases; 3 compiled runtime mutants rejected")

if __name__ == "__main__":
    main()

