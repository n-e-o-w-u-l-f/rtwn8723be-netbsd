#!/usr/bin/env python3
"""Require real RF software-owner publication AFTER all initial seed owners.

The RTL physical PHY is already powered during this callback, but the
NetBSD runtime must not claim RF ready when channel/media seed or BT-MP
generation activation failed. Source-level only: HP native runtime and
physical RF tests are separate gates.
"""
from pathlib import Path

source = (Path(__file__).resolve().parents[1] /
          "src/rtwn8723be_runtime.c").read_text()
marker = "rtwn8723be_runtime_bt_hw_init(void *arg)"
assert source.count(marker) == 1
body = source.split(marker, 1)[1].split(
    "\nint\nrtwn8723be_runtime_dm_init", 1)[0]
need = (
    "r->rf_on = false;",
    "r->rf_state_valid = false;",
    "r->poweroff_verified = false;",
    "rtwn8723be_channel_state_seed(&r->channel",
    "rtwn8723be_media_state_seed(&r->media",
    "rtwn8723be_btc_mp_native_activate(sc);",
    "if (error == 0) {",
    "r->rx_generation = sc->sc_h2c.firmware_generation;",
    "r->rf_on = true;",
    "r->rf_state_valid = true;",
    "return error;",
)
indices = [body.find(t) for t in need]
assert all(i >= 0 for i in indices), list(zip(need, indices))
assert indices == sorted(indices), "RF lifetime published ahead of producer success"
assert body.count("r->rf_on = true;") == 1
assert body.count("r->rf_state_valid = true;") == 1
assert body.count("rtwn8723be_btc_mp_native_activate(sc);") == 1
assert "if (error == 0) error = rtwn8723be_btc_mp_native_activate(sc);" in body
print("RTL_RF_OWNER_PUBLISH_AFTER_BT_MP_SEED_SOURCE_PASS")
