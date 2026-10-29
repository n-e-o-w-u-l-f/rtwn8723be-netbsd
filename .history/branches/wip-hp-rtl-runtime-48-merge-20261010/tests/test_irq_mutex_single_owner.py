#!/usr/bin/env python3
"""Catch duplicate softc IRQ mutex ownership across RTL PCI and runtime paths.

This source-lifecycle regression is not a substitute for the real HP kernel
compile, IRQ, detach/unwind, RF, receive or WPA2 acceptance tests.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
context = (SRC / "rtwn8723be_netbsd.c").read_text()
runtime = (SRC / "rtwn8723be_runtime.c").read_text()
native = (SRC / "rtwn8723be_native.c").read_text()

assert context.count("mutex_init(&sc->sc_irq_lock,") == 1, (
    "Only NetBSD PCI context_init may initialize the IRQ mutex"
)
assert context.count("mutex_destroy(&sc->sc_irq_lock)") == 1, (
    "Only NetBSD PCI context_fini may destroy the IRQ mutex"
)
assert "sc->sc_irq_lock_initialized = true;" in context
assert "sc->sc_irq_lock_initialized = false;" in context
assert "KASSERT(!sc->sc_irq_requested);" in context
assert "KASSERT(!sc->sc_irq_enabled);" in context
assert "sc->sc_ih == NULL && sc->sc_soft_ih == NULL" in context

for forbidden in (
    "mutex_init(&sc->sc_irq_lock,",
    "mutex_destroy(&sc->sc_irq_lock)",
    "sc->sc_irq_lock_initialized = false;",
    "sc->sc_irq_lock_initialized = true;",
):
    assert forbidden not in runtime, f"Runtime must not own IRQ mutex: {forbidden}"

assert "KASSERT(sc->sc_irq_lock_initialized);" in runtime
assert "if (r == NULL || !runtime_thread())" in runtime
assert "r->net.registered || sc->sc_linux.started" in runtime
assert "sc->sc_ih != NULL || sc->sc_soft_ih != NULL" in runtime
assert "rtwn8723be_netbsd_context_init(sc, self, pa);" in native
assert "rtwn8723be_netbsd_context_fini(sc);" in native

print("RTL_IRQ_MUTEX_SINGLE_OWNER_SOURCE_PASS")
