#!/usr/bin/env python3
"""Source-only NetBSD RTL8723BE order regression against pinned Linux call order.

Frozen reference (manually checked against original on 2026-10-17):
Linux torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab,
rtlwifi/pci.c:rtl_pci_start/stop and rtl8723be/hw.c:rtl8723be_hw_init.
NetBSD source 03d918f6d0e81fa05b8f1160eca0628ad39988a6.

This checks the NetBSD sequence modeled from the original Linux reference.
It does not execute either kernel, validate firmware handshakes, or justify
removing the hardware-dependent RF calibration/poweroff owner gates.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def body(source, function):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    pattern = r"\n" + function + r"\([^;]*?\)\s*\n\{(.*?)\n\}"
    m = re.search(pattern, source, re.S)
    assert m is not None, function
    return m.group(1)


def in_order(source, *tokens):
    last = 0
    for token in tokens:
        pos = source.find(token, last)
        if pos < 0:
            return False
        last = pos + len(token)
    return True


PROBE = (
    "R23BE_STAGE_PCI_ENABLE", "R23BE_STAGE_DMA_CONFIG",
    "R23BE_STAGE_BUS_MASTER", "R23BE_STAGE_SOFTC_ALLOC",
    "R23BE_STAGE_BAR_MAP", "R23BE_STAGE_PCI_D0",
    "R23BE_STAGE_ADAPTER_IDENTIFY", "R23BE_STAGE_IO_INIT",
    "R23BE_STAGE_EEPROM", "R23BE_STAGE_SW_VARS",
    "R23BE_STAGE_LEDS", "R23BE_STAGE_ASPM_INIT",
    "R23BE_STAGE_CORE_INIT", "R23BE_STAGE_PCI_RINGS",
    "R23BE_STAGE_IEEE80211_REGISTER", "R23BE_STAGE_RFKILL",
    "R23BE_STAGE_IRQ_ESTABLISH",
)
# Match Linux rtl8723be_hw_init(): ASMP disable, CR, DMA hang/old state,
# power-on/MAC, firmware, MAC/BB/RF, security, BT, IQK/LCK, DMA, DM.
HW = (
    "ops->disable_aspm", "ops->read_cr", "ops->check_pcie_dma_hang",
    "ops->reset_pcie_interface_dma", "ops->poweroff_adapter",
    "ops->init_mac", "ops->sys_cfg_clear_bit7", "ops->download_firmware",
    "state->fw_ready = true;", "ops->phy_mac_config",
    "ops->rcr_postprocess", "ops->phy_bb_config", "ops->phy_rf_config",
    "ops->rf_channel_state_init", "ops->hw_configure",
    "ops->cam_reset_all", "ops->enable_hw_security",
    "ops->set_mac_address", "ops->enable_aspm_backdoor",
    "ops->enable_aspm", "ops->bt_hw_init", "ops->rf_calibration",
    "ops->set_nav_upper_235", "ops->release_rx_dma",
    "ops->release_pcie_dma", "ops->dm_init",
)
START = (
    "ops->reset_trx_ring", "ops->bt_prepare", "ops->establish_irq",
    "rtwn8723be_linux_hw_init(", "ops->set_retry_limit",
    "ops->enable_interrupt", "ops->init_rx_config",
    "ops->mark_hal_start", "state->stage = R23BE_STAGE_RUNNING;",
    "state->started = true;",
)
STOP = (
    "ops->bt_halt_deinit", "ops->mark_hal_stop",
    "ops->disable_interrupt", "ops->wait_rf_change_idle",
    "ops->hw_disable", "ops->enable_aspm",
    "state->started = false;", "state->fw_ready = false;",
    "state->stage = R23BE_STAGE_STOPPED;",
)
RUN = (
    "rtwn8723be_netbsd_disestablish_irq(sc);",
    "rtwn8723be_btc_mp_native_stop(sc);",
    "rtwn8723be_runtime_io_enter(sc);",
    "rtwn8723be_linux_adapter_start(sc,",
    "rtwn8723be_datapath_start(&r->datapath);",
    "rtwn8723be_net80211_tx_run(&r->tx);",
    "rtwn8723be_btc_native_enable_events(sc);",
    "ieee80211_new_state(&sc->sc_ic, IEEE80211_S_SCAN, -1);",
)
SHUTDOWN = (
    "rtwn8723be_net80211_tx_stop(&r->tx);",
    "rtwn8723be_datapath_stop(&r->datapath);",
    "rtwn8723be_linux_adapter_stop(sc,",
    "rtwn8723be_netbsd_disestablish_irq(sc);",
    "rtwn8723be_netbsd_reset_trx_ring(sc);",
    "rtwn8723be_btc_native_retire(sc);",
)


def contract(linux_state, runtime, calibration, disable):
    try:
        p = body(linux_state, "rtwn8723be_linux_probe")
        h = body(linux_state, "rtwn8723be_linux_hw_init")
        s = body(linux_state, "rtwn8723be_linux_adapter_start")
        t = body(linux_state, "rtwn8723be_linux_adapter_stop")
        r = body(runtime, "rtwn8723be_runtime_start")
        d = body(runtime, "runtime_shutdown")
        c = body(calibration, "cal_native_phase")
        cd = body(disable, "disable_native_phase")
    except AssertionError:
        return False
    return (
        in_order(p, *PROBE)
        and in_order(h, *HW)
        and in_order(s, *START)
        and in_order(t, *STOP)
        and in_order(r, *RUN)
        and in_order(d, *SHUTDOWN)
        # NetBSD's IRQ handler must be re-established after the quiesced
        # ring reset but before firmware/IRQ mask are enabled.
        and in_order(s, "ops->reset_trx_ring", "ops->establish_irq",
                     "ops->enable_interrupt")
        # Enforce real hardware conditions rather than replacing all
        # errors with success or releasing unowned RF resources.
        and in_order(c, "sc->sc_mapped", "sc->sc_core_initialized",
                     "sc->sc_bb_valid", "sc->sc_linux.fw_ready",
                     "sc->sc_rf_path_count == 1U",
                     "sc->sc_linux.stage == R23BE_STAGE_RF_CALIBRATION")
        and in_order(cd, "R23BE_STAGE_STOPPING", "sc->sc_linux.started",
                     "!sc->sc_hal_started", "!sc->sc_irq_enabled",
                     "rtwn8723be_netbsd_rf_change_owned(sc)")
        and "R23BE_STAGE_RUNNING" in body(linux_state,
                                         "rtwn8723be_linux_adapter_start")
    )


state = (ROOT / "src/rtwn8723be_linux_state.c").read_text()
runtime = (ROOT / "src/rtwn8723be_runtime.c").read_text()
cal = (ROOT / "src/rtwn8723be_calibration_native.c").read_text()
disable = (ROOT / "src/rtwn8723be_hw_disable_native.c").read_text()
assert contract(state, runtime, cal, disable), (
    "Linux-reference sequence/NetBSD hardware-owner contract changed"
)

mutations = [
    (state.replace("R23BE_STAGE_PCI_RINGS, ops->init_pci_rings",
                   "R23BE_STAGE_PCI_RINGS, missing_pci_rings"), runtime, cal, disable),
    (state.replace("ops->download_firmware, ctx",
                   "missing_fw_download, ctx"), runtime, cal, disable),
    (state.replace("ops->phy_bb_config, ctx",
                   "missing_phy_bb, ctx"), runtime, cal, disable),
    (state.replace("ops->rf_calibration, ctx",
                   "missing_calibration, ctx"), runtime, cal, disable),
    (state.replace("ops->enable_interrupt, ctx",
                   "missing_interrupt_enable, ctx"), runtime, cal, disable),
    (state.replace("ops->hw_disable, ctx",
                   "missing_stop_poweroff, ctx"), runtime, cal, disable),
    (state, runtime.replace("rtwn8723be_btc_native_enable_events(sc)",
                            "missing_btc_ready(sc)"), cal, disable),
    (state, runtime.replace("rtwn8723be_datapath_start(&r->datapath)",
                            "missing_datapath_start(&r->datapath)"), cal, disable),
    (state, runtime, cal.replace("sc->sc_rf_path_count == 1U",
                                "sc->sc_rf_path_count == 2U"), disable),
    (state, runtime, cal,
     disable.replace("rtwn8723be_netbsd_rf_change_owned(sc)",
                     "true")),
]
for i, changed in enumerate(mutations):
    assert changed != (state, runtime, cal, disable), i
    assert not contract(*changed), i
print(f"LINUX_NETBSD_SEQUENCE_SOURCE_PASS: {len(mutations)} negative mutations;"
      " probe/hw/start/stop/runtime/guard order; kernel NOT_RUN")
