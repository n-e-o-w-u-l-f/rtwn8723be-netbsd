#!/usr/bin/env python3
"""Frame preparation/abort ownership boundaries; no native execution."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def body(source, name):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    match = re.search(r"\n" + name + r"\([^;]+?\n\{(.*?)\n\}", source, re.S)
    return match[1] if match else ""


def ordered(b, tokens):
    end = 0
    for token in tokens:
        pos = b.find(token, end)
        if pos < 0:
            return False
        end = pos + len(token)
    return True


def contract(source):
    prep = body(source, "r23be_tx_prepare_frame")
    abort = body(source, "r23be_tx_abort_prepared")
    send = body(source, "rtwn8723be_net80211_tx_frame")
    if any(t in prep for t in ("datapath_enqueue", "bus_dmamap_", "reports_sent++")):
        return False
    return (ordered(prep, ["memset(prepared, 0, sizeof(*prepared));",
             "ieee80211_crypto_encap(ic, ni, m)", "m = r23be_tx_linearize(m);",
             "ticket = r23be_tx_report_allocate(tx, ni);", "prepared->frame.m = m;",
             "prepared->frame.params = p;", "prepared->ticket = ticket;",
             "return 0;", "fail:", "r23be_tx_free_frames(m);", "ieee80211_free_node(ni);"])
        and "prepared->frame.owner = ticket != NULL ? (void *)ticket : (void *)ni;" in prep
        and "ticket != NULL ? r23be_tx_report_dma_release : r23be_tx_node_release;" in prep
        and ordered(abort, ["if (prepared->frame.m == NULL)", "return;",
             "if (prepared->ticket != NULL)", "r23be_tx_report_enqueue_failed(",
             "else", "prepared->frame.release(", "memset(prepared, 0, sizeof(*prepared));"])
        and "prepared->frame.m, false);" in abort
        and ordered(send, ["error = r23be_tx_prepare_frame(", "if (error != 0)",
             "return error;", "error = rtwn8723be_datapath_enqueue_owned_notify(",
             "if (error != 0) {", "r23be_tx_abort_prepared(&prepared);",
             "return error;", "if (prepared.ticket != NULL)", "tx->reports_sent++;"])
        and send.count("r23be_tx_abort_prepared(") == 1
        and all(t not in send for t in ("m_freem(", "ieee80211_free_node(", "crypto_encap(")))


def mutate_single_frame(source, old, new):
    """The fragment-batch helper now has its own abort; target the single-frame one."""
    marker = "\\nrtwn8723be_net80211_tx_frame("
    # The source string is split at the exact function definition.
    marker = marker.replace("\\\\n", "\\n")
    assert source.count(marker) == 1
    prefix, tail = source.split(marker, 1)
    assert old in tail
    return prefix + marker + tail.replace(old, new, 1)


source = (ROOT / "src/rtwn8723be_net80211_tx.c").read_text()
assert contract(source), "frame preparation must own resources without publishing; abort once"
mutations = [
    source.replace("prepared->frame.m = m;", "", 1),
    source.replace("prepared->ticket = ticket;", "", 1),
    source.replace("prepared->frame.owner = ticket != NULL ? (void *)ticket : (void *)ni;", "prepared->frame.owner = ni;", 1),
    source.replace("prepared->frame.m, false);", "prepared->frame.m, true);", 1),
    mutate_single_frame(source, "r23be_tx_abort_prepared(&prepared);", ""),
    source.replace("if (prepared.ticket != NULL)", "if (prepared.ticket == NULL)", 1),
    source.replace("prepared->frame.params = p;", "prepared->frame.params = p;\n    datapath_enqueue();", 1),
]
for i, mutation in enumerate(mutations):
    assert mutation != source and not contract(mutation), i
print("TX_FRAME_PREPARE_SOURCE_PASS: preparation/abort/publication ownership; 7 mutations")
