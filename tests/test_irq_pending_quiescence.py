#!/usr/bin/env python3
"""Executable pending IRQ ledger plus source-level NetBSD hard/softint order.

A portable C11/UBSan run verifies the actual shared production helper.
Source negative controls ensure the real IRQ/softint/teardown consumers
hold the same IPL_NET mutex. NetBSD hardware concurrency remains open.
"""
from pathlib import Path
import subprocess
import tempfile
import re

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/rtwn8723be_irq_pending.h"
SOURCE = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
assert HEADER.exists()

def body(src: str, name: str) -> str:
    pat = re.compile(r"(?m)^(?:static\s+)?(?:int|void)\s*\n" +
                     re.escape(name) + r"\([^;{}]*\)\n\{")
    matches = list(pat.finditer(src))
    assert len(matches) == 1, (name, len(matches))
    return src[matches[0].start():src.index("\n}\n", matches[0].end())+3]

def verify_native(src: str) -> None:
    hard = body(src, "rtwn8723be_netbsd_intr")
    soft = body(src, "rtwn8723be_netbsd_softintr")
    release = body(src, "rtwn8723be_netbsd_disestablish_irq")
    assert '#include "rtwn8723be_irq_pending.h"' in src
    assert "if (irq_epoch != sc->sc_irq_epoch ||" in hard
    assert "!rtwn8723be_irq_pending_record(sc->sc_irq_pending," in hard
    assert hard.index("irq_epoch = sc->sc_irq_epoch;") < hard.index(
        "rtwn8723be_read_4(sc, R23BE_REG_HISR);")
    assert hard.index("irq_epoch != sc->sc_irq_epoch ||") < hard.index(
        "rtwn8723be_irq_pending_record(sc->sc_irq_pending,")
    record = hard.index("rtwn8723be_irq_pending_record(sc->sc_irq_pending,")
    assert hard.index("mutex_enter(&sc->sc_irq_lock);", hard.index(
        "if ((inta | intb) == 0 || inta == 0xffffU)")) < record
    assert record < hard.index("mutex_exit(&sc->sc_irq_lock);", record)
    assert record < hard.index("softint_schedule(sc->sc_soft_ih);")
    assert "sc->sc_irq_requested, sc->sc_irq_dispatch_ready, inta, intb" in hard
    assert "sc->sc_irq_pending[0] |=" not in hard
    assert "sc->sc_irq_pending[1] |=" not in hard

    assert "if (!rtwn8723be_irq_pending_take(sc->sc_irq_pending," in soft
    take = soft.index("rtwn8723be_irq_pending_take(sc->sc_irq_pending,")
    assert soft.index("mutex_enter(&sc->sc_irq_lock);") < take
    assert take < soft.index("mutex_exit(&sc->sc_irq_lock);", take)
    assert "sc->sc_irq_requested, sc->sc_irq_dispatch_ready, &inta, &intb" in soft
    assert soft.index("return;", take) < soft.index(
        "sc->sc_irq_dispatch.rx(", take)
    assert "sc->sc_irq_pending[0] = 0;" not in soft

    assert release.index("pci_intr_disestablish(") < release.index(
        "softint_disestablish(") < release.index(
        "rtwn8723be_irq_pending_clear(sc->sc_irq_pending);")
    assert release.index("mutex_enter(&sc->sc_irq_lock);") < release.index(
        "rtwn8723be_irq_pending_clear(sc->sc_irq_pending);")
    assert release.index("rtwn8723be_irq_pending_clear(") < release.index(
        "mutex_exit(&sc->sc_irq_lock);")

verify_native(SOURCE)

