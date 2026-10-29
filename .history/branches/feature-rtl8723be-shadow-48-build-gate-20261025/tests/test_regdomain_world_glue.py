#!/usr/bin/env python3
"""Protect the shared NetBSD world-regdomain publication path."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NETBSD_C = (ROOT / "src" / "rtwn8723be_netbsd.c").read_text()
NET80211_C = (ROOT / "src" / "rtwn8723be_net80211.c").read_text()


def body(text: str, signature: str, successor: str) -> str:
    assert signature in text, f"missing {signature}"
    part = text.split(signature, 1)[1]
    assert successor in part, f"missing boundary after {signature}"
    return part.split(successor, 1)[0]


apply = body(
    NETBSD_C,
    "rtwn8723be_netbsd_apply_world_regdomain(struct rtwn8723be_softc *sc)",
    "\nint\nrtwn8723be_netbsd_init_core",
)
assert "rtwn8723be_regdomain_world_channel_mode(ch, &mode)" in apply
assert "R23BE_REGDOMAIN_ACTIVE_CCK_OFDM" in apply
assert "IEEE80211_CHAN_CCK | IEEE80211_CHAN_OFDM |" in apply
assert "IEEE80211_CHAN_DYN | IEEE80211_CHAN_2GHZ;" in apply
assert "R23BE_REGDOMAIN_PASSIVE_CCK_OFDM" in apply
assert "IEEE80211_CHAN_DYN | IEEE80211_CHAN_2GHZ |" in apply
assert "IEEE80211_CHAN_PASSIVE;" in apply
assert "R23BE_REGDOMAIN_PASSIVE_CCK_ONLY" in apply
assert "IEEE80211_CHAN_CCK | IEEE80211_CHAN_2GHZ |" in apply
assert "return EINVAL;" in apply

core = body(
    NETBSD_C,
    "rtwn8723be_netbsd_init_core(void *arg)",
    "\nstatic uint32_t\nrtwn8723be_netbsd_tx_ring_count",
)
assert "rtwn8723be_netbsd_apply_world_regdomain(sc);" in core
assert "if (error != 0)" in core
assert "ic->ic_channels[i].ic_flags" not in core

register = body(
    NET80211_C,
    "rtwn8723be_net80211_register(struct rtwn8723be_net80211 *n,",
    "\nint\nrtwn8723be_net80211_unregister",
)
assert "rtwn8723be_netbsd_apply_world_regdomain(sc);" in register
assert "if (error != 0)" in register
assert "ic->ic_channels[ch].ic_flags" not in register

print("RTL_REGDOMAIN_WORLD_GLUE_OK")
