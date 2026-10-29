# 0084 — RTL rejected DMA-map unwind and dual-driver source reconciliation

State: SOURCE PATCH + SOURCE CHECKS ONLY. Parent port remains PARTIAL.
NetBSD pin: `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
i915 starting HEAD: `45f278306e2f34674cbf90a2524ac0872c84ef9e`.
RTL starting HEAD: `e33bdeb969e7efddcf7352c8874a0d30351db214`.

## Reconciled branches and evidence

i915 work branch `work/hp-native-drm-stage-replay-20261015` was independently read at the requested 0083 HEAD; main remains `27fd4d7d483be456158884c08d04446dd5312326`.
RTL work branch `wip/hp-rtl-runtime-48-merge-20261010` was read at e33bdeb; main remains `569d0d16cc307bfbef40aef9fd7b553322cadb1f`.
The old main STATUS files do not describe current WIP runtime bindings: WIP netbsd_ops binds register_ieee80211, bt_prepare and dm_init to actual runtime functions. This proves source wiring, not working WLAN.

Canonical AGENT_BOOTSTRAP, AGENT_STANDARD, LAST_TASKS, PROJECT_REGISTRY, GOVERNANCE_MAP, requester preferences, both project states, HP-I915 CURRENT and 0071/0081/0054 events were read.
LAST_TASKS remains an index; its historical build descriptions are not fresh runtime observations.
The referenced ChatGPT conversation exposes content-reference placeholders only, with no research report attachment/body. A line-by-line report review is therefore NOT_POSSIBLE in this session. No report claim has been silently accepted.

## Actual source repair (RTL owning repository)

`src/rtwn8723be_f16_1_dma.c:rtwn8723be_f16_1_dma_mem_alloc` loads a map, then rejects unexpected segment count, mapsize, segment length or 32-bit range. Previously it jumped directly to the common free routine. Since the map was loaded, free performed POSTREAD|POSTWRITE even though the first PREREAD|PREWRITE and descriptor publication had not happened.

The patch unloads the successfully loaded but rejected map before common cleanup. The pinned x86 unload clears dm_mapsize and dm_nsegs, so free skips POST and the second unload, then releases KVA, allocation and handle. The successful allocation path, packet mappings, register writes and release order are unchanged.
This is a defensive rejection-path repair; the expected 32-bit tag should already enforce the address constraint. No HP incident or observed corruption is attributed to this branch.

Source commit: [114fe8178da5c1037c4458016e8dbbaee05470b2](https://github.com/n-e-o-w-u-l-f/rtwn8723be-netbsd/commit/114fe8178da5c1037c4458016e8dbbaee05470b2).
Original Git blob: `25014517a145a731c33ab5130b9a757d88ff56be`.
Patched Git blob: `790e4c3cbd46cf6405b689023087d94e5b481050`.
Patch SHA256: `59b163f9162902eb0f8c726c458c95ae012e90ce440ece03646b845fe47ea03a`.

## Critical DMA corrections from pinned primary sources

[NetBSD bus_dma(9)](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/share/man/man9/bus_dma.9) defines READ as device-to-memory and WRITE as memory-to-device. PRE and POST may not be mixed in one call; PREREAD|PREWRITE and POSTREAD|POSTWRITE are same-phase pairs and are legitimate for bidirectional descriptor ownership.
Coherent mappings can allow the backend to omit expensive cache operations; they do not justify deleting required DMA synchronization/order boundaries. Other DMA operations cannot be relied upon to synchronize implicitly.
DMA addresses come from a successfully loaded map's dm_segs, not directly from bus_dmamem_alloc's opaque segments.
[The pinned x86 backend](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/x86/bus_dma.c) invalidates map size/count on unload; POSTREAD can copy a bounce buffer. An unnecessary pre-publication POST is not a hardware completion.
No FreeBSD bus_dmamap_load callback signature or cache rule was transplanted into this NetBSD driver. No conclusion about every FreeBSD architecture is needed or claimed.

## Open coverage and verified source observations

| Coverage | Observed current source | Remaining acceptance |
|---|---|---|
| RTL TX rings | private descriptor encode, 32-bit loaded-map validation, packet PREWRITE, OWN and queue doorbell; batch tail-to-head publication; reclaim POSTWRITE/unload before owner release | Native map failure injection, ring wrap/exhaustion, device ordering, DMA-stop-before-free and timeout/recovery |
| RTL RX rings | two queues, descriptor POST sync; bounded single-buffer map validation; payload POSTREAD, borrowed dispatch, PREREAD before rearm | Native bus_dma diagnostics, real beacon/BSS scan, C2H/frame dispatch and stopped-DMA teardown |
| RTL PCI IRQ | softint creation, pci_intr_alloc/establish and failure unwind; requested-state lock prevents softint rearm after disable; teardown disestablishs hard IRQ then softint | Native in-flight hard/soft IRQ and worker rundown; stale pending/posted-MMIO behavior, stop/suspend/detach races |
| RTL net80211/WPA2 | WIP advertises WPA2 and explicitly selects framework software crypto; hardware CAM offload is separate; runtime has real owners | Association, four-way handshake, key/replay handling, real encrypted TX/RX and sustained traffic, suspend/restart |
| i915 GEM/GTT/PPGTT | Existing full-32-bit-PPGTT patch and gen8/gen6 VM-unwind candidates remain source artifacts | Actual composed pinned native build, page/table DMA lifetime, GGTT/PPGTT switching, requests/reset/PM; no causal black-screen conclusion |
| i915 connector/backlight | 0083 is separate staged ABI/provider prototype; pinned backlight implementation is enable/disable no-op; config remains class=0 | Actual pinned header/C integration, preserved class=0 behavior, native configured object/consumer compilation, wsdisplay/ACPI owner, callback lock/lifetime and rollback |
| Physical HP recovery | Historical 0079/0080 safe-textmode observations are newer than main STATUS's F77-only description | Current state not reprobed; independent early console and physical F77/stock recovery drill before experimental boot |

0083 unregister waits on admitted callbacks; external ownership must serialize unregister and prevent use after completion. Its pthread fixture is not proof of all native DRM lock interleavings. No backlight config or production i915 source was enabled here.

## Executed validation and diagnostics

Local Windows Python source-only guard:
- Original exact e33bdeb source: expected rejection, exit 1, missing pre-cleanup unload.
- Patched actual source: exit 0.
- Five source-text mutants refused: removed/duplicate/unreachable unload, inserted premature POST, lost EFBIG.
- Source patch exact preimage and Git blob/SHA256 manifest recorded.

The first guard version matched both function definitions and call sites and failed on both sources before reaching the intended assertion. It was corrected to definition markers; original-red and patched-green acceptance were rerun. This was a checker defect, not a driver build failure.
Local Git is unavailable, so difflib generated the review patch; a real git apply on a checkout was NOT_RUN.
Evidence JSON preserves commands, full captured error output, exits and identities. Its timestamp is from the execution host; governance event times use the clock service.

No C compiler was invoked. Existing C mock harness `test_dma_mem_unwind.py` exercises free in isolation and omits this allocator rejection path; its historic PASS does not cover this change.
Native NetBSD compile/object/link, native DMA failure injection, QEMU, HP boot, KMS and WPA2 are all NOT_RUN.
No native or hardware coverage row is closed by these source predicates.

## Safety and next action

0071 Legion source-preflight, 0081 HP header read, 0054 unknown scratch/readback and Nouveau restrictions were not retried or rerouted. No HP/Legion command, kernel tree, installed kernel, EFI, boot.cfg, radio or production change. No hosted CI was launched; commits use skip-ci.

Next source step: extend the owning allocator/free C failure-injection fixture to execute the actual allocator rejection and successful teardown paths, including DMA sync state, then run it only on a legitimately permitted HP compiler. Native execution remains blocked until its environment and permission are independently available; do not retrieve denied header paths by another route. Independently continue exact pinned backlight integration design without enabling the feature.
