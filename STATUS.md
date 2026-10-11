# RTL8723BE NetBSD project status

Date: 2026-10-11

## IST

**Hardware bring-up is partial — this is not a functional WLAN release.**

Target hardware is HP TPN-W121 on NetBSD 11.0 amd64:

- RTL8723BE PCIe, `10ec:b723`, subsystem `103c:81c1`
- F77 is the verified recovery boot and keeps `i915drmkms` disabled.
- F77 must not be confused with acceptance of the current Git source tree.
- F16.0 must never be booted. F83 and F84 reached a black screen with
  backlight after early text; the root cause is unconfirmed.

The current private manifest contains 45 C units. It remains intentionally
unbound: `register_ieee80211`, `init_rfkill`, `bt_prepare`, and `dm_init` are
not live lifecycle owners, so the current source does not activate PCI, DMA,
IRQ, RFKill or a net80211 device on the HP. GitHub `main` is currently
`229269002a7a52bb3620988ae46c15f6a217d709`.

Historical Shadow D evidence at commit
`409d1b739ea96dcebe697d73c7d4b6c83ae4d00c` is limited but positive:

- the original `files.pci` was unchanged;
- the generated private configuration explicitly excluded i915;
- all 44 selected C objects compiled nonempty; and
- their ordered SHA-256 aggregate is
  `1c588c7d4a6fb466ebe50232427b7e543ea52dfeeb67c3b6d59c54c2f31c14f0`.

The current 45-unit Shadow E stage, built from
`f57eaeadef553d04692231e283e400d61630c967`, is the first complete private
kernel-link evidence:

- all 45 selected C objects compiled nonempty;
- the ordered object aggregate is
  `c76cc21790575f56d3c5d35db8ca7a25acc192362f7aa52acbbbeef7cbc84839`;
- the original `/usr/src/sys/dev/pci/files.pci` still hashes to
  `584bf78070c5868e2e48d0e563949cbf70a958b08166150f5363cfcbf5d7b707`;
- the private config contains `no i915drmkms*`, and the rendered Makefile has
  no i915 input; and
- the full private `netbsd` link succeeded. Its SHA-256 is
  `77be29c81d0f5a243f7c20cd54be857e46c323f6137ee6f46876d9826e6730f1` and
  its identity is `RTWN8723BE-NATIVE-SHADOW`.

The prior `collect2: fatal error: cannot find 'ld'` was traced to the
non-interactive build environment omitting `/usr/tools/bin`. The successful
link uses an explicit per-command `PATH` containing that tool directory; no
system profile, symlink, source tree, installed kernel, or boot entry was
changed. Link success is build evidence only, not WLAN acceptance.

A fresh checkout at `84f1b9704e7fa1628b729a8da5ae6cb819155d38` completed
all 53 HP-only regression scripts successfully. The batch runner now supplies
its own result directory as the test-artifact work directory; this fixes the
former stale `/root/hp-driver-port-20261005` test-harness path without changing
driver behavior. This is source-test evidence only, not a native link or
hardware result.

## ÄNDERUNGEN

- Added a conservative Linux-world 2.4 GHz regulatory baseline: 1–11 active
  CCK/OFDM, 12–13 passive CCK/OFDM, 14 passive CCK-only. The portable C11
  regression passed. This does not yet read EFUSE channel plan `0xb8`, map a
  country, or process country-IE notifier changes.
- Prevented partial Net80211 publication when the fallible policy setup
  fails.
- Added a tested whitelist for teardown of a registered but unstarted
  interface at `IEEE80211_REGISTER`, `RFKILL`, `IRQ_ESTABLISH`, `PROBED`, and
  `STOPPED`. Hardware-start failure states remain blocked for a future,
  explicit reverse-recovery owner.
- Kept NetBSD's reference-compatible `splnet()` detach scope after checking
  `if_rtwn.c`; no speculative locking change was made.
- CI now executes the new regulatory and Net80211 regression tests on source
  and test-only changes.
- Replaced the earlier generic failed-start abort with the exact Linux-shaped
  behavior: a pre-`RUNNING` error returns directly and retains its last stage
  as a fail-closed quarantine. The Red/Green C11 regression proves that no
  normal stop callback is invoked for a failed `mark_hal_start` path.
- Completed the isolated 45-object and full private-kernel link described
  above, still with i915 excluded and without installing or booting it.

## NEXT

1. Repeat the complete isolated object/link gate from `2292690`; the prior
   Shadow E is tied to the earlier source revision and is not reused.
2. Design and test the full resource-journaled pre-`RUNNING` recovery owner
   before binding any lifecycle callback. It must mask and drain start-local
   IRQ work before resource teardown, preserve probe-owned allocations, and
   never reuse the normal `RUNNING` stop path.
3. Close real lifecycle owners in reverse-cleanup order before binding any
   operation to the PCI probe path.
4. Keep i915 trace-only until a physical early serial capture exists. Never
   use F16.0, F83 or F84 as a test kernel.
5. Test scan with received BSS entries, authentication, association, traffic,
   recovery, suspend/resume and detach only after full runtime closure.
   Package work follows that hardware acceptance.
