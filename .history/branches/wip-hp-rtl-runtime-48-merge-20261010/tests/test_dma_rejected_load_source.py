#!/usr/bin/env python3
"""Source-only guard for loaded-but-rejected ring DMA allocation.

No compiler, kernel, bus_dma implementation, or device is executed here.
Run with --source FILE to review another source; --self-test checks mutations.
"""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def block(source, marker):
    """Extract one brace-balanced C block after a unique marker."""
    if source.count(marker) != 1:
        raise ValueError(f"expected unique marker: {marker!r}")
    start = source.index("{", source.index(marker))
    depth = 0
    for pos in range(start, len(source)):
        depth += (source[pos] == "{") - (source[pos] == "}")
        if depth == 0:
            return source[start + 1:pos]
    raise ValueError(f"unterminated block after {marker!r}")


def check(source):
    # Remove comments before examining control-flow tokens, so explanatory
    # prose cannot accidentally satisfy the source predicates.
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    alloc = block(code, "\nint\nrtwn8723be_f16_1_dma_mem_alloc(")
    reject = block(alloc, "if (dma->map->dm_nsegs != 1 ||")
    free = block(code, "\nvoid\nrtwn8723be_f16_1_dma_mem_free(")
    flat = " ".join(reject.split())
    expected = "error = EFBIG; bus_dmamap_unload(dmat, dma->map); goto fail;"
    if flat != expected:
        raise ValueError("rejection must set EFBIG, unload exactly once, then goto fail; got " + flat)
    load = alloc.index("error = bus_dmamap_load(")
    reject_pos = alloc.index("if (dma->map->dm_nsegs != 1 ||")
    pre = alloc.index("bus_dmamap_sync(")
    if not load < reject_pos < pre:
        raise ValueError("map validation must follow load and precede first PRE synchronization")
    if "if (error != 0)\n        goto fail;" not in alloc[load:reject_pos]:
        raise ValueError("failed load must bypass rejection unload")
    if "dma->map != NULL && dma->map->dm_mapsize != 0" not in free:
        raise ValueError("free must not synchronize/unload an invalidated map")
    if not free.index("bus_dmamap_unload(") < free.index("bus_dmamem_unmap(") < free.index("bus_dmamem_free(") < free.index("bus_dmamap_destroy("):
        raise ValueError("map/KVA/memory/handle cleanup ordering changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "src/rtwn8723be_f16_1_dma.c")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    check(source)
    refused = 0
    if args.self_test:
        start = source.index("if (dma->map->dm_nsegs != 1 ||")
        end = source.index("\n    memset(dma->kva", start)
        region = source[start:end]
        unload = "        bus_dmamap_unload(dmat, dma->map);\n"
        variants = [
            region.replace(unload, ""),
            region.replace(unload, unload + unload),
            region.replace(unload, "        goto fail;\n" + unload),
            region.replace(unload, "        bus_dmamap_sync(dmat, dma->map, 0, size, BUS_DMASYNC_POSTREAD);\n" + unload),
            region.replace("error = EFBIG;", "error = 0;"),
        ]
        for i, variant in enumerate(variants, 1):
            try:
                check(source[:start] + variant + source[end:])
            except ValueError:
                refused += 1
            else:
                raise ValueError(f"source mutation {i} escaped rejection")
    print(f"RTL_DMA_REJECTED_LOAD_SOURCE_PASS mutations_refused={refused}; native=NOT_RUN")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(f"RTL_DMA_REJECTED_LOAD_SOURCE_FAIL: {error}", file=sys.stderr)
        sys.exit(1)
