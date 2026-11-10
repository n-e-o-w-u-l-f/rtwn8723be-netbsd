#!/usr/bin/env python3
"""Genuine registration retains stable per-softc and private bridge storage.

These source contracts preserve the ownership and reverse-unwind boundary.
The forward callback is real, while the early native gate still rejects
incomplete providers before PCI effects. No hardware is executed here.
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

# The real callback must retain structural admission before PCI effects.
OPS = NETBSD_C.split("const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops", 1)[1]
assert ".register_ieee80211 = rtwn8723be_netbsd_register_ieee80211," in OPS
for name in ("bt_prepare", "dm_init"):
    assert "." + name + " = rtwn8723be_netbsd_" + name + "," in OPS
ATTACH = NATIVE_C.split("rtwn8723be_native_attach(", 1)[1]
assert ATTACH.index("rtwn8723be_runtime_probe_ready(sc)") < ATTACH.index(
    "pci_get_powerstate(") < ATTACH.index("rtwn8723be_linux_probe(")
OWNER_H = (SRC / "rtwn8723be_runtime_owner.h").read_text()
OWNER_C = (SRC / "rtwn8723be_runtime_owner.c").read_text()
assert "struct rtwn8723be_runtime_context *context;" in OWNER_H
assert "struct rtwn8723be_rx_binding rx;" in OWNER_C
assert "struct rtwn8723be_datapath dp;" in OWNER_C
assert "created = kmem_zalloc(sizeof(*created), KM_NOSLEEP);" in OWNER_C
assert "rtwn8723be_net80211_register(&sc->sc_net80211, sc, &methods)" in OWNER_C
assert ".init_rfkill = rtwn8723be_netbsd_init_rfkill," in NETBSD_C
assert "rtwn8723be_netbsd_init_rfkill(void *arg)" in NETBSD_C
assert "sc->sc_net80211.sc != sc" in NETBSD_C
assert "rtwn8723be_net80211_register(" not in NATIVE_C
# An unstarted registered interface now has a real, bounded reverse owner.
# Forward registration is brokered by the persistent runtime owner; it
# does not remove this reverse owner or authorize physical WLAN operation.
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
# The attachment still delegates framework registration through its owner;
# no direct registration or speculative hardware start is inserted here.
assert "rtwn8723be_net80211_register(" not in NATIVE_C

print("RTL_NET80211_OWNER_STORAGE_CONTRACT_OK")
