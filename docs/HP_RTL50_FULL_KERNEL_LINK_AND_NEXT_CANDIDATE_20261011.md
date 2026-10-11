# HP RTL8723BE – verified full NetBSD 11 kernel link and next-source gate (2026-10-11)

STATUS: **FULL 50-UNIT NETBSD KERNEL LINKED; NEXT SOURCE REVISION NOT YET REBUILT; RADIO RX/WPA2 NOT TESTED.** Times Europe/Berlin. This record supersedes earlier partial-link claims; it does not promote a kernel to TESTREADY or production.

## Real HP NetBSD executable link: supplied and checked 2026-10-11

At approx 07:50 CEST on 2026-10-11, the native HP owner build completed in the isolated, immutable pre-RX-filter source staging directory:

`/home/andreas/projects/netbsd-driver-recovery-20261011/rtl-kconfig-live-inc-20261011`

The HP's separately fetched `full-kernel-link-ldfixed.state` reads **`LINKED`**. The `obj/netbsd` file is **26 MiB** and its `newvers.sh` identity is:

`NetBSD 11.0 (HP-RTL-WIP50-SAFE-GENFB) #0: Sun Oct 11 07:48:35 CEST 2026`.

The actual build log contains a complete `x86_64--netbsd-ld -Map netbsd.map ... -o netbsd` command, including all 50 `rtwn8723be_*.o` native C files, with successful link, a `size` report, final `netbsd.gdb`, separated debug file and the finalized executable `netbsd`. No link failure remains for this **prepatch** source candidate. The user independently supplied the output through `ssh andreas@10.1.0.44`; this is readback evidence, not an inferred background job state.

**The 26 MiB file has NOT been installed, rebooted or demonstrated PCI/RX/WPA2 hardware function.** It does not contain the newer `RXFLTMAP0/1` management-filter patch committed separately afterward. Do not claim it represents current GitHub HEAD or recommend booting it for WPA2 acceptance.

The original `libkern.o` failure (`collect2: fatal error: cannot find 'ld'`) was rooted in the owner wrapper's cross-GCC linker lookup; the generated wrapper now supplies isolated `x86_64--netbsd-ld` and checks a real GCC `-nostdlib -r` link before an entire kernel build.

## Reconciliation following the verified link

The opt-in WIP source branch `wip/hp-rtl-runtime-48-merge-20261010` now contains all 50 C sources, all 53 Linux-stage callback mappings, and the newer candidate `RXFLTMAP0/1/2=ffff/0400/ffff` from identified 8723B source reference. An earlier **physical HP native C compilation** of the RX-filter change and source-order gate PASSED (2 exact affected units). However, that RX patch has **not** been included in the full executable kernel linked above.

After the link, two further source-level shutdown bugs were found and fixed, **not yet compiled on HP**:

1. `src/rtwn8723be_runtime.c:rtwn8723be_runtime_stop`: a registered net80211 ifnet at the explicitly enumerated `IEEE80211_REGISTER`, `RFKILL`, `IRQ_ESTABLISH` or `PROBED` stage has never started HAL/firmware/RX engines. Stop can disestablish its PCI interrupt and return without invoking a hardware shutdown, but only if `being_init_adapter`, both firmware readiness flags, HAL, BTC and IRQ-enable state are clear. An actual partial HW start must not pass this software-only exit.
2. `src/rtwn8723be_runtime.c:rtwn8723be_runtime_unregister`: previously swallowed a nonzero stop error if just `poweroff_verified` was true, incorrectly allowing net80211 detach after failed RX/TX ring DMA reset, BTC retire or ASPM restore. Now **any nonzero shutdown result retains the ifnet/PCI lifetime**; no partial-poweroff pretext grants permission to release DMA.

New `tests/test_probe_unstarted_and_failed_shutdown_gates.py` source check verifies these explicit stages/guards, accepted shutdown failure and reverse-order PCI/net80211 lifetime retention. A direct GitHub source check of these guards passed; **actual native compilation and fault-injection run are pending**.

## Source-identified, no-install next HP build

A new safety-gated, **unprivileged** script is committed at `tools/build_hp_rtl50_next_candidate.sh`. The generator `tools/configure_hp_live_native_50.py` now checks a clean and exact WIP branch, captures the full Git SHA and writes the build's short SHA into the kernel version itself: `HP-RTL50-<12-char-git-sha>-SAFE-GENFB`. This prevents the successful **old** kernel from being mistaken for the **new** source with beacon filter and teardown changes.

The script:

