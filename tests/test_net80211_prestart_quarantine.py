#!/usr/bin/env python3
"""Source mutation controls for net80211 false-success and restart quarantine.

Production C11 behavior is executed by test_rfkill_net80211_start.py and
test_net80211_unstarted_rollback.py. This test specifically requires the
real native source to *retain* partially started firmware/MAC ownership.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NET = (ROOT / "src/rtwn8723be_net80211.c").read_text()
STATE = (ROOT / "src/rtwn8723be_net80211_state.h").read_text()

def body(source: str, name: str) -> str:
    marker = "\n" + name + "("
    assert source.count(marker) == 1, name
    return source.split(marker, 1)[1].split("\n}\n", 1)[0]

def require_contract(net: str, state: str) -> None:
    start = body(state, "rtwn8723be_net80211_start_checkpoint_ok")
    detach = body(state, "rtwn8723be_net80211_unstarted_detach_allowed")
    ifinit = body(net, "rtwn8723be_n80211_ifinit")

    for function in (start, detach):
        for field in (
            "state == NULL", "state->started",
            "state->being_init_adapter", "state->fw_ready",
            "state->mac_func_enable",
        ):
            assert field in function, field
    assert "R23BE_STAGE_PROBED" in start
    assert "R23BE_STAGE_STOPPED" in start
    assert "R23BE_STAGE_RUNNING" not in start
    assert "R23BE_STAGE_IEEE80211_REGISTER" in detach
    assert "R23BE_STAGE_PROBED" in detach
    assert "R23BE_STAGE_STOPPED" in detach

    checkpoint = "rtwn8723be_net80211_start_checkpoint_ok(&sc->sc_linux)"
    hwstart = "error = n->methods.hw_start(sc);"
    assert checkpoint in ifinit
    assert ifinit.index(checkpoint) < ifinit.index(hwstart)
    assert "(ifp->if_flags & IFF_RUNNING) != 0" in ifinit[:ifinit.index(checkpoint)]
    assert "return EBUSY;" in ifinit[:ifinit.index(checkpoint)]
    fail = ifinit.split(
        "if (!sc->sc_linux.started || !sc->sc_linux.fw_ready ||", 1)[1]
    fail = fail.split("\n    }\n", 1)[0]
    assert "sc->sc_linux.stage != R23BE_STAGE_RUNNING" in fail
    assert "return EIO;" in fail
    assert "hw_stop(sc)" not in fail
    second_rfkill = ifinit.rindex(
        "error = rtwn8723be_rfkill_native_radio_on(sc, &radio_on);")
    assert ifinit.index("return EIO;", ifinit.index(hwstart)) < second_rfkill
    assert "int stop_error = n->methods.hw_stop(sc);" in ifinit[second_rfkill:]

require_contract(NET, STATE)

mutations = (
    (NET, STATE.replace("state->fw_ready || state->mac_func_enable",
                        "state->mac_func_enable", 1)),
    (NET, STATE.replace("state->fw_ready || state->mac_func_enable",
                        "state->fw_ready", 1)),
    (NET, STATE.replace("state->being_init_adapter ||",
                        "false ||", 1)),
    (NET, STATE.replace("state->stage == R23BE_STAGE_STOPPED;",
                        "state->stage == R23BE_STAGE_RUNNING;", 1)),
    (NET, STATE.replace("state->fw_ready || state->mac_func_enable",
                        "state->mac_func_enable", 2)),
    (NET, STATE.replace("state->being_init_adapter ||",
                        "false ||", 2)),
    (NET.replace("rtwn8723be_net80211_start_checkpoint_ok(&sc->sc_linux)",
                 "true", 1), STATE),
    (NET.replace("(ifp->if_flags & IFF_RUNNING) != 0",
                 "false", 1), STATE),
    (NET.replace("        return EIO;\n    }\n    /*\n     * The physical RF switch",
                 "        return n->methods.hw_stop(sc);\n    }\n    /*\n     * The physical RF switch", 1), STATE),
    (NET.replace("        return EIO;\n    }\n    /*\n     * The physical RF switch",
                 "        return 0;\n    }\n    /*\n     * The physical RF switch", 1), STATE),
)
for number, (net, state) in enumerate(mutations, 1):
    assert net != NET or state != STATE, ("mutation did not apply", number)
    try:
        require_contract(net, state)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe net80211 partial-start mutation {number}")
print("RTL_NET80211_PRESTART_QUARANTINE_SOURCE_OK negatives=10")
