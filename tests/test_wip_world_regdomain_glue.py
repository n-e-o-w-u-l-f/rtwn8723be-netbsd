#!/usr/bin/env python3
"""WIP 50-unit native world-regdomain owner and publication source contract.

Source authority: frozen Linux rtlwifi/regd.c (CH1–11 active CCK/OFDM,
CH12–13 passive CCK/OFDM, CH14 passive CCK only) and same shared policy
in main's rtwn8723be_regdomain_world_channel_mode(). This is source-only:
country EEPROM authority, real RF TX limits and WPA2 need physical proof.
"""
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "src"
netbsd = (src / "rtwn8723be_netbsd.c").read_text()
header = (src / "rtwn8723be_netbsd.h").read_text()
ifnet = (src / "rtwn8723be_net80211.c").read_text()


def section(data: str, start: str, end: str) -> str:
    assert data.count(start) == 1, start
    body = data.split(start, 1)[1]
    assert end in body, end
    return body.split(end, 1)[0]


world = section(
    netbsd,
    "rtwn8723be_netbsd_apply_world_regdomain(struct rtwn8723be_softc *sc)",
    "\nint\nrtwn8723be_netbsd_init_core(",
)
core = section(
    netbsd,
    "rtwn8723be_netbsd_init_core(void *arg)",
    "\nstatic uint32_t\nrtwn8723be_netbsd_tx_ring_count(",
)
register = section(
    ifnet,
    "rtwn8723be_net80211_register(struct rtwn8723be_net80211 *n,",
    "\nint\nrtwn8723be_net80211_unregister(",
)
assert "int rtwn8723be_netbsd_apply_world_regdomain(struct rtwn8723be_softc *);" in header
assert world.count("ic->ic_channels[ch].ic_flags =") == 3
assert "for (ch = 1; ch <= 14U; ch++)" in world
assert "if (ch <= 11U)" in world
assert "else if (ch <= 13U)" in world
assert world.count("IEEE80211_CHAN_PASSIVE") == 2
assert world.count("IEEE80211_CHAN_OFDM") == 2
assert world.count("IEEE80211_CHAN_CCK") == 3
assert world.count("IEEE80211_CHAN_2GHZ") == 4  # freq + three flags
assert world.index("if (ch <= 11U)") < world.index("else if (ch <= 13U)")
assert "if (sc == NULL)\n        return EINVAL;" in world

for body in (core, register):
    assert "error = rtwn8723be_netbsd_apply_world_regdomain(sc);" in body
    assert "if (error != 0)\n        return error;" in body
    assert "ic->ic_channels[" not in body, "a second channel writer bypasses world policy"

assert core.index("error = rtwn8723be_netbsd_apply_world_regdomain(sc);") < (
    core.index("sc->sc_core_initialized = true;"))
assert register.index("error = rtwn8723be_netbsd_apply_world_regdomain(sc);") < (
    register.index("n->sc = sc;"))
assert register.index("error = rtwn8723be_netbsd_apply_world_regdomain(sc);") < (
    register.index("if_register(ifp);"))
print("RTL_WORLD_REGDOMAIN_CORE_IFNET_SINGLE_OWNER_SOURCE_PASS")