- checks HP NetBSD, unprivileged owner, running safe F77, clean WIP branch and preserved prior linked candidate;
- verifies source-backed RX-filter, ownership, IRQ, DMA, runtime and probe rollback regressions before config;
- generates an **entirely new** owner-only source overlay and NetBSD Kconfig with i915drmkms disabled and a working private NetBSD cross-linker;
- invokes actual `nbmake-owner -C obj -j2 dependall`, logs to the new directory and persists `full-link.state`;
- verifies final `netbsd` file nonempty, `what` containing exact expected commit-specific kernel identity and unchanged checkout HEAD/working tree; prints SHA256 if link accepted;
- intentionally performs **no install, boot, firmware replacement, root access, WLAN activation, Tailscale or network changes**.

This script was audited by GitHub-source assertions, not executed on the HP. The new full binary remains **NOT_BUILT**. It is not safe to conflate source checks with compiler or hardware acceptance.

## Execution and permission constraint

At 11:56 CEST the ChatGPT Remote Desktop Commander connector returned an explicit **monthly usage quota** refusal (`INVALID_ARGUMENT`, device still connected) and instructed **do not retry/reconnect**. No subsequent HP tool access or new full kernel build was claimed. No executable Tailscale connector is exposed. The user still has independently functioning client SSH access to `andreas@10.1.0.44`, confirmed by the full kernel log above. Any future manual SSH action remains user-directed and must not evade an externally denied assistant connector operation.

## Source-level blocker found while SHA-pinned 2e5a2cc is building (2026-10-11)

The owner reported `full-link.state=RUNNING source=2e5a2cc97b9bbae3e55aa984e1477e7c29858bce` at roughly 12:12 Europe/Berlin. The 3.0 MiB log was still producing normal `nbmkdep` .d targets (`if_re_pci.d`); the final new-kernel ELF link was **not** shown. No remote privileged command, install, radio probe, boot or connection reset was performed. This user-observed output supersedes no earlier ELF result.

A deterministic **first firmware start RF calibration prerequisite cycle** was found by reading the exact frozen Linux `rtl8723be/hw.c:rtl8723be_hw_init()` and `dm.c` reference:
- Linux performs `rtl8723be_phy_iq_calibrate()`, `rtl8723be_dm_check_txpower_tracking()` and `rtl8723be_phy_lc_calibrate()` under ERFON **before** `rtl8723be_dm_init()`. The tracking helper returns early when `txpower_tracking` is false; `dm_init_txpower_tracking()` runs later.
- Native NetBSD Linux-state order preserves `R23BE_STAGE_RF_CALIBRATION` before `R23BE_STAGE_DM_INIT`. Its runtime owner truthfully sets `in->dm_state_valid=r->dm.software_initialized`, so on the first start this flag is false.
- The earlier portable `rtwn8723be_calibration_run()` rejected *all* RF-ON IQK/LCK if `!input->dm_state_valid`, yielding unavoidable `ENXIO` on a first start even when the real RF, BT and register owners were ready.

Fix committed **after** source 2e5a2cc was already building: `src/rtwn8723be_calibration.c` now requires BTC owner as before, but requires initialized DM **only if** the driver explicitly enables temperature-based TX power tracking. On the first start with tracking not enabled, source-derived IQK/LCK may run without falsely claiming DM initialized. Tracking requested without DM still fails closed with `ENXIO`.

`tests/calibration_check.c` gained both negative (tracking enabled, no DM -> ENXIO, zero MMIO) and positive (tracking disabled, no DM -> real LCK transaction) regressions. `tests/test_rf_calibration_pre_dm_source.py` guards the Linux-stage order, real runtime DM readiness producer and selective calibration preflight; the next candidate build runner also runs the HP-only native calibration and calibration-adapter C oracles. The changed source and checks were directly reread on GitHub; source checks passed, but **new production C native build and host-executed oracles have not yet run on HP** because RDC quota was reached. The in-progress 2e5a2cc build uses its older immutable source; do not mutate it or pretend this later fix is included.

FAILURE_FINGERPRINT: `RTL first hardware start | calibrated RF/DM callback ordering | DM initialized only after calibration, but portable calibration required it in advance | frozen Linux rtl8723be + NetBSD 11 owner state graph | first radio start must not fail ENXIO before IQK/LCK`. Classification: **source sequencing contract defect**, not an unverified PCI/firmware failure.

Pinned Linux reference:
- https://raw.githubusercontent.com/torvalds/linux/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/rtl8723be/hw.c
- https://raw.githubusercontent.com/torvalds/linux/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/rtl8723be/dm.c

