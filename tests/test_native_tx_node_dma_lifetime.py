#!/usr/bin/env python3
"""Source-level TX DMA/802.11 node ownership proof with C11 queue preflight.

Runtime datapath enqueue and STOPPING are exercised by the existing strict
C11/UBSan production-source tests. This test checks the production TX DMA
slot acquisition, rollback, normal completion and two teardown paths.
Native PCI DMA/MMIO/node APIs require a NetBSD kernel for final validation.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TX = (ROOT / "src/rtwn8723be_tx_native.c").read_text()
DMA = (ROOT / "src/rtwn8723be_f16_1_dma.c").read_text()
NET = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
F16 = (ROOT / "src/rtwn8723be_f16_1.h").read_text()
DP = (ROOT / "src/rtwn8723be_datapath.c").read_text()
TXH = (ROOT / "src/rtwn8723be_tx_native.h").read_text()
DPH = (ROOT / "src/rtwn8723be_datapath.h").read_text()

def func(src: str, name: str) -> str:
    anchor = "\n" + name + "("
    assert src.count(anchor) == 1, name
    tail = name + "(" + src.split(anchor, 1)[1]
    level = 0
    for index in range(tail.index("{"), len(tail)):
        if tail[index] == "{":
            level += 1
        elif tail[index] == "}":
            level -= 1
            if level == 0:
                return tail[:index + 1]
    raise AssertionError(name)

enq = func(TX, "rtwn8723be_tx_native_enqueue")
rec = func(TX, "rtwn8723be_tx_native_reclaim")
fre = func(DMA, "rtwn8723be_f16_1_tx_ring_free")
res = func(NET, "rtwn8723be_netbsd_reset_trx_ring")
dep = func(DP, "rtwn8723be_datapath_enqueue")
queue = func(TX, "r23be_tx_queue_check")

def contract(e: str, r: str, f: str, t: str, d: str) -> None:
    assert "struct ieee80211_node *ni;" in F16
    assert "struct ieee80211_node *" in TXH and "struct ieee80211_node *" in DPH
    assert "struct ieee80211_node *ni" in e and "ni == NULL" in e
    assert "slot->m != NULL || slot->ni != NULL" in e
    assert '#include <net80211/ieee80211_var.h>' in TX
    assert '#include <net80211/ieee80211_var.h>' in DMA
    dma_check = e.index("slot->map->dm_mapsize != (bus_size_t)input->buffer_len")
    mapped = e.index("bus_dmamap_sync(sc->sc_dmat, slot->map,")
    mbuf = e.index("slot->m = m;")
    node = e.index("slot->ni = ni;")
    own = e.index("R23BE_TXD0_OWN", node)
    assert dma_check < mapped < mbuf < node < own
    assert "ieee80211_free_node(" not in e
    assert "m_freem(" not in e
    assert "goto restore_desc;" in e and "goto unload_map;" in e
    assert e.index("restore_desc:") > node
    assert "struct ieee80211_node *ni" in d
    assert "m == NULL || ni == NULL || p == NULL" in d
    assert d.index("mutex_enter(&dp->tx_lock);") < d.index(
        "rtwn8723be_tx_native_enqueue(") < d.index("mutex_exit(&dp->tx_lock);")
    assert "qid, m, ni, p, command" in d

    for label, fn in (("reclaim", r), ("free", f), ("reset", t)):
        assert "ieee80211_free_node(" in fn, label
        if label == "reclaim":
            release_m = fn.index("m_freem(slot->m);")
            release_n = fn.index("ieee80211_free_node(slot->ni);")
            clear_n = fn.index("slot->ni = NULL;", release_n)
        else:
            release_m = fn.index("m_freem(ring->slot[i].m);")
            release_n = fn.index("ieee80211_free_node(ring->slot[i].ni);")
            clear_n = fn.index("ring->slot[i].ni = NULL;", release_n)
        sync = fn.index("BUS_DMASYNC_POSTWRITE")
        unload = fn.index("bus_dmamap_unload(", sync)
        assert sync < unload < release_m < release_n < clear_n, label
        assert "KASSERT(" in fn and "ni == NULL" in fn, label
    assert "slot->map == NULL || slot->map->dm_nsegs != 1" in r

contract(enq, rec, fre, res, dep)
mutants = (
    (enq.replace("ni == NULL ||", "false ||", 1), rec, fre, res, dep),
    (enq.replace("slot->ni = ni;", "", 1), rec, fre, res, dep),
    (enq.replace("slot->m != NULL || slot->ni != NULL",
                 "slot->m != NULL", 1), rec, fre, res, dep),
    (enq, rec.replace("ieee80211_free_node(slot->ni);", "", 1), fre, res, dep),
    (enq, rec.replace("slot->ni = NULL;", "", 1), fre, res, dep),
    (enq, rec, fre.replace("ieee80211_free_node(ring->slot[i].ni);", "", 1), res, dep),
    (enq, rec, fre, res.replace("ieee80211_free_node(ring->slot[i].ni);", "", 1), dep),
    (enq, rec, fre, res, dep.replace("qid, m, ni, p, command", "qid, m, p, command", 1)),
)
for i, mutant in enumerate(mutants, 1):
    assert mutant != (enq, rec, fre, res, dep), i
    try:
        contract(*mutant)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe TX node owner mutation {i} accepted")

# The production queue preflight rejects command/unsupported queues before
# accessing DMA; C11 executes the exact source body, not an imitation.
prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#define RTWN8723BE_BK_QUEUE 0
#define RTWN8723BE_BE_QUEUE 1
#define RTWN8723BE_VI_QUEUE 2
#define RTWN8723BE_VO_QUEUE 3
#define RTWN8723BE_BEACON_QUEUE 4
#define RTWN8723BE_MGNT_QUEUE 6
#define RTWN8723BE_HIGH_QUEUE 7
#define RTWN8723BE_TX_FW_BK 2
#define RTWN8723BE_TX_FW_BE 0
#define RTWN8723BE_TX_FW_VI 5
#define RTWN8723BE_TX_FW_VO 7
#define RTWN8723BE_TX_FW_MGNT 18
#define RTWN8723BE_TX_FW_HIGH 17
'''
tail = r'''
int main(void) {
    assert(r23be_tx_queue_check(2,5,false)==0);
    assert(r23be_tx_queue_check(2,0,false)==EINVAL);
    assert(r23be_tx_queue_check(2,5,true)==EOPNOTSUPP);
    assert(r23be_tx_queue_check(4,0,false)==EOPNOTSUPP);
    assert(r23be_tx_queue_check(5,0,false)==EINVAL);
    puts("RTL_TX_NODE_QUEUE_GUARD_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-txnode-") as td:
    src = Path(td) / "test.c"
    exe = Path(td) / "test"
    src.write_text(prefix + "\nstatic int\n" + queue + "\n" + tail)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all", str(src), "-o", str(exe)],
                   check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_TX_NODE_OWNER_SOURCE_MUTATIONS_OK negatives=8")
