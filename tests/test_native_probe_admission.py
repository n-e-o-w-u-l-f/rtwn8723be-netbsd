#!/usr/bin/env python3
"""C11/UBSan probe-admission matrix and native attach source guards.

This is purely an admission predicate test. It neither configures a NetBSD
kernel nor authorizes PCI, Wi-Fi, i915 or any experimental boot.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/rtwn8723be_native.c").read_text()
HEADER = ROOT / "src/rtwn8723be_probe_admission.h"
NETBSD = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
assert HEADER.is_file()

FIELDS = (
    "phase_probed", "quiescent", "pci_snapshot", "bar_mapped",
    "core_initialized", "dma32_configured", "rings_allocated",
    "net80211_registered", "net80211_owned", "net80211_methods_ready",
    "rfkill_initialized", "rfkill_active", "irq_dispatch_ready",
    "irq_handlers_owned", "irq_disabled",
)


def source_contract(source: str) -> None:
    assert '#include "rtwn8723be_probe_admission.h"' in source
    head = source.index("rtwn8723be_native_probe_resources_ready(")
    body = source[head:source.index("\n}\n", head)]
    for field in FIELDS:
        assert ".%s =" % field in body, field
    assert "return rtwn8723be_probe_admission_ok(&a);" in body
    attach = source[source.index("rtwn8723be_native_attach("):]
    assert attach.index("error = rtwn8723be_linux_probe(") < attach.index(
        "if (!rtwn8723be_native_probe_resources_ready(sc))")
    assert attach.index("if (!rtwn8723be_native_probe_resources_ready(sc))") < (
        attach.index('aprint_normal_dev(self, "native RTL8723BE probe completed')
    )
    refusal = attach.split(
        "if (!rtwn8723be_native_probe_resources_ready(sc))", 1)[1]
    refusal = refusal.split("\n    }", 1)[0]
    assert "aprint_error_dev(self," in refusal
    assert "WLAN not accepted" in refusal
    assert "return;" in refusal
    assert "rtwn8723be_native_probe_cleanup(sc)" not in refusal
    # The missing real owner gates must not be hidden by a success-only check.
    ops = NETBSD.split("const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops", 1)[1]
    for name in ("register_ieee80211", "init_rfkill", "bt_prepare", "dm_init"):
        assert "." + name + " =" not in ops


source_contract(SOURCE)

# Negative controls: bypassing admission, skipping an ownership input, or
# speculatively tearing down a partial post-registration state must fail.
for changed in (
    SOURCE.replace("return rtwn8723be_probe_admission_ok(&a);",
                   "return true;", 1),
    SOURCE.replace(".rfkill_active = sc->sc_rfkill_native.active,", "", 1),
    SOURCE.replace("if (!rtwn8723be_native_probe_resources_ready(sc))",
                   "if (false)", 1),
    SOURCE.replace("WLAN not accepted\\n", "WLAN accepted\\n", 1),
    SOURCE.replace("WLAN not accepted\\n",
                   "WLAN not accepted\\n\");\n"
                   "        rtwn8723be_native_probe_cleanup(sc);\n"
                   "        aprint_error_dev(self, \"", 1),
):
    assert changed != SOURCE, "negative mutation was not applied"
    try:
        source_contract(changed)
    except (AssertionError, ValueError):
        pass
    else:
        raise AssertionError("unsafe native attach mutation accepted")

HARNESS = r"""
#include <assert.h>
#include <stdio.h>
#include "rtwn8723be_probe_admission.h"

static const struct rtwn8723be_probe_admission good = {
    .phase_probed = true,
    .quiescent = true,
    .pci_snapshot = true,
    .bar_mapped = true,
    .core_initialized = true,
    .dma32_configured = true,
    .rings_allocated = true,
    .net80211_registered = true,
    .net80211_owned = true,
    .net80211_methods_ready = true,
    .rfkill_initialized = true,
    .rfkill_active = true,
    .irq_dispatch_ready = true,
    .irq_handlers_owned = true,
    .irq_disabled = true,
};
#define MUST_REJECT(field) do {                       \
    struct rtwn8723be_probe_admission bad = good;      \
    bad.field = false;                                 \
    assert(!rtwn8723be_probe_admission_ok(&bad));       \
} while (0)

int main(void)
{
    assert(!rtwn8723be_probe_admission_ok(NULL));
    assert(rtwn8723be_probe_admission_ok(&good));
    MUST_REJECT(phase_probed);
    MUST_REJECT(quiescent);
    MUST_REJECT(pci_snapshot);
    MUST_REJECT(bar_mapped);
    MUST_REJECT(core_initialized);
    MUST_REJECT(dma32_configured);
    MUST_REJECT(rings_allocated);
    MUST_REJECT(net80211_registered);
    MUST_REJECT(net80211_owned);
    MUST_REJECT(net80211_methods_ready);
    MUST_REJECT(rfkill_initialized);
    MUST_REJECT(rfkill_active);
    MUST_REJECT(irq_dispatch_ready);
    MUST_REJECT(irq_handlers_owned);
    MUST_REJECT(irq_disabled);
    puts("RTL_NATIVE_PROBE_ADMISSION_C11_OK fields=15");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-probe-admission-") as directory:
    tmp = Path(directory)
    src = tmp / "admission.c"
    exe = tmp / "admission"
    src.write_text(HARNESS)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(ROOT / "src"), str(src), "-o", str(exe),
    ], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_NATIVE_PROBE_ADMISSION_SOURCE_NEGATIVES_OK")
