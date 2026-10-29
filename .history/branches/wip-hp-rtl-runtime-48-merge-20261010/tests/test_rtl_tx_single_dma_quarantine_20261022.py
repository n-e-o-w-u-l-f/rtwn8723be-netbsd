#!/usr/bin/env python3
"""Source-only RTL8723BE single-frame TX DMA quarantine regression (0084).

No NetBSD kernel, DMA or HP hardware is executed. The failure contract is
verified on tracked C code and deliberately altered source variants.
"""
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parents[1] / "src" / "rtwn8723be_tx_native.c"
START = "\nrtwn8723be_tx_native_enqueue_owned("
END = "\nrtwn8723be_tx_native_enqueue_batch("
LOAD = "\n    error = bus_dmamap_load_mbuf("
SYNC = "rtwn8723be_f16_1_dma_sync_for_cpu("
TOKENS = {
    "payload-map-nonnull": "slot->map == NULL",
    "dma-tag-nonnull": "sc->sc_dmat == NULL",
    "packet-header": "(m->m_flags & M_PKTHDR) == 0",
    "no-fragment-chain": "m->m_nextpkt != NULL",
    "descriptor-map-capacity": "ring->desc_dma.map->dm_mapsize <",
    "payload-map-unloaded": "slot->map->dm_mapsize != 0",
    "payload-map-segment-count": "slot->map->dm_nsegs != 0",
    "stale-node-owner": "slot->tx_owner != NULL",
    "stale-release-callback": "slot->tx_release != NULL",
}
MUTATIONS = {
    "payload-map-nonnull": "slot->map != NULL",
    "dma-tag-nonnull": "sc->sc_dmat != NULL",
    "packet-header": "(m->m_flags & M_PKTHDR) != 0",
    "no-fragment-chain": "m->m_nextpkt == NULL",
    "descriptor-map-capacity": "ring->desc_dma.map->dm_mapsize >",
    "payload-map-unloaded": "slot->map->dm_mapsize == 0",
    "payload-map-segment-count": "slot->map->dm_nsegs == 0",
    "stale-node-owner": "slot->tx_owner == NULL",
    "stale-release-callback": "slot->tx_release == NULL",
}


def single_body(source):
    return source[source.index(START):source.index(END)]


def audit(source):
    failures = []
    try:
        body = single_body(source)
        load = body.index(LOAD)
        sync = body.index(SYNC)
    except ValueError as exc:
        return ["function/DMA boundary missing: " + str(exc)]
    pre = body[:load]
    for name, token in TOKENS.items():
        if token not in pre:
            failures.append(name + " absent before first DMA map load")
    # The historical V1 crash dereferenced NULL map + 0x30. The NULL
    # check must short-circuit before any map field access, not just load.
    null_pos = pre.find("slot->map == NULL")
    field_pos = pre.find("slot->map->")
    if null_pos < 0 or field_pos < 0 or null_pos >= field_pos:
        failures.append("NULL payload map guard must precede field access")
    # Checking only text presence is insufficient: quarantine must precede
    # descriptor access and DMA mapping. Negative ordering mutation below.
    pos = pre.find("slot->map->dm_mapsize != 0")
    if pos < 0 or pos >= sync or sync >= load:
        failures.append("stale-map quarantine ordering before descriptor sync/load")
    if "slot->tx_release != NULL)\n        return EIO;" not in pre:
        failures.append("stale map/owner must return EIO")
    if "if (slot->m != NULL)\n        return EBUSY;" not in pre:
        failures.append("busy-slot ownership check missing")
    if "BUS_DMASYNC_PREWRITE" not in body or "BUS_DMASYNC_POSTWRITE" in body:
        # Enqueue needs PREWRITE; POSTWRITE belongs to reclaim, not enqueue.
        failures.append("single-frame TX DMA direction changed")
    if "if (error != 0)\n        goto restore_desc;" not in body:
        failures.append("DMA load failure rollback missing")
    if "bus_dmamap_unload(sc->sc_dmat, slot->map);" not in body:
        failures.append("failed encode/map rollback missing")
    return failures


def main():
    source = SOURCE.read_text(encoding="utf-8")
    checks = 0
    errs = audit(source)
    if errs:
        raise AssertionError("baseline FAIL: " + "; ".join(errs))
    checks += 1
    single = single_body(source)
    for name, bad in MUTATIONS.items():
        good = TOKENS[name]
        if single.count(good) != 1:
            raise AssertionError("ambiguous positive guard " + name)
        broken = source.replace(good, bad, 1)
        if not audit(broken):
            raise AssertionError("mutation escaped: " + name)
        checks += 1
    for token in ("slot->map == NULL || ", " || sc->sc_dmat == NULL"):
        if single.count(token) != 1:
            raise AssertionError("ambiguous NULL guard: " + token)
        if not audit(source.replace(token, "", 1)):
            raise AssertionError("removed NULL guard escaped: " + token)
        checks += 1
    good_order = "slot->map == NULL || slot->map->dm_mapsize != 0"
    bad_order = "slot->map->dm_mapsize != 0 || slot->map == NULL"
    if single.count(good_order) != 1:
        raise AssertionError("ambiguous map guard ordering")
    if not audit(source.replace(good_order, bad_order, 1)):
        raise AssertionError("late NULL guard escaped")
    checks += 1
    precheck = "slot->map->dm_mapsize != 0 ||"
    if single.count(precheck) != 1:
        raise AssertionError("ambiguous map guard")
    # Moving the guard past bus_dmamap_load_mbuf must fail the ordering audit.
    broken = source.replace(precheck, "slot->map->dm_mapsize == 0 ||", 1)
    if not audit(broken):
        raise AssertionError("quarantine reversal escaped")
    checks += 1
    # Keep packet header validation before touching m_pkthdr.
    if single.index("(m->m_flags & M_PKTHDR) == 0") > single.index("m->m_pkthdr.len"):
        raise AssertionError("M_PKTHDR checked too late")
    checks += 1
    batch = source[source.index(END):]
    if "for (i = count; i != 0; )" not in batch:
        raise AssertionError("reverse OWN publication in batch removed")
    checks += 1
    if "BUS_DMASYNC_POSTWRITE" not in source[source.index("\nrtwn8723be_tx_native_reclaim("):]:
        raise AssertionError("TX reclaim POSTWRITE was removed")
    checks += 1
    print(f"HP_RTL_0084_TX_SINGLE_DMA_SOURCE_PASS checks={checks} "
          "scope=source_only kernel=NOT_RUN wlan=NOT_RUN")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, ValueError, OSError) as exc:
        print("HP_RTL_0084_TX_SINGLE_DMA_SOURCE_FAIL:", exc, file=sys.stderr)
        raise SystemExit(1)
