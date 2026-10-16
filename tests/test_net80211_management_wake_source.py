#!/usr/bin/env python3
"""Source contracts for management-only TX wake and lock/lifetime ownership.

No compiler/kernel execution. Frozen NetBSD if_schedule_deferred_start checks
only if_snd; rtwn_softintr instead restarts at splnet after TX reclamation.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def body(source, name):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    match = re.search(r"\n" + name + r"\([^;]+?\n\{(.*?)\n\}", source, re.S)
    return match[1] if match else ""


def contract(source):
    complete = body(source, "rtwn8723be_net80211_tx_complete")
    order = [complete.find(s) for s in (
        "s = splnet();", "mutex_enter(&tx->producer_lock);",
        "if (tx->enabled && (ifp->if_flags & IFF_RUNNING) != 0)",
        "ifp->if_flags &= ~IFF_OACTIVE;",
        "restart_mgt = tx->sc->sc_ic.ic_mgtq.ifq_head != NULL;",
        "if (!restart_mgt)", "if_schedule_deferred_start(ifp);",
        "mutex_exit(&tx->producer_lock);", "if (restart_mgt)",
        "if_start_lock(ifp);", "splx(s);")]
    start = body(source, "rtwn8723be_net80211_tx_start")
    return (min(order) >= 0 and order == sorted(set(order))
            and complete.count("if_start_lock(ifp);") == 1
            and "bool restart_mgt = false;" in complete
            and "if (!tx->enabled ||" in start
            and "(ifp->if_flags & IFF_RUNNING) == 0" in start
            and "ic->ic_mgtq.ifq_head == NULL" in start
            and "if (ic->ic_mgtq.ifq_head != NULL)" in start
            and start.index("mutex_enter(&tx->producer_lock);") < start.index("if (!tx->enabled ||"))


source = (ROOT / "src/rtwn8723be_net80211_tx.c").read_text()
assert contract(source), "management-only wake must bypass if_snd gate after releasing producer lock"
mutations = [
    source.replace("restart_mgt = tx->sc->sc_ic.ic_mgtq.ifq_head != NULL;", "", 1),
    source.replace("ifq_head != NULL", "ifq_head == NULL", 1),
    source.replace("if (restart_mgt)", "if (!restart_mgt)", 1),
    source.replace("if_start_lock(ifp);", "if_schedule_deferred_start(ifp);", 1),
    source.replace("if_start_lock(ifp);", "/* if_start_lock(ifp); */", 1),
    source.replace("bool restart_mgt = false;", "bool restart_mgt = true;", 1),
    source.replace("    if (restart_mgt)\n        if_start_lock(ifp);", "", 1).replace(
        "    mutex_exit(&tx->producer_lock);\n    /*\n     * The deferred helper",
        "    if (restart_mgt)\n        if_start_lock(ifp);\n    mutex_exit(&tx->producer_lock);\n    /*\n     * The deferred helper", 1),
]
for index, mutation in enumerate(mutations):
    assert mutation != source and not contract(mutation), index
dp = body((ROOT / "src/rtwn8723be_datapath.c").read_text(), "rtwn8723be_dp_tx_done")
assert dp.index("mutex_exit(&dp->tx_lock);") < dp.index("dp->tx_complete(dp->tx_complete_arg")
irq = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
assert "softint_establish(SOFTINT_NET," in irq
assert "softint_disestablish(sc->sc_soft_ih);" in body(irq, "rtwn8723be_netbsd_disestablish_irq")
print("NET80211_MANAGEMENT_WAKE_SOURCE_PASS: restart/lock contracts; 7 rejected mutations")
