#!/usr/bin/env python3
"""Verify resource-unwind fencing for an unstarted RTL net80211 probe.

HP-only C ABI and fault injection are still needed. Source gate prevents
a source regression that frees PCI/DMA while ifnet remains registered.
"""
from pathlib import Path
src=Path(__file__).resolve().parents[1]/"src"
net=(src/"rtwn8723be_net80211.c").read_text()
native=(src/"rtwn8723be_native.c").read_text()
runtime=(src/"rtwn8723be_runtime.c").read_text()
a=native.index("rtwn8723be_native_probe_cleanup(struct rtwn8723be_softc *sc)")
z=native.index("rtwn8723be_native_detach(device_t self, int flags)",a)
cleanup=native[a:z]
for x in ("R23BE_STAGE_IEEE80211_REGISTER", "R23BE_STAGE_RFKILL",
          "R23BE_STAGE_IRQ_ESTABLISH", "R23BE_STAGE_PROBED",
          "R23BE_STAGE_STOPPED"):
    assert x in net, x
assert "!n->sc->sc_linux.started" in net
assert "rtwn8723be_n80211_ifstop(n)" in net
assert "rtwn8723be_runtime_unregister(sc)" in cleanup
assert "sc->sc_runtime->net.registered" in cleanup
assert cleanup.index("rtwn8723be_netbsd_disestablish_irq(sc)") < (
    cleanup.index("rtwn8723be_runtime_unregister(sc)"))
assert cleanup.index("rtwn8723be_runtime_unregister(sc)") < (
    cleanup.index("rtwn8723be_runtime_fini(sc)"))
assert cleanup.index("rtwn8723be_runtime_fini(sc)") < (
    cleanup.index("rtwn8723be_h2c_native_fini(sc)"))
assert cleanup.index("rtwn8723be_h2c_native_fini(sc)") < (
    cleanup.index("rtwn8723be_netbsd_free_pci_rings(sc)"))
assert cleanup.index("rtwn8723be_netbsd_dma_release(sc)") < (
    cleanup.index("bus_space_unmap(sc->sc_st, sc->sc_sh, sc->sc_mapsize)"))
assert "if (sc->sc_linux.stage >= R23BE_STAGE_IEEE80211_REGISTER)" in native, (
    "detach must remain disabled until successful runtime stop/suspend proven"
)
assert "r->net.registered" in runtime and "rtwn8723be_net80211_unregister(&r->net)" in runtime
print("RTL_PRESTART_PROBE_ROLLBACK_SOURCE_PASS")
