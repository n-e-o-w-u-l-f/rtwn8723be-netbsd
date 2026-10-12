# RTL8723BE: NetBSD net80211 stopped/restart IRQ owner — 2026-10-12

**Scope:** WIP source fix only; actual RTL50 panic, native HP build, WLAN RX and WPA2 all OPEN. No GitHub Actions, new runner, kernel boot, install or root remote command.

## Frozen and actual owners

- Linux hardware-order reference: torvalds/linux `fd179f8a05be3ccae366b9b96e176b51fbe54aab`, rtlwifi PCI/rtl8723be start and reset.
- NetBSD reference: NetBSD/src `03d918f6d0e81fa05b8f1160eca0628ad39988a6`, native PCI IRQ/Net80211 mechanisms.
- Exact source-before WIP ref: `91f9e5ac72e0d096dd154a735149f409081a4563`; NetBSD net80211 source blob `af532c7a0a59df6cffe2356f3901b56222107494`.
- The WIP native `rtwn8723be_netbsd_disestablish_irq` tears down hard interrupt, PCI interrupt handle allocation and softint, setting `sc_ih`, `sc_pihp`, `sc_soft_ih` NULL.
- The **normal, successfully finished** `runtime_shutdown` enters `R23BE_STAGE_STOPPED` after IRQ teardown + ring reset. `runtime_start` deliberately drains previous IRQ and `linux_adapter_start` requires `reset_trx_ring` then `bt_prepare`, followed by `establish_irq` and later `enable_interrupt`.

## Deterministic bug

Prior `rtwn8723be_n80211_ifinit` demanded `sc_ih != NULL` in BOTH `PROBED` and `STOPPED`. Every correctly quiesced `STOPPED` generation has `sc_ih == NULL`. Thus a legitimate `ifconfig down; ifconfig up` (or ENETRESET restart) returned `EAGAIN` before `runtime_start` could legally reestablish IRQ. Restoring IRQ prematurely merely to placate the preflight would violate the DMA reset owner and is prohibited.

## Reviewed narrow source correction

`src/rtwn8723be_net80211.c` now preserves common mandatory `sc_irq_dispatch_ready`, mapped PCI BAR and allocated rings, but checks IRQ handles by explicit stage:

1. `PROBED`: require all three PCI hard/soft IRQ owner handles non-NULL (otherwise `EAGAIN`);
2. `STOPPED`: require all three IRQ handles NULL and `sc_irq_enabled == false` (otherwise `EBUSY`);
3. allow `runtime_start` to perform real IRQ reestablishment **after** DMA ring reset/BT prepare, not in net80211 wrapper.

No hardware register values, regulatory domain, firmware source, IRQ handler implementation, shell, NetBSD boot config, or Linux reference pin was invented or changed.

The existing **HP-only builder** `tools/build_hp_rtl50_next_candidate.sh` already executes `tests/test_probe_unstarted_and_failed_shutdown_gates.py`. That source regression was extended to assert the PROBED/STOPPED inverse owner cases and cross-check native IRQ teardown against Linux-stage start callback ordering; no previously denied builder write was retried.

## Verification and gate boundaries

- GitHub exact source readback: `src/rtwn8723be_net80211.c` blob `0b56cb0fee2e20d87eb745c4b2121714898a02d3`, updated regression blob `ac5c82e245bdc6825b5fd205028a484ebc8c4ffa`.
- Direct cross-file **19 source-contract assertions PASS** (not native Python script execution or C compilation).
- The initial new source-test text accidentally contained doubled newline escapes and a boolean-precedence error in the callback order check. Identified in exact Git readback; corrected at commit `00cfd7b9fcbd9a3e215fd0bfb58b3dd81a6c8382` with explicit sorted unique positions. No failing native test was concealed or rerun.
- Actual Python test, NetBSD C compilation, full kernel executable link for this corrected source, F77/GENERIC boot identity, RTL50 crash stack, RX/scan, WPA2, IP traffic and suspend/resume: **NOT RUN / NOT VERIFIED**.
- **Safety gate from** `docs/HP_RTL50_PANIC_TRIAGE_20261012.md`: older `2e5a2cc` executable caused user-reported panic; DDB trace/crashdump unknown. Latest desired boot default was original GENERIC, but current host boot state unverified. Stale F77-only check in `tools/build_hp_rtl50_next_candidate.sh` is not authorization for an additional kernel build; do not invoke or modify previously externally denied panic-gate integration without genuine permission change.

## Next dependency-first steps

1. On a genuinely available HP-authorized execution route (not a quota bypass), **read only**: `uname -v`, `sysctl kern.bootfile`, full `/boot.cfg`, kernel image identities, and redacted dump/backtrace; protect private crash memory.
2. Resolve the actual RTL50 panic cause and immutable kernel buildplan/boot fallback with exact NetBSD/Linux reference semantics. Audit the STOPPED reestablish source against the actual HP 11 headers and compile it as part of the later HP-only source test gate; avoid premature hardware boot.
3. Once a candidate is native-linked and demonstrably TESTREADY with recovery, validate IRQ/RX/beacons, scan, WPA2 handshake, traffic and recovery separately. i915 display KMS physical G01–G09 remains a separate unsatisfied requirement.

Parent acceptance remains **two fully functional drivers**, not a source-only restart patch.
