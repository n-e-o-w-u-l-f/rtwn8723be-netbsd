#!/usr/bin/env python3
"""Protect native DMA32 lease invalidation on PCI probe rollback.

Source-level contract only: actual bus_dma subregion destruction and ring
lifetime still require a native NetBSD object build and fault injection.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
native = (ROOT / "src/rtwn8723be_native.c").read_text()
header = (ROOT / "src/rtwn8723be_netbsd.h").read_text()
datapath = (ROOT / "src/rtwn8723be_datapath.c").read_text()


def extract_body(text: str, function_name: str) -> str:
    marker = re.compile(r"(?m)^void\s*\n" + re.escape(function_name) +
                        r"\([^;{}]*\)\n\{")
    matches = list(marker.finditer(text))
    assert len(matches) == 1, function_name
    i = matches[0].end()
    return text[i:text.index("\n}\n", i)]


def validate_dma_release(text: str) -> None:
    body = extract_body(text, "rtwn8723be_netbsd_dma_release")
    order = (
        "bus_dmatag_destroy(sc->sc_dmat);",
        "sc->sc_dmat_owned = false;",
        "sc->sc_dmat = sc->sc_dmat_parent;",
        "sc->sc_dma_32bit = false;",
    )
    positions = [body.find(s) for s in order]
    assert all(i >= 0 for i in positions), "DMA release misses mandatory state reset"
    assert positions == sorted(positions), "unsafe DMA32 lease release ordering"


validate_dma_release(source)
assert "bool sc_dma_32bit;" in header
assert "bool sc_dmat_owned;" in header
assert "if (!sc->sc_dma_32bit || sc->sc_dmat == NULL)" in source
assert "!sc->sc_dma_32bit" in datapath
assert native.index("rtwn8723be_netbsd_free_pci_rings(sc);") < (
    native.index("rtwn8723be_netbsd_dma_release(sc);"))

for mutation in (
    source.replace("    sc->sc_dma_32bit = false;\n}\n\nint\n"
                   "rtwn8723be_netbsd_pci_set_master",
                   "}\n\nint\nrtwn8723be_netbsd_pci_set_master", 1),
    source.replace("    sc->sc_dmat = sc->sc_dmat_parent;\n"
                   "    /*\n     * The unrestricted parent DMA tag",
                   "    /*\n     * The unrestricted parent DMA tag", 1),
):
    assert mutation != source, "negative mutation was not applied"
    try:
        validate_dma_release(mutation)
    except AssertionError:
        pass
    else:
        raise AssertionError("stale DMA32 lease accepted")

print("RTL_DMA32_POST_ROLLBACK_LEASE_INVALIDATION_OK")
