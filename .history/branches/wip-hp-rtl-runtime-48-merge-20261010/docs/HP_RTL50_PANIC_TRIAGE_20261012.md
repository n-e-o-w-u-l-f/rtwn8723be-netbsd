# HP RTL50 panic: mandatory evidence and no-guess repair checkpoint

Date: 2026-10-12. Source of truth: WIP `wip/hp-rtl-runtime-48-merge-20261010`, not unrelated 48-unit default `main`.

## Observed, not extrapolated

- The HP produced a complete NetBSD 11 amd64 ELF link for exact Git `2e5a2cc97b9bbae3e55aa984e1477e7c29858bce`, identity `HP-RTL50-2e5a2cc97b9b-SAFE-GENFB`, SHA-256 `2eecc4e188c247514d5bc5b639c2773f3d8a823e4f84cc3a65e7e4960471a423`. The user verified status, embedded ident, and hash over SSH.
- The user subsequently **reported a kernel panic when attempting to boot RTL50**. This overrides previous statements suggesting the linked ELF was boot-safe. Neither the panic text nor a DDB stack trace was supplied; exact faulting function/stage/cause is **UNKNOWN**.
- Earlier user-visible F77 boot was successful after the panic. Later the user requested replacing F77/F16/RTL50 defaults with original NetBSD GENERIC. A restoration script was previously offered, but no successful staging/boot/cleanup evidence was provided. Thus the **current live bootfile and fallback are UNKNOWN**, not implicitly F77 or GENERIC. The next host access must verify `uname -v`, `kern.bootfile`, `/boot.cfg`, `/netbsd` identity, and backups before any change. Do not delete recovery artifacts based on intent alone.
- The source branch after 2e5a2cc contains corrective DM/BTC event lifetime, calibration order, RF ownership publication, regression and teardown changes. They have **not** been compiled into the panicking ELF, and do not by themselves establish the root cause of its boot panic.
- RDC remote command quota readback was 0% remaining; account reset timestamp was not exposed. Tailscale enables network transport but this chat still has no independently authenticated command executor on the tailnet; another remote device being ONLINE is not proof of command authorization.

## Immediate forensic gate: read only

New program `tools/inspect_hp_rtl50_panic.py` captures the exact candidate and boot identities plus `/var/crash` filenames/sizes and `savecore` config, **without reading core memory, writing files, or triggering a reboot**. Python source-only regression `tests/test_hp_rtl50_panic_inventory_source.py` checks AST/regex/read-only contract. Both are COMMITTED. Independent host-side **pure-Python** test run passed `HP_RTL50_PANIC_INVENTORY_READ_ONLY_SOURCE_CONTRACT_OK`: both reconstructed test/collector files were byte-exact to GitHub blob SHA-1 `4169777ccc5f652f393e999e8c931c7a6e73ab41` and `bf6bd2699c2a328410b7eadbf610aadcfb21a61f`. The first test run caught a real false-positive guard (`platform.system()` vs `os.system()`); guard repaired and the exact regression rerun PASS. A direct collector execution on a NON-HP host refused as designed (exit 2). An additional isolated Python fixture test of the exact committed collector passed `HP_RTL50_PANIC_INVENTORY_SYNTHETIC_FIXTURE_PASS`: two simulated dump files, three boot menu lines, exact kernel SHA over mock bytes, absent artifact classification and exclusion of an unrelated `private_key` filename. No real HP file was accessed by that fixture. **Actual HP execution, recovered crashdump, C/native compile, physical root cause and new kernel link remain OPEN**.

In NetBSD, DDB `trace` at the panic prompt, and a saved crash dump under `/var/crash` analyzed with the **matching** kernel image (ideally corresponding `netbsd.gdb`) are the authoritative fault evidence, not a later GENERIC/F77 dmesg alone.

Useful official NetBSD references:
- https://www.netbsd.org/docs/kernel/
- https://wiki.netbsd.org/tutorials/panic/
- https://man.netbsd.org/savecore.8

Core dumps contain process memory and sensitive information: retain privately and report redacted diagnostic frames, not raw memory to GitHub.

## No-build/no-reboot release gate

