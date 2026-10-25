#!/usr/bin/env python3
"""RX/C2H binding owner, staged BT admission, and teardown order contract.

Static mutation regression complements test_rx_binding.py's compiled C11
production function harness; neither simulates NetBSD IRQ/softint races.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RX = (ROOT / "src/rtwn8723be_rx_binding.c").read_text()
H = (ROOT / "src/rtwn8723be_netbsd.h").read_text()
N = (ROOT / "src/rtwn8723be_native.c").read_text()
BROKER = (ROOT / "src/rtwn8723be_probe_unwind.h").read_text()
NETBSD = (ROOT / "src/rtwn8723be_netbsd.c").read_text()

def function(s: str, ident: str) -> str:
    term = "\n" + ident + "("
    assert term in s
    fragment = s.split(term, 1)[1]
    return fragment[:fragment.index("\n}\n")]

def source_contract(rx: str, native: str) -> None:
    init = function(rx, "rtwn8723be_rx_binding_init")
    recv = function(rx, "rtwn8723be_rx_binding_c2h")
    fini = function(rx, "rtwn8723be_rx_binding_fini")

    assert "net->sc->sc_rx_binding != NULL" in init
    assert "net->sc->sc_rx_binding = binding;" in init
    assert init.index("binding->dispatch.c2h =") < init.index(
        "net->sc->sc_rx_binding = binding;")
    assert "!net->sc->sc_btc_mp.active" not in init

    for x in (
        "packet->c2h_id == R23BE_C2H_BT_INFO",
        "!binding->net->sc->sc_btc.initialized",
        "packet->c2h_id == R23BE_C2H_BT_MP",
        "!binding->net->sc->sc_btc_mp.initialized",
        "!binding->net->sc->sc_btc_mp.active",
        "return EAGAIN;",
    ):
        assert x in recv, x
        assert recv.index(x) < recv.index(
            "rtwn8723be_c2h_native_receive("), x

    for x in (
        "sc->sc_rx_binding != binding",
        "binding->dispatch.arg != binding",
        "sc->sc_datapath != NULL",
        "sc->sc_irq_arg != NULL",
        "sc->sc_irq_requested",
        "sc->sc_irq_enabled",
        "sc->sc_ih != NULL",
        "sc->sc_soft_ih != NULL",
        "sc->sc_pihp != NULL",
    ):
        assert x in fini, x
    assert fini.index("sc->sc_irq_enabled") < fini.index(
        "sc->sc_rx_binding = NULL;")
    assert fini.index("sc->sc_rx_binding = NULL;") < fini.index(
        "memset(binding, 0, sizeof(*binding));")

    owner = function(native, "rtwn8723be_native_unwind_rx_binding")
    assert "error = rtwn8723be_rx_binding_fini(sc->sc_rx_binding);" in owner
    assert "if (error != 0)" in owner
    assert ".unbind_rx = rtwn8723be_native_unwind_rx_binding" in native
    assert ".rx_binding_present = sc->sc_rx_binding != NULL," in native
    assert ".rx_binding_owned = sc->sc_rx_binding != NULL &&" in native
    for x in (
        "sc->sc_datapath->rx.arg == sc->sc_rx_binding",
        "sc->sc_datapath->rx.frame ==",
        "sc->sc_datapath->rx.c2h ==",
    ):
        assert x in native, x
    cleanup = function(native, "rtwn8723be_native_probe_cleanup")
    assert cleanup.index("rtwn8723be_native_unwind_datapath(sc)") < (
        cleanup.index("rtwn8723be_native_unwind_rx_binding(sc)"))
    assert cleanup.index("rtwn8723be_native_unwind_rx_binding(sc)") < (
        cleanup.index("rtwn8723be_netbsd_free_pci_rings(sc)"))

assert "struct rtwn8723be_rx_binding *sc_rx_binding;" in H
assert "KASSERT(sc->sc_rx_binding == NULL);" in NETBSD
assert "R23BE_PROBE_UNWIND_RX_BINDING" in BROKER
assert "error = ops->unbind_rx(owner);" in BROKER
source_contract(RX, N)

cases = (
    (RX.replace("net->sc->sc_rx_binding != NULL",
                "false", 1), N),
    (RX.replace("net->sc->sc_rx_binding = binding;",
                "/* publish suppressed */", 1), N),
    (RX.replace("packet->c2h_id == R23BE_C2H_BT_MP",
                "false", 1), N),
    (RX.replace("!binding->net->sc->sc_btc.initialized",
                "false", 1), N),
    (RX.replace("sc->sc_irq_requested ||", "", 1), N),
    (RX.replace("sc->sc_rx_binding = NULL;", "", 1), N),
    (RX.replace("    sc->sc_rx_binding = NULL;\n"
                "    memset(binding, 0, sizeof(*binding));",
                "    sc->sc_rx_binding = NULL;\n"
                "    /* forget to revoke callbacks */", 1), N),
    (RX, N.replace("sc->sc_datapath->rx.arg == sc->sc_rx_binding",
                   "true", 1)),
    (RX, N.replace(".unbind_rx = rtwn8723be_native_unwind_rx_binding,",
                   "", 1)),
)
for i, (rx, native) in enumerate(cases, 1):
    assert rx != RX or native != N, f"mutation {i} failed"
    try:
        source_contract(rx, native)
    except (ValueError, AssertionError):
        continue
    raise AssertionError(f"unsafe RX ownership mutation {i} accepted")
print("RTL_RX_BINDING_FIVE_OWNER_SOURCE_OK negatives=9")
