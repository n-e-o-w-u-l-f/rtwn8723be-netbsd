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

## Next exact acceptance

1. On the HP, synchronize clean WIP HEAD and compile the **new** SHA-labeled kernel with `tools/build_hp_rtl50_next_candidate.sh`; verify its actual native output and SHA256. Do not overwrite the previously linked prepatch `obj/netbsd` or F77.
2. Audit actual startup/runtime/abort semantics with failure injection and validate fresh PCI + H2C + DMA IRQ + register readback. Do not boot an unverified candidate without recoverable console/logging/physical fallback.
3. Measure **real** management beacon counters, scan results, WPA2 4-way handshake, association, IPv4/DNS/traffic and restart/PM after safe candidate deployment. Existing F77 radio remains DOWN/SSID empty at last actual host inspection.
4. Independently complete physical Intel i915 DRM/KMS (F83/F84 both previously black-screened) with durable display-phase evidence. This RTL-only kernel intentionally does not include the modern KMS port.

Parent objective remains **two physically functional NetBSD drivers**; only the RTL executable link gate is DONE for the prepatch source.
