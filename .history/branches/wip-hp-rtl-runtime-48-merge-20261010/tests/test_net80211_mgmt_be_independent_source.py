#!/usr/bin/env python3
"""Source-only MGNT/BE admission separation regression.

Frozen RTL reference: torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab
drivers/net/wireless/realtek/rtlwifi/pci.c, rtl_pci_tx(): the selected
hw_queue indexes an independent hardware descriptor ring. NetBSD 11 has one
IFF_OACTIVE bit shared by ic_mgtq and if_snd.

This is NOT a native kernel compile or a physical backpressure/air test.
"""
from pathlib import Path
import re
from itertools import product

ROOT = Path(__file__).resolve().parents[1]


def body(source, function):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    match = re.search(r"\n" + function + r"\([^;]+?\n\{(.*?)\n\}", source, re.S)
    assert match is not None, function
    return match.group(1)


def contract(n80211, tx):
    ifstart = body(n80211, "rtwn8723be_n80211_ifstart")
    start = body(tx, "rtwn8723be_net80211_tx_start")

    if "if (n == NULL || !n->registered ||" not in ifstart:
        return False
    if "(ifp->if_flags & IFF_RUNNING) == 0" not in ifstart:
        return False
    if "n->methods.tx_start == NULL" not in ifstart:
        return False
    if ("if ((ifp->if_flags & IFF_OACTIVE) != 0 &&\n"
            "        n->sc->sc_ic.ic_mgtq.ifq_head == NULL)" not in ifstart):
        return False
    if "n->methods.tx_start(n->sc, ifp);" not in ifstart:
        return False
    if "IFF_RUNNING | IFF_OACTIVE" in ifstart:
        return False

    start_guard = (
        "if (!tx->enabled || (ifp->if_flags & IFF_RUNNING) == 0 ||\n"
        "        ((ifp->if_flags & IFF_OACTIVE) != 0 &&\n"
        "         ic->ic_mgtq.ifq_head == NULL))"
    )
    if start_guard not in start or "mutex_enter(&tx->producer_lock);" not in start:
        return False
    if start.index("mutex_enter(&tx->producer_lock);") > start.index(start_guard):
        return False
    if "IFF_RUNNING | IFF_OACTIVE" in start:
        return False

    try:
        admission = start.split("for (;;) {", 1)[1].split(
            "special_kind = RTWN8723BE_TX_SPECIAL_NONE;", 1)[0]
        order = [
            admission.index("if (ic->ic_mgtq.ifq_head != NULL)"),
            admission.index("rtwn8723be_datapath_tx_check(tx->dp,\n"
                            "                RTWN8723BE_MGNT_QUEUE);"),
            admission.index("else {"),
            admission.index("if (ic->ic_state != IEEE80211_S_RUN)"),
            admission.index("rtwn8723be_datapath_tx_check(tx->dp,\n"
                            "                RTWN8723BE_BE_QUEUE);"),
            admission.index("if (error != 0) {"),
        ]
    except (IndexError, ValueError):
        return False
    if order != sorted(set(order)):
        return False
    # Never dequeue while the selected ring has not passed the gate.
    if admission.find("IF_DEQUEUE(") >= 0 or admission.find("IFQ_DEQUEUE(") >= 0:
        return False
    return True


n80211 = (ROOT / "src/rtwn8723be_net80211.c").read_text()
tx = (ROOT / "src/rtwn8723be_net80211_tx.c").read_text()
assert contract(n80211, tx), "MGNT must not depend on BE ring/OACTIVE"

start = body(tx, "rtwn8723be_net80211_tx_start")
admission_start = start.split("for (;;) {", 1)[1].split(
    "special_kind = RTWN8723BE_TX_SPECIAL_NONE;", 1)[0]

# Fully enumerated behavioral policy, distinct from source assertions above.
cases = 0
recovered_mgmt = 0
for running, enabled, oactive, mgmt_pending, mgmt_free, be_free in product(
        (False, True), repeat=6):
    can_start = running and enabled and (not oactive or mgmt_pending)
    selected = ("MGNT" if mgmt_pending else "BE") if can_start else None
    accepted = can_start and (mgmt_free if mgmt_pending else be_free)
    # Former policy had a global IFF_OACTIVE gate and checked both rings.
    old_accepted = (running and enabled and not oactive and
                    mgmt_free and be_free)
    if running and enabled and mgmt_pending and mgmt_free:
        assert accepted and selected == "MGNT"  # BE cannot block MGNT.
        if not old_accepted:
            recovered_mgmt += 1
    if oactive and not mgmt_pending:
        assert not accepted
    if not running or not enabled:
        assert not accepted
    cases += 1
assert recovered_mgmt == 3  # BE full (two OACTIVE states), or stale OACTIVE.
mutations = [
    (n80211, tx.replace("if (ic->ic_mgtq.ifq_head != NULL)",
                       "if (ic->ic_mgtq.ifq_head == NULL)", 1)),
    (n80211, tx.replace("RTWN8723BE_MGNT_QUEUE);\n        else {",
                       "RTWN8723BE_BE_QUEUE);\n        else {", 1)),
    (n80211, tx.replace("RTWN8723BE_BE_QUEUE);\n        }\n        if (error != 0)",
                       "RTWN8723BE_MGNT_QUEUE);\n        }\n        if (error != 0)", 1)),
    (n80211, tx.replace("ic->ic_mgtq.ifq_head == NULL))",
                       "ic->ic_mgtq.ifq_head != NULL))", 1)),
    (n80211.replace("n->sc->sc_ic.ic_mgtq.ifq_head == NULL)",
                    "n->sc->sc_ic.ic_mgtq.ifq_head != NULL)", 1), tx),
    (n80211, tx.replace("if (ic->ic_state != IEEE80211_S_RUN)",
                       "if (ic->ic_state == IEEE80211_S_RUN)", 1)),
    (n80211, tx.replace("if (!tx->enabled || (ifp->if_flags & IFF_RUNNING) == 0 ||",
                       "if (!tx->enabled ||", 1)),
]
for i, (bad_n80211, bad_tx) in enumerate(mutations):
    assert (bad_n80211, bad_tx) != (n80211, tx), i
    assert not contract(bad_n80211, bad_tx), i

assert "rtwn8723be_datapath_tx_check(tx->dp, RTWN8723BE_MGNT_QUEUE);" not in admission_start
assert "rtwn8723be_datapath_tx_check(tx->dp, RTWN8723BE_BE_QUEUE);" not in admission_start
print(f"NET80211_MGMT_BE_INDEPENDENT_SOURCE_OK: {cases} policy combinations; "
      f"{len(mutations)} rejected mutations; {recovered_mgmt} recovered MGNT cases; native hardware NOT_RUN")
