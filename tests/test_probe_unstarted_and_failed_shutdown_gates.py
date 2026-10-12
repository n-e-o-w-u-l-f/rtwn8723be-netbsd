#!/usr/bin/env python3
"""Regression guard for pre-start PCI probe rollback and failed DMA rundown.

This is a SOURCE-only validation, not a NetBSD kernel compile, boot, IRQ,
firmware, recovery, RF scan, WPA2 or PM hardware test. Run on the real HP
after synchronizing the WIP branch before promoting a candidate kernel.
"""
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "src"
runtime = (src / "rtwn8723be_runtime.c").read_text()
native = (src / "rtwn8723be_native.c").read_text()
net = (src / "rtwn8723be_net80211.c").read_text()

stop = runtime.split("rtwn8723be_runtime_stop(struct rtwn8723be_softc *sc)", 1)[1]
stop = stop.split("rtwn8723be_runtime_unregister(struct rtwn8723be_softc *sc)", 1)[0]
prestart = stop.split("Probe registers net80211 before RFkill", 1)[1]
prestart = prestart.split("if (!sc->sc_linux.started &&", 2)[1]

for stage in (
    "R23BE_STAGE_IEEE80211_REGISTER",
    "R23BE_STAGE_RFKILL",
    "R23BE_STAGE_IRQ_ESTABLISH",
    "R23BE_STAGE_PROBED",
):
    assert stage in prestart, stage

for guard in (
    "!sc->sc_linux.being_init_adapter",
    "!sc->sc_linux.fw_ready",
    "!sc->sc_h2c.state.firmware_ready",
    "!sc->sc_hal_started",
    "!sc->sc_btc.initialized",
    "!sc->sc_irq_enabled",
):
    assert guard in prestart, guard

assert prestart.index("rtwn8723be_netbsd_disestablish_irq(sc);") < (
    prestart.index("return 0;")), "quiesce IRQ even on unstarted PCI probe"
assert "R23BE_STAGE_INIT_MAC" not in prestart.split(
    "rtwn8723be_netbsd_disestablish_irq(sc);", 1)[0]
assert "R23BE_STAGE_STOPPED && r->poweroff_verified" in stop
assert "r->mcu_rx_drained && !sc->sc_btc.initialized" in stop

unregister = runtime.split(
    "rtwn8723be_runtime_unregister(struct rtwn8723be_softc *sc)", 1)[1]
unregister = unregister.split("static int\nruntime_queue(", 1)[0]
assert "error = rtwn8723be_runtime_stop(sc);" in unregister
assert "if (error != 0)\n        return error;" in unregister, (
    "failed DMA/MP/BTC teardown must NOT detach net80211")
assert "if (error != 0 && !r->poweroff_verified)" not in unregister
assert unregister.index("if (error != 0)\n        return error;") < (
    unregister.index("rtwn8723be_net80211_unregister(&r->net)"))

cleanup = native.split(
    "rtwn8723be_native_probe_cleanup(struct rtwn8723be_softc *sc)", 1)[1]
cleanup = cleanup.split("rtwn8723be_native_detach(device_t self", 1)[0]
assert cleanup.index("rtwn8723be_runtime_unregister(sc)") < (
    cleanup.index("rtwn8723be_runtime_fini(sc)"))
assert cleanup.index("rtwn8723be_runtime_fini(sc)") < (
    cleanup.index("rtwn8723be_netbsd_free_pci_rings(sc)"))
assert "if (unregister_error != 0 || sc->sc_runtime->net.registered)" in cleanup

ifstop = net.split("rtwn8723be_n80211_ifstop(struct rtwn8723be_net80211 *n)", 1)[1]
ifstop = ifstop.split("rtwn8723be_n80211_ifstart(struct ifnet *ifp)", 1)[0]
for stage in (
    "R23BE_STAGE_IEEE80211_REGISTER",
    "R23BE_STAGE_RFKILL",
    "R23BE_STAGE_IRQ_ESTABLISH",
    "R23BE_STAGE_PROBED",
):
    assert stage in ifstop
assert "return EBUSY; /* An interrupted stop needs explicit recovery. */" in ifstop
# A successful STOPPED generation owns NO hard/soft PCI IRQ handles.
# Requiring a live hard IRQ in if_init would reject every clean restart.
ifinit = net.split("static int\nrtwn8723be_n80211_ifinit(struct ifnet *ifp)", 1)[1]
ifinit = ifinit.split("static int\nrtwn8723be_n80211_ifstop(", 1)[0]
assert "sc->sc_linux.stage != R23BE_STAGE_PROBED" in ifinit
assert "sc->sc_linux.stage != R23BE_STAGE_STOPPED" in ifinit
assert "!sc->sc_irq_dispatch_ready" in ifinit
assert "!sc->sc_rings_allocated || !sc->sc_mapped" in ifinit
probed = ifinit.split("if (sc->sc_linux.stage == R23BE_STAGE_PROBED) {", 1)[1]
probed, stopped = probed.split("} else {", 1)
stopped = stopped.split("\n    }", 1)[0]
for owner in ("sc->sc_ih", "sc->sc_soft_ih", "sc->sc_pihp"):
    assert owner + " == NULL" in probed, owner
    assert owner + " != NULL" in stopped, owner
assert "sc->sc_irq_enabled" in stopped
assert "return EBUSY;" in stopped

linux = (src / "rtwn8723be_linux_state.c").read_text()
adapter_start = linux.split(
    "rtwn8723be_linux_adapter_start(void *ctx,", 1)[1]
adapter_start = adapter_start.split(
    "rtwn8723be_linux_adapter_stop(void *ctx,", 1)[0]
for callback in ("ops->reset_trx_ring", "ops->bt_prepare",
                 "ops->establish_irq", "ops->enable_interrupt"):
    assert callback in adapter_start
ordering = [adapter_start.index(name) for name in (
    "ops->reset_trx_ring", "ops->bt_prepare",
    "ops->establish_irq", "ops->enable_interrupt")]
assert ordering == sorted(ordering) and len(set(ordering)) == 4

pci = (src / "rtwn8723be_netbsd.c").read_text()
irq_stop = pci.split(
    "rtwn8723be_netbsd_disestablish_irq(struct rtwn8723be_softc *sc)", 1)[1]
irq_stop = irq_stop.split("static void\nrtwn8723be_netbsd_irq_mask_locked", 1)[0]
for owner in ("sc->sc_ih", "sc->sc_soft_ih", "sc->sc_pihp"):
    assert owner + " = NULL;" in irq_stop, owner

print("RTL_NET80211_STOPPED_IRQ_RESTART_OWNER_SOURCE_PASS")

print("RTL_PRESTART_UNREGISTER_AND_SHUTDOWN_FAILURE_SOURCE_PASS")
