#!/usr/bin/env python3
"""Inventory Linux lifecycle callback closure; never interpret a link as runtime proof."""
import argparse
import pathlib
import re
import sys

EXPECTED_MISSING = {
    "probe": ("register_ieee80211", "init_rfkill"),
    "start": ("bt_prepare", "dm_init"),
    "stop": (),
}

def check(root, require_closure=False):
    src = root / "src"
    header = (src / "rtwn8723be_linux_state.h").read_text()
    body = (src / "rtwn8723be_netbsd.c").read_text()
    manifest = (root / "config/files.rtwn8723be_native").read_text()
    # The frozen rtlwifi RTL8723BE old-TRX ABI uses 32-bit bus addresses.
    # No single 32-bit pointer, descriptor or buffer span may cross the
    # 4-GiB boundary. Validate spans before a descriptor/mbuf is published,
    # not just the starting address.  This is SOURCE-only, NOT a C build.
    dma_h = (src / "rtwn8723be_f16_1.h").read_text()
    dma_alloc = (src / "rtwn8723be_f16_1_dma.c").read_text()
    tx_native = (src / "rtwn8723be_tx_native.c").read_text()
    rx_native = (src / "rtwn8723be_rx_native.c").read_text()
    helper = dma_h.split("rtwn8723be_dma32_range_valid(", 1)
    if len(helper) != 2:
        raise ValueError("missing source-derived 32-bit DMA span validator")
    helper = helper[1].split("}", 1)[0]
    if not all(tok in helper for tok in (
            "bytes != 0",
            "(uint64_t)addr <= UINT32_MAX",
            "(uint64_t)(bytes - 1) <= UINT32_MAX - (uint64_t)addr")):
        raise ValueError("DMA32 validator missing 4-GiB boundary/overflow check")
    mem_alloc = dma_alloc.split("rtwn8723be_f16_1_dma_mem_alloc(", 1)
    if len(mem_alloc) != 2:
        raise ValueError("native descriptor DMA alloc not found")
    mem_alloc = mem_alloc[1].split("rtwn8723be_f16_1_dma_mem_free(", 1)[0]
    if not all(tok in mem_alloc for tok in (
            "dma->map->dm_mapsize != size",
            "dma->map->dm_segs[0].ds_len < size",
            "!rtwn8723be_dma32_range_valid(")):
        raise ValueError("descriptor DMA mapping omits complete 32-bit span")
    if mem_alloc.find("!rtwn8723be_dma32_range_valid(") > mem_alloc.find(
            "dma->paddr ="):
        raise ValueError("DMA descriptor was published before span check")
    tx_alloc = dma_alloc.split("rtwn8723be_f16_1_tx_ring_alloc(", 1)
    if len(tx_alloc) != 2:
        raise ValueError("native TX ring allocator not found")
    tx_alloc = tx_alloc[1].split("rtwn8723be_f16_1_tx_ring_free(", 1)[0]
    if (not all(x in tx_alloc for x in (
            "count == 0", "count > RTWN8723BE_TX_RING_BE_COUNT",
            "!rtwn8723be_dma32_range_valid(next,",
            "goto fail; /* Do not commit a partial linked TX ring. */")) or
            tx_alloc.find("!rtwn8723be_dma32_range_valid(next,") >
            tx_alloc.find("desc[i].d[RTWN8723BE_TX_NEXT_DESC_DW] =")):
        raise ValueError("native TX descriptor list may cross 4-GiB limit")
    rx_alloc = dma_alloc.split("rtwn8723be_f16_1_rx_ring_alloc(", 1)
    if len(rx_alloc) != 2:
        raise ValueError("native RX ring allocator not found")
    rx_alloc = rx_alloc[1].split("rtwn8723be_f16_1_rx_ring_free(", 1)[0]
    if (not all(x in rx_alloc for x in (
            "count == 0", "count > RTWN8723BE_RX_RING_COUNT",
            "ring->slot[i].map->dm_mapsize !=",
            "ring->slot[i].map->dm_segs[0].ds_len <",
            "!rtwn8723be_dma32_range_valid(")) or
            rx_alloc.find("!rtwn8723be_dma32_range_valid(") >
            rx_alloc.find("ring->slot[i].m = m;")):
        raise ValueError("native RX DMA slot published without full span check")
    enqueue = tx_native.split("rtwn8723be_tx_native_enqueue(", 1)
    if len(enqueue) != 2:
        raise ValueError("native TX old-TRX enqueue not found")
    enqueue = enqueue[1].split("rtwn8723be_tx_native_reclaim(", 1)[0]
    if (enqueue.count("!rtwn8723be_dma32_range_valid(") < 3 or
            "slot->map->dm_segs[0].ds_len <" not in enqueue or
            "ring->desc_dma.size < (bus_size_t)ring->count *" not in enqueue or
            enqueue.find("slot->map->dm_segs[0].ds_len <") >
            enqueue.find("slot->m = m;")):
        raise ValueError("native TX may publish truncated 32-bit DMA")
    # Source-derived NetBSD DMA ownership: any mapping/encoding failure
    # after descriptor POSTREAD must restore saved bytes, then re-sync
    # PREWRITE/PREREAD before returning. No partial OWN or mbuf publication.
    tx_rollback = (
        "saved_desc = *desc;",
        "error = bus_dmamap_load_mbuf(",
        "goto restore_desc;",
        "goto unload_map;",
        "slot->m = m;",
        "ring->producer = (idx + 1U) % ring->count;",
        "unload_map:",
        "bus_dmamap_unload(sc->sc_dmat, slot->map);",
        "restore_desc:",
        "*desc = saved_desc;",
        "rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,",
        "return error;",
    )
    tx_positions = [enqueue.find(tok) for tok in tx_rollback]
    if (any(i < 0 for i in tx_positions) or
            tx_positions != sorted(tx_positions) or
            enqueue.count("goto unload_map;") < 4):
        raise ValueError("native TX error path may leak CPU-owned descriptor")
    if enqueue.index("slot->m = m;") > enqueue.index("unload_map:"):
        raise ValueError("native TX publishes mbuf inside error path")
    reclaim = tx_native.split("rtwn8723be_tx_native_reclaim(", 1)
    if len(reclaim) != 2 or not all(x in reclaim[1] for x in (
            "!rtwn8723be_dma32_range_valid(",
            "ring->desc_dma.size < (bus_size_t)ring->count *")):
        raise ValueError("native TX completion lacks valid DMA ring guard")
    if ("!rtwn8723be_dma32_range_valid(" not in rx_native or
            "slot->map->dm_segs[0].ds_len <" not in rx_native):
        raise ValueError("native RX rearm lacks complete DMA segment guard")
    struct = re.search(r"struct rtwn8723be_linux_ops\s*\{(.*?)\n\};", header, re.S)
    initializer = re.search(
        r"const struct rtwn8723be_linux_ops\s+rtwn8723be_netbsd_ops\s*=\s*\{(.*?)\n\};",
        body, re.S)
    if struct is None or initializer is None:
        raise ValueError("Linux ops declaration or native callback initializer missing")
    names = re.findall(r"\bint\s*\(\*(\w+)\)\s*\(", struct.group(1))
    bound = re.findall(r"\.([a-z_]\w*)\s*=\s*(rtwn8723be_\w+)",
                       initializer.group(1))
    if len(names) != len(set(names)) or len(bound) != len(set(k for k, _ in bound)):
        raise ValueError("duplicate callback declaration/binding")
    if set(k for k, _ in bound) - set(names):
        raise ValueError("unknown callback binding")
    missing = [n for n in names if n not in dict(bound)]
    expected = {n for phase in EXPECTED_MISSING.values() for n in phase}
    native_units = re.findall(r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native",
                              manifest, re.M)
    pg_in_build = "rtwn8723be_txpwr_pg.c" in native_units
    if not {"rtwn8723be_btc_mp.c", "rtwn8723be_btc_mp_native.c"} <= set(native_units):
        raise ValueError("actual BTC MP wire unit missing from native manifest")
    if not {"rtwn8723be_btc1.c", "rtwn8723be_btc2.c",
            "rtwn8723be_btc_engine.c", "rtwn8723be_btc_native.c",
            "rtwn8723be_btc_providers_native.c"} <= set(native_units):
        raise ValueError("actual BTC algorithms/native event owner missing from manifest")
    if len(names) != 53 or len(native_units) != 42:
        raise ValueError("source or native build manifest changed; re-inventory required")
    if set(missing) != expected:
        raise ValueError("callback inventory changed: now missing " + repr(missing))
    if len(bound) != 49:
        raise ValueError("bound callback count changed; re-inventory required")
    if dict(bound).get("wait_rf_change_idle") != \
            "rtwn8723be_netbsd_wait_rf_change_idle":
        raise ValueError("RF-change wait callback binding changed")
    if dict(bound).get("bt_halt_deinit") != \
            "rtwn8723be_netbsd_bt_halt_deinit":
        raise ValueError("BTC halt/deinit callback binding changed")
    btc_native = (src / "rtwn8723be_btc_native.c").read_text()
    if dict(bound).get("bt_hw_init") != "rtwn8723be_netbsd_bt_hw_init":
        raise ValueError("source-backed BTC hardware init binding missing")
    hw_init_match = re.search(
        r"\nint\nrtwn8723be_netbsd_bt_hw_init\(void \*arg\).*?\n\}\n",
        btc_native, re.S)
    if hw_init_match is None:
        raise ValueError("native BTC hardware init callback missing")
    hw_init = hw_init_match.group(0)
    ordered = (
        "R23BE_STAGE_BT_HW",
        "!sc->sc_btc.initialized",
        "event.kind = R23BE_BTC_INIT_HW;",
        "event.value = sc->sc_btcoexist ? 0 : 1;",
        "rtwn8723be_btc_native_execute(sc, &event);",
        "if (error != 0)",
        "event.kind = R23BE_BTC_INIT_DM;",
        "return rtwn8723be_btc_native_execute(sc, &event);",
    )
    offsets = [hw_init.find(token) for token in ordered]
    if any(i < 0 for i in offsets) or offsets != sorted(offsets):
        raise ValueError("BTC native HW/DM source order or preflight changed")
    # Frozen RTL8723BE get_btc_status() is always true even when the
    # physical rtl_get_hwpg_bt_exist() result is false.  Disallow both
    # the old success/no-op shortcut and a constant wifi_only flag.
    if (re.search(
            r"if\s*\(\s*!sc->sc_btcoexist\s*\)\s*return\s+0",
            hw_init) or
            hw_init.count("event.value = sc->sc_btcoexist ? 0 : 1;") != 1):
        raise ValueError("RTL8723BE physical BT presence masked BTC support")
    if ("if (error == 0 && event->kind == R23BE_BTC_INIT_DM)" not in
            btc_native or
            "n->engine.btc.initialized = true;" not in btc_native):
        raise ValueError("BTC init_coex_dm success publication missing")
    btc_engine = (src / "rtwn8723be_btc_engine.c").read_text()
    engine_init = btc_engine.split("rtwn8723be_btc_engine_init(", 1)
    if len(engine_init) != 2:
        raise ValueError("BTC engine initializer not found")
    engine_init = engine_init[1].split("rtwn8723be_btc_event_validate(", 1)[0]
    if ("s->btc = copy;" not in engine_init or
            "s->btc.initialized = false;" not in engine_init or
            engine_init.index("s->btc = copy;") >
            engine_init.index("s->btc.initialized = false;")):
        raise ValueError("BTC copied context published pre-initialized")
    if ("rtwn8723be_btc_native_fini(sc)" not in btc_native or
            "if (!sc->sc_btc.initialized)" not in btc_native):
        raise ValueError("BTC halt/deinit lifetime incomplete")
    stop_part = btc_native.split("rtwn8723be_netbsd_bt_halt_deinit(void *arg)", 1)
    if len(stop_part) != 2 or (
            "if (!sc->sc_btc.initialized)" not in stop_part[1] or
            "if (sc->sc_btcoexist && !sc->sc_btc.initialized)" in
            stop_part[1]):
        raise ValueError("BTC HALT must follow Linux always-true get_btc_status")
    # Failed full-callback preflight occurs with state IDLE and zero
    # hardware writes.  The PCI snapshot must be retired, otherwise native
    # detach incorrectly returns EBUSY forever.  Any partially registered
    # net80211 resource must STILL be retained and cannot be freed by the
    # pre-registration cleanup path.
    pci_attach = (src / "rtwn8723be_native.c").read_text()
    cleanup = pci_attach.split(
        "rtwn8723be_native_probe_cleanup(struct rtwn8723be_softc *sc)", 1)
    if len(cleanup) != 2:
        raise ValueError("native PCI probe rollback missing")
    cleanup = cleanup[1].split("rtwn8723be_native_detach(", 1)[0]
    preflight = cleanup.split("if (stage == R23BE_STAGE_IDLE)", 1)
    if len(preflight) != 2:
        raise ValueError("IDLE no-write rollback gate missing")
    preflight = preflight[1].split("if (stage >= R23BE_STAGE_IEEE80211_REGISTER)", 1)
    if (len(preflight) != 2 or
            "sc->sc_initial_pci_saved = false;" not in preflight[0] or
            "return;" not in preflight[0] or
            "refusing incomplete post-registration teardown" not in preflight[1]):
        raise ValueError("unsafe IDLE or post-registration probe cleanup")
    attach = pci_attach.split("rtwn8723be_native_attach(", 1)
    if len(attach) != 2:
        raise ValueError("native PCI attach entry missing")
    attach = attach[1]
    snapshot_error = attach.split("cannot snapshot original PCI power state;", 1)
    if (len(snapshot_error) != 2 or
            "rtwn8723be_netbsd_context_fini(sc);" not in
            snapshot_error[1].split("return;", 1)[0]):
        raise ValueError("PCI snapshot failure leaks RF-PS lock")
    fail_cleanup = attach.split("failed_stage = sc->sc_linux.stage;", 1)
    if len(fail_cleanup) != 2:
        raise ValueError("probe failure cleanup missing")
    fail_cleanup = fail_cleanup[1].split("native RTL8723BE probe failed:", 1)[0]
    expected_cleanup_sequence = (
        "rtwn8723be_native_probe_cleanup(sc);",
        "if (sc->sc_linux.stage == R23BE_STAGE_IDLE &&",
        "!sc->sc_initial_pci_saved)",
        "rtwn8723be_netbsd_context_fini(sc);",
    )
    cleanup_offsets = [fail_cleanup.find(token)
                       for token in expected_cleanup_sequence]
    if (any(i < 0 for i in cleanup_offsets) or
            cleanup_offsets != sorted(cleanup_offsets)):
        raise ValueError("pre-registration probe failure leaves RF owner active")

    # NetBSD/src if.c requires if_register() before if_detach(); it is
    # invalid to call if_detach() from if_percpuq_create()'s pre-register
    # branch. Frozen if_percpuq_create uses KM_SLEEP allocation and
    # NetBSD if_rtwn.c follows if_initialize -> ieee80211_ifattach ->
    # if_percpuq_create -> if_register, with no such fake ENOMEM unwind.
    # Station WPA2 is software-only here; this must not be mistaken for
    # a working key/TX/RX datapath.
    n80211 = (src / "rtwn8723be_net80211.c").read_text()
    registration = n80211.split(
        "rtwn8723be_net80211_register(", 1)
    if len(registration) != 2:
        raise ValueError("net80211 registration entry missing")
    registration = registration[1].split(
        "rtwn8723be_net80211_unregister(", 1)[0]
    required = (
        "ic->ic_caps = IEEE80211_C_SHPREAMBLE | IEEE80211_C_SHSLOT |",
        "IEEE80211_C_WPA2;",
        "sc->sc_sw_crypto = true;",
        "sc->sc_use_sw_sec = true;",
        "sc->sc_use_defaultkey = false;",
    )
    if not all(token in registration for token in required):
        raise ValueError("software WPA2 station capability/policy incomplete")
    net_register_path = registration.split("if_initialize(ifp);", 1)
    if len(net_register_path) != 2:
        raise ValueError("NetBSD if_initialize registration order lost")
    reg_window = net_register_path[1].split("if_register(ifp);", 1)
    if len(reg_window) != 2:
        raise ValueError("NetBSD interface is not registered")
    reg_window = reg_window[0]
    if (reg_window.find("ieee80211_ifattach(ic);") < 0 or
            reg_window.find("ifp->if_percpuq = if_percpuq_create(ifp);") < 0 or
            "if_detach(ifp);" in reg_window or
            "ieee80211_ifdetach(ic);" in reg_window or
            "KASSERT(ifp->if_percpuq != NULL);" not in reg_window):
        raise ValueError("unregistered ifnet cleanup or NetBSD attach order")
    if registration.index("if_initialize(ifp);") > registration.index(
            "ieee80211_ifattach(ic);"):
        raise ValueError("NetBSD if_initialize must precede ieee80211_ifattach")
    # WPA2 capability is backed by the NetBSD software crypto choice,
    # not by an unimplemented hardware CAM programming path. The native
    # security callback must exit before any SECCFG or CR register write.
    security_native = (src / "rtwn8723be_security_native.c").read_text()
    software = security_native.split(
        "rtwn8723be_netbsd_enable_hw_security(void *arg)", 1)
    if len(software) != 2:
        raise ValueError("native security owner missing")
    software = software[1]
    software_branch = software.split(
        "if (sc->sc_sw_crypto || sc->sc_use_sw_sec) {", 1)
    if len(software_branch) != 2:
        raise ValueError("software WPA2 policy lacks cipher-engine gate")
    software_branch = software_branch[1].split("}", 1)[0]
    if ("sc->sc_security_configured = true;" not in software_branch or
            "return 0;" not in software_branch or
            "rtwn8723be_write_" in software_branch):
        raise ValueError("software WPA2 branch must not program HW cipher")
    if software.find("if (sc->sc_sw_crypto || sc->sc_use_sw_sec)") > \
            software.find("rtwn8723be_write_1(sc, 0x100U + 1"):
        raise ValueError("native WPA2 software decision occurs after HW IO")
    netbsd = (src / "rtwn8723be_netbsd.c").read_text()
    btc_power = netbsd.split("rtwn8723be_netbsd_bt_power_on_setting(", 1)
    if len(btc_power) != 2:
        raise ValueError("native BTC MAC power-on missing")
    btc_power = btc_power[1].split(
        "rtwn8723be_netbsd_bt_preload_firmware(", 1)[0]
    if ("!sc->sc_mapped || !sc->sc_btc.initialized" not in btc_power or
            "if (!sc->sc_btcoexist)" in btc_power or
            btc_power.find("!sc->sc_btc.initialized") >
            btc_power.find("rtwn8723be_write_1(sc, 0x0067")):
        raise ValueError("BTC power-on context/order mismatches RTL8723BE")
    # Native GPIO RF switch sample (NOT the full polling/registration path):
    # match frozen rtl8723be GPIO offsets, non-inverted default polarity,
    # invalid-sample ownership and RF-change lock order before any MMIO.
    regs = (src / "rtwn8723be_f16_1.h").read_text()
    softc_h = (src / "rtwn8723be_netbsd.h").read_text()
    if (not re.search(r"R23BE_REG_GPIO_PIN_CTRL_2\s+0x0060\b", regs)
            or not re.search(r"R23BE_REG_GPIO_IO_SEL_2\s+0x0062\b", regs)
            or "sc_hwradiooff;" not in softc_h
            or "sc_rfkill_sample_valid;" not in softc_h):
        raise ValueError("pinned RTL8723BE GPIO register/state ABI missing")
    sample_part = netbsd.split(
        "rtwn8723be_netbsd_rfkill_gpio_sample(", 1)
    if len(sample_part) != 2:
        raise ValueError("native RTL8723BE GPIO RF sampler missing")
    sample = sample_part[1].split(
        "rtwn8723be_netbsd_wait_rf_change_idle(", 1)[0]
    ordered_sample = (
        "*valid = false;",
        "cpu_intr_p() || cpu_softintr_p()",
        "sc->sc_linux.being_init_adapter",
        "mutex_enter(&sc->sc_rf_ps_lock);",
        "if (sc->sc_rfchange_inprogress)",
        "sc->sc_rfchange_inprogress = true;",
        "rtwn8723be_read_1(sc, R23BE_REG_GPIO_IO_SEL_2);",
        "rtwn8723be_write_1(sc, R23BE_REG_GPIO_IO_SEL_2,",
        "rtwn8723be_read_1(sc, R23BE_REG_GPIO_PIN_CTRL_2);",
        "on = (pins & (1U << 1)) != 0;",
        "sc->sc_hwradiooff = !on;",
        "sc->sc_rfchange_inprogress = false;",
        "*radio_on = on;",
        "*valid = true;",
    )
    offsets = [sample.find(t) for t in ordered_sample]
    if (any(i < 0 for i in offsets) or offsets != sorted(offsets)):
        raise ValueError("GPIO RF sample violated frozen ordering/validity")
    # The busy branch unlocks earlier than successful admission; check
    # the second unlock next to the successful ownership claim explicitly.
    if ("sc->sc_rfchange_inprogress = true;\n    mutex_exit(&sc->sc_rf_ps_lock);" not in
            sample or
            "if (sc->sc_rfchange_inprogress) {\n        mutex_exit(&sc->sc_rf_ps_lock);"
            not in sample):
        raise ValueError("GPIO RF owner is not released on both paths")
    if "if (sc->sc_linux.stage == R23BE_STAGE_RUNNING &&" not in sample:
        raise ValueError("GPIO sample must not report unstarted hardware")
    if ".init_rfkill = " in initializer.group(1):
        raise ValueError("rfkill probe callback bound before poll/teardown owner")
    shutdown_native = (src / "rtwn8723be_hw_disable_native.c").read_text()
    if ("sc_rfchange_inprogress = true" not in netbsd or
            "ETIMEDOUT" not in netbsd or
            "rtwn8723be_netbsd_rf_change_end(sc)" not in shutdown_native):
        raise ValueError("RF-change wait/release lifetime incomplete")
    calibration = (src / "rtwn8723be_calibration_native.c").read_text()
    if (dict(bound).get("rf_calibration") != "rtwn8723be_netbsd_rf_calibration" or
            "sc_calibration_owner" not in calibration or
            "cal_native_phase" not in calibration):
        raise ValueError("guarded calibration implementation changed; re-inventory required")
    if re.search(r"\bsc_calibration_owner\s*=(?!=)",
                 "\n".join(p.read_text() for p in src.glob("*.c"))):
        raise ValueError("calibration owner assignment added; audit real BTC/DM/RF ownership first")
    shutdown = (src / "rtwn8723be_hw_disable_native.c").read_text()
    if (dict(bound).get("hw_disable") != "rtwn8723be_netbsd_hw_disable" or
            "sc_hw_disable_owner" not in shutdown):
        raise ValueError("guarded card-disable implementation changed; re-inventory required")
    if re.search(r"\bsc_hw_disable_owner\s*=(?!=)",
                 "\n".join(p.read_text() for p in src.glob("*.c"))):
        raise ValueError("card-disable owner assignment added; audit real STOPPING/BTC/RF/IRQ lifetime first")
    providers = (src / "rtwn8723be_btc_providers_native.c").read_text()
    provider_header = (src / "rtwn8723be_btc_providers_native.h").read_text()
    for token in (
            "btc_read_1byte = btc_read_1",
            "btc_write_1byte_bitmask = btc_write_1_mask",
            "btc_set_bb_reg = btc_set_bb",
            "btc_get_bb_reg = btc_get_bb",
            "btc_set_rf_reg = btc_set_rf",
            "btc_get_rf_reg = btc_get_rf",
            "btc_fill_h2c = btc_fill_h2c",
            "r23be_delay_ms = btc_delay_ms"):
        if token not in providers:
            raise ValueError("native BTC low-level provider missing: " + token)
    if "This does NOT make the coexistence" not in provider_header:
        raise ValueError("BTC provider partial-closure guard missing")
    # Complete typed receive ABI is necessary but not sufficient: the
    # external lifecycle owner must prove a fresh MCU/RX lifetime first.
    mp_source = (src / "rtwn8723be_btc_mp_native.c").read_text()
    mp_header = (src / "rtwn8723be_btc_mp_native.h").read_text()
    rx_binding = (src / "rtwn8723be_rx_binding.c").read_text()
    if ("rtwn8723be_btc_mp_native_c2h(void *context," not in mp_source or
            "return rtwn8723be_btc_mp_native_receive(context, event);" not in
            mp_source or
            "rtwn8723be_btc_mp_native_c2h(void *," not in mp_header):
        raise ValueError("typed native BTC MP C2H consumer adapter missing")
    publish = rx_binding.find("memset(binding, 0, sizeof(*binding))")
    if publish < 0 or any(
            rx_binding.find(token) < 0 or rx_binding.find(token) > publish
            for token in ("!net->sc->sc_btc.initialized",
                          "!net->sc->sc_btc_mp.initialized",
                          "!net->sc->sc_btc_mp.active")):
        raise ValueError("BTC C2H RX callbacks publish before activation")

    # Frozen halbtc_get_bt_afh_map_from_bt() publishes L then M then H.
    # These are source-order guards, not an executable native/firmware test.
    afh_match = re.search(
        r"static bool\s+btc_get_afh_map\s*\(.*?\n\}\n",
        providers, re.S)
    if afh_match is None:
        raise ValueError("native AFH provider missing")
    afh = afh_match.group(0)
    ordered = (
        "R23BE_BT_OP_AFH_L",
        "btc->bt_info.afh_map_l = low;",
        "map[3] =",
        "R23BE_BT_OP_AFH_M",
        "btc->bt_info.afh_map_m = middle;",
        "map[7] =",
        "R23BE_BT_OP_AFH_H",
        "btc->bt_info.afh_map_h = (uint16_t)high;",
        "map[9] =",
        "return true;",
        "fail:",
        "btc_provider_fail(sc, error);",
        "return false;",
    )
    # The input guard also returns false; require the terminal failure
    # return rather than that earlier, legitimate NULL/not-ready guard.
    offsets = [afh.rfind(token) if token == "return false;" else afh.find(token)
               for token in ordered]
    if (any(i < 0 for i in offsets) or offsets != sorted(offsets) or
            afh.count("goto fail;") != 3):
        raise ValueError("AFH per-segment publication/partial-error parity changed")
    guarded = ("rf_calibration", "hw_disable")
    if re.search(r"\brtwn8723be_btc_native_init\s*\(",
        "\n".join(p.read_text() for p in src.glob("*.c")
                    if p.name != "rtwn8723be_btc_native.c")):
        raise ValueError("BTC owner bound; audit all 27 providers and real state/MCU/RX lifetime first")
    print(f"DECLARED={len(names)} BOUND={len(bound)} MISSING={len(missing)}")
    for phase, items in EXPECTED_MISSING.items():
        print(phase.upper() + "=" + ",".join(items))
    print("NATIVE_C_OBJECTS=" + str(len(native_units)))
    print("TX_POWER_PG_IN_NATIVE_BUILD=" + str(pg_in_build).lower())
    print("GUARDED_CALLBACKS_WITH_OPEN_OWNER=" + ",".join(guarded))
    print("BTC_ALGORITHMS_BUILT=1ant,2ant; BTC_FULL_PROVIDER_LIFETIME=OPEN")
    # This gate is deliberately stricter than a successful kernel link.
    complete = not missing and pg_in_build and not guarded
    print("CALLBACK_AND_PG_CLOSURE=" + ("CLOSED" if complete else "OPEN"))
    if require_closure and not complete:
        return 1
    return 0

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=pathlib.Path,
                   default=pathlib.Path(__file__).resolve().parent.parent)
    p.add_argument("--require-closure", action="store_true")
    args = p.parse_args()
    try:
        sys.exit(check(args.root, args.require_closure))
    except (OSError, ValueError) as exc:
        print("PORT_CLOSURE_INVENTORY_FAILED: " + str(exc), file=sys.stderr)
        sys.exit(2)
