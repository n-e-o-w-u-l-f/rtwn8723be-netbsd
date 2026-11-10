#!/usr/bin/env python3
"""Proof of preregistration admission and the genuine native callback binding.

The unchanged stage predicate runs under strict portable C11/UBSan. Source
contracts retain every registration-before-effects check and require the
real owner callback plus its early structural gate before PCI effects.
Missing BT/DM suppliers still prevent native hardware admission. This test
does not execute the NetBSD framework or physical HP WLAN hardware.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STATE = (ROOT / "src/rtwn8723be_net80211_state.h").read_text()
NET = (ROOT / "src/rtwn8723be_net80211.c").read_text()
OPS = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
NATIVE = (ROOT / "src/rtwn8723be_native.c").read_text()

def extract(source: str, name: str) -> str:
    anchor = "\n" + name + "("
    assert source.count(anchor) == 1, name
    rest = name + "(" + source.split(anchor, 1)[1]
    start, depth = rest.index("{"), 0
    for i in range(start, len(rest)):
        if rest[i] == "{":
            depth += 1
        elif rest[i] == "}":
            depth -= 1
            if depth == 0:
                return rest[:i+1]
    raise AssertionError(name)

PRED = extract(STATE, "rtwn8723be_net80211_registration_checkpoint_ok")
REG = extract(NET, "rtwn8723be_net80211_register")
OPS_TABLE = OPS.split(
    "const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops", 1)[1]
assert ".register_ieee80211 = rtwn8723be_netbsd_register_ieee80211," in OPS_TABLE
for name in ("bt_prepare", "dm_init"):
    assert "." + name + " = rtwn8723be_netbsd_" + name + "," in OPS_TABLE
ATTACH = extract(NATIVE, "rtwn8723be_native_attach")
EARLY = ATTACH.index("error = rtwn8723be_runtime_probe_ready(sc);")
PCI = ATTACH.index("pci_get_powerstate(")
assert EARLY < PCI < ATTACH.index("error = rtwn8723be_linux_probe(")
REFUSAL = ATTACH[EARLY:ATTACH.index("pci_aprint_devinfo(")]
assert "if (error != 0)" in REFUSAL and "return;" in REFUSAL
assert "rtwn8723be_netbsd_context_fini(sc)" in REFUSAL
OWNER = (ROOT / "src/rtwn8723be_runtime_owner.c").read_text()
CALLBACK = extract(OWNER, "rtwn8723be_netbsd_register_ieee80211")
assert CALLBACK.index("rtwn8723be_net80211_register(") < CALLBACK.index(
    "rtwn8723be_rx_binding_init(") < CALLBACK.index("rtwn8723be_datapath_prepare(")
assert ".hw_start = rtwn8723be_runtime_hw_start," in CALLBACK
assert ".hw_stop = rtwn8723be_runtime_hw_stop," in CALLBACK
assert ".tx_start = rtwn8723be_net80211_tx_start," in CALLBACK
assert "rtwn8723be_net80211_register(" not in NATIVE

def contract(p: str, r: str) -> None:
    for clause in (
        "state != NULL",
        "state->stage == R23BE_STAGE_IEEE80211_REGISTER",
        "!state->started", "!state->fw_ready",
        "!state->mac_func_enable", "!state->being_init_adapter",
    ):
        assert clause in p, clause

    gates = (
        "n != &sc->sc_net80211",
        "rtwn8723be_net80211_registration_checkpoint_ok(",
        "!sc->sc_initial_pci_saved",
        "!sc->sc_mapped",
        "!sc->sc_core_initialized",
        "!sc->sc_rings_allocated",
        "!sc->sc_dma_32bit",
        "sc->sc_dmat == NULL",
        "!sc->sc_irq_lock_initialized",
        "sc->sc_irq_requested",
        "sc->sc_irq_enabled",
        "sc->sc_ih != NULL",
        "sc->sc_soft_ih != NULL",
        "sc->sc_pihp != NULL",
        "sc->sc_irq_dispatch_ready",
        "sc->sc_irq_arg != NULL",
        "sc->sc_datapath != NULL",
        "sc->sc_rx_binding != NULL",
        "sc->sc_rfkill_native.initialized",
        "sc->sc_rfkill_native.active",
        "sc->sc_rfkill_native.wq != NULL",
    )
    for clause in gates:
        assert clause in r, clause
    guard = r.index("n != &sc->sc_net80211")
    refuse = r.index("return EBUSY;", guard)
    ident = r.index("!sc->sc_package_valid")
    domain = r.index("rtwn8723be_netbsd_apply_world_regdomain(sc)")
    publish = r.index("n->sc = sc;")
    netbsd_effects = ("if_initialize(ifp);", "ieee80211_ifattach(ic);",
                      "if_percpuq_create(ifp)", "if_register(ifp);",
                      "ieee80211_media_init(ic,")
    assert 0 < guard < refuse < ident < domain < publish
    for token in gates:
        assert guard <= r.index(token) < refuse
    for token in netbsd_effects:
        assert refuse < r.index(token), token
    for clause in (
        "methods->hw_start == NULL", "methods->hw_stop == NULL",
    ):
        assert r.index(clause) < guard, clause
    assert r.index("n->registered") < guard
    assert "return ENOSYS;" in r[:guard]
    # NULL TX now binds the real consumer after all mandatory pre-effect gates.
    assign = r.index("n->methods = *methods;")
    native = r.index("n->methods.tx_start = rtwn8723be_net80211_tx_start;")
    assert assign < r.index("if (n->methods.tx_start == NULL)") < native
    assert native < r.index("if_initialize(ifp);")
    assert r.index("ieee80211_ifattach(ic);") < r.index(
        "rtwn8723be_n80211_tx_install(n);") < r.index("if_register(ifp);")

contract(PRED, REG)
mutants = (
    (PRED.replace("state != NULL", "true", 1), REG),
    (PRED.replace("state->stage == R23BE_STAGE_IEEE80211_REGISTER",
                  "true", 1), REG),
    (PRED.replace("!state->started", "true", 1), REG),
    (PRED.replace("!state->fw_ready", "true", 1), REG),
    (PRED.replace("!state->mac_func_enable", "true", 1), REG),
    (PRED.replace("!state->being_init_adapter", "true", 1), REG),
    (PRED, REG.replace("n != &sc->sc_net80211", "false", 1)),
    (PRED, REG.replace("!sc->sc_rings_allocated", "false", 1)),
    (PRED, REG.replace("!sc->sc_dma_32bit", "false", 1)),
    (PRED, REG.replace("sc->sc_dmat == NULL", "false", 1)),
    (PRED, REG.replace("sc->sc_irq_requested", "false", 1)),
    (PRED, REG.replace("sc->sc_ih != NULL", "false", 1)),
    (PRED, REG.replace("sc->sc_rx_binding != NULL", "false", 1)),
    (PRED, REG.replace("sc->sc_rfkill_native.wq != NULL", "false", 1)),
)
for i, mutant in enumerate(mutants, 1):
    assert mutant != (PRED, REG), i
    try:
        contract(*mutant)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe net80211 registration mutation {i} passed")

harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include "rtwn8723be_net80211_state.h"

static void check_clean(enum rtwn8723be_linux_stage stage, bool admitted)
{
    struct rtwn8723be_linux_state s = {0};
    s.stage = stage;
    assert(rtwn8723be_net80211_registration_checkpoint_ok(&s) == admitted);
}
int main(void)
{
    struct rtwn8723be_linux_state s = {0};
    assert(!rtwn8723be_net80211_registration_checkpoint_ok(NULL));
    check_clean(R23BE_STAGE_IDLE, false);
    check_clean(R23BE_STAGE_CORE_INIT, false);
    check_clean(R23BE_STAGE_PCI_RINGS, false);
    check_clean(R23BE_STAGE_IEEE80211_REGISTER, true);
    check_clean(R23BE_STAGE_RFKILL, false);
    check_clean(R23BE_STAGE_IRQ_ESTABLISH, false);
    check_clean(R23BE_STAGE_PROBED, false);
    check_clean(R23BE_STAGE_RESET_RINGS, false);
    check_clean(R23BE_STAGE_RUNNING, false);
    check_clean(R23BE_STAGE_STOPPING, false);
    check_clean(R23BE_STAGE_STOPPED, false);
    s.stage=R23BE_STAGE_IEEE80211_REGISTER;
    s.started=true;
    assert(!rtwn8723be_net80211_registration_checkpoint_ok(&s));
    s.started=false;
    s.fw_ready=true;
    assert(!rtwn8723be_net80211_registration_checkpoint_ok(&s));
    s.fw_ready=false;
    s.mac_func_enable=true;
    assert(!rtwn8723be_net80211_registration_checkpoint_ok(&s));
    s.mac_func_enable=false;
    s.being_init_adapter=true;
    assert(!rtwn8723be_net80211_registration_checkpoint_ok(&s));
    puts("RTL_NET80211_PREREGISTRATION_STAGE_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-n80211-prereg-") as td:
    source = Path(td) / "check.c"
    exe = Path(td) / "check"
    source.write_text(harness)
    subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror",
                    "-pedantic","-fsanitize=undefined",
                    "-fno-sanitize-recover=all",
                    "-I",str(ROOT/"src"),str(source),"-o",str(exe)],
                   check=True)
    subprocess.run([str(exe)],check=True)
print("RTL_NET80211_PREREGISTRATION_SOURCE_MUTATIONS_OK negatives=14")