1. Confirm the current HP boot identity and recoverable default independently; never assume F77 is still installed or even desired.
2. Retrieve the **actual RTL50 crash evidence**, identify the faulting PC, DDB `trace` or saved core stack, exact PCI/RF/net80211 phase, error path, and relevant kernel `netbsd.gdb`.
3. Compare the faulting call graph to frozen Linux `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab` and NetBSD/src `03d918f6d0e81fa05b8f1160eca0628ad39988a6`. Use the actual NetBSD PCI, bus_dma, net80211, kthread/task, lock, firmware and unwind primitives – no invented Linux API callbacks or register guesses. Retain negative controls and untouched hardware reference data.
4. Review every selected source and the full NetBSD build config, compile options, object/DMA/IRQ/lifetime graph and retained prebuild manifest; close every critical mismatch before calling the builder.
5. Execute **only on HP** tests and a new isolated 50-unit kernel compile and full link after panic cause and recovery verification; preserve source SHA, Kconfig, logs and kernel `what`/SHA-256. Compiled is not boot-safe.
6. Expose a single recoverable manual boot candidate ONLY after a separate TESTREADY review. No silent boot default promotion, no automatic reboot or production WLAN claim.

A documentary panic evidence guard `tools/verify_hp_rtl50_panic_gate.py` is published. Its attempted integration into the existing kernel builder was rejected by an external safety check, so **the build script remains UNGUARDED BY THIS NEW GATE**. Never claim an enforced guard that was not published; manually withhold approval of that builder. Do not repeat the previously rejected write through another shell, account or endpoint absent new permission evidence.

## 2026-10-12 — audited PCI command/status source correction (NOT panic attribution)

The frozen Linux `drivers/net/wireless/realtek/rtlwifi/pci.c` driver invokes `pci_enable_device()` then `pci_set_master()`, abstracting PCI command setup through Linux PCI core. The NetBSD WIP binds these to `rtwn8723be_netbsd_pci_enable()` and `rtwn8723be_netbsd_pci_set_master()`. Previously both read `PCI_COMMAND_STATUS_REG` and echoed all 32 bits into a PCI config write, including the 16-bit status half. NetBSD `sys/dev/pci/pcireg.h` at the pinned commit defines `PCI_COMMAND_MASK=0xffff` and `PCI_STATUS_SHIFT=16`; status includes write-one-to-clear bits. The existing WIP native unwind independently warned that writing saved status [31:16] could acknowledge unrelated PCI state.

Source change published on WIP in commit `8af255e05d3a763b635d0f37eae94f92ffd488fa`: both C functions now compute `pci_conf_read(...) & PCI_COMMAND_MASK` *before* OR'ing the respective unchanged IO/MEM/bus-master enable bits. This translates the Linux PCI intent through native NetBSD PCI command semantics; it does not add a Linux API stub, firmware or register constant. No other driver operation changed.

Regression `tests/test_netbsd_pci_command_status_w1c.py` published in `19b17b83f6219e4f8e717bdf68ca2c4c5bae570f`, tightened in `832a0144ce3625e0e758d125a51445bd391c62f8`. Independent GitHub readback: native C blob `73e74c1c7fe22432b1285ee676f81d534b041498`, regression blob `12903072f13a151523f8f796a54fe029f853c9bc`. Source-shape verification and a separate JavaScript W1C model passed 25 representative command/status states **per each of the two functions** and a negative-control old write cleared status. This is **NOT** the Python test script or a NetBSD C build run, and it is NOT a hardware or RTL50 panic repair acceptance. Next HP-only native compile should run the published regression and compare the final object/linked kernel source hash.

### Critical buildplan drift

The existing `tools/build_hp_rtl50_next_candidate.sh` still requires `uname -v` to contain `RTWN8723BE-F77-LINUX-EFUSE-MAP`. The user's more recent destination is **original NetBSD GENERIC as boot default**, with obsolete F-series kernels to be retired only after GENERIC is actually verified running. The HP's latest live boot identity, the GENERIC recovery file and the current boot.cfg are unknown. Therefore the stale F77 identity gate is *not* valid evidence of the new desired safe configuration and the existing builder must remain unapproved. Its separate mandatory panic dossier checker has still not been integrated due a platform-denied write. Do not silently change the boot default, automatically reboot, or replace `/netbsd`; first verify actual target console/boot state and hardware panic evidence, then legitimately reconcile the builder's recovery assertions and exact source checkout.

## Independent i915 blackscreen scope

The Intel Cherryview/Braswell 8086:22b1 i915drmkms blackout is separately reproduced in F83 and F84 (backlight on). No persistent early display trace survives. Its already published `patches/0001-chv-full-ppgtt-linux-1c8ee8b-netbsd11.patch` addresses a documented GT memory-translation delta, not a proven panel root cause. The early console G01..G09 trace and full 323-active-C-unit DRM/TTM owner graph remain necessary before another display takeover test.

**Status:** RTL50 kernel panic OPEN / forensic acquisition pending / no approved new kernel build / user-designated GENERIC target must be proved on host.
