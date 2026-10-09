#!/usr/bin/env python3
"""Source-only mutation controls for guarded native attach/net80211 code.

This is NOT a kernel compiler, wireless simulator, or hardware acceptance test.
It proves the closure checker rejects several real prior source regressions.
Runs on a disposable copy and NEVER writes into the owning checkout.
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import shutil
import tempfile

from test_port_closure_inventory import check

ROOT = Path(__file__).resolve().parents[1]

# path, unique source excerpt, mutation, expected diagnostic substring
CONTROLS = (
    (
        "src/rtwn8723be_tx_native.c",
        "    *desc = saved_desc;",
        "    *desc = *desc; /* regression: failed TX leaves partial encoder IO */",
        "native TX must restore descriptor before error return",
    ),
    (
        "src/rtwn8723be_f16_1.h",
        "(uint64_t)(bytes - 1) <= UINT32_MAX - (uint64_t)addr;",
        "(uint64_t)bytes <= UINT32_MAX - (uint64_t)addr;",
        "DMA32 validator missing 4-GiB boundary/overflow check",
    ),
    (
        "src/rtwn8723be_f16_1_dma.c",
        "        dma->map->dm_segs[0].ds_len < size ||",
        "        false || /* regression: truncated DMA segment accepted */",
        "descriptor DMA mapping omits complete 32-bit span",
    ),
    (
        "src/rtwn8723be_f16_1_dma.c",
        "            !rtwn8723be_dma32_range_valid(\n"
        "                ring->slot[i].map->dm_segs[0].ds_addr,\n"
        "                RTWN8723BE_RX_BUFFER_SIZE)) {",
        "            false) { /* regression: out-of-range RX segment */",
        "native RX DMA slot published without full span check",
    ),
    (
        "src/rtwn8723be_tx_native.c",
        "        slot->map->dm_segs[0].ds_len <\n"
        "            (bus_size_t)input->buffer_len ||",
        "        false || /* regression: truncated TX mapped span */",
        "native TX may publish truncated 32-bit DMA",
    ),
    (
        "src/rtwn8723be_net80211.c",
        "        IEEE80211_C_WPA2;",
        "        0;",
        "software WPA2 station capability/policy incomplete",
    ),
    (
        "src/rtwn8723be_net80211.c",
        "    ifp->if_percpuq = if_percpuq_create(ifp);\n"
        "    KASSERT(ifp->if_percpuq != NULL);\n"
        "    if_register(ifp);",
        "    ifp->if_percpuq = if_percpuq_create(ifp);\n"
        "    if_detach(ifp); /* deliberately invalid before registration */\n"
        "    KASSERT(ifp->if_percpuq != NULL);\n"
        "    if_register(ifp);",
        "unregistered ifnet cleanup or NetBSD attach order",
    ),
    (
        "src/rtwn8723be_native.c",
        "    if (stage == R23BE_STAGE_IDLE) {\n"
        "        sc->sc_initial_pci_saved = false;\n"
        "        return;\n"
        "    }",
        "    if (stage == R23BE_STAGE_IDLE) {\n"
        "        return; /* intentionally leaks active PCI snapshot */\n"
        "    }",
        "unsafe IDLE or post-registration probe cleanup",
    ),
    (
        "src/rtwn8723be_security_native.c",
        "    if (sc->sc_sw_crypto || sc->sc_use_sw_sec) {\n"
        "        sc->sc_security_configured = true;\n"
        "        return 0;\n"
        "    }",
        "    if (sc->sc_sw_crypto || sc->sc_use_sw_sec) {\n"
        "        sc->sc_security_configured = true;\n"
        "        return EIO; /* deliberately breaks software crypto */\n"
        "    }",
        "software WPA2 branch must not program HW cipher",
    ),
    (
        "src/rtwn8723be_native.c",
        "        rtwn8723be_netbsd_context_fini(sc);\n"
        "        return;\n"
        "    }\n"
        "    sc->sc_pci_command_initial",
        "        return; /* intentionally leaks attach RF-PS lock */\n"
        "    }\n"
        "    sc->sc_pci_command_initial",
        "PCI snapshot failure leaks RF-PS lock",
    ),
)

def main() -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        if check(ROOT) != 0:
            raise RuntimeError("baseline source inventory did not pass")
    with tempfile.TemporaryDirectory(prefix="r23be-negative-") as base:
        scratch = Path(base)
        shutil.copytree(ROOT / "src", scratch / "src")
        shutil.copytree(ROOT / "config", scratch / "config")
        for number, (relative, good, bad, expected) in enumerate(CONTROLS, 1):
            path = scratch / relative
            original = path.read_text()
            if original.count(good) != 1:
                raise RuntimeError(
                    f"negative control {number} source anchor changed")
            path.write_text(original.replace(good, bad))
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = check(scratch)
            except ValueError as exc:
                if expected not in str(exc):
                    raise RuntimeError(
                        f"control {number}: wrong rejection: {exc}") from exc
            else:
                raise RuntimeError(
                    f"control {number}: invalid source accepted ({result})")
            finally:
                path.write_text(original)
            print(f"NEGATIVE_CONTROL_{number}=REJECTED {expected}")
    print("SOURCE_NEGATIVE_CONTROLS=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
