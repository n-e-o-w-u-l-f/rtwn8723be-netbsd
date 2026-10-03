# Native source integration checkpoint — 2026-10-03

Status: **SOURCE-WIRED / FAIL-CLOSED / NOT COMPILED / NOT TESTREADY**.
Parent objective remains complete RTL8723BE Linux-to-NetBSD lifecycle and firmware port, not merely first hardware bring-up.

## Actual committed delta

- `src/rtwn8723be_native.c` introduces a distinct, opt-in NetBSD PCI CFATTACH for PCI vendor/product `10ec:b723`. It uses the **real** `struct rtwn8723be_softc`, initializes the real NetBSD context, and enters `rtwn8723be_linux_probe()` with the existing `rtwn8723be_netbsd_ops` rather than the historical F8.4 dry-run implementation.
- `config/files.rtwn8723be_native` defines a separate NetBSD `device`/`attach` pair and the present twelve-source object graph: PCI/native entry, NetBSD adapter, DMA, firmware, Linux-order lifecycle, package EFUSE, power sequence, BB sequencer, PHY interpreter, RF serial, RF path and OEM selection. This is NOT the complete driver build closure.
- Unchanged `src/rtwn8723be.c` is the original passive F8 diagnostic entry. It is **not** listed in the new native graph. Do not silently replace F8 or select both attachment definitions in a kernel.
- Fresh direct GitHub readback verified native-entry blob `3d2ef54175668c6361fa0588c06d7584950c5c50` and filelist blob `2b966bc8140532190e5d1d353519396593aedce0`. An independent graph check established all twelve listed C source files exist, all fourteen quoted local header dependencies are present, and a lexical cross-source check found no unresolved `rtwn8723be_*` function names across this candidate graph (113 referenced/identified, including definitions; **not** an object/link test). The device/file declaration syntax was checked against the frozen NetBSD `sys/dev/pci/files.pci` convention for `rtwn`.

## Why this is not an attachable WLAN driver

- Existing `rtwn8723be_linux_probe()` preflights **all** probe operations before its first PCI/MMIO/DMA mutation. Today `rtwn8723be_netbsd_ops.register_ieee80211` and `init_rfkill` are NULL, so this candidate returns `ENOSYS` rather than registering an imaginary interface. Other start/hw callbacks are absent. Native entry logs failure; it is not a successful device activation.
- Probe rollback, detach, net80211 teardown, and full error ownership across PCI command/BAR/32-bit DMA/rings/IRQ/RF are **not** closed. **Before making the last missing probe callback available**, implement and verify full reverse-order rollback, stop/detach, registration ownership and failure-injection cases. The native entry must not be selected in a running/boot candidate before that work is complete.
- `src/rtwn8723be_txpwr_pg.c` still has an independently identified missing `<stddef.h>` while using NULL; its prior requested fix was externally safety-denied. It is deliberately not in the current *partial* filelist: full-scope inclusion remains a blocker and must not be silently classified as inapplicable.
- Published `tests/test_phy_bb_sequence.py` is out of sync with the required `reset_pwrgroup` callback; earlier exact edit denied. Crystal-cap extraction, actual PHY identity, RF bus_space/locking, H2C/C2H protocol, TX/RX datapath and BT/calibration/PM remain open.
- No NetBSD `nbconfig`/`nbmake-amd64` executable was found on the freshly inspected Legion shell `PATH`; the prior blocked host-sync/native-build operations have not been retried through another route. **No kernel object, linker result, installed kernel, association or packet transfer is claimed.**

## Correct next dependency sequence (the unchanged full parent scope)

1. Repair known TX-PG/BB/XTAL issues through a genuinely authorized normal edit route and complete **validated** PHY/EFUSE identity plus the RF adapter. Reconcile the published candidate with any unpublished work before synchronizing.
2. Implement real net80211 registration, rfkill and full failure rollback/detach **before** enabling native probe. Implement complete frame buffers, descriptor ownership, TX/RX, interrupts and firmware H2C/C2H semantics. Integrate MAC/BB/RF/calibration/coexistence/runtime/PM callbacks in pinned-Linux phase order.
3. Obtain an authorized NetBSD build environment and add this manifest to an **isolated** candidate tree, not the F77/recovery tree. Compile all required objects with generated NetBSD kernel headers, link, resolve every failure, and run regression and fault-injection tests. Expand manifest to **every** required source, including fixed TX-PG; do not accept this partial manifest as build parity.
4. Preserve F77; only after build/rollback/source-review gates, select an independent kernel and test on the actual HP, where current live reachability/kernel/boot state is unknown. Neither the RTL driver nor the parallel 323-unit i915/DRM/TTM port is FULL/PARITY/TESTREADY.

Reference authority: `torvalds/linux fd179f8a05be3ccae366b9b96e176b51fbe54aab`, `NetBSD/src 03d918f6d0e81fa05b8f1160eca0628ad39988a6`, and each current owning project GitHub HEAD. Project FULL_SCOPE_CONTRACT remains the parent coverage authority.

## Continuation: pre-registration rollback and H2C transport boundary

Verified new production commits:

- `35714c2` extends `rtwn8723be_netbsd.h` to snapshot PCI COMMAND, power state, device configuration bytes 0x44/0x81 and a saved-state flag before any probe mutation.
- `e4aceba` extends `rtwn8723be_native.c` with a pre-registration cleanup path for established IRQ/softint, DMA rings, 32-bit DMA tag, original PCIe LCSR, BAR mapping and saved PCI settings; it adds a guarded detach that refuses a registered/running adapter until the full net80211/runtime teardown exists. These are committed source changes, NOT a native NetBSD build or runtime proof.
- **REMAINING CORRECTNESS BLOCKER:** Source review identified that `0x44` is restored before PCI COMMAND and `pci_set_powerstate()`; this can restore D3 prematurely, and full-word byte restoration can affect the PMCSR write-one-to-clear PME status bit. A targeted correction was attempted and externally safety-DENIED. Do not repeat by another route. This code is **not authorized for hardware activation** until corrected and source/build/error-injection reviewed. Current probe preflight still returns ENOSYS before any hardware mutation, so this incomplete cleanup is not exercised by the current ops table.
- `a56f8e4` created `src/rtwn8723be_h2c.h` from pinned Linux `rtl8723be/fw.c` mailbox semantics (four boxes, 1..7 payload bytes, extension-first for long messages, serialization, poisoned-on-write-failure contract). Creation of `src/rtwn8723be_h2c.c` was independently safety-DENIED; it does **not** exist in GitHub main, was **not** added to `config/files.rtwn8723be_native`, and H2C/C2H remain OPEN.
- Latest verified RTL main `a56f8e49b55ca9686dcb0da3cba3cb9ead9854d2`, i915 main at turn entry `b8101ecc54bf8f8970f44937bdcfaf40ecc26a52`. Legion online; HP direct agent offline; six-edit local i915 overlay and F77 are unchanged. `LAST_TASKS.md` remains at blob `509c514...`; the old oversized canonical update path was previously safety-DENIED. This project-local checkpoint records new facts without claiming LAST has been updated.

Acceptance remains: resolve the external policy-blocked specific corrections via genuine authorized permission change, complete net80211 registration and teardown, full PHY/RF identity, TX/RX, BT/firmware protocols, all 53 lifecycle callbacks and i915 source closure, native NetBSD build, then separate candidate hardware testing. No FULL/PARITY/TESTREADY label.
