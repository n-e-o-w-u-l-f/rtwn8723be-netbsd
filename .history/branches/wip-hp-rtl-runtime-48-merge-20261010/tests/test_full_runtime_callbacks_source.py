#!/usr/bin/env python3
"""Static integration gate for RTL8723BE NetBSD Linux-stage callback graph.

Does not certify hardware, regulatory compliance, firmware RF, WPA2 or PM.
Run native HP compiler/kernel tests separately before installing a candidate.
"""
from pathlib import Path
src=Path(__file__).resolve().parents[1]/"src"
net=(src/"rtwn8723be_netbsd.c").read_text()
state=(src/"rtwn8723be_linux_state.c").read_text()
run=(src/"rtwn8723be_runtime.c").read_text()
native=(src/"rtwn8723be_native.c").read_text()
ifnet=(src/"rtwn8723be_net80211.c").read_text()
for mapping in (
    ".register_ieee80211 = rtwn8723be_runtime_register,",
    ".init_rfkill = rtwn8723be_runtime_rfkill_init,",
    ".bt_prepare = rtwn8723be_runtime_bt_prepare,",
    ".bt_hw_init = rtwn8723be_netbsd_bt_hw_runtime_init,",
    ".dm_init = rtwn8723be_runtime_dm_init,",
    ".establish_irq = rtwn8723be_netbsd_establish_irq,",
    ".bt_halt_deinit = rtwn8723be_netbsd_bt_halt_deinit,",
    ".wait_rf_change_idle = rtwn8723be_netbsd_wait_rf_change_idle,",
    ".hw_disable = rtwn8723be_netbsd_hw_disable,",
):
    assert mapping in net, mapping
assert net.index("error = rtwn8723be_netbsd_bt_hw_init(arg);") < net.index(
    "return rtwn8723be_runtime_bt_hw_init(arg);")
# Frozen synchronous BTC initialization executes exactly once; the runtime
# only seeds the already verified firmware generation and DM state.
bt=run[run.index("rtwn8723be_runtime_bt_hw_init(void *arg)"):run.index(
    "rtwn8723be_runtime_dm_init(void *arg)")]
assert "rtwn8723be_runtime_btc_event(sc, R23BE_BTC_INIT_HW" not in bt
assert "rtwn8723be_runtime_btc_event(sc, R23BE_BTC_INIT_DM" not in bt
assert "rtwn8723be_btc_mp_native_activate(sc)" in bt
assert "r->rx_generation = sc->sc_h2c.firmware_generation;" in bt
start=state[state.index("rtwn8723be_linux_adapter_start(void *ctx"):state.index(
    "rtwn8723be_linux_adapter_stop(void *ctx")]
for token in ("ops->reset_trx_ring", "ops->bt_prepare",
              "ops->establish_irq", "rtwn8723be_linux_hw_init",
              "ops->enable_interrupt", "ops->mark_hal_start"):
    assert token in start,token
order = ("ops->reset_trx_ring", "ops->bt_prepare",
         "ops->establish_irq", "rtwn8723be_linux_hw_init",
         "ops->enable_interrupt", "ops->mark_hal_start")
positions = [start.index(name) for name in order]
assert positions == sorted(positions), list(zip(order, positions))
assert "ops->establish_irq == NULL" in state
detach=native[native.index("rtwn8723be_native_detach(device_t self"):native.index(
    "rtwn8723be_native_attach(device_t parent")]
assert "rtwn8723be_runtime_unregister(sc)" in detach
assert "rtwn8723be_native_probe_cleanup(sc)" in detach
assert detach.index("rtwn8723be_runtime_unregister(sc)") < (
    detach.index("rtwn8723be_native_probe_cleanup(sc)"))
assert "sc->sc_runtime->net.registered" in detach
# Under NetBSD splnet IPL, init/stop cannot block in firmware or worker drains.
ioctl=ifnet[ifnet.index("rtwn8723be_n80211_ioctl(struct ifnet *ifp, u_long cmd, void *data)\n{"):ifnet.index(
    "rtwn8723be_n80211_media_change(struct ifnet *ifp)\n{")]
assert ioctl.count("splx(s);\n            error = rtwn8723be_n80211_ifinit(") == 1
assert ioctl.count("splx(s);\n            error = rtwn8723be_n80211_ifstop(") == 2
assert "s = splnet();" in ioctl
print("RTL_LINUX_STAGE_CALLBACKS_AND_IRQ_RESTART_SOURCE_PASS")
