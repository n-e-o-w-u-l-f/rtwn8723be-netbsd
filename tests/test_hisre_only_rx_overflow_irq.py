#!/usr/bin/env python3
"""Execute real NetBSD hard IRQ, softint and STOP for HISRE-only RX overflow.

HISRE RXFOVW is an independent RX event. Hard IRQ must not ACK and discard
it because the first-bank HISR interrupt vector is empty. Tests compile
actual production C bodies under strict portable C11 and UBSan, including
pending ledger, IRQ mask/rearm/disable and softint dispatch.

Not a native NetBSD kernel, SMP, PCI, bus_space or DMA hardware test.
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
F16 = (ROOT / "src/rtwn8723be_f16_1.h").read_text()
PENDING = (ROOT / "src/rtwn8723be_irq_pending.h").read_text()

def func(name: str, ret: str) -> str:
    marker = "\n" + name + "("
    assert SOURCE.count(marker) == 1, name
    fragment = name + "(" + SOURCE.split(marker, 1)[1]
    depth = 0
    for i in range(fragment.index("{"), len(fragment)):
        if fragment[i] == "{":
            depth += 1
        elif fragment[i] == "}":
            depth -= 1
            if depth == 0:
                return ret + "\n" + fragment[:i + 1]
    raise AssertionError(name)

mask = func("rtwn8723be_netbsd_irq_mask_locked", "static void")
arm = func("rtwn8723be_netbsd_irq_arm_locked", "static void")
rearm = func("rtwn8723be_netbsd_irq_rearm_if_requested", "static void")
enable = func("rtwn8723be_netbsd_enable_interrupt", "int")
disable = func("rtwn8723be_netbsd_disable_interrupt", "int")
hard = func("rtwn8723be_netbsd_intr", "static int")
soft = func("rtwn8723be_netbsd_softintr", "static void")

def contract(hard_src: str, soft_src: str, rearm_src: str) -> None:
    empty = "if ((inta | intb) == 0 || inta == 0xffffU)"
    assert empty in hard_src
    assert "if (inta == 0 || inta == 0xffffU)" not in hard_src
    assert hard_src.index("intb = rawb & sc->sc_irq_mask[1];") < (
        hard_src.index(empty))
    for token in (
        "rtwn8723be_write_4(sc, R23BE_REG_HISR, inta);",
        "rtwn8723be_write_4(sc, R23BE_REG_HISRE, intb);",
        "rtwn8723be_irq_pending_record(sc->sc_irq_pending,",
        "softint_schedule(sc->sc_soft_ih);",
    ):
        assert token in hard_src
    assert hard_src.index(empty) < hard_src.index(
        "rtwn8723be_irq_pending_record(sc->sc_irq_pending,")
    assert "sc->sc_irq_requested, sc->sc_irq_dispatch_ready, inta, intb" in hard_src
    assert "if (!rtwn8723be_irq_pending_take(sc->sc_irq_pending," in soft_src
    assert "sc->sc_irq_requested, sc->sc_irq_dispatch_ready, &inta, &intb" in soft_src
    assert "if ((inta & (R23BE_IMR_ROK | R23BE_IMR_RDU)) != 0 ||" in soft_src
    assert "(intb & R23BE_IMR_RXFOVW) != 0)" in soft_src
    assert "sc->sc_irq_dispatch.rx(sc->sc_irq_arg);" in soft_src
    assert soft_src.index("rtwn8723be_irq_pending_take(") < (
        soft_src.index("sc->sc_irq_dispatch.rx("))
    assert "rtwn8723be_netbsd_irq_rearm_if_requested(sc);" in soft_src
    assert "sc->sc_irq_requested && sc->sc_mapped &&" in rearm_src
    assert "sc->sc_ih != NULL && sc->sc_soft_ih != NULL &&" in rearm_src
    assert "sc->sc_irq_dispatch_ready" in rearm_src
    assert '#include "rtwn8723be_irq_pending.h"' in SOURCE
    assert "#define R23BE_IMR1_DEFAULT R23BE_IMR_RXFOVW" in F16
    assert "pending[1] |= intb;" in PENDING

contract(hard, soft, rearm)

def verify_epoch(e: str, d: str, h: str) -> None:
    begin = e.index("if (!sc->sc_irq_requested) {")
    cleared = e.index("rtwn8723be_irq_pending_clear(sc->sc_irq_pending);", begin)
    generation = e.index("sc->sc_irq_epoch++;", begin)
    new_owner = e.index("sc->sc_irq_requested = true;", begin)
    assert begin < cleared < generation < new_owner
    assert e.index("mutex_enter(&sc->sc_irq_lock);") < begin < (
        e.index("mutex_exit(&sc->sc_irq_lock);"))

    stop = d.index("sc->sc_irq_requested = false;")
    age = d.index("sc->sc_irq_epoch++;", stop)
    wipe = d.index("rtwn8723be_irq_pending_clear(sc->sc_irq_pending);", age)
    out = d.index("mutex_exit(&sc->sc_irq_lock);", wipe)
    assert stop < age < wipe < out
    assert d.index("mutex_enter(&sc->sc_irq_lock);") < stop
    assert "irq_epoch = sc->sc_irq_epoch;" in h
    assert h.index("irq_epoch = sc->sc_irq_epoch;") < h.index(
        "rtwn8723be_read_4(sc, R23BE_REG_HISR);")
    assert h.index("irq_epoch != sc->sc_irq_epoch ||") < h.index(
        "rtwn8723be_irq_pending_record(sc->sc_irq_pending,")
    assert h.index("mutex_enter(&sc->sc_irq_lock);", h.index(
        "if ((inta | intb) == 0 || inta == 0xffffU)")) < h.index(
        "irq_epoch != sc->sc_irq_epoch ||")

verify_epoch(enable, disable, hard)
epoch_mutants = (
    (enable.replace("if (!sc->sc_irq_requested) {", "if (false) {", 1), disable, hard),
    (enable.replace("rtwn8723be_irq_pending_clear(sc->sc_irq_pending);", "", 1), disable, hard),
    (enable.replace("sc->sc_irq_epoch++;", "", 1), disable, hard),
    (enable, disable.replace("sc->sc_irq_epoch++;", "", 1), hard),
    (enable, disable.replace("rtwn8723be_irq_pending_clear(sc->sc_irq_pending);", "", 1), hard),
    (enable, disable, hard.replace("irq_epoch = sc->sc_irq_epoch;", "", 1)),
    (enable, disable, hard.replace("irq_epoch != sc->sc_irq_epoch ||", "", 1)),
)
for i, candidate in enumerate(epoch_mutants, 1):
    assert candidate != (enable, disable, hard), i
    try:
        verify_epoch(*candidate)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe STOP/restart IRQ epoch mutation {i}")

mutants = (
    (hard.replace("(inta | intb) == 0", "inta == 0", 1), soft, rearm),
    (hard.replace("inta == 0xffffU", "false", 1), soft, rearm),
    (hard.replace("intb = rawb & sc->sc_irq_mask[1];",
                  "intb = 0;", 1), soft, rearm),
    (hard.replace("rtwn8723be_write_4(sc, R23BE_REG_HISRE, intb);",
                  "/* lost overflow ACK */", 1), soft, rearm),
    (hard.replace("rtwn8723be_irq_pending_record(sc->sc_irq_pending,",
                  "discard_overflow(sc->sc_irq_pending,", 1), soft, rearm),
    (hard.replace("softint_schedule(sc->sc_soft_ih);",
                  "/* missed scheduled softint */", 1), soft, rearm),
    (hard, soft.replace("(intb & R23BE_IMR_RXFOVW) != 0)",
                        "false)", 1), rearm),
    (hard, soft.replace("rtwn8723be_irq_pending_take(",
                        "discard_pending(", 1), rearm),
    (hard, soft.replace("sc->sc_irq_dispatch.rx(sc->sc_irq_arg);",
                        "/* no RX overflow service */", 1), rearm),
    (hard, soft, rearm.replace("sc->sc_irq_requested &&",
                              "true &&", 1)),
    (hard, soft, rearm.replace("sc->sc_irq_dispatch_ready",
                              "true", 1)),
)
for i, candidate in enumerate(mutants, 1):
    assert candidate != (hard, soft, rearm), i
    try:
        contract(*candidate)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe HISRE-only IRQ source mutation {i}")

macros = [
    "R23BE_REG_HISR", "R23BE_REG_HISRE",
    "R23BE_REG_HIMR", "R23BE_REG_HIMRE", "R23BE_REG_HSIMR",
    "R23BE_REG_HSISR",
    "R23BE_IMR_RXFOVW", "R23BE_IMR_ROK", "R23BE_IMR_RDU",
    "R23BE_IMR_MGNTDOK", "R23BE_IMR_HIGHDOK",
    "R23BE_IMR_BKDOK", "R23BE_IMR_BEDOK",
    "R23BE_IMR_VIDOK", "R23BE_IMR_VODOK",
    "R23BE_IMR_HSISR_IND_ON_INT",
    "RTWN8723BE_MGNT_QUEUE", "RTWN8723BE_HIGH_QUEUE",
    "RTWN8723BE_BK_QUEUE", "RTWN8723BE_BE_QUEUE",
    "RTWN8723BE_VI_QUEUE", "RTWN8723BE_VO_QUEUE",
]
defines = []
for macro in macros:
    match = re.search(r"(?m)^#define\s+" + re.escape(macro) +
                      r"\s+[^\n\\]+$", F16)
    assert match is not None, macro
    defines.append(match.group(0))

prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_irq_pending.h"

typedef struct { bool held; } kmutex_t;
struct rtwn8723be_irq_dispatch {
    void (*rx)(void *);
    void (*tx_done)(void *, unsigned int);
    void (*power_event)(void *);
};
struct rtwn8723be_softc {
    kmutex_t sc_irq_lock;
    bool sc_irq_lock_initialized, sc_irq_requested, sc_irq_enabled;
    bool sc_irq_dispatch_ready, sc_mapped;
    void *sc_ih, *sc_soft_ih, *sc_irq_arg;
    uint32_t sc_irq_mask[2], sc_sys_irq_mask;
    volatile uint32_t sc_irq_pending[2];
    uint32_t sc_irq_epoch;
    struct rtwn8723be_irq_dispatch sc_irq_dispatch;
};
static uint32_t raw_hisr, raw_hisre, mmio_himr, mmio_himre;
static int enter_count, exit_count, schedule_count, rx_count, tx_count;
static int hisr_acks, hisre_acks, mmio_masks, mmio_arms, stop_on_read, stop_on_schedule;
static void mutex_enter(kmutex_t *m)
{ assert(m && !m->held); m->held = true; enter_count++; }
static void mutex_exit(kmutex_t *m)
{ assert(m && m->held); m->held = false; exit_count++; }
static int rtwn8723be_netbsd_disable_interrupt(void *);
static uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *sc, int reg)
{
    assert(sc && !sc->sc_irq_lock.held);
    if (reg == R23BE_REG_HISR)
        return raw_hisr;
    assert(reg == R23BE_REG_HISRE);
    if (stop_on_read) {
        int mode = stop_on_read;
        stop_on_read = 0;
        assert(rtwn8723be_netbsd_disable_interrupt(sc) == 0);
        if (mode == 2)
            assert(rtwn8723be_netbsd_enable_interrupt(sc) == 0);
    }
    return raw_hisre;
}
static void rtwn8723be_write_4(struct rtwn8723be_softc *sc,
    int reg, uint32_t value)
{
    assert(sc && sc->sc_irq_lock.held == (
        reg == R23BE_REG_HIMR || reg == R23BE_REG_HIMRE ||
        reg == R23BE_REG_HSIMR));
    if (reg == R23BE_REG_HISR) {
        assert(value == (raw_hisr & sc->sc_irq_mask[0]));
        hisr_acks++;
    } else if (reg == R23BE_REG_HISRE) {
        assert(value == (raw_hisre & sc->sc_irq_mask[1]));
        hisre_acks++;
    } else if (reg == R23BE_REG_HIMR) {
        mmio_himr = value;
        if (value == 0) mmio_masks++;
        else mmio_arms++;
    } else if (reg == R23BE_REG_HIMRE) {
        mmio_himre = value;
    } else {
        assert(reg == R23BE_REG_HSIMR);
    }
}
static uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *sc, int reg)
{ assert(sc && reg == R23BE_REG_HSISR); return 0; }
static void rtwn8723be_write_1(struct rtwn8723be_softc *sc,
    int reg, uint8_t v)
{ assert(sc && reg == R23BE_REG_HSISR); (void)v; }
static void softint_schedule(void *soft)
{
    struct rtwn8723be_softc *sc = soft;
    assert(sc && sc->sc_soft_ih == sc);
    schedule_count++;
    if (stop_on_schedule)
        assert(rtwn8723be_netbsd_disable_interrupt(sc) == 0);
}
static void receive(void *p)
{ struct rtwn8723be_softc *sc = p; assert(sc); rx_count++; }
static void complete(void *p, unsigned int queue)
{ struct rtwn8723be_softc *sc = p; assert(sc); (void)queue; tx_count++; }
'''
tail = r'''
static void setup(struct rtwn8723be_softc *sc)
{
    *sc = (struct rtwn8723be_softc){0};
    sc->sc_irq_lock_initialized = true;
    sc->sc_mapped = sc->sc_irq_dispatch_ready = true;
    sc->sc_irq_arg = sc;
    sc->sc_ih = sc;
    sc->sc_soft_ih = sc;
    sc->sc_irq_mask[0] = R23BE_IMR_ROK | R23BE_IMR_RDU |
        R23BE_IMR_BEDOK | R23BE_IMR_HSISR_IND_ON_INT;
    sc->sc_irq_mask[1] = R23BE_IMR_RXFOVW;
    sc->sc_irq_dispatch.rx = receive;
    sc->sc_irq_dispatch.tx_done = complete;
    sc->sc_sys_irq_mask = 0x3;
    raw_hisr = raw_hisre = mmio_himr = mmio_himre = 0;
    enter_count = exit_count = schedule_count = rx_count = tx_count = 0;
    hisr_acks = hisre_acks = mmio_masks = mmio_arms = 0;
    stop_on_read = stop_on_schedule = 0;
    assert(rtwn8723be_netbsd_enable_interrupt(sc) == 0);
    assert(sc->sc_irq_requested && sc->sc_irq_enabled);
    assert(sc->sc_irq_epoch == 1);
    assert(sc->sc_irq_pending[0] == 0 && sc->sc_irq_pending[1] == 0);
}
static void balanced(struct rtwn8723be_softc *sc)
{
    assert(enter_count == exit_count);
    assert(!sc->sc_irq_lock.held);
}
int main(void)
{
    struct rtwn8723be_softc sc;

    /* The specific regression: only second-bank RX overflow is asserted. */
    setup(&sc);
    raw_hisre = R23BE_IMR_RXFOVW;
    assert(rtwn8723be_netbsd_intr(&sc) == 1);
    assert(hisr_acks == 0 && hisre_acks == 1);
    assert(schedule_count == 1);
    assert(sc.sc_irq_pending[0] == 0);
    assert(sc.sc_irq_pending[1] == R23BE_IMR_RXFOVW);
    assert(!sc.sc_irq_enabled);
    rtwn8723be_netbsd_softintr(&sc);
    assert(rx_count == 1 && tx_count == 0);
    assert(sc.sc_irq_pending[0] == 0 && sc.sc_irq_pending[1] == 0);
    assert(sc.sc_irq_enabled && mmio_himr == sc.sc_irq_mask[0] &&
           mmio_himre == sc.sc_irq_mask[1]);
    balanced(&sc);

    /* Both interrupt banks may be pending simultaneously. */
    setup(&sc);
    raw_hisr = R23BE_IMR_ROK | R23BE_IMR_BEDOK;
    raw_hisre = R23BE_IMR_RXFOVW;
    assert(rtwn8723be_netbsd_intr(&sc) == 1);
    assert(hisr_acks == 1 && hisre_acks == 1);
    rtwn8723be_netbsd_softintr(&sc);
    assert(rx_count == 1 && tx_count == 1 && schedule_count == 1);
    balanced(&sc);

    /* Empty or unsupported-bank vector still belongs to a shared IRQ. */
    setup(&sc);
    assert(rtwn8723be_netbsd_intr(&sc) == 0);
    assert(schedule_count == 0 && sc.sc_irq_enabled);
    assert(hisr_acks == 0 && hisre_acks == 0);
    balanced(&sc);
    setup(&sc);
    raw_hisre = R23BE_IMR_RXFOVW << 1;
    assert(rtwn8723be_netbsd_intr(&sc) == 0);
    assert(schedule_count == 0 && hisre_acks == 0);
    balanced(&sc);

    /* All-ones bus read is inaccessible, never use it as a valid IRQ. */
    setup(&sc);
    raw_hisr = UINT32_MAX;
    assert(rtwn8723be_netbsd_intr(&sc) == 0);
    assert(schedule_count == 0 && sc.sc_irq_enabled);
    balanced(&sc);

    /* STOP while reading HISRE must not publish a softint event. */
    setup(&sc);
    raw_hisre = R23BE_IMR_RXFOVW;
    stop_on_read = 1;
    assert(rtwn8723be_netbsd_intr(&sc) == 0);
    assert(schedule_count == 0 && !sc.sc_irq_requested &&
           !sc.sc_irq_enabled);
    assert(sc.sc_irq_pending[0] == 0 && sc.sc_irq_pending[1] == 0);
    balanced(&sc);

    /* STOP after hardirq queueing: softint must retire stale overflow. */
    setup(&sc);
    raw_hisre = R23BE_IMR_RXFOVW;
    stop_on_schedule = 1;
    assert(rtwn8723be_netbsd_intr(&sc) == 1);
    assert(schedule_count == 1 && !sc.sc_irq_requested);
    assert(sc.sc_irq_pending[1] == 0);
    /* Same IRQ handler lifetime is now dead. A new owner enables IRQ
     * before the old queued softint executes; no stale callback fires. */
    assert(rtwn8723be_netbsd_enable_interrupt(&sc) == 0);
    assert(sc.sc_irq_requested && sc.sc_irq_enabled);
    rtwn8723be_netbsd_softintr(&sc);
    assert(rx_count == 0 && tx_count == 0);
    assert(sc.sc_irq_pending[0] == 0 && sc.sc_irq_pending[1] == 0);
    assert(sc.sc_irq_enabled && mmio_himre == sc.sc_irq_mask[1]);
    balanced(&sc);

    /* A new owner must reject an old hard IRQ that resumes MMIO reads
     * after STOP and a fresh enable, even though requested is true. */
    setup(&sc);
    raw_hisre = R23BE_IMR_RXFOVW;
    stop_on_read = 2;
    uint32_t old_epoch = sc.sc_irq_epoch;
    assert(rtwn8723be_netbsd_intr(&sc) == 0);
    assert(sc.sc_irq_requested && sc.sc_irq_enabled);
    assert(sc.sc_irq_epoch == old_epoch + 2);
    assert(sc.sc_irq_pending[0] == 0 && sc.sc_irq_pending[1] == 0);
    assert(schedule_count == 0);
    rtwn8723be_netbsd_softintr(&sc);
    assert(rx_count == 0);
    balanced(&sc);

    /* A repeated enable inside the SAME IRQ lifetime may not drop
     * already published pending work from a masked hard IRQ. */
    setup(&sc);
    raw_hisre = R23BE_IMR_RXFOVW;
    assert(rtwn8723be_netbsd_intr(&sc) == 1);
    assert(sc.sc_irq_pending[1] == R23BE_IMR_RXFOVW);
    uint32_t same_epoch = sc.sc_irq_epoch;
    assert(rtwn8723be_netbsd_enable_interrupt(&sc) == 0);
    assert(sc.sc_irq_epoch == same_epoch);
    assert(sc.sc_irq_pending[1] == R23BE_IMR_RXFOVW);
    rtwn8723be_netbsd_softintr(&sc);
    assert(rx_count == 1);
    balanced(&sc);

    /* Already stopped: hardirq ignores even an overflow-only vector. */
    setup(&sc);
    assert(rtwn8723be_netbsd_disable_interrupt(&sc) == 0);
    raw_hisre = R23BE_IMR_RXFOVW;
    assert(rtwn8723be_netbsd_intr(&sc) == 0);
    assert(schedule_count == 0 && rx_count == 0);
    balanced(&sc);
    puts("RTL_HISRE_ONLY_RXFOVW_HARD_SOFTIRQ_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtl-hisre-overflow-") as td:
    source = Path(td) / "test.c"
    exe = Path(td) / "test"
    source.write_text(prefix.replace(
        "typedef struct { bool held; } kmutex_t;",
        "\n".join(defines) + "\ntypedef struct { bool held; } kmutex_t;"
    ) + "\n" + mask + "\n" + arm + "\n" + rearm + "\n" +
        enable + "\n" + disable + "\n" + hard + "\n" + soft + "\n" + tail)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(ROOT / "src"), str(source), "-o", str(exe)
    ], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_HISRE_RXFOVW_SOURCE_MUTATIONS_OK negatives=18")
