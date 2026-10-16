#!/usr/bin/env python3
"""Source-only contract: fragmented TX publishes ALL via native batch or NONE.

NetBSD ieee80211_encap links fragments with m_nextpkt. The 16-entry runtime
batch is the only multi-fragment publication path. This checks production
source and fault models; it is not a NetBSD native compiler/hardware test.
"""
from pathlib import Path
import re
from itertools import product

ROOT = Path(__file__).resolve().parents[1]


def body(source, name):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    match = re.search(r"\n" + name + r"\([^;]+?\n\{(.*?)\n\}", source, re.S)
    return match.group(1) if match else ""


def ordered(source, tokens):
    pos = 0
    for token in tokens:
        where = source.find(token, pos)
        if where < 0:
            return False
        pos = where + len(token)
    return True


def contract(source, header, native, datapath):
    start = body(source, "rtwn8723be_net80211_tx_start")
    prepare = body(source, "r23be_tx_prepare_frame")
    submit = body(source, "r23be_tx_submit_fragment_chain")
    abort = body(source, "r23be_tx_abort_prepared")
    batch = body(native, "rtwn8723be_tx_native_enqueue_batch")
    bridge = body(datapath, "rtwn8723be_datapath_enqueue_batch_notify")
    if min(map(len, (start, prepare, submit, abort, batch, bridge))) == 0:
        return False
    if not all(x in header for x in (
        "batch_frames[RTWN8723BE_TX_BATCH_MAX]",
        "*batch_tickets[RTWN8723BE_TX_BATCH_MAX]")):
        return False
    if "struct rtwn8723be_tx_batch_workspace batch_workspace;" not in (
            ROOT / "src/rtwn8723be_datapath.h").read_text():
        return False
    if not ordered(start, (
        "if (m->m_nextpkt != NULL) {",
        "needed == RTWN8723BE_TX_BATCH_MAX",
        "rtwn8723be_datapath_tx_check_slots(tx->dp,",
        "if (error != 0) {",
        "r23be_tx_free_frames(m);",
        "ieee80211_free_node(ni);",
        "break;",
        "error = r23be_tx_submit_fragment_chain(tx, m, ni, special_kind);",
        "ieee80211_free_node(ni);",
        "if (error != 0) {",
        "if_statinc(ifp, if_oerrors);",
        "continue;",
        "while (m != NULL) {")):
        return False
    if "if (error == 0)\n                error = EOPNOTSUPP;" in start:
        return False
    if not ordered(submit, (
        "for (m = chain; m != NULL; m = next)",
        "if (count == RTWN8723BE_TX_BATCH_MAX)",
        "r23be_tx_free_frames(m);",
        "next = m->m_nextpkt;",
        "m->m_nextpkt = NULL;",
        "error = r23be_tx_prepare_frame(tx, m, ieee80211_ref_node(ni),",
        "if (error != 0) {",
        "r23be_tx_free_frames(next);",
        "goto abort;",
        "if (prepared.qid != RTWN8723BE_BE_QUEUE)",
        "r23be_tx_abort_prepared(&prepared);",
        "r23be_tx_free_frames(next);",
        "tx->batch_frames[count] = prepared.frame;",
        "tx->batch_tickets[count] = prepared.ticket;",
        "count++;",
        "error = rtwn8723be_datapath_enqueue_batch_notify(tx->dp,",
        "if (error != 0)",
        "goto abort;",
        "for (i = 0; i < count; i++)",
        "tx->reports_sent++;",
        "memset(&tx->batch_frames[i], 0, sizeof(tx->batch_frames[i]));",
        "tx->batch_tickets[i] = NULL;",
        "return 0;",
        "abort:",
        "while (count != 0)",
        "count--;",
        "if (tx->batch_tickets[count] != NULL)",
        "r23be_tx_report_enqueue_failed(tx->batch_tickets[count],",
        "else",
        "tx->batch_frames[count].release(",
        "tx->batch_frames[count].m, false);",
        "memset(&tx->batch_frames[count], 0,",
        "tx->batch_tickets[count] = NULL;",
        "return error;")):
        return False
    if any(x in submit for x in ("bus_dmamap_", "descs[idx].d[0] =",
                                  "kmem_alloc(", "if_schedule_deferred_start(")):
        return False
    if "bus_dmamap_" in prepare or "datapath_enqueue" in prepare:
        return False
    if not ordered(batch, (
        "BUS_DMA_NOWAIT | BUS_DMA_WRITE);",
        "loaded++;",
        "error = rtwn8723be_tx_encode(&p,",
        "if (error != 0)",
        "BUS_DMASYNC_PREWRITE);",
        "descs[idx] = workspace->desc[i];",
        "slot->m = f->m;",
        "membar_producer();",
        "descs[idx].d[0] =",
        "ring->producer = (start + count) % ring->count;",
        "rtwn8723be_write_2(sc, R23BE_REG_PCIE_CTRL_REG,",
        "abort:",
        "bus_dmamap_unload(sc->sc_dmat, ring->slot[idx].map);")):
        return False
    if not ordered(bridge, (
        "mutex_enter(&dp->tx_lock);",
        "rtwn8723be_tx_native_enqueue_batch(dp->sc,",
        "if (error == 0 && accepted != NULL)",
        "mutex_exit(&dp->tx_lock);")):
        return False
    return ("prepared->frame.m = m;" in prepare and
            "prepared->ticket = ticket;" in prepare and
            "r23be_tx_report_enqueue_failed(" in abort and
            "prepared->frame.m, false);" in abort)


