# RTL8723BE NetBSD RX DMA span hardening — 2026-10-03

Status: SOURCE-COMMITTED / SOURCE-READBACK-VERIFIED / ISOLATED-GUARD-TESTED / NATIVE-BUILD-OPEN / HP-TEST-OPEN.

## Scope and authority

Parent coverage: COV-RTL-003 (rings/DMA) and COV-RTL-014 (RX data path) in `docs/FULL_SCOPE_CONTRACT.md`. Frozen Linux hardware reference: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`, RTL8723BE old-TRX RX descriptor/PCI path. Frozen target reference: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`. NetBSD `bus_dma(9)` requires explicit synchronization of a *valid loaded mapping*; the physical device uses 32-bit buffer addresses in its descriptors. Normal RX buffer size is 9,100 bytes.

## Actual production changes, not a new hardware experiment

- Commit `a7b04d7dd3342fb85a8c208a8aa24dfe5dbb7c33`: `src/rtwn8723be_rx_native.c` rejects a descriptor ring whose mapped size is smaller than `count * sizeof(descriptor)`, and rejects RX slots whose loaded map or only segment is shorter than 9,100 bytes. Checks precede corresponding bus_dma synchronization. Do not re-arm a corrupt slot.
- Commit `e0e25d061526db610eb3671d3bc327a875f3d08d`: also validates the full buffer DMA span rather than only its start. The maximum permitted start address is `UINT32_MAX - (9100 - 1)`. A buffer starting at `UINT32_MAX` is invalid despite its start address fitting in 32 bits.
- Regression: `tests/test_rx_dma_bounds.py`, commits `f31d5ce383b8ff1b6ecce2ef684f7638c38428b5` and `6b40726890f0c5ba4716ca29c3a7e0f96ac4f141`. It extracts the actual slot guard from production C and compiles it with strict C11/`-Wall -Wextra -Werror -pedantic`/UBSan plus negative and boundary cases; separately asserts the descriptor-ring capacity preflight in source.

## Verification and limits

Direct GitHub readback confirmed exact production blob `1a449bf9b3071ff0e2ea430dc2d9fa6451025026` and Python test blob `5568445f7dedd6ff8705b599541d2faaf10bd89b`; all seven direct source/test predicates passed. Independently compiled and executed the committed *guard logic copied into a standalone C11/UBSan harness*: 12 positive/negative assertions passed, exit 0. The exact published Python regression has **not** been executed. The complete `rtwn8723be_rx_native.c` has **not** been compiled as a native NetBSD kernel object, linked, or exercised on HP hardware; no IRQ/ring concurrency or complete driver readiness is implied.

The last verified recovery kernel F77 and existing i915 six-edit overlay were not modified. Direct HP Desktop Commander agent remained offline during this continuation. This checkpoint does NOT close COV-RTL-003 or COV-RTL-014.

## Required next dependencies

Keep source/published-test and native-object testing distinct. Repair only through an actually permitted route the previously externally denied PCI power rollback, H2C implementation and TX-PG/BB test corrections; do not reroute around those denials. Finish RX/TX/net80211 ownership, interrupt and reverse-detach semantics; complete remaining PHY/RF/BT/security/PM and all 53 Linux lifecycle callbacks. Build in an isolated genuine NetBSD tree before any candidate/HP boot test. Parallel i915 complete 323-unit/DRM/TTM scope remains OPEN. Canonical oversized `Agent-Governance/LAST_TASKS.md` in-place update was previously externally denied; this project-local handoff records the scoped verified delta without claiming LAST was synchronized.
