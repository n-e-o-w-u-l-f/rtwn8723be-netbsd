#!/usr/bin/env python3
"""Execute the production BT MP RX readiness gate under strict C11/UBSan.

The test runs the real function body with a mock IPL_SOFTNET lock that
asserts synchronization, and verifies that the RX site uses this API rather
than reading the firmware-active flag without the lock. This does not
replace HP NetBSD mutex/interrupt/concurrency testing.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MP = (ROOT / "src/rtwn8723be_btc_mp_native.c").read_text()
RX = (ROOT / "src/rtwn8723be_rx_binding.c").read_text()

name = "rtwn8723be_btc_mp_native_rx_ready"
anchor = "\n" + name + "("
assert MP.count(anchor) == 1
candidate = name + "(" + MP.split(anchor, 1)[1]
start = candidate.index("{")
depth = 0
end = -1
for i in range(start, len(candidate)):
    if candidate[i] == "{":
        depth += 1
    elif candidate[i] == "}":
        depth -= 1
        if depth == 0:
            end = i
            break
assert end != -1
production = "bool\n" + candidate[:end + 1]
assert production.index("mutex_enter(&mp->lock);") < production.index(
    "ready = mp->active && !mp->faulted && !mp->cancelled;") < (
    production.index("mutex_exit(&mp->lock);"))
assert "cpu_intr_p()" in production

rx = RX.split("rtwn8723be_rx_binding_c2h(", 1)[1].split("\n}\n", 1)[0]
assert "!rtwn8723be_btc_mp_native_rx_ready(binding->net->sc)" in rx
assert "sc_btc_mp.active" not in rx, "raw RX-side MP active read is racy"
assert "sc_btc_mp.faulted" not in rx
assert "sc_btc_mp.cancelled" not in rx

prologue = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stddef.h>

static int irq_context, entries, exits;
struct mock_lock { bool held; };
static void mutex_enter(struct mock_lock *l)
{ assert(l != NULL && !l->held); l->held = true; entries++; }
static void mutex_exit(struct mock_lock *l)
{ assert(l != NULL && l->held); l->held = false; exits++; }
static bool cpu_intr_p(void) { return irq_context != 0; }

struct rtwn8723be_btc_mp_native {
    struct mock_lock lock;
    bool initialized, active, faulted, cancelled;
};
struct rtwn8723be_softc {
    struct rtwn8723be_btc_mp_native sc_btc_mp;
};
'''
epilogue = r'''
static void expect(struct rtwn8723be_softc *sc, bool result,
    bool takes_lock)
{
    int before = entries;
    assert(rtwn8723be_btc_mp_native_rx_ready(sc) == result);
    assert(entries - before == (takes_lock ? 1 : 0));
    assert(entries == exits);
    if (sc != NULL)
        assert(!sc->sc_btc_mp.lock.held);
}
int main(void)
{
    struct rtwn8723be_softc sc = {0};
    expect(NULL, false, false);
    expect(&sc, false, false);
    sc.sc_btc_mp.initialized = true;
    expect(&sc, false, true);
    sc.sc_btc_mp.active = true;
    expect(&sc, true, true);
    sc.sc_btc_mp.faulted = true;
    expect(&sc, false, true);
    sc.sc_btc_mp.faulted = false;
    sc.sc_btc_mp.cancelled = true;
    expect(&sc, false, true);
    sc.sc_btc_mp.cancelled = false;
    expect(&sc, true, true);
    irq_context = 1;
    expect(&sc, false, false);
    irq_context = 0;
    sc.sc_btc_mp.active = false;
    expect(&sc, false, true);
    sc.sc_btc_mp.initialized = false; /* lifetime owner has drained IRQ */
    expect(&sc, false, false);
    puts("RTL_BT_MP_RX_GATE_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtwn-bt-mp-ready-") as d:
    source = Path(d) / "test.c"
    exe = Path(d) / "test"
    source.write_text(prologue + production + "\n" + epilogue)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        str(source), "-o", str(exe),
    ], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_BT_MP_RX_SOURCE_ADMISSION_OK")
