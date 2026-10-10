#!/usr/bin/env python3
"""Static regression for the NetBSD RTL native pre-registration resource order.

Run on HP NetBSD for integration verification. This does not prove PCI
attach, hardware reception, firmware, WPA2, or complete Linux parity.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
netbsd = (SRC / "rtwn8723be_netbsd.c").read_text()
native = (SRC / "rtwn8723be_native.c").read_text()
runtime = (SRC / "rtwn8723be_runtime.c").read_text()

def cut(text, first, last):
    start = text.index(first)
    end = text.index(last, start + len(first))
    return text[start:end]

sw = cut(netbsd, "rtwn8723be_netbsd_init_sw_vars(void *arg)", "rtwn8723be_netbsd_init_leds(void *arg)")
assert sw.index("rtwn8723be_h2c_native_init(sc)") < sw.index(
    "rtwn8723be_btc_mp_native_init(sc)") < sw.index("rtwn8723be_runtime_init(sc)")
assert "if (error != 0)" in sw
assert "rtwn8723be_btc_mp_native_fini(sc)" in sw
assert "rtwn8723be_h2c_native_fini(sc)" in sw

cleanup = cut(native, "rtwn8723be_native_probe_cleanup(struct rtwn8723be_softc *sc)",
              "rtwn8723be_native_detach(device_t self, int flags)")
need = (
    "if (stage >= R23BE_STAGE_IEEE80211_REGISTER)",
    "rtwn8723be_netbsd_disestablish_irq(sc)",
    "rtwn8723be_runtime_fini(sc)",
    "rtwn8723be_btc_mp_native_fini(sc)",
    "rtwn8723be_h2c_native_fini(sc)",
    "rtwn8723be_netbsd_free_pci_rings(sc)",
    "rtwn8723be_netbsd_dma_release(sc)",
    "bus_space_unmap(sc->sc_st, sc->sc_sh, sc->sc_mapsize)",
    "rtwn8723be_netbsd_context_fini(sc)",
)
assert all(s in native for s in need), "Missing required rollback stage"
# context_fini happens in the caller only after native_probe_cleanup
for first, second in zip(need[1:-1], need[2:-1]):
    assert cleanup.index(first) < cleanup.index(second), (first, second)
assert cleanup.index(need[0]) < cleanup.index(need[1])
assert "if (sc->sc_runtime != NULL && rtwn8723be_runtime_fini(sc) != 0)" in cleanup
assert "if (sc->sc_linux.stage == R23BE_STAGE_IDLE" in native

assert "KASSERT(sc->sc_irq_lock_initialized);" in runtime
assert "mutex_init(&sc->sc_irq_lock" not in runtime
assert "mutex_destroy(&sc->sc_irq_lock" not in runtime
print("RTL_RUNTIME_SW_OWNER_ORDER_SOURCE_PASS")