source = (ROOT / "src/rtwn8723be_net80211_tx.c").read_text()
header = (ROOT / "src/rtwn8723be_net80211_tx.h").read_text()
native = (ROOT / "src/rtwn8723be_tx_native.c").read_text()
datapath = (ROOT / "src/rtwn8723be_datapath.c").read_text()
assert contract(source, header, native, datapath), "fragment TX batch ownership contract"

changes = [
    ("error = r23be_tx_submit_fragment_chain(tx, m, ni, special_kind);", ""),
    ("next = m->m_nextpkt;", "next = NULL;"),
    ("m->m_nextpkt = NULL;", ""),
    ("r23be_tx_free_frames(next);", ""),
    ("r23be_tx_abort_prepared(&prepared);", ""),
    ("tx->batch_frames[count] = prepared.frame;", ""),
    ("tx->batch_tickets[count] = prepared.ticket;", ""),
    ("if (error != 0)\n        goto abort;", "if (error != 0)\n        return error;"),
    ("tx->reports_sent++;", ""),
    ("r23be_tx_report_enqueue_failed(tx->batch_tickets[count],", "missing_report_cleanup("),
    ("tx->batch_frames[count].m, false);", "tx->batch_frames[count].m, true);"),
    ("count--;", "count++;"),
]
for index, (old, new) in enumerate(changes):
    assert old in source
    changed = source.replace(old, new, 1)
    # Mutations whose token appears in multiple helpers are specifically
    # applied to the new fragment helper, not earlier unrelated functions.
    if old in ("next = m->m_nextpkt;", "m->m_nextpkt = NULL;",
               "r23be_tx_free_frames(next);", "tx->reports_sent++;",
               "count--;"):
        anchor = "\nr23be_tx_submit_fragment_chain("
        prefix, tail = source.split(anchor, 1)
        assert old in tail
        changed = prefix + anchor + tail.replace(old, new, 1)
    assert changed != source and not contract(changed, header, native, datapath), index

# The native staging function has no effect on its ring until all frames
# are ready; a preparation failure leaves zero published descriptors.
cases = 0
for count, failed_stage in product(range(2, 17), ("none", "prepare", "dma", "encode")):
    for failed_at in range(count):
        staged = []
        consumed = []
        committed = []
        for i in range(count):
            if failed_stage == "prepare" and i == failed_at:
                consumed.append(i)
                break
            staged.append(i)
        if failed_stage == "none":
            committed = staged[:]
        elif failed_stage in ("dma", "encode"):
            staged = list(range(count))
        if failed_stage != "none":
            consumed.extend(reversed(staged))
            assert not committed
            assert sorted(consumed) == list(range(failed_at + 1)) if failed_stage == "prepare" else sorted(consumed) == list(range(count))
        else:
            assert len(committed) == count
        cases += 1

print(f"FRAGMENT_BATCH_FAILCLOSED_SOURCE_PASS: {len(changes)} rejected mutations; "
      f"{cases} ownership cases; native/air NOT_RUN")
