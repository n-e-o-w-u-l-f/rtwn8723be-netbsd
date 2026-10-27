#!/usr/bin/env python3
"""Datapath owner publication, IRQ callback identity and release source gates.

Actual NetBSD mutex, IRQ, softint and DMA synchronization must still be
verified in a native kernel; this portable test validates the source contract.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
H = (ROOT / "src/rtwn8723be_netbsd.h").read_text()
DP = (ROOT / "src/rtwn8723be_datapath.c").read_text()
NATIVE = (ROOT / "src/rtwn8723be_native.c").read_text()
UNWIND = (ROOT / "src/rtwn8723be_probe_unwind.h").read_text()
NETBSD_C = (ROOT / "src/rtwn8723be_netbsd.c").read_text()

def body(src: str, name: str) -> str:
    match = re.search(r"(?m)^(?:static\s+)?int\s*\n" +
                      re.escape(name) + r"\([^;{}]*\)\n\{", src)
    assert match is not None, name
    return src[match.end():src.index("\n}\n", match.end())]

def ordered(src: str, strings: tuple[str, ...]) -> None:
    positions = [src.find(s) for s in strings]
    assert min(positions) >= 0 and positions == sorted(positions), strings

def contract(dp_source: str, native_source: str) -> None:
    prepare = body(dp_source, "rtwn8723be_datapath_prepare")
    unprepare = body(dp_source, "rtwn8723be_datapath_unprepare")
    unwind = body(native_source, "rtwn8723be_native_unwind_datapath")
    rollback = native_source.split(
        "rtwn8723be_native_probe_cleanup(struct rtwn8723be_softc *sc)", 1)[1]
    rollback = rollback.split("rtwn8723be_native_detach(", 1)[0]

    assert "sc->sc_datapath != NULL" in prepare
    assert "sc->sc_irq_arg != NULL" in prepare
    assert "sc->sc_pihp != NULL" in prepare
    ordered(prepare, (
        "mutex_init(&dp->tx_lock, MUTEX_DEFAULT, IPL_NET);",
        "dp->prepared = true;",
        "sc->sc_datapath = dp;",
        "rtwn8723be_netbsd_irq_set_dispatch(sc, &irq, dp);",
    ))
    for token in (
        "sc->sc_datapath != dp",
        "sc->sc_irq_arg != dp",
        "sc->sc_irq_dispatch.rx != rtwn8723be_dp_rx",
        "sc->sc_irq_dispatch.tx_done != rtwn8723be_dp_tx_done",
        "sc->sc_irq_dispatch.power_event != NULL",
        "dp->tx_enabled",
        "sc->sc_irq_requested",
        "sc->sc_irq_enabled",
        "sc->sc_ih != NULL",
        "sc->sc_soft_ih != NULL",
        "sc->sc_pihp != NULL",
    ):
        assert token in unprepare, token
    ordered(unprepare, (
        "rtwn8723be_netbsd_irq_set_dispatch(sc, NULL, NULL);",
        "sc->sc_datapath = NULL;",
        "mutex_destroy(&dp->tx_lock);",
        "memset(dp, 0, sizeof(*dp));",
    ))
    assert "error = rtwn8723be_datapath_unprepare(sc->sc_datapath);" in unwind
    assert "if (error != 0)" in unwind
    assert "sc->sc_datapath != NULL || sc->sc_irq_arg != NULL" in unwind
    assert "sc->sc_irq_dispatch.ready" not in unwind
    assert "sc->sc_irq_dispatch_ready" in unwind

    assert ".unprepare_datapath = rtwn8723be_native_unwind_datapath," in native_source
    admission = native_source.split(
        "rtwn8723be_native_probe_resources_ready(struct rtwn8723be_softc *sc)", 1)[1]
    admission = admission.split("\n}\n", 1)[0]
    assert "sc->sc_datapath != NULL" in admission
    assert "sc->sc_datapath->prepared" in admission
    assert "sc->sc_datapath->sc == sc" in admission
    assert "sc->sc_irq_arg == sc->sc_datapath" in admission
    assert ".datapath_owner_valid = dp != NULL ?" in native_source
    assert ".datapath_tx_enabled = dp != NULL && dp->tx_enabled," in native_source
    assert "sc->sc_datapath = NULL;" not in rollback, (
        "native cleanup must call the real datapath owner")
    assert "rtwn8723be_native_unwind_datapath(sc)" in rollback
    assert rollback.index("rtwn8723be_native_unwind_datapath(sc)") < (
        rollback.index("rtwn8723be_netbsd_free_pci_rings(sc);"))

assert "struct rtwn8723be_datapath *sc_datapath;" in H
assert "struct rtwn8723be_datapath;" in H
assert "R23BE_PROBE_UNWIND_DATAPATH" in UNWIND
assert "KASSERT(sc->sc_datapath == NULL);" in NETBSD_C
assert "KASSERT(sc->sc_irq_arg == NULL && !sc->sc_irq_dispatch_ready);" in NETBSD_C
assert "error = ops->unprepare_datapath(owner);" in UNWIND
assert "s->datapath_tx_enabled" in UNWIND
assert "!s->datapath_owner_valid" in UNWIND

contract(DP, NATIVE)

# Every mutation must target an actual contract token and be rejected.
controls = (
    (DP.replace("    sc->sc_datapath = dp;", "", 1), NATIVE),
    (DP.replace("if (sc->sc_datapath != dp || sc->sc_irq_arg != dp ||",
                "if (false || sc->sc_irq_arg != dp ||", 1), NATIVE),
    (DP.replace("sc->sc_irq_requested || ", "", 1), NATIVE),
    (DP.replace("sc->sc_irq_dispatch.rx != rtwn8723be_dp_rx",
                "false", 1), NATIVE),
    (DP.replace("    sc->sc_datapath = NULL;", "", 1), NATIVE),
    (DP.replace("    mutex_destroy(&dp->tx_lock);", "", 1), NATIVE),
    (DP, NATIVE.replace(
        ".unprepare_datapath = rtwn8723be_native_unwind_datapath,", "", 1)),
    (DP, NATIVE.replace(
        "error = rtwn8723be_datapath_unprepare(sc->sc_datapath);",
        "error = 0;", 1)),
    (DP, NATIVE.replace(
        "if (rtwn8723be_native_unwind_datapath(sc) != 0)",
        "if (false)", 1)),
    (DP, NATIVE.replace(
        "sc->sc_datapath->prepared", "true", 1)),
)
for i, (changed_dp, changed_native) in enumerate(controls, 1):
    assert changed_dp != DP or changed_native != NATIVE, i
    try:
        contract(changed_dp, changed_native)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe datapath lifetime mutation {i} accepted")

print("RTL_DATAPATH_OWNER_LIFETIME_SOURCE_OK negatives=10")
