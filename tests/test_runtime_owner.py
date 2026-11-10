#!/usr/bin/env python3
"""Guard the admitted runtime-owner structure and release-build teardown.

Executable orchestration and IRQ ordering are covered by the separate compiled
production-C fixtures. This source contract retains the ban on obsolete runtime
imports and direct unowned hardware/worker operations; it is not runtime proof.
"""
from pathlib import Path
import re
from runtime_owner_fixture import function

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
owner_h = (SRC / "rtwn8723be_runtime_owner.h").read_text()
owner_c = (SRC / "rtwn8723be_runtime_owner.c").read_text()
netbsd_h = (SRC / "rtwn8723be_netbsd.h").read_text()
netbsd_c = (SRC / "rtwn8723be_netbsd.c").read_text()
native_c = (SRC / "rtwn8723be_native.c").read_text()
linux_c = (SRC / "rtwn8723be_linux_state.c").read_text()
manifest = (ROOT / "config/files.rtwn8723be_native").read_text()

def ordered(source, tokens):
    positions = [source.index(token) for token in tokens]
    assert positions == sorted(positions), tokens

def contract(owner, native, context):
    init = function(owner, "rtwn8723be_runtime_owner_init")
    fini = function(owner, "rtwn8723be_runtime_owner_fini")
    claim = function(owner, "runtime_claim")
    assert '#include <sys/cpu.h>' in owner
    ordered(init, (
        "mutex_init(&owner->lifecycle_lock, MUTEX_DEFAULT, IPL_NET);",
        "mutex_init(&owner->io_lock, MUTEX_DEFAULT, IPL_NONE);",
        "owner->io_depth = 0;",
        "owner->operation = R23BE_RUNTIME_NONE;",
        "owner->operation_lwp = NULL;",
        "owner->context = NULL;",
        "owner->initialized = true;",
    ))
    assert "runtime_caller_locks_held(sc)" in claim
    assert "owner->operation != R23BE_RUNTIME_NONE" in claim
    assert "owner->operation_lwp != NULL || owner->io_depth != 0" in claim
    assert "owner->closing || owner->io_depth != 0" in fini
    assert "runtime_publication_present(sc)" in fini
    assert "runtime_private_publication_present(owner->context)" in fini
    assert "return EBUSY;" in fini and "return EWOULDBLOCK;" in fini
    ordered(fini[fini.index("owner->closing = true;"):], (
        "owner->closing = true;",
        "owner->operation = R23BE_RUNTIME_RETIRE;",
        "owner->context = NULL;",
        "mutex_exit(&owner->lifecycle_lock);",
        "kmem_free(ctx, sizeof(*ctx));",
        "mutex_destroy(&owner->io_lock);",
        "mutex_destroy(&owner->lifecycle_lock);",
        "owner->initialized = false;",
    ))
    outer = function(context, "rtwn8723be_netbsd_context_fini")
    assert outer.startswith("int\n")
    ordered(outer, (
        "error = rtwn8723be_runtime_owner_fini(sc);",
        "if (error != 0)",
        "return error;",
        "mutex_destroy(&sc->sc_irq_lock);",
        "mutex_destroy(&sc->sc_rf_ps_lock);",
    ))
    attach = function(native, "rtwn8723be_native_attach")
    ordered(attach, (
        "rtwn8723be_netbsd_context_init(sc, self, pa);",
        "error = rtwn8723be_runtime_probe_ready(sc);",
        "if (error != 0)",
        "return;",
        "pci_get_powerstate(",
        "error = rtwn8723be_linux_probe(",
    ))
    assert "return rtwn8723be_netbsd_context_fini(sc);" in function(
        native, "rtwn8723be_native_detach")
    for obsolete in (
        '#include "rtwn8723be_runtime.h"',
        "struct rtwn8723be_runtime ",
        "rtwn8723be_read_", "rtwn8723be_write_",
        "pci_conf_write(", "bus_dmamap_", "workqueue_create(",
        "callout_schedule(",
    ):
        assert obsolete not in owner, obsolete

assert "struct rtwn8723be_runtime_owner sc_runtime_owner;" in netbsd_h
ordered(netbsd_h, (
    "struct rtwn8723be_linux_state sc_linux;",
    "struct rtwn8723be_runtime_owner sc_runtime_owner;",
    "struct rtwn8723be_h2c_native sc_h2c;",
))
for token in (
    "unsigned int io_depth;", "enum rtwn8723be_runtime_operation operation;",
    "struct lwp *operation_lwp;", "struct rtwn8723be_runtime_context *context;",
    "Never block acquiring io_lock while lifecycle_lock is held.",
):
    assert token in owner_h, token
for name in ("configure", "fini"):
    assert "int rtwn8723be_runtime_owner_" + name + "(" in owner_h
assert manifest.count("rtwn8723be_runtime_owner.c") == 1
units = re.findall(
    r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native$",
    manifest, re.M)
assert len(units) == 49 and len(set(units)) == 49
ready = function(linux_c, "rtwn8723be_linux_runtime_ops_ready")
assert "rtwn8723be_start_ops_ready(ops)" in ready
assert "rtwn8723be_stop_ops_ready(ops)" in ready
contract(owner_c, native_c, netbsd_c)

negative = (
    (owner_c.replace("lifecycle_lock, MUTEX_DEFAULT, IPL_NET",
                     "lifecycle_lock, MUTEX_DEFAULT, IPL_NONE", 1),
     native_c, netbsd_c),
    (owner_c.replace("owner->closing || owner->io_depth != 0",
                     "owner->closing", 1), native_c, netbsd_c),
    (owner_c, native_c,
     netbsd_c.replace("error = rtwn8723be_runtime_owner_fini(sc);",
                      "error = 0;", 1)),
    (owner_c, native_c.replace(
        "error = rtwn8723be_runtime_probe_ready(sc);", "error = 0;", 1),
     netbsd_c),
)
for altered in negative:
    assert altered != (owner_c, native_c, netbsd_c)
    try:
        contract(*altered)
    except (AssertionError, ValueError):
        continue
    raise AssertionError("unsafe runtime owner source mutation accepted")
print("RTL_RUNTIME_OWNER_CONTRACT_OK source_negatives=4 native_units=49 "
      "compiled_orchestration=separate physical_runtime=OPEN")
