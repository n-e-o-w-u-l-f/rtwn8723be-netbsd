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
):
    assert forbidden not in NETBSD_C, forbidden
assert ".init_rfkill = rtwn8723be_netbsd_init_rfkill," in NETBSD_C
assert "rtwn8723be_netbsd_init_rfkill(void *arg)" in NETBSD_C
assert "sc->sc_net80211.sc != sc" in NETBSD_C
assert "rtwn8723be_net80211_register(" not in NATIVE_C
# An unstarted registered interface now has a real, bounded reverse owner.
# Do not mistake this explicit teardown for binding the forbidden forward
# register_ieee80211 callback or enabling a working ifnet.
assert NATIVE_C.count("rtwn8723be_net80211_unregister(") == 1
owner = NATIVE_C.split("rtwn8723be_native_unwind_net80211(void *arg)", 1)
assert len(owner) == 2
owner = owner[1].split("\n}\n", 1)[0]
assert "error = rtwn8723be_net80211_unregister(&sc->sc_net80211);" in owner
assert "if (error != 0)" in owner
assert "if (sc->sc_net80211.registered || sc->sc_net80211.sc != NULL)" in owner
assert "return EBUSY;" in owner
assert "rtwn8723be_probe_unwind_post_registration(" in NATIVE_C
assert "rtwn8723be_native_post_registration_unwind(sc);" in NATIVE_C
# Both the forward callback and any speculative hardware/network start
# remain excluded from the PCI attachment.
assert "rtwn8723be_net80211_register(" not in NATIVE_C

print("RTL_NET80211_OWNER_STORAGE_CONTRACT_OK")
