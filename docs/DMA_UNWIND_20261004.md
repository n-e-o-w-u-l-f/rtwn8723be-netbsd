# Native RTL8723BE descriptor DMA allocation-unwind correction — 2026-10-04

Status: SOURCE-COMMITTED / DIRECT-GITHUB-READBACK / ISOLATED-HOST-C-PASS / PUBLISHED-PYTHON-AND-CI-RUN-UNVERIFIED / NATIVE-NETBSD-OPEN.

## Parent contract and evidence

- Parent scope: `docs/FULL_SCOPE_CONTRACT.md`, COV-RTL-003 (bus_dma, descriptor and packet rings), with RX/TX dependencies COV-RTL-014.
- Frozen hardware reference: Linux `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`; frozen target: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
- NetBSD `bus_dma(9)` states that `dm_mapsize == 0` denotes an invalid DMA mapping; `bus_dmamap_sync()` requires valid arguments and cannot operate on an unloaded map. Official reference: https://man.netbsd.org/bus_dma.9
- Before repair `rtwn8723be_f16_1_dma_mem_free()` required only a non-NULL map handle and KVA before calling `bus_dmamap_sync()`. If `bus_dmamem_map()` had succeeded but subsequent `bus_dmamap_load()` failed, the shared `fail:` cleanup called `bus_dmamap_sync()` on an unloaded map. This is a software allocation-failure defect, not a conjectured hardware register workaround.

## Actual production and test changes

1. Commit `8a57336ecfe6d13c9764c664177d012ac487dac7` updates `src/rtwn8723be_f16_1_dma.c`. Synchronization/unload is conditional on nonzero `dma->map->dm_mapsize`; the synchronization length is the actual loaded map size. Whether or not loading succeeded, independent KVA unmap, allocated-segment free and map-handle destruction are preserved in reverse resource order. Direct readback production Git blob: `f712c89a438e903ccea8f79786b78e945d865e43`.
2. Commit `ef69c29c46b382a93af42d27d15b686a346de0f1` adds `tests/test_dma_mem_unwind.py`, which extracts the actual production C function and compiles it with C11/Wall/Wextra/Werror/pedantic/UBSan. It tests no handle, map handle only, allocated memory only, KVA mapped but DMA load failed, normally loaded map, and actual mapped-length synchronization. Published test blob `c66c216287cea73f2bc13389bf6b25408bf43a7d`.
3. Commit `01eb12169bbb2881ec3051ebf03e12c965ab7da3` extends `.github/workflows/portable-c-regressions.yml` with the DMA-unwind test and the corrected existing `tests/test_rx_dma_bounds.py` and triggers on relevant source/test changes. Workflow blob `a7d59668109b942a358295964302919301128c2d`; permissions remain `contents: read`.

## Tests and precise limits

- After direct readback, an independent standalone C11/UBSan reproduction using the current function body and mocked NetBSD DMA interfaces was compiled and executed in an isolated container: `RTL_DMA_UNWIND_C11_UBSAN_OK cases=6`, exit 0. This is **not** a native NetBSD object build and does **not** establish physical device behavior.
- The exact published Python test and the triggered GitHub Actions run are **not independently confirmed to have executed**. The available GitHub generic-fetch endpoint rejected the Actions workflow-run collection with HTTP 400; do not report the CI job as passed without separate job/status evidence. The workflow is committed and read back, not an execution proof.
- The earlier `tests/test_rx_dma_bounds.py` already includes the corrected host-only `bus_addr_t` typedef. Its exact published execution also remains to be verified.
- No denied correction to `src/rtwn8723be_rx_native.c` (descriptor-map preflight/partial-delivery reporting), PCI power rollback, H2C implementation or TX-PG/BB was retried. No previously denied host-sync strategy, protected HP boot, F77 recovery kernel, or six-edit i915 overlay was touched. The central oversized Agent-Governance `LAST_TASKS.md` mutation remains independently blocked; this subordinate handoff does not claim a central shared-state update.

## Next dependency-ordered action

Obtain legitimate current-revision CI execution evidence; close remaining independent ring allocation and data-path ownership regressions; only after the relevant authorization changes, repair the previously denied RX fatal-exit/descriptor-map errors. Finish lifecycle/PHY/RF/PM/security/net80211 wiring and build the **entire** candidate using genuine NetBSD headers/objects before any HP kernel or WLAN testing. COV-RTL-003 and COV-RTL-014 remain IN_PROGRESS, not COMPLETE.
