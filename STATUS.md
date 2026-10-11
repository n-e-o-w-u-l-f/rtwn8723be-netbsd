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

The current private manifest contains 48 C units. It remains intentionally
unbound: `register_ieee80211`, `init_rfkill`, `bt_prepare`, and `dm_init` are
not live lifecycle owners, so the current source does not activate PCI, DMA,
IRQ, RFKill or a net80211 device on the HP. The added BTC policy unit ports
Linux high-level `halbtc_get()`/`halbtc_set()` decisions only; it remains
unbound until a real whole-driver owner supplies coherent state and callbacks.
The 48th unit prepares a Linux-shaped BTC coexistence context atomically from
a parsed identity and separate low-level/policy binders. It maps the raw
RTL8723BE antenna encoding, validates the binder effects and publishes no
partial output. It neither discovers nor starts hardware and has no
`bt_prepare`, PCI, DMA, IRQ, RFKill, net80211 or workqueue binding. The
recorded generator-source revision is
`6b37ae2ccb65505f331fb678fe110b5921da4b83`; the local 48-unit source state
extends that recorded revision pending its matching build gate. Shadow H
remains the exact historical 47-unit build record for
`66fed5c6e732a373e4faa16f96b5742725c99d3b`.

The isolated historical Shadow H checkout at
`66fed5c6e732a373e4faa16f96b5742725c99d3b` completed the full private
47-unit object and kernel-link gate without changing `/netbsd`, the boot menu,
or the F77 recovery environment:

- 47/47 selected objects are nonempty; their ordered SHA-256 aggregate is
  `d5835976634e14bdbb456f6d235d6b009f2a5e6f924fccca597d7be9a1b43847`.
- `rtwn8723be_btc_policy.o` is 72,376 bytes and hashes to
  `64322ab1b87ab50db2fad6f594cca8128bb06960c719c2fde12710a2796de2c2`.
- The private kernel is 27,289,096 bytes, hashes to
  `390a3905b41463dee6b0395138ed406dee37051d6506a696c8f764fb0024ac38`, and
  embeds `NetBSD 11.0 (RTWN8723BE-NATIVE-SHADOW) #0: Sun Oct 11 20:11:59
  CEST 2026` exactly once.
- The config explicitly contains `no i915drmkms*`; the private PCI manifest
  and rendered Makefile each have zero i915 lines. The original
  `/usr/src/sys/dev/pci/files.pci` remains
  `584bf78070c5868e2e48d0e563949cbf70a958b08166150f5363cfcbf5d7b707`.
- The candidate differs from the live F77 `/netbsd`; it was neither installed
  nor booted.

This is build evidence only; it does not make the unbound lifecycle callbacks,
PCI attach, WLAN, or i915 functional. It is not build evidence for the current
48-unit source selection. That selection needs a new isolated private object
and full kernel-link gate; no kernel candidate from it has been installed or
booted, and no i915 action occurred.

Historical Shadow D evidence at commit
`409d1b739ea96dcebe697d73c7d4b6c83ae4d00c` is limited but positive:

- the original `files.pci` was unchanged;
- the generated private configuration explicitly excluded i915;
- all 44 selected C objects compiled nonempty; and
- their ordered SHA-256 aggregate is
  `1c588c7d4a6fb466ebe50232427b7e543ea52dfeeb67c3b6d59c54c2f31c14f0`.

The historical 45-unit Shadow E stage, built from
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

The historical 46-unit Shadow G result is reproducible from its retained private
output directory:

- all 46 selected objects are nonempty;
- the ordered object-hash record hashes to
  `18b1b4b85b71af884e24b8e9199f2901a6bc7068be576dc1cac1fbc2aa7a6c23`;
- the new pre-`RUNNING` recovery object is 28,976 bytes and hashes to
  `41a34e2cb3f9c24a1fd9eaa3d90d295a86205972de64b48895d9df4c1096bb71`;
- the complete private kernel hashes to
  `e3ac1437d70a910ab41550292a6d6dbe78118a6d0d8fd595fa1a9e0a5b2adef6`
  and embeds `NetBSD 11.0 (RTWN8723BE-NATIVE-SHADOW) #0: Sun Oct 11
  18:45:02 CEST 2026`;
