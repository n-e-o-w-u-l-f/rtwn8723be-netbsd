#!/usr/bin/env python3
"""A failed policy setup must not publish a partial net80211 owner."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "src" / "rtwn8723be_net80211.c").read_text()
PREFIX = "rtwn8723be_net80211_register(struct rtwn8723be_net80211 *n,"
SUFFIX = "\nint\nrtwn8723be_net80211_unregister"

assert PREFIX in TEXT, "net80211 registration entry missing"
body = TEXT.split(PREFIX, 1)[1]
assert SUFFIX in body, "net80211 registration boundary missing"
body = body.split(SUFFIX, 1)[0]

ordered = (
    "error = rtwn8723be_netbsd_apply_world_regdomain(sc);",
    "if (error != 0)\n        return error;",
    "sc->sc_security_policy_valid = false;",
    "n->sc = sc;",
    "n->methods = *methods;",
)
positions = [body.find(token) for token in ordered]
assert all(pos >= 0 for pos in positions), "missing policy/publication step"
assert positions == sorted(positions), (
    "fallible policy setup publishes partial net80211 state")

print("RTL_NET80211_UNPUBLISHED_REGISTRATION_GUARD_OK")
