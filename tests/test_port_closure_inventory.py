#!/usr/bin/env python3
"""Inventory Linux lifecycle callback closure; never interpret a link as runtime proof."""
import argparse
import pathlib
import re
import sys

EXPECTED_MISSING = {
    "probe": ("register_ieee80211", "init_rfkill"),
    "start": ("bt_prepare",
              "bt_hw_init",
              "dm_init"),
    "stop": (),
}

def check(root, require_closure=False):
    src = root / "src"
    header = (src / "rtwn8723be_linux_state.h").read_text()
    body = (src / "rtwn8723be_netbsd.c").read_text()
    manifest = (root / "config/files.rtwn8723be_native").read_text()
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
    if len(bound) != 48:
        raise ValueError("bound callback count changed; re-inventory required")
    if dict(bound).get("wait_rf_change_idle") != \
            "rtwn8723be_netbsd_wait_rf_change_idle":
        raise ValueError("RF-change wait callback binding changed")
    if dict(bound).get("bt_halt_deinit") != \
            "rtwn8723be_netbsd_bt_halt_deinit":
        raise ValueError("BTC halt/deinit callback binding changed")
    btc_native = (src / "rtwn8723be_btc_native.c").read_text()
    if ("rtwn8723be_btc_native_fini(sc)" not in btc_native or
            "sc->sc_btcoexist && !sc->sc_btc.initialized" not in btc_native):
        raise ValueError("BTC halt/deinit lifetime incomplete")
    netbsd = (src / "rtwn8723be_netbsd.c").read_text()
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