- the object and link logs hash to
  `0b630b14c0697ae482e3470a68bd57888e5d7b6190a57774c19ed54b585b2fbe`
  and `638274f03439d04bf82c8cdd89e132dedfc01675b4852a975fadce87ecbf32b5`;
- the generated config explicitly contains `no i915drmkms*`, while the private
  PCI manifest and rendered Makefile contain zero i915 lines; the original PCI
  manifest remains
  `584bf78070c5868e2e48d0e563949cbf70a958b08166150f5363cfcbf5d7b707`,
  and the candidate is not the live `/netbsd`.

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
- Added a 46th, unbound pre-`RUNNING` resource journal. It accepts only an
  explicit failed-start checkpoint under exclusive ownership, preflights all
  compensators before an effect, masks and drains start-local IRQ work first,
  and performs reverse cleanup without releasing probe-owned PCI/BAR/DMA/IRQ
  objects or calling the normal `RUNNING` stop path. Phases may be skipped,
  but cannot be reordered; DMA/DM is released before the earlier Post-HW
  resource. A C11/UBSan test covers
  missing-compensator rejection, drain-failure quarantine, and successful
  reverse ordering. It changes no live hardware path.
- Added a 47th, unbound BTC policy translation unit. It ports the Linux
  high-level `halbtc_get()`/`halbtc_set()` decision policy behind explicit
  owner callbacks, including the source's LPS and aggregation rules. It has no
  PCI, DMA, IRQ, net80211, or hardware lifecycle binding.
- Corrected the BTC generator and generated source-proof hash so that the
  policy-context extension is reproducible from the pinned Linux source. This
  changes no driver runtime code or H build input.
- Added the 48th, pure BTC context-preparation translation unit. It builds a
  temporary Linux-shaped coexistence context from a validated parsed identity,
  composes the low-level and policy binders in order, rejects partial or
  lifecycle-mutating results, and publishes only after the existing callback
  gate succeeds. Its C11/UBSan contract covers both antenna encodings and
  atomic failure paths. It does not bind `bt_prepare`, PCI, DMA, IRQ, RFKill,
  net80211, workqueues, native hardware state, or i915.
- The HP-only regression runner completed all 56 `test_*.py` checks at
  `6b37ae2ccb65505f331fb678fe110b5921da4b83`, using a fresh temporary work
  directory that was removed after success. This is source-test evidence only,
  not a kernel installation, boot, or WLAN hardware result.
- Completed the isolated 45-object and full private-kernel link described
  above, still with i915 excluded and without installing or booting it.
- Completed the matching isolated 46-object and full private-kernel G link,
  including object hashes, kernel identity, source-integrity check and live
  kernel comparison. It was neither installed nor booted.
- Completed the matching isolated 47-object and full private-kernel H link at
  `66fed5c6e732a373e4faa16f96b5742725c99d3b`, with i915 explicitly excluded
  and without installing or booting the candidate.
- Removed the confirmed, inactive historical Shadow E/F output directories
  after their hashes were recorded. The current G output remains retained as
  the reproducible build-only record.

## NEXT

1. Preserve the completed H result (and historical G record) as build-only
   evidence; do not install or boot either. The superseded, confirmed E/F
   private build shadows are removed.
2. Run a matching isolated 48-object and full private-kernel link gate for the
   current BTC-context source state. Treat it as build-only evidence; do not
   install or boot a candidate.
3. Implement the real `bt_prepare` owner with genuine MCU/RX-drain,
   serialization and reverse-release semantics; do not reuse the historical
   runtime model as a shortcut.
4. Close `dm_init`, net80211/RFKill ownership and the matching start/stop
   paths with real NetBSD API integrations before PCI/IRQ binding.
5. Bind the recovery journal only when each real NetBSD lifecycle owner has
   recorded its own acquired resources and provides compatible compensators;
   keep the normal `RUNNING` stop path separate.
6. Keep i915 trace-only until a physical early serial capture exists. Never
   use F16.0, F83 or F84 as a test kernel.
7. Test scan with received BSS entries, authentication, association, traffic,
   recovery, suspend/resume and detach only after full runtime closure.
   Package work follows that hardware acceptance.