## Source and branch reconciliation – follow-up while 2e5a2cc builds

**Last actual HP status presented by requester:** `RUNNING source=2e5a2cc97b9bbae3e55aa984e1477e7c29858bce`; log approx 3.0 MiB at 2026-10-11 12:12 CEST; `nbmkdep` still writing dependency targets. The kernel's final `LINKED` identity has **not** been shown. Do not infer completion from elapsed time and do not update the HP source checkout while this specific build is accessing it.

**Two active histories (GitHub compare, 2026-10-11):** canonical `main` and this experimental 50-unit WIP have **diverged**, not fast-forwardable. From main to WIP: WIP ahead 89 commits, behind 12; merge base `08dcf79a83e9e6a7e4ee1196d4a41845dca4e341`. Main includes independent `rtwn8723be_regdomain.c/.h`, fail-start `linux_adapter_abort`, `net80211_state.h`, runtime owner foundation and tests, while this branch has the 50-unit Linux runtime, BT callbacks, RX filter and kernel link. **Do not blindly merge conflicting PCI, net80211, RFkill or abort paths.** The current WIP channel loop marks 1–14 uniformly active while main's independently validated world baseline treats channels 12–13 as passive and 14 as passive CCK only; the parity discrepancy is **open**, not declared resolved.

**New source-graph safety improvement, not in SHA 2e5a2cc:**
- `rtwn8723be_runtime_start` previously returned the *initial* startup error even if reverse hardware shutdown then failed. Because a secondary failed DMA ring reset/BTC retire/ASPM restoration can leave the device unsafe, the returned error now prioritizes the actual shutdown fault while `r->first_error` retains the original fault and `r->shutdown_error` the rollback fault.
- `tests/test_runtime_start_shutdown_error_source.py` is included in the next HP preflight and guards two-error reporting, stop-on-failed-unregister and real post-poweroff error accounting. GitHub source-readback assertions passed; there is no HP production C or kernel build of this fix yet.

**Private immutable source build fix, not in SHA 2e5a2cc:**
- Previously `tools/configure_hp_live_native_50.py` symlinked every RTL C/H/INC directly to the mutable Git checkout. A `git pull` or checkout replacement during `nbmake` could silently mix source revisions under one ELF-ident label.
- New generator **copies** all matching RTL C/H/INC files into the owner-only Kconfig overlay, hashes each source before copying, validates copied bytes immediately and after Kconfig/toolchain preflight, and records full `source_snapshot_sha256` and Git SHA in `status.json`. Baseline NetBSD system source is unchanged and remains read-only.
- The new read-only `tools/verify_hp_rtl50_source_snapshot.py` checks the 50-source selection, all regular-file digests, full Git SHA and kernel-ident relationship. The safe no-install build runner calls it **both before and after** `dependall`. A new source regression `tests/test_hp_rtl50_source_snapshot_contract.py` checks the absence of mutable per-file Git symlinks and requires the two integrity gates.
- These changes were committed and GitHub-readback source-gate checks passed. The generated snapshot, additional tests and next candidate are **not yet HP-executed/compiled**. Do not change the running 2e5a2cc overlay to retrofit this after its build started.

**i915 scope remains separate:** F83/F84 both physically black-screened; F84 async fbdev scheduling was disproven as an adequate fix. The i915 trace transport record requires a proven independent early console/trace before another physical display takeover; no new i915 hardware experiment, install or boot was performed in this pass.

## Next exact acceptance

1. On the HP, synchronize clean WIP HEAD and compile the **new** SHA-labeled kernel with `tools/build_hp_rtl50_next_candidate.sh`; verify its actual native output and SHA256. Do not overwrite the previously linked prepatch `obj/netbsd` or F77.
2. Audit actual startup/runtime/abort semantics with failure injection and validate fresh PCI + H2C + DMA IRQ + register readback. Do not boot an unverified candidate without recoverable console/logging/physical fallback.
3. Measure **real** management beacon counters, scan results, WPA2 4-way handshake, association, IPv4/DNS/traffic and restart/PM after safe candidate deployment. Existing F77 radio remains DOWN/SSID empty at last actual host inspection.
4. Independently complete physical Intel i915 DRM/KMS (F83/F84 both previously black-screened) with durable display-phase evidence. This RTL-only kernel intentionally does not include the modern KMS port.

Parent objective remains **two physically functional NetBSD drivers**; only the RTL executable link gate is DONE for the prepatch source.
