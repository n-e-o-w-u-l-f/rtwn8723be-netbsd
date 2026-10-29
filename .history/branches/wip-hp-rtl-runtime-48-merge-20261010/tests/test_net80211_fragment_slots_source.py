#!/usr/bin/env python3
"""Bounded source-only fragment slot admission and owner regression.

NetBSD11 ieee80211_fragment() returns m_nextpkt-fragment chains. The real
DMA owner may still fail after the preflight, so this is NOT an atomic map
or a kernel/hardware test. Compiler-invoking tests remain HP-only.
"""
from pathlib import Path
from itertools import product
import re

ROOT = Path(__file__).resolve().parents[1]


def body(source, name):
    cleaned = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    match = re.search(r"\n" + name + r"\([^;]+?\n\{(.*?)\n\}", cleaned, re.S)
    assert match is not None, name
    return match.group(1)


def contract(datapath, header, producer):
    if ("int rtwn8723be_datapath_tx_check_slots(struct rtwn8723be_datapath *,"
            not in header):
        return False
    gate = body(datapath, "rtwn8723be_datapath_tx_check_slots")
    start = body(producer, "rtwn8723be_net80211_tx_start")
    if "if (dp == NULL || !dp->prepared || dp->sc == NULL ||" not in gate:
        return False
    guard = (
        "if (!dp->tx_enabled || !dp->sc->sc_linux.started ||\n"
        "        !dp->sc->sc_linux.fw_ready)"
    )
    if guard not in gate or "else if (needed > ring->count)" not in gate:
        return False
    slots = (
        "if (ring->slot[idx].m != NULL)",
        "error = EBUSY;",
        "idx++;",
        "if (idx == ring->count)",
        "idx = 0;",
    )
    if not all(token in gate for token in slots):
        return False
    if not (gate.index("mutex_enter(&dp->tx_lock);") <
            gate.index("if (ring->slot[idx].m != NULL)") <
            gate.index("mutex_exit(&dp->tx_lock);")):
        return False
    # Native enqueue rejects a hardware-owned descriptor even if its
    # mbuf slot appears empty. Preflight must use identical DMA sync/OWN
    # checks for *every* candidate slot before the first fragment.
    own_sequence = (
        "if (ring->slot[idx].m != NULL)",
        "if (ring->slot[idx].map == NULL)",
        "offset = (bus_size_t)idx * sizeof(*descs);",
        "rtwn8723be_f16_1_dma_sync_for_cpu(dp->sc->sc_dmat,",
        "if ((le32toh(descs[idx].d[0]) & R23BE_TXD0_OWN) != 0)",
        "error = EBUSY;",
        "rtwn8723be_f16_1_dma_sync_for_device(dp->sc->sc_dmat,",
        "if (error != 0)",
        "idx++;",
    )
    if not all(token in gate for token in own_sequence):
        return False
    search_from = 0
    for token in own_sequence:
        where = gate.find(token, search_from)
        if where < 0:
            return False
        search_from = where + len(token)
    dma_guards = (
        "!dp->sc->sc_mapped", "!dp->sc->sc_rings_allocated",
        "dp->sc->sc_dmat == NULL", "!dp->sc->sc_dma_32bit",
        "ring->desc_dma.kva == NULL", "ring->desc_dma.map == NULL",
        "ring->desc_dma.size < (bus_size_t)ring->count *",
        "!rtwn8723be_dma32_range_valid(",
        "else if (needed > ring->count)"
    )
    if not all(x in gate for x in dma_guards):
        return False

    try:
        preflight = start.split("if (m->m_nextpkt != NULL) {", 1)[1].split(
            "while (m != NULL) {", 1)[0]
    except IndexError:
        return False
    conditions = [
        "for (frag = m; frag != NULL; frag = frag->m_nextpkt)",
        "if (needed == tx->sc->sc_tx_ring[RTWN8723BE_BE_QUEUE].count ||",
        "needed == RTWN8723BE_TX_BATCH_MAX)",
        "error = EFBIG;",
        "needed++;",
        "if (error == 0)",
        "error = rtwn8723be_datapath_tx_check_slots(tx->dp,",
        "RTWN8723BE_BE_QUEUE, needed);",
        "if (error != 0) {",
        "r23be_tx_free_frames(m);",
        "ieee80211_free_node(ni);",
        "if_statinc(ifp, if_oerrors);",
        "if (error == EBUSY)",
        "ifp->if_flags |= IFF_OACTIVE;",
        "break;",
    ]
    if not all(token in preflight for token in conditions):
        return False
    order = [preflight.index(x) for x in conditions[:-1]]
    # The bounded-count loop has an earlier break on oversized chains;
    # test the failure-path break separately, after ownership cleanup.
    if order != sorted(set(order)):
        return False
    if preflight.rindex("break;") <= preflight.index(
            "ifp->if_flags |= IFF_OACTIVE;"):
        return False
    if "rtwn8723be_datapath_tx_check_slots(" not in preflight:
        return False
    if start.index("if (m->m_nextpkt != NULL)") > start.index("while (m != NULL)"):
        return False
    if "m->m_nextpkt = NULL;" not in start:
        return False
    if "ieee80211_ref_node(ni), special_kind" not in start:
        return False
    # Independent management admission is not affected by this BE-only check.
    if "if (ic->ic_mgtq.ifq_head != NULL)" not in start:
        return False
    return True


