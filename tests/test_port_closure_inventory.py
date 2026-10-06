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
    "stop": ("bt_halt_deinit", "wait_rf_change_idle"),
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
            "rtwn8723be_btc_engine.c", "rtwn8723be_btc_native.c"} <= set(native_units):
        raise ValueError("actual BTC algorithms/native event owner missing from manifest")
    if len(names) != 53 or len(native_units) != 41:
        raise ValueError("source or native build manifest changed; re-inventory required")
    if set(missing) != expected:
        raise ValueError("callback inventory changed: now missing " + repr(missing))
    if len(bound) != 46:
        raise ValueError("bound callback count changed; re-inventory required")
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
