#!/usr/bin/env python3
"""NetBSD 11 net80211 detach: sleepable HW stop MUST precede splnet IPL.

Source contract only; this is not a NetBSD object/boot/WLAN/PANIC test.
Freeze the original acceptance against the pinned NetBSD if_rtwn.c lifetime.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "src/rtwn8723be_net80211.c").read_text(encoding="utf-8")
runtime = (ROOT / "src/rtwn8723be_runtime.c").read_text(encoding="utf-8")

def unregister_contract(source: str) -> bool:
    begin = "rtwn8723be_net80211_unregister(struct rtwn8723be_net80211 *n)\n{"
    end = "rtwn8723be_net80211_input("
    if source.count(begin) != 1 or source.count(end) != 1:
        return False
    body = source.split(begin, 1)[1].split(end, 1)[0]
    stop = "error = rtwn8723be_n80211_ifstop(n);"
    raise_ipl = "s = splnet();"
    if body.count(stop) != 1 or body.count(raise_ipl) != 1:
        return False
    if not body.index(stop) < body.index(raise_ipl):
        return False
    if "if (error != 0)\n        return error;" not in body:
        return False
    if not body.index(stop) < body.index("if (error != 0)\n        return error;") < body.index(raise_ipl):
        return False
    for name in ("ieee80211_ifdetach(&n->sc->sc_ic);", "if_detach(ifp);"):
        if body.count(name) != 1:
            return False
        if not body.index(raise_ipl) < body.index(name) < body.index("splx(s);"):
            return False
    if not body.index("ieee80211_ifdetach(&n->sc->sc_ic);") < body.index("if_detach(ifp);"):
        return False
    if body.count("splx(s);") != 1:
        return False
    return True

assert unregister_contract(src), "sleepable HW stop must be outside splnet"
# Negative control reconstructs the older hazardous ordering. The test itself
# must detect the original bug rather than merely assert the new comment.
invalid = src.replace(
    "error = rtwn8723be_n80211_ifstop(n);\n    if (error != 0)\n        return error;",
    "s = splnet();\n    error = rtwn8723be_n80211_ifstop(n);\n    if (error != 0)\n        return error;",
    1,
)
assert invalid != src
assert not unregister_contract(invalid), "unsafe old splnet order was accepted"

unreg = runtime.split(
    "rtwn8723be_runtime_unregister(struct rtwn8723be_softc *sc)\n{", 1
)[1].split("static int\nruntime_queue(", 1)[0]
assert unreg.index("error = rtwn8723be_runtime_stop(sc);") < unreg.index(
    "rtwn8723be_net80211_unregister(&r->net)")
assert "if (error != 0)\n        return error;" in unreg
print("RTL_NETBSD_NET80211_UNREGISTER_SLEEPABLE_IPL_SOURCE_PASS")
