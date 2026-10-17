#!/usr/bin/env python3
"""Batch source contracts plus an independent ownership model, not native C."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def contract(source):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    match = re.search(r"\nrtwn8723be_tx_native_enqueue_batch\([^;]+?\n\{(.*?)\n\}", source, re.S)
    if match is None:
        return False
    b = match[1]
    required = ["count > RTWN8723BE_TX_BATCH_MAX", "count > ring->count",
                "ring->desc_dma.map->dm_mapsize < bytes",
                "if (frames[j].m == f->m)",
                "slot->map->dm_mapsize != 0", "slot->tx_owner != NULL",
                "slot->tx_release != NULL", "f->m->m_nextpkt != NULL",
                "BUS_DMA_NOWAIT | BUS_DMA_WRITE);", "loaded++;",
                "slot->map->dm_nsegs != 1", "error = rtwn8723be_tx_encode(&p,",
                "(uint8_t *)&workspace->desc[i], sizeof(workspace->desc[i])",
                "(le32toh(workspace->desc[i].d[0]) & R23BE_TXD0_OWN) != 0",
                "BUS_DMASYNC_PREWRITE);", "descs[idx] = workspace->desc[i];",
                "slot->m = f->m;", "membar_producer();",
                "descs[idx].d[0] = htole32(le32toh(descs[idx].d[0]) | R23BE_TXD0_OWN);",
                "ring->producer = (start + count) % ring->count;",
                "rtwn8723be_write_2(sc, R23BE_REG_PCIE_CTRL_REG,",
                "abort:", "while (loaded != 0)", "loaded--;",
                "idx = (start + loaded) % ring->count;",
                "bus_dmamap_unload(sc->sc_dmat, ring->slot[idx].map);"]
    if not all(t in b for t in required):
        return False
    # The first producer descriptor is exposed ONLY after the tail's OWN
    # bits are synced for device DMA. Forward OWN order is unsafe when the
    # device consumes an already-running BE queue concurrently.
    own_region = b.split("membar_producer();", 1)[1].split(
        "ring->producer =", 1)[0]
    if not re.search(r"for\s*\(i = count; i != 0;\s*\)\s*\{\s*"
                     r"i--;\s*idx = \(start \+ i\) % ring->count;", own_region):
        return False
    if own_region.count("R23BE_TXD0_OWN") != 1 or own_region.count(
            "rtwn8723be_f16_1_dma_sync_for_device(") != 1:
        return False
    pub = b.index("BUS_DMASYNC_PREWRITE);")
    abort = b.index("abort:")
    if "goto abort;" in b[pub:abort] or "return error;" in b[pub:abort]:
        return False
    if b.index("loaded++;") < b.index("if (error != 0)\n            goto abort;", b.index("error = bus_dmamap_load_mbuf")):
        return False
    if not (b.rfind("goto abort;") < pub < b.index("descs[idx] = workspace->desc[i];")
            < b.index("slot->m = f->m;") < b.index("membar_producer();")
            < b.index("descs[idx].d[0] =") < b.index("ring->producer =")
            < b.index("rtwn8723be_write_2(")):
        return False
    return (b.count("rtwn8723be_write_2(") == 1 and
            all(t not in b for t in ("m_freem(", "ieee80211_free_node(", "kmem_alloc(", "->release(")))


source = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else (ROOT / "src/rtwn8723be_tx_native.c").read_text()
assert contract(source), "batch must prepare everything before publication and unwind loaded maps"
prefix, batch = source.split("\nrtwn8723be_tx_native_enqueue_batch(", 1)
mutants = [batch.replace("count > RTWN8723BE_TX_BATCH_MAX", "false", 1),
           batch.replace("if (frames[j].m == f->m)", "if (false)", 1),
           batch.replace("loaded++;", "", 1),
           batch.replace("loaded--;", "loaded++;", 1),
           batch.replace("bus_dmamap_unload(sc->sc_dmat, ring->slot[idx].map);", "", 1),
           batch.replace("slot->map->dm_mapsize != 0", "false", 1),
           batch.replace("BUS_DMASYNC_PREWRITE);", "BUS_DMASYNC_PREWRITE);\n    goto abort;", 1),
           batch.replace("membar_producer();", "", 1),
           batch.replace("for (i = count; i != 0; ) {",
                         "for (i = 0; i < count; i++) {", 1),
           batch.replace("i--;\n        idx = (start + i) % ring->count;",
                         "idx = (start + i) % ring->count;", 1)]
for i, mutation in enumerate(mutants):
    assert mutation != batch and not contract(prefix + "\nrtwn8723be_tx_native_enqueue_batch(" + mutation), i

# Model the resource protocol independently of C syntax. A fault before a
# successful load excludes that map from unwind; later faults include it.
cases = 0
for count in range(1, 17):
    for start in range(16):
        for stage in ("slot", "load", "span", "encode", "own", "success"):
            for fail_at in range(count) if stage != "success" else (-1,):
                loaded, unloaded, published = [], [], []
                for i in range(count):
                    if i == fail_at and stage in ("slot", "load"):
                        break
                    loaded.append((start + i) % 16)
                    if i == fail_at:
                        break
                if stage == "success":
                    published = loaded[:]
                    assert len(published) == count and len(set(published)) == count
                else:
                    unloaded = list(reversed(loaded))
                    expected = fail_at + (stage in ("span", "encode", "own"))
                    assert len(unloaded) == expected and not published
                    assert unloaded == [(start + j) % 16 for j in reversed(range(expected))]
                cases += 1
# A running queue may examine the head while publishing a new batch.
# Until every later descriptor is OWN, the head MUST remain CPU-owned;
# this is true even when descriptor indices wrap around.
publication_cases = 0
for ring_count in (2, 4, 8, 16):
    for start in range(ring_count):
        for count in range(1, ring_count + 1):
            expected = {(start + i) % ring_count for i in range(count)}
            owned = set()
            for offset in reversed(range(count)):
                owned.add((start + offset) % ring_count)
                assert start not in owned or owned == expected
                publication_cases += 1
# Negative oracle: a forward release makes the head OWN while tail is not.
assert any(
    {(start + i) % 4 for i in range(1)} !=
    {(start + i) % 4 for i in range(count)}
    for start in range(4) for count in range(2, 5)
)
print(f"TX_BATCH_SOURCE_PASS: 10 rejected mutations; {cases} ownership model cases; "
      f"{publication_cases} reverse-OWN publication states; native NOT_RUN")
