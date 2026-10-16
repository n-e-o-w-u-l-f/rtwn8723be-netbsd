#!/usr/bin/env python3
"""Source-only deferred producer lifetime gate; no compiler or hardware.

NetBSD src@03d918f6d0e81fa05b8f1160eca0628ad39988a6 sys/net/if.c
requires initialization before scheduling; if_detach owns destruction.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def body(source, name):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    match = re.search(r"\n" + name + r"\([^;]+?\n\{(.*?)\n\}", source, re.S)
    return match[1] if match else ""


def contract(source, tx):
    register = body(source, "rtwn8723be_net80211_register")
    unregister = body(source, "rtwn8723be_net80211_unregister")
    complete = body(tx, "rtwn8723be_net80211_tx_complete")
    init = "if_deferred_start_init(ifp, NULL);"
    order = [register.find(s) for s in (
        "if_initialize(ifp);", init, "if_register(ifp);", "n->registered = true;")]
    if min(order) < 0 or order != sorted(set(order)) or register.count(init) != 1:
        return False
    order = [unregister.find(s) for s in (
        "error = rtwn8723be_n80211_ifstop(n);", "if (error != 0)",
        "return error;", "if_detach(ifp);", "n->registered = false;")]
    return (min(order) >= 0 and order == sorted(set(order))
            and "if_schedule_deferred_start(ifp);" in complete
            and "if_deferred_start_destroy(" not in source)


source = (ROOT / "src/rtwn8723be_net80211.c").read_text()
tx = (ROOT / "src/rtwn8723be_net80211_tx.c").read_text()
assert contract(source, tx), "deferred TX producer must be initialized before ifnet publication"
init = "if_deferred_start_init(ifp, NULL);"
mutations = [
    source.replace(init, "", 1),
    source.replace(init, "/* " + init + " */", 1),
    source.replace(init, init + "\n    " + init, 1),
    source.replace(init, "", 1).replace("if_initialize(ifp);", init + "\n    if_initialize(ifp);", 1),
    source.replace(init, "", 1).replace("if_register(ifp);", "if_register(ifp);\n    " + init, 1),
    source.replace("if_detach(ifp);", "", 1),
    source.replace("return error; /* Retain registered resources", "/* Retain registered resources", 1),
]
for index, mutation in enumerate(mutations):
    assert mutation != source and not contract(mutation, tx), index
print("NET80211_DEFERRED_START_SOURCE_PASS: lifetime ordering; 7 rejected mutations")
