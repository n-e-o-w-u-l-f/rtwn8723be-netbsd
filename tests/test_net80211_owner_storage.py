#!/usr/bin/env python3
"""A future net80211 registration needs stable per-softc storage.

This is deliberately a source-contract test.  It proves only the ownership
boundary and preserves the fail-closed probe callback inventory; it does not
make a WLAN interface, touch PCI, or compile a kernel.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
NET80211_H = (SRC / "rtwn8723be_net80211.h").read_text()
NETBSD_H = (SRC / "rtwn8723be_netbsd.h").read_text()
NETBSD_C = (SRC / "rtwn8723be_netbsd.c").read_text()
NATIVE_C = (SRC / "rtwn8723be_native.c").read_text()


# The public net80211 declaration layer must not recursively pull the full
# PCI softc definition.  It needs only the two opaque types used by pointers.
assert '#include "rtwn8723be_netbsd.h"' not in NET80211_H
assert "struct rtwn8723be_softc;" in NET80211_H
assert "struct ifnet;" in NET80211_H

# The complete softc owns exactly one long-lived net80211 registration state.
assert '#include "rtwn8723be_net80211.h"' in NETBSD_H
assert NETBSD_H.count("struct rtwn8723be_net80211 sc_net80211;") == 1

# Storage alone must not weaken the existing fail-closed hardware boundary.
for forbidden in (
        ".register_ieee80211 =",
        ".init_rfkill =",
):
    assert forbidden not in NETBSD_C, forbidden
assert "rtwn8723be_net80211_register(" not in NATIVE_C
assert "rtwn8723be_net80211_unregister(" not in NATIVE_C

print("RTL_NET80211_OWNER_STORAGE_CONTRACT_OK")
