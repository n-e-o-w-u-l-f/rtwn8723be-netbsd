#!/usr/bin/env python3
"""Prevent partial MSDU publication; source-only, no compiler/hardware."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def contract(source):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    start = source.split("\nrtwn8723be_net80211_tx_start(", 1)[1]
    prefix, fragments = start.split("if (m->m_nextpkt != NULL) {", 1)
    gate, publish = fragments.split("while (m != NULL) {", 1)
    required = [
        "error = rtwn8723be_datapath_tx_check_slots(tx->dp,",
        "if (error == 0)\n                error = EOPNOTSUPP;",
        "if (error != 0) {", "r23be_tx_free_frames(m);",
        "ieee80211_free_node(ni);", "if_statinc(ifp, if_oerrors);",
        "if (error == EBUSY)", "ifp->if_flags |= IFF_OACTIVE;",
    ]
    positions = [gate.find(x) for x in required]
    return (min(positions) >= 0 and positions == sorted(set(positions))
            and gate.rfind("break;") > positions[-1]
            and gate.count("r23be_tx_free_frames(m);") == 1
            and gate.count("ieee80211_free_node(ni);") == 1
            and "EOPNOTSUPP" not in prefix
            and "rtwn8723be_net80211_tx_frame(" not in prefix + gate
            and "rtwn8723be_net80211_tx_frame(" in publish)


source = (ROOT / "src/rtwn8723be_net80211_tx.c").read_text()
assert contract(source), "successful slot check must not authorize partial fragment publication"
guard = "if (error == 0)\n                error = EOPNOTSUPP;"
prefix, tail = source.split("if (m->m_nextpkt != NULL) {", 1)
mutations = [tail.replace(guard, "", 1),
             tail.replace(guard, "/* " + guard + " */", 1),
             tail.replace(guard, guard.replace("== 0", "!= 0"), 1),
             tail.replace("error = EOPNOTSUPP;", "error = 0;", 1),
             tail.replace("r23be_tx_free_frames(m);", "", 1),
             tail.replace("ieee80211_free_node(ni);", "", 1),
             tail.replace("if (error == EBUSY)", "if (error != 0)", 1)]
for i, mutation in enumerate(mutations):
    assert mutation != tail and not contract(prefix + "if (m->m_nextpkt != NULL) {" + mutation), i
print("FRAGMENT_FAILCLOSED_SOURCE_PASS: no multi-fragment publication; 7 rejected mutations")