d = (ROOT / "src/rtwn8723be_datapath.c").read_text()
h = (ROOT / "src/rtwn8723be_datapath.h").read_text()
t = (ROOT / "src/rtwn8723be_net80211_tx.c").read_text()
assert contract(d, h, t)

def fragment_mutation(source, old, new):
    """Mutate only the newly added preflight, never earlier TX branches."""
    anchor = "if (m->m_nextpkt != NULL) {"
    assert source.count(anchor) == 1
    prefix, suffix = source.split(anchor, 1)
    assert old in suffix
    return prefix + anchor + suffix.replace(old, new, 1)


mutants = [
    (d, h, t.replace("if (m->m_nextpkt != NULL)", "if (m->m_nextpkt == NULL)", 1)),
    (d, h, fragment_mutation(t,
        "needed == RTWN8723BE_TX_BATCH_MAX)",
        "needed != RTWN8723BE_TX_BATCH_MAX)")),
    (d, h, t.replace("RTWN8723BE_BE_QUEUE, needed);",
                     "RTWN8723BE_MGNT_QUEUE, needed);", 1)),
    (d, h, t.replace("for (frag = m; frag != NULL; frag = frag->m_nextpkt)",
                     "for (frag = m; frag != NULL; frag = frag->m_next)", 1)),
    (d, h, t.replace("r23be_tx_free_frames(m);\n                ieee80211_free_node(ni);",
                     "ieee80211_free_node(ni);", 1)),
    (d, h, fragment_mutation(t,
        "ieee80211_free_node(ni);\n                if_statinc(ifp, if_oerrors);",
        "if_statinc(ifp, if_oerrors);")),
    (d, h, fragment_mutation(t,
        "if (error == EBUSY)\n                    ifp->if_flags |= IFF_OACTIVE;",
        "if (error != EBUSY)\n                    ifp->if_flags |= IFF_OACTIVE;")),
    (d.replace("if (ring->slot[idx].m != NULL)",
               "if (ring->slot[idx].m == NULL)", 1), h, t),
    (d.replace("else if (needed > ring->count)",
               "else if (needed < ring->count)", 1), h, t),
    (d.replace("if (idx == ring->count)", "if (idx != ring->count)", 1), h, t),
    (d, h.replace("int rtwn8723be_datapath_tx_check_slots(", "int missing_check_slots(", 1), t),
    (d.replace("if (ring->slot[idx].map == NULL)",
               "if (ring->slot[idx].map != NULL)", 1), h, t),
    (d.replace("R23BE_TXD0_OWN) != 0)", "R23BE_TXD0_OWN) == 0)", 1), h, t),
    (d.replace("rtwn8723be_f16_1_dma_sync_for_cpu(dp->sc->sc_dmat,",
               "rtwn8723be_f16_1_dma_sync_for_device(dp->sc->sc_dmat,", 1), h, t),
    (d.replace("rtwn8723be_f16_1_dma_sync_for_device(dp->sc->sc_dmat,",
               "rtwn8723be_f16_1_dma_sync_for_cpu(dp->sc->sc_dmat,", 1), h, t),
    (d.replace("ring->desc_dma.map == NULL", "ring->desc_dma.map != NULL", 1), h, t),
]
for i, mutation in enumerate(mutants):
    assert mutation != (d, h, t), i
    assert not contract(*mutation), i

# Portable ring admission model: producer wraparound, every ring shape,
# occupied slots and needed length, plus no-admission after stopped TX.
cases = 0
for size in (2, 4, 8):
    for producer, mask, needed, enabled in product(
            range(size), range(1 << size), range(1, size + 2), (False, True)):
        slots = [(mask & (1 << idx)) != 0 for idx in range(size)]
        expect = (enabled and needed <= size and all(
            not slots[(producer + offset) % size] for offset in range(needed)))
        idx = producer
        accept = enabled and needed <= size
        if accept:
            for _ in range(needed):
                if slots[idx]:
                    accept = False
                    break
                idx = 0 if idx + 1 == size else idx + 1
        assert accept == expect
        cases += 1

print("NET80211_FRAGMENT_SLOTS_SOURCE_PASS: "
      f"{len(mutants)} rejected mutations, {cases} ring model cases; "
      "no native/hardware test")