mutations = (
    SOURCE.replace("if (irq_epoch != sc->sc_irq_epoch ||",
                   "if (false ||",1),
    SOURCE.replace("sc->sc_irq_requested, sc->sc_irq_dispatch_ready, inta, intb",
                   "true, true, inta, intb",1),
    SOURCE.replace("if (!rtwn8723be_irq_pending_take(sc->sc_irq_pending,",
                   "if (false && !rtwn8723be_irq_pending_take(sc->sc_irq_pending,",1),
    SOURCE.replace("sc->sc_irq_requested, sc->sc_irq_dispatch_ready, &inta, &intb",
                   "true, true, &inta, &intb",1),
    SOURCE.replace("        rtwn8723be_irq_pending_clear(sc->sc_irq_pending);",
                   "        /* left over stale events */",1),
    SOURCE.replace("    if (sc->sc_soft_ih != NULL) {\n"
                   "        softint_disestablish(sc->sc_soft_ih);",
                   "    if (sc->sc_soft_ih != NULL) {\n"
                   "        /* did not actually drain softint */",1),
)
for i, candidate in enumerate(mutations, 1):
    assert candidate != SOURCE, ("mutation did not apply", i)
    try:
        verify_native(candidate)
    except (AssertionError, ValueError):
        pass
    else:
        raise AssertionError(f"unsafe IRQ pending mutation accepted: {i}")

harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include "rtwn8723be_irq_pending.h"

static void stage(bool requested, bool ready,
    uint32_t a, uint32_t b, bool record_expected)
{
    volatile uint32_t pending[2] = {0x21, 0x4};
    bool ok = rtwn8723be_irq_pending_record(pending,
        requested, ready, a, b);
    assert(ok == record_expected);
    assert(pending[0] == (record_expected ? (0x21U | a) : 0x21U));
    assert(pending[1] == (record_expected ? (0x4U | b) : 0x4U));
}

int main(void)
{
    volatile uint32_t pending[2] = {0};
    uint32_t a=9, b=7;

    assert(!rtwn8723be_irq_pending_record(NULL, true,true,1,1));
    stage(false,true,1,2,false);
    stage(true,false,1,2,false);
    stage(true,true,0,0,false);
    stage(true,true,1,2,true);

    assert(rtwn8723be_irq_pending_record(pending, true,true,0x4,0x10));
    assert(rtwn8723be_irq_pending_record(pending, true,true,0x2,0x20));
    assert(pending[0] == 0x6 && pending[1] == 0x30);
    assert(rtwn8723be_irq_pending_take(pending,true,true,&a,&b));
    assert(a == 0x6 && b == 0x30 && !pending[0] && !pending[1]);
    assert(!rtwn8723be_irq_pending_take(pending,true,true,&a,&b));
    assert(a == 0 && b == 0);
    assert(rtwn8723be_irq_pending_record(pending,true,true,7,9));

    /* A permanent stop must drop pending completions before callbacks. */
    a=b=0xffffffffU;
    assert(!rtwn8723be_irq_pending_take(pending,false,true,&a,&b));
    assert(a == 0 && b == 0 && !pending[0] && !pending[1]);
    assert(!rtwn8723be_irq_pending_record(pending,false,true,7,9));

    assert(rtwn8723be_irq_pending_record(pending,true,true,0x80,0x40));
    assert(!rtwn8723be_irq_pending_take(pending,true,false,&a,&b));
    assert(a == 0 && b == 0 && !pending[0] && !pending[1]);

    /* Missing output buffers are rejected without mutating the ledger. */
    pending[0] = 0x80000000U;
    pending[1] = 0x40000000U;
    assert(!rtwn8723be_irq_pending_take(pending,true,true,NULL,&b));
    assert(pending[0] == 0x80000000U && pending[1] == 0x40000000U);
    rtwn8723be_irq_pending_clear(pending);
    assert(pending[0] == 0 && pending[1] == 0);
    rtwn8723be_irq_pending_clear(NULL);
    puts("RTL_IRQ_PENDING_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtl-irq-pending-") as d:
    src = Path(d) / "test.c"
    exe = Path(d) / "test"
    src.write_text(harness)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(ROOT / "src"), str(src), "-o", str(exe)
    ], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_IRQ_PENDING_SOURCE_ORDER_OK negatives=6")
