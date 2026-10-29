#!/usr/bin/env python3
"""RTL8723BE hard-IRQ/softint permanent-stop race source and negative gates.

Source-structure checks only; actual NetBSD hard/soft IRQ concurrency and
hardware W1C/IRQ effects remain full-kernel/HP-runtime acceptance gates.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
header = (ROOT / "src/rtwn8723be_netbsd.h").read_text()


def function(src: str, name: str) -> str:
    # Resolve exactly the kernel function definition, not a call site.
    import re
    expression = re.compile(
        r"(?m)^(?:static\s+)?(?:int|void)\s*\n" +
        re.escape(name) + r"\([^;{}]*\)\n\{")
    matches = list(expression.finditer(src))
    assert len(matches) == 1, (name, len(matches))
    begin = matches[0].start()
    end = src.index("\n}\n", matches[0].end()) + 3
    return src[begin:end]


def contract(c_src: str, h_src: str) -> None:
    start = function(c_src, "rtwn8723be_netbsd_context_init")
    done = function(c_src, "rtwn8723be_netbsd_context_fini")
    arm = function(c_src, "rtwn8723be_netbsd_irq_arm_locked")
    mask = function(c_src, "rtwn8723be_netbsd_irq_mask_locked")
    rearm = function(c_src, "rtwn8723be_netbsd_irq_rearm_if_requested")
    enable = function(c_src, "rtwn8723be_netbsd_enable_interrupt")
    disable = function(c_src, "rtwn8723be_netbsd_disable_interrupt")
    hard = function(c_src, "rtwn8723be_netbsd_intr")
    soft = function(c_src, "rtwn8723be_netbsd_softintr")
    disestablish = function(c_src, "rtwn8723be_netbsd_disestablish_irq")

    for token in ("kmutex_t sc_irq_lock;", "bool sc_irq_lock_initialized;",
                  "bool sc_irq_requested;", "bool sc_irq_enabled;"):
        assert token in h_src, token
    assert "mutex_init(&sc->sc_irq_lock, MUTEX_DEFAULT, IPL_NET);" in start
    assert "sc->sc_irq_lock_initialized = true;" in start
    assert "mutex_destroy(&sc->sc_irq_lock);" in done
    assert done.index("KASSERT(!sc->sc_irq_requested);") < done.index(
        "mutex_destroy(&sc->sc_irq_lock);")
    assert "KASSERT(!sc->sc_irq_enabled);" in done

    assert "R23BE_REG_HIMR, 0" in mask
    assert "R23BE_REG_HIMRE, 0" in mask
    assert "sc->sc_irq_enabled = false;" in mask
    assert "R23BE_REG_HIMR, sc->sc_irq_mask[0]" in arm
    assert "R23BE_REG_HIMRE, sc->sc_irq_mask[1]" in arm
    assert arm.index("sc->sc_irq_enabled = true;") < arm.index(
        "R23BE_REG_HSIMR, sc->sc_sys_irq_mask")

    for body in (enable, disable, hard, rearm):
        assert "mutex_enter(&sc->sc_irq_lock);" in body
        assert "mutex_exit(&sc->sc_irq_lock);" in body

    assert enable.index("sc->sc_irq_requested = true;") < enable.index(
        "rtwn8723be_netbsd_irq_arm_locked(sc);")
    assert disable.index("sc->sc_irq_requested = false;") < disable.index(
        "rtwn8723be_netbsd_irq_mask_locked(sc);")
    assert "rtwn8723be_netbsd_disable_interrupt(sc)" in disestablish

    # A hard interrupt MUST NOT call the owner's permanent disable:
    # it preserves the desire state until the soft interrupt drains.
    assert "rtwn8723be_netbsd_disable_interrupt(sc)" not in hard
    assert "rtwn8723be_netbsd_enable_interrupt(sc)" not in hard
    assert "rtwn8723be_netbsd_irq_mask_locked(sc);" in hard
    assert "if (!sc->sc_irq_requested || !sc->sc_irq_enabled)" in hard
    assert "rtwn8723be_netbsd_irq_rearm_if_requested(sc);" in hard
    assert "rtwn8723be_netbsd_enable_interrupt(sc)" not in soft
    assert "rtwn8723be_netbsd_irq_rearm_if_requested(sc);" in soft

    # Guard the exact permanent-stop vs asynchronous rearm race under
    # the SAME NetBSD spin mutex (not a naked pre-lock check).
    want = "sc->sc_irq_requested && sc->sc_mapped &&"
    assert want in rearm
    assert rearm.index("mutex_enter(&sc->sc_irq_lock);") < rearm.index(want)
    assert rearm.index(want) < rearm.index(
        "rtwn8723be_netbsd_irq_arm_locked(sc);")
    assert rearm.index("rtwn8723be_netbsd_irq_arm_locked(sc);") < rearm.index(
        "mutex_exit(&sc->sc_irq_lock);")
    assert "sc->sc_ih != NULL && sc->sc_soft_ih != NULL" in rearm

contract(source, header)

# Source-level negative controls. A mutation must demonstrably invalidate
# the exact guarded contract, not merely produce a differently worded comment.
negative = (
    (source.replace("sc->sc_irq_requested = false;",
                    "sc->sc_irq_requested = true;", 1), header),
    (source.replace("sc->sc_irq_requested && sc->sc_mapped &&",
                    "sc->sc_mapped &&", 1), header),
    (source.replace("rtwn8723be_netbsd_irq_mask_locked(sc);\n"
                    "    mutex_exit(&sc->sc_irq_lock);\n\n    rawa",
                    "rtwn8723be_netbsd_disable_interrupt(sc);\n"
                    "    mutex_exit(&sc->sc_irq_lock);\n\n    rawa", 1), header),
    (source.replace("mutex_init(&sc->sc_irq_lock, MUTEX_DEFAULT, IPL_NET);",
                    "mutex_init(&sc->sc_irq_lock, MUTEX_DEFAULT, IPL_NONE);", 1),
     header),
)
for count, (mutated, h_src) in enumerate(negative, 1):
    assert mutated != source, ("mutation did not target actual source", count)
    try:
        contract(mutated, h_src)
    except (AssertionError, ValueError):
        # A removed required source token fails via index(), not assert.
        continue
    raise AssertionError("IRQ stop/rearm unsafe mutation accepted: " + str(count))

print("RTL_IRQ_HARD_SOFT_STOP_RACE_SOURCE_CONTRACT_OK negatives=4 "
      "owner-IPL_NET serialization=source-only "
      "full-native-IRQ-hardware=OPEN")
