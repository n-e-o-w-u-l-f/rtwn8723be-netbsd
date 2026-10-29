#!/usr/bin/env python3
"""Production C11/UBSan regression for unstarted post-registration probe unwind.

The C tests exercise the ACTUAL inline broker, with explicit compensator
failures and reject-before-effects cases. Source guards verify that the
native callbacks are real NetBSD owners, not dummy successful stubs.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
native = (SRC / "rtwn8723be_native.c").read_text()
unwind = (SRC / "rtwn8723be_probe_unwind.h").read_text()
netbsd = (SRC / "rtwn8723be_netbsd.c").read_text()

assert '#include "rtwn8723be_probe_unwind.h"' in native
for function, effect in (
    ("rtwn8723be_native_unwind_irq", "rtwn8723be_netbsd_disestablish_irq(sc)"),
    ("rtwn8723be_native_unwind_datapath", "rtwn8723be_datapath_unprepare(sc->sc_datapath)"),
    ("rtwn8723be_native_unwind_rx_binding", "rtwn8723be_rx_binding_fini(sc->sc_rx_binding)"),
    ("rtwn8723be_native_unwind_rfkill", "rtwn8723be_rfkill_native_fini(sc)"),
    ("rtwn8723be_native_unwind_net80211", "rtwn8723be_net80211_unregister(&sc->sc_net80211)"),
):
    assert function + "(" in native and effect in native, function
assert "return rtwn8723be_probe_unwind_post_registration(" in native
assert ".net80211_owned = sc->sc_net80211.registered &&" in native
assert ".rfkill_queue_present = sc->sc_rfkill_native.wq != NULL" in native
assert ".irq_handles_coherent = all_irq || no_irq" in native
assert ".hal_started = sc->sc_hal_started" in native
assert ".irq_requested = sc->sc_irq_requested" in native
assert ".datapath_bound = dp != NULL," in native
assert ".datapath_owner_valid = dp != NULL ?" in native
assert ".datapath_tx_enabled = dp != NULL && dp->tx_enabled," in native
assert ".unprepare_datapath = rtwn8723be_native_unwind_datapath," in native
assert ".unbind_rx = rtwn8723be_native_unwind_rx_binding," in native
assert ".rx_binding_present = sc->sc_rx_binding != NULL," in native
assert ".rx_binding_owned = sc->sc_rx_binding != NULL &&" in native
assert "sc->sc_rx_binding->net == &sc->sc_net80211" in native
assert ".progress = sc->sc_probe_unwind_progress" in native
assert "&sc->sc_probe_unwind_progress, &ops, sc" in native
assert "sc->sc_probe_unwind_progress = R23BE_PROBE_UNWIND_NONE;" in native

cleanup = native.split(
    "rtwn8723be_native_probe_cleanup(struct rtwn8723be_softc *sc)", 1)[1]
cleanup = cleanup.split("rtwn8723be_native_detach(", 1)[0]
assert cleanup.index("if (stage == R23BE_STAGE_IDLE)") < cleanup.index(
    "if (stage >= R23BE_STAGE_IEEE80211_REGISTER)")
assert cleanup.index("rtwn8723be_native_post_registration_unwind(sc)") < (
    cleanup.index("rtwn8723be_btc_mp_native_fini(sc)"))
assert cleanup.index("rtwn8723be_native_unwind_datapath(sc)") < (
    cleanup.index("rtwn8723be_native_unwind_rx_binding(sc)"))
assert cleanup.index("rtwn8723be_native_unwind_rx_binding(sc)") < (
    cleanup.index("rtwn8723be_btc_mp_native_fini(sc)"))
assert cleanup.index("rtwn8723be_btc_mp_native_fini(sc)") < (
    cleanup.index("rtwn8723be_h2c_native_fini(sc)"))
assert cleanup.index("rtwn8723be_h2c_native_fini(sc)") < (
    cleanup.index("rtwn8723be_netbsd_free_pci_rings(sc)"))
assert cleanup.index("rtwn8723be_netbsd_free_pci_rings(sc)") < (
    cleanup.index("rtwn8723be_netbsd_dma_release(sc)"))
assert cleanup.index("rtwn8723be_netbsd_dma_release(sc)") < (
    cleanup.index("bus_space_unmap(sc->sc_st, sc->sc_sh, sc->sc_mapsize)"))
assert "retaining PCI/MMIO resources" in cleanup
assert "if (error != 0)" in cleanup
assert "return;" in cleanup.split("if (error != 0)", 1)[1].split("\n    }", 1)[0]
assert "if (sc->sc_linux.stage >= R23BE_STAGE_IEEE80211_REGISTER)\n        return EBUSY;" not in native

# The remaining three real-owner gaps stay blocked. The RFKill probe
# callback is genuinely implemented and retains the existing reverse owner.
# No runtime PCI attach, hardware init or i915 policy is enabled.
ops = netbsd.split("const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops", 1)[1]
for slot in ("register_ieee80211", "bt_prepare", "dm_init"):
    assert "." + slot + " =" not in ops
assert ".init_rfkill = rtwn8723be_netbsd_init_rfkill," in ops
assert "rtwn8723be_rfkill_native_fini(sc);" in native

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_probe_unwind.h"

struct fixture {
    int calls;
    int order[5];
    int fail_on;
};
static int
effect(void *arg, int step)
{
    struct fixture *f = arg;
    assert(f->calls < 5);
    f->order[f->calls++] = step;
    return f->fail_on == step ? EIO : 0;
}
static int irq(void *p) { return effect(p, 1); }
static int datapath(void *p) { return effect(p, 2); }
static int rx(void *p) { return effect(p, 3); }
static int rfkill(void *p) { return effect(p, 4); }
static int n80211(void *p) { return effect(p, 5); }

static const struct rtwn8723be_probe_unwind_ops ops = {
    irq, datapath, rx, rfkill, n80211
};
static struct rtwn8723be_probe_unwind_snapshot
baseline(enum rtwn8723be_linux_stage stage, bool dp)
{
    struct rtwn8723be_probe_unwind_snapshot s = {0};
    s.stage = stage;
    s.progress = R23BE_PROBE_UNWIND_NONE;
    s.pci_snapshot = true;
    s.bar_mapped = true;
    s.datapath_owner_valid = true;
    s.datapath_bound = dp;
    s.rx_binding_present = dp;
    s.rx_binding_owned = dp;
    s.irq_handles_coherent = true;
    s.net80211_registered = stage > R23BE_STAGE_IEEE80211_REGISTER;
    s.net80211_owned = s.net80211_registered;
    s.rfkill_initialized = stage > R23BE_STAGE_RFKILL;
    s.rfkill_queue_present = s.rfkill_initialized;
    s.rfkill_active = s.rfkill_initialized;
    s.irq_handles_present = stage == R23BE_STAGE_PROBED;
    return s;
}
static void
passes(enum rtwn8723be_linux_stage stage, bool dp)
{
    struct rtwn8723be_probe_unwind_snapshot s = baseline(stage, dp);
    enum rtwn8723be_probe_unwind_progress progress = R23BE_PROBE_UNWIND_NONE;
    struct fixture f = {0};

    assert(rtwn8723be_probe_unwind_eligible(&s));
    assert(rtwn8723be_probe_unwind_post_registration(
        &s, &progress, &ops, &f) == 0);
    assert(progress == R23BE_PROBE_UNWIND_NET80211);
    assert(f.calls == 5);
    for (int j = 0; j < 5; j++)
        assert(f.order[j] == j + 1);

    for (int fail = 1; fail <= 5; fail++) {
        s = baseline(stage, dp);
        progress = R23BE_PROBE_UNWIND_NONE;
        memset(&f, 0, sizeof(f));
        f.fail_on = fail;
        assert(rtwn8723be_probe_unwind_post_registration(
            &s, &progress, &ops, &f) == EIO);
        assert(f.calls == fail);
        assert(progress == (enum rtwn8723be_probe_unwind_progress)(fail - 1));
        for (int j = 0; j < fail; j++)
            assert(f.order[j] == j + 1);

        /* Simulate successful native owner postconditions on retry. */
        s.progress = progress;
        if (progress >= R23BE_PROBE_UNWIND_IRQ)
            s.irq_handles_present = false;
        if (progress >= R23BE_PROBE_UNWIND_DATAPATH)
            s.datapath_bound = false;
        if (progress >= R23BE_PROBE_UNWIND_RX_BINDING) {
            s.rx_binding_present = false;
            s.rx_binding_owned = false;
        }
        if (progress >= R23BE_PROBE_UNWIND_RFKILL) {
            s.rfkill_initialized = false;
            s.rfkill_queue_present = false;
            s.rfkill_active = false;
        }
        if (progress >= R23BE_PROBE_UNWIND_NET80211) {
            s.net80211_registered = false;
            s.net80211_owned = false;
        }
        assert(rtwn8723be_probe_unwind_eligible(&s));
        memset(&f, 0, sizeof(f));
        assert(rtwn8723be_probe_unwind_post_registration(
            &s, &progress, &ops, &f) == 0);
        assert(progress == R23BE_PROBE_UNWIND_NET80211);
        assert(f.calls == 6 - fail);
        for (int j = 0; j < f.calls; j++)
            assert(f.order[j] == fail + j);

        /* A completed owner graph must be a true no-op on reentry. */
        s.progress = progress;
        s.irq_handles_present = false;
        s.datapath_bound = false;
        s.rx_binding_present = false;
        s.rx_binding_owned = false;
        s.rfkill_initialized = false;
        s.rfkill_queue_present = false;
        s.rfkill_active = false;
        s.net80211_registered = false;
        s.net80211_owned = false;
        memset(&f, 0, sizeof(f));
        assert(rtwn8723be_probe_unwind_post_registration(
            &s, &progress, &ops, &f) == 0);
        assert(f.calls == 0);
    }
}
static void
reject(struct rtwn8723be_probe_unwind_snapshot s)
{
    struct fixture f = {0};
    enum rtwn8723be_probe_unwind_progress progress = s.progress;
    assert(!rtwn8723be_probe_unwind_eligible(&s));
    assert(rtwn8723be_probe_unwind_post_registration(
        &s, &progress, &ops, &f) == EBUSY);
    assert(f.calls == 0);
}
int main(void)
{
    struct rtwn8723be_probe_unwind_snapshot s, other;
    struct rtwn8723be_probe_unwind_ops missing = ops;
    enum rtwn8723be_probe_unwind_progress progress = R23BE_PROBE_UNWIND_NONE;
    struct fixture f = {0};

    assert(!rtwn8723be_probe_unwind_eligible(NULL));
    passes(R23BE_STAGE_IEEE80211_REGISTER, false);
    passes(R23BE_STAGE_RFKILL, false);
    passes(R23BE_STAGE_IRQ_ESTABLISH, false);
    passes(R23BE_STAGE_PROBED, false);
    passes(R23BE_STAGE_IEEE80211_REGISTER, true);
    passes(R23BE_STAGE_RFKILL, true);
    passes(R23BE_STAGE_IRQ_ESTABLISH, true);
    passes(R23BE_STAGE_PROBED, true);

    s = baseline(R23BE_STAGE_IEEE80211_REGISTER, true);
    s.net80211_registered = true;
    s.net80211_owned = true;
    assert(rtwn8723be_probe_unwind_eligible(&s));
    s = baseline(R23BE_STAGE_RFKILL, false);
    s.rfkill_initialized = true;
    s.rfkill_queue_present = true;
    s.rfkill_active = true;
    assert(rtwn8723be_probe_unwind_eligible(&s));
    s = baseline(R23BE_STAGE_IRQ_ESTABLISH, false);
    s.irq_handles_present = true;
    assert(rtwn8723be_probe_unwind_eligible(&s));

    s = baseline(R23BE_STAGE_PROBED, true);
#define REJECT_FIELD(field) do { other = s; other.field = false; reject(other); } while (0)
    REJECT_FIELD(pci_snapshot);
    REJECT_FIELD(bar_mapped);
    REJECT_FIELD(datapath_owner_valid);
    REJECT_FIELD(rx_binding_owned);
    REJECT_FIELD(irq_handles_coherent);
    REJECT_FIELD(net80211_registered);
    REJECT_FIELD(net80211_owned);
    REJECT_FIELD(rfkill_initialized);
    REJECT_FIELD(rfkill_queue_present);
    REJECT_FIELD(irq_handles_present);
#undef REJECT_FIELD
#define TRUE_REJECT_FIELD(field) do { other = s; other.field = true; reject(other); } while (0)
    TRUE_REJECT_FIELD(started);
    TRUE_REJECT_FIELD(being_init_adapter);
    TRUE_REJECT_FIELD(fw_ready);
    TRUE_REJECT_FIELD(hal_started);
    TRUE_REJECT_FIELD(datapath_tx_enabled);
    TRUE_REJECT_FIELD(irq_requested);
    TRUE_REJECT_FIELD(irq_enabled);
#undef TRUE_REJECT_FIELD
    other = s; other.stage = R23BE_STAGE_RUNNING; reject(other);
    other = s; other.stage = R23BE_STAGE_STOPPING; reject(other);
    other = s; other.stage = R23BE_STAGE_STOPPED; reject(other);
    other = s; other.stage = R23BE_STAGE_BT_PREPARE; reject(other);
    other = s; other.stage = R23BE_STAGE_IDLE; reject(other);
    other = s; other.stage = R23BE_STAGE_PCI_RINGS; reject(other);

    s = baseline(R23BE_STAGE_IEEE80211_REGISTER, false);
    other = s; other.net80211_registered = true; reject(other);
    other = s; other.rfkill_initialized = true;
    other.rfkill_queue_present = true; reject(other);
    other = s; other.irq_handles_present = true; reject(other);
    s = baseline(R23BE_STAGE_RFKILL, false);
    other = s; other.irq_handles_present = true; reject(other);
    other = s; other.rfkill_active = true; reject(other);
    other = s; other.rfkill_queue_present = true; reject(other);

    s = baseline(R23BE_STAGE_PROBED, true);
    other = s;
    other.progress = R23BE_PROBE_UNWIND_DATAPATH;
    other.irq_handles_present = false;
    reject(other); /* A journalled datapath cannot remain prepared. */
    other = s;
    other.progress = R23BE_PROBE_UNWIND_RX_BINDING;
    other.irq_handles_present = false;
    other.datapath_bound = false;
    reject(other); /* A journalled RX binding cannot remain published. */

    s = baseline(R23BE_STAGE_PROBED, false);
    missing.unbind_rx = NULL;
    assert(rtwn8723be_probe_unwind_post_registration(
        &s, &progress, &missing, &f) == ENOSYS && f.calls == 0);
    assert(rtwn8723be_probe_unwind_post_registration(
        &s, &progress, NULL, &f) == ENOSYS && f.calls == 0);
    assert(rtwn8723be_probe_unwind_post_registration(
        &s, NULL, &ops, &f) == EBUSY && f.calls == 0);
    progress = R23BE_PROBE_UNWIND_IRQ;
    assert(rtwn8723be_probe_unwind_post_registration(
        &s, &progress, &ops, &f) == EBUSY && f.calls == 0);
    other = s;
    other.progress = R23BE_PROBE_UNWIND_IRQ;
    reject(other);
    other = s;
    other.progress = (enum rtwn8723be_probe_unwind_progress)99;
    reject(other);
    other = s;
    other.progress = (enum rtwn8723be_probe_unwind_progress)-1;
    reject(other);
    puts("RTL_POSTREG_PROBE_UNWIND_C11_OK callbacks=5 retry=5");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix="rtl-postreg-unwind-") as name:
    d = Path(name)
    src = d / "test.c"
    binary = d / "test"
    src.write_text(HARNESS)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(SRC), str(src), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
print("RTL_POSTREG_PROBE_UNWIND_SOURCE_ORDER_OK")
