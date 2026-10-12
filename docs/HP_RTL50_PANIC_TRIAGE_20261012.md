# HP RTL50 panic: mandatory evidence and no-guess repair checkpoint

Date: 2026-10-12. Source of truth: WIP `wip/hp-rtl-runtime-48-merge-20261010`, not unrelated 48-unit default `main`.

## Observed, not extrapolated

- The HP produced a complete NetBSD 11 amd64 ELF link for exact Git `2e5a2cc97b9bbae3e55aa984e1477e7c29858bce`, identity `HP-RTL50-2e5a2cc97b9b-SAFE-GENFB`, SHA-256 `2eecc4e188c247514d5bc5b639c2773f3d8a823e4f84cc3a65e7e4960471a423`. The user verified status, embedded ident, and hash over SSH.
- The user subsequently **reported a kernel panic when attempting to boot RTL50**. This overrides previous statements suggesting the linked ELF was boot-safe. Neither the panic text nor a DDB stack trace was supplied; exact faulting function/stage/cause is **UNKNOWN**.
- Earlier user-visible F77 boot was successful after the panic. Later the user requested replacing F77/F16/RTL50 defaults with original NetBSD GENERIC. A restoration script was previously offered, but no successful staging/boot/cleanup evidence was provided. Thus the **current live bootfile and fallback are UNKNOWN**, not implicitly F77 or GENERIC. The next host access must verify `uname -v`, `kern.bootfile`, `/boot.cfg`, `/netbsd` identity, and backups before any change. Do not delete recovery artifacts based on intent alone.
- The source branch after 2e5a2cc contains corrective DM/BTC event lifetime, calibration order, RF ownership publication, regression and teardown changes. They have **not** been compiled into the panicking ELF, and do not by themselves establish the root cause of its boot panic.
- RDC remote command quota readback was 0% remaining; account reset timestamp was not exposed. Tailscale enables network transport but this chat still has no independently authenticated command executor on the tailnet; another remote device being ONLINE is not proof of command authorization.

## Immediate forensic gate: read only

New program `tools/inspect_hp_rtl50_panic.py` captures the exact candidate and boot identities plus `/var/crash` filenames/sizes and `savecore` config, **without reading core memory, writing files, or triggering a reboot**. Python source-only regression `tests/test_hp_rtl50_panic_inventory_source.py` checks AST/regex/read-only contract. Both are COMMITTED; HP execution and native verification are **OPEN**.

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

## Independent i915 blackscreen scope

The Intel Cherryview/Braswell 8086:22b1 i915drmkms blackout is separately reproduced in F83 and F84 (backlight on). No persistent early display trace survives. Its already published `patches/0001-chv-full-ppgtt-linux-1c8ee8b-netbsd11.patch` addresses a documented GT memory-translation delta, not a proven panel root cause. The early console G01..G09 trace and full 323-active-C-unit DRM/TTM owner graph remain necessary before another display takeover test.

**Status:** RTL50 kernel panic OPEN / forensic acquisition pending / no approved new kernel build / user-designated GENERIC target must be proved on host.
