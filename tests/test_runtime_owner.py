#!/usr/bin/env python3
"""Keep the RTL runtime-owner foundation inert and lifecycle-only.

This is deliberately a source-contract test: it protects the initial owner
from absorbing the stale frozen runtime's DMA, IRQ, net80211, workqueue and
coexistence responsibilities before their real NetBSD lifetime exists.
"""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OWNER_H = SRC / "rtwn8723be_runtime_owner.h"
OWNER_C = SRC / "rtwn8723be_runtime_owner.c"
NETBSD_H = SRC / "rtwn8723be_netbsd.h"
NETBSD_C = SRC / "rtwn8723be_netbsd.c"
MANIFEST = ROOT / "config" / "files.rtwn8723be_native"


def ordered(text: str, tokens: tuple[str, ...], label: str) -> None:
    positions = [text.find(token) for token in tokens]
    assert all(pos >= 0 for pos in positions), f"{label}: missing {tokens!r}"
    assert positions == sorted(positions), f"{label}: wrong order {tokens!r}"


def owner_body(text: str, name: str, following: str) -> str:
    prefix = f"void\n{name}("
    assert prefix in text, f"missing {name} definition"
    body = text.split(prefix, 1)[1]
    assert following in body, f"missing {name} boundary"
    return body.split(following, 1)[0]


def check_owner_body(text: str) -> None:
    init = owner_body(text, "rtwn8723be_runtime_owner_init",
                      "\n}\n\nvoid\nrtwn8723be_runtime_owner_fini")
    fini = owner_body(text, "rtwn8723be_runtime_owner_fini", "\n}\n")
    assert init.count("MUTEX_DEFAULT, IPL_NONE") == 2
    ordered(init, (
        "mutex_init(&owner->lifecycle_lock, MUTEX_DEFAULT, IPL_NONE);",
        "mutex_init(&owner->io_lock, MUTEX_DEFAULT, IPL_NONE);",
        "owner->io_depth = 0;",
        "owner->closing = false;",
        "owner->initialized = true;",
    ), "runtime-owner init")
    ordered(fini, (
        "owner->closing = true;",
        "KASSERT(owner->io_depth == 0);",
        "mutex_destroy(&owner->io_lock);",
        "mutex_destroy(&owner->lifecycle_lock);",
        "owner->initialized = false;",
    ), "runtime-owner fini")


assert OWNER_H.is_file(), "runtime-owner header missing"
assert OWNER_C.is_file(), "runtime-owner implementation missing"
owner_h = OWNER_H.read_text()
owner_c = OWNER_C.read_text()
netbsd_h = NETBSD_H.read_text()
netbsd_c = NETBSD_C.read_text()
manifest = MANIFEST.read_text()

ordered(owner_h, (
    "kmutex_t lifecycle_lock;",
    "kmutex_t io_lock;",
    "unsigned int io_depth;",
    "bool initialized;",
    "bool closing;",
), "runtime-owner layout")
assert "lifecycle_lock -> io_lock" in owner_h
assert "struct rtwn8723be_runtime_owner sc_runtime_owner;" in netbsd_h
ordered(netbsd_h, (
    "struct rtwn8723be_linux_state sc_linux;",
    "struct rtwn8723be_runtime_owner sc_runtime_owner;",
    "struct rtwn8723be_h2c_native sc_h2c;",
), "softc runtime-owner placement")

assert manifest.count("rtwn8723be_runtime_owner.c") == 1
native_units = re.findall(
    r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native$",
    manifest, re.M)
assert len(native_units) == 46 and len(set(native_units)) == 46

check_owner_body(owner_c)
for forbidden in (
        "pci_", "bus_", "dma", "ieee80211", "workqueue", "callout",
        "btc", "rtwn8723be_linux_adapter", "rtwn8723be_write_",
        "rtwn8723be_read_"):
    assert forbidden not in owner_c.lower(), f"runtime owner is not inert: {forbidden}"

init_context = owner_body(netbsd_c, "rtwn8723be_netbsd_context_init",
                          "\n}\n\nvoid\nrtwn8723be_netbsd_context_fini")
fini_context = owner_body(netbsd_c, "rtwn8723be_netbsd_context_fini",
                          "\n}\n\nbool\nrtwn8723be_netbsd_rf_change_owned")
ordered(init_context, (
    "memset(sc, 0, sizeof(*sc));",
    "rtwn8723be_runtime_owner_init(sc);",
), "context runtime-owner init")
ordered(fini_context, (
    "mutex_destroy(&sc->sc_irq_lock);",
    "mutex_destroy(&sc->sc_rf_ps_lock);",
    "rtwn8723be_runtime_owner_fini(sc);",
), "context runtime-owner fini")

# Negative controls prove the assertions reject the two most dangerous
# accidental changes: an interrupt-level mutex and destruction with I/O live.
for bad in (
        owner_c.replace("MUTEX_DEFAULT, IPL_NONE", "MUTEX_DEFAULT, IPL_NET", 1),
        owner_c.replace("KASSERT(owner->io_depth == 0);", "", 1)):
    try:
        check_owner_body(bad)
    except AssertionError:
        pass
    else:
        raise AssertionError("runtime-owner negative control was accepted")

print("RTL_RUNTIME_OWNER_CONTRACT_OK")
