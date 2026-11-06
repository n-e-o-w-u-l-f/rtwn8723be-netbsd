#!/usr/bin/env python3
"""Compile production TX DMA interval guard; detect missing usage before DMA sync."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/rtwn8723be_tx_native.c").read_text()
netbsd = (root / "src/rtwn8723be_netbsd.h").read_text()
match = re.search(r"^#define\s+RTWN8723BE_DMA_MAXADDR\s+(0x[0-9a-fA-F]+ULL)", netbsd, re.M)
assert match, "missing source-defined 32-bit DMA maximum"
anchor = "static bool\nr23be_tx_span_valid("
assert source.count(anchor) == 1
start = source.index(anchor)
end = source.index("\n}\n", start) + 3
guard = source[start:end]
assert source.count("r23be_tx_span_valid(") == 5, "four call sites + definition required"
enqueue = source[source.index("rtwn8723be_tx_native_enqueue("):
                 source.index("\nint\nrtwn8723be_tx_native_reclaim(")]
reclaim = source[source.index("rtwn8723be_tx_native_reclaim("):]
assert enqueue.count("r23be_tx_span_valid(") == 2
assert reclaim.count("r23be_tx_span_valid(") == 2
assert enqueue.index("!r23be_tx_span_valid(slot->map->dm_segs[0].ds_addr") < (
    enqueue.index("BUS_DMASYNC_PREWRITE")), "TX span checked too late"
assert "slot->map->dm_segs[0].ds_len <" in enqueue
assert "slot->map->dm_segs[0].ds_len < slot->map->dm_mapsize" in reclaim
c = """#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef uint64_t bus_addr_t;
typedef uint64_t bus_size_t;
#define RTWN8723BE_DMA_MAXADDR """ + match.group(1) + "\n" + guard + """
int main(void) {
    assert(!r23be_tx_span_valid(0, 0));
    assert(r23be_tx_span_valid(0, 1));
    assert(r23be_tx_span_valid(0xffffffffULL, 1));
    assert(!r23be_tx_span_valid(0xffffffffULL, 2));
    assert(r23be_tx_span_valid(0xfffffff0ULL, 16));
    assert(!r23be_tx_span_valid(0xfffffff0ULL, 17));
    assert(!r23be_tx_span_valid(0x100000000ULL, 1));
    assert(r23be_tx_span_valid(0, 0x100000000ULL));
    assert(!r23be_tx_span_valid(0, 0x100000001ULL));
    assert(r23be_tx_span_valid(0xfffffffeULL, 2));
    assert(!r23be_tx_span_valid(0xfffffffeULL, 3));
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-tx-span-") as tmp:
    path = Path(tmp) / "span.c"
    exe = Path(tmp) / "span"
    path.write_text(c)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all", str(path), "-o", str(exe)],
                   check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_TX_32BIT_SPAN_C11_UBSAN_OK boundary_cases=11 "
      "production_guard_sites=4")
