# RTL8723BE NetBSD project status

Date: 2026-10-25 (last verified HP native build: 2026-10-11)

## SOURCE CHECKPOINT — ATOMIC TX STOPPING ENTRY (2026-10-27)

The production Linux-order stop controller now **requires a real,
bound `begin_stop` callback** before BT, HAL, IRQ or MAC teardown.
The NetBSD implementation delegates to a native datapath entry that
sets `tx_enabled = false` and changes the actual Linux state from
RUNNING to STOPPING in **one IPL_NET TX-mutex critical section**.
This closes the prior race between unguarded STOPPING publication
and an in-progress descriptor producer. Missing/foreign callbacks
refuse hardware stop; an incomplete but still owned lifecycle
also revokes TX admission.

At a disposable Linux x86_64 checkout of
`5e9e184b92f0a9f6e65df049f62961c03b7def7b`,
**59 of 59 host-permitted regression scripts passed**, with
12 of 71 tests excluded for HP/NetBSD or unavailable pinned
reference requirements. Strict C11/UBSan compiles the **actual
native STOPPING and TX enqueue bodies** and injects state/owner
changes at lock acquisition. Ten negative mutation tests protect
the transition and the existing Linux lifecycle test now
rejects absent or false-success STOP-entry callbacks.
The native callback inventory is **54 declared, 50 bound,
four intentionally missing**, with 48 native C objects unchanged.
See `docs/SERIALIZED_STOPPING_TX_ENTRY_20261027.md`.

The owner for in-flight callbacks after the TX lock is released,
IRQ/softint drain, ring teardown, failed STOP recovery and
native HP kernel validation are **still OPEN**. No active WLAN
or boot safety claim follows from portable C11 testing.

## SOURCE CHECKPOINT — TX START/COMPLETION LOCK SNAPSHOT (2026-10-27)

The native datapath `start` now checks sole device/IRQ owner
and genuine RUNNING status **under `dp->tx_lock`**, directly
before publishing `tx_enabled`; stale pre-lock approval no
longer enables TX after a STOPPING/owner transition.

The native TX completion bridge refuses ring reclaim and
net80211 callback publication for disabled TX, foreign owner
or non-RUNNING/firmware-unready state. A successful nonzero
reclaim may snapshot the completion callback under the TX lock,
but calls it **outside** the lock to avoid reentrant deadlock.
Failed partial ring reclamation retains the failure/owner and
does not advertise a successful completion.

At a disposable Linux x86_64 checkout of
`e13eb385f2c9cca265a1168d518f4ad30bc79e40`,
**58/58 host-permitted tests passed**, with 12 excluded of 70
total scripts. The production-function C11/UBSan test injects
STOPPING and ownership loss exactly at TX mutex acquisition
and rejects nine unsafe source mutations. The diff against
stacked PR #11 was clean. See
`docs/DATAPATH_TX_START_COMPLETION_20261027.md`.

This does **not** yet serialize the Linux STOPPING write with
`dp->tx_lock`, drain a callback already in progress, or prove
NetBSD kernel/hardware behavior. The complete runtime lifetime
owner and four unfinished callback bindings remain open.

## SOURCE CHECKPOINT — DATAPATH TX STOPPING GATE (2026-10-27)

The actual native datapath `enqueue` now refuses TX unless the
published bridge is the sole device datapath and Linux lifecycle
is **started + firmware-ready + RUNNING**. This closes a source
admission hole: `STOPPING` still preserves the earlier started and
firmware flags until the full Linux stop completes. Native datapath
`start` also checks the published IRQ/owner identity.

The RX binding translation unit now imports the complete PCI softc
header explicitly, removing reliance on its previous **already
working transitive include** through `rx_native.h`. This is
dependency hygiene, **not evidence of an earlier compile failure**.

A disposable Linux x86_64 checkout at
`e7a7247a436bfbbe90c903c3f50e5cdf34930a04`
passed **57/57 host-permitted Python tests**, with 12 of 69
scripts excluded for target or pinned reference requirements.
The new strict C11/UBSan test compiles the real production
datapath start/enqueue function bodies and detects seven unsafe
mutations. `git diff --check` against PR #10 passed.
See `docs/NATIVE_RX_SOFTC_TX_STOP_GATE_20261027.md`.

**The actual STOPPING transition still lacks a common runtime lock
with TX producer; this is not a full race-free stop owner.**
Native NetBSD compilation/link and HP firmware/WLAN validation
remain OPEN; the four unfinished lifecycle slots stay unbound.

## SOURCE CHECKPOINT — FALSE-SUCCESS HARDWARE START QUARANTINE (2026-10-26)

A zero-returning hardware start that failed to produce a real
`started + fw_ready + RUNNING` state no longer calls the normal
`hw_stop` callback, which requires an actual RUNNING adapter.
Instead `if_init` returns EIO and preserves the incomplete Linux
stage for the separate pre-RUNNING recovery owner. This avoids a
fake STOPPED transition and unsafe speculative MMIO teardown.

A source-shared start predicate now admits retries only from
truly quiescent PROBED/STOPPED, with no active firmware,
MAC, adapter initialization or started state. The unstarted
net80211-detach predicate rejects these residual resources too.
The genuine post-RUNNING RFKill compensator remains unchanged.

A fresh disposable Linux x86_64 checkout at
`08ccea0171afdd0c26ba6d3f0af38e736900043f`
passed **56/56 host-permitted regression scripts** with no
failures; 12 of 68 scripts require HP/NetBSD or absent pinned
reference source checkouts. The updated strict C11/UBSan
production ifinit harness, source-shared checkpoint tests and
10 unsafe mutation controls passed. `git diff --check` against
the stacked PR #9 base passed. See
`docs/NET80211_PRESTART_QUARANTINE_20261026.md`.

**Not a NetBSD kernel compile or HP WLAN hardware result.** The
actual pre-RUNNING recovery compensators, net80211 start/stop,
BT/DM and four Linux callback slots remain unbound.

## SOURCE CHECKPOINT — NET80211 LATE RX/STOP PUBLICATION (2026-10-26)

Native RX ingress revalidates net80211 registration, softc ownership,
IFF_RUNNING and the actual started/RUNNING lifecycle *under splnet*
after the bounded `m_devget` copy and before any 802.11 node lookup
or packet injection. A concurrent STOP mid-copy now drops the mbuf
rather than delivering a stale frame. The if_start bridge also requires
a genuine started/RUNNING device before any TX handoff. Ifstop rejects
an orphaned registered softc and retains actual hardware ownership
on failure; no fake hardware stop is credited.

A disposable Linux x86_64 checkout at
`9c867298c9e7f6efd6eb61dab4f822a63ad54093` executed
**55/55 host-permitted regression tests successfully**; 12 more
require HP/NetBSD or unavailable pinned reference checkout paths
(67 scripts total). Two new tests compile real net80211 RX, TX
and stop production function bodies under strict C11 and UBSan
and reject 13 unsafe source mutations. The base-branch
`git diff --check` passed.

**Not native NetBSD 11 compilation, full kernel link, hardware RX/TX
or actual softint/detach concurrency evidence.** Full runtime
stop/rollback and the four missing lifecycle callbacks remain
unbound. See `docs/NET80211_RX_STOP_ADMISSION_20261026.md`.

## SOURCE CHECKPOINT — IRQ PENDING-BIT DRAIN (2026-10-26)

NetBSD hard IRQ and SOFTINT_NET now use the same IPL_NET
`sc_irq_lock` for publishing and consuming `sc_irq_pending[2]`.
The production source-shared C11 helper refuses pending work after
the owner revokes IRQs, atomically discards stale callbacks when STOP
preceded the softint snapshot, and clears residual bits only after
hard and soft handler disestablishment. `context_fini` requires an
empty IRQ ledger.

At a disposable Linux x86_64 branch revision
`45cbeeeefd9c99813f2fb43cae248fbce27e47b5`,
**53/53 host-permitted portable tests passed**, with 12 of 65
target/reference-specific tests not run. The new IRQ pending helper
was actually compiled with strict C11 and UBSan; six negative source
mutations reject unsafe hard/soft IRQ order. This is not a native
NetBSD kernel compile or physical IRQ race validation. The external
runtime stop must still drain any softint already executing.
See `docs/IRQ_PENDING_QUIESCENCE_20261026.md`.

## SOURCE CHECKPOINT — SERIALIZED BT MP C2H / PENDING RFKILL (2026-10-26)

The RX C2H bridge no longer reads the MP transaction `active`
flag without locking: a new real native gate snapshots active,
faulted and cancelled under the MP owner IPL_SOFTNET mutex, which
also serializes firmware activation, timeout, cancellation and STOP.
This does not bypass external MP fini/softint drain requirements.

The RFKill net80211 start predicate also rejects
`sc_rfkill_native.work_queued` while a newer GPIO sample is
pending or in flight, instead of allowing the previous radio-on
sample to authorize a hardware start.

On a disposable Linux x86_64 checkout at
`eac9d8322de848272b7d4e64d40a1ae2bdea4eef`,
**52/52 portable permitted tests passed** with no timeouts;
12 target/reference-dependent tests were not executed (64 total).
The new production MP gate compiled and passed C11/UBSan owner-lock
negative cases. **HP NetBSD kernel link and WLAN tests remain OPEN**;
four lifecycle slots remain unbound. See
`docs/BT_MP_RFKILL_PENDING_20261026.md`.

## SOURCE CHECKPOINT — RFKILL-VALIDATED NET80211 START (2026-10-25)

An invalid or failed GPIO poll now revokes the previous valid RFKill
sample; stale last-known radio-on readings can no longer authorize a
subsequent net80211 hardware start. A lock-protected snapshot returns
ENXIO/EAGAIN when owner state or current sample is untrustworthy.
Native net80211 `if_init` checks the switch both before hardware start
and again before publishing IFF_RUNNING, invoking real hw_stop if the
switch turns off/becomes unknown during initialization. Successful
hardware start is never reported as WLAN running on that error path.

The production worker, snapshot and if_init implementations were
compiled under C11/UBSan as part of the new regression. On legion at
`658b286e14cf5483fbc74d81be935d1e6ce89e0b`, **51/51 permitted
portable scripts passed**, and 12 scripts remained target/reference
dependent. This does **not** provide asynchronous RFKill switch-off
notifications after IFF_RUNNING or NetBSD native kernel/HP evidence.
The four unbound lifecycle owners and full-port acceptance remain OPEN.
See `docs/RX_C2H_STAGED_ADMISSION_20261025.md`.

## SOURCE CHECKPOINT — STAGED RX/C2H & BINDING OWNER (2026-10-25)

A real probe/start ordering deadlock was removed at source level:
net80211 and shared RX/IRQ callbacks can be prepared before the firmware-
dependent Bluetooth coexistence/MP owners have been activated. The actual
RX C2H callback rejects premature BT_INFO/BT_MP events with EAGAIN before
forwarding borrowed DMA data; native BTC event admission still occurs under
its own lock. No real Bluetooth activation is fabricated.

The shared RX binding now has a single softc owner and a checked fini
requiring IRQ and datapath shutdown. Post-registration teardown journals
NONE → IRQ → DATAPATH → RX_BINDING → RFKILL → NET80211. Native PCI probe
success also requires RX and datapath callback identity consistency.

In a disposable clone on legion Linux x86_64 at
`cab2f716b532d00245c3fc22f4030b2227d5dd4f`, **50 of 50
permitted portable regression scripts passed**; 12 of 62 require the
HP/NetBSD target or missing pinned Linux reference checkouts. Both the
RX binding and five-compensator broker were actually compiled under
strict portable C11/UBSan. This is **not** a NetBSD/HP kernel link or
hardware WLAN acceptance. Full net80211 methods, RFKill state
publication, BTC/DM lifecycle and four unbound callbacks remain OPEN.
See `docs/RX_C2H_STAGED_ADMISSION_20261025.md`.

## SOURCE CHECKPOINT — DATAPATH/TX LIFETIME (2026-10-25)

The native softc now records the unique prepared datapath bridge owner
(`sc_datapath`). Prepare publishes the owner only after initializing its
TX mutex and before wiring the IRQ callbacks. Unprepare verifies the same
owner and callback identity, no running TX or live IRQ handles, then unbinds
the dispatch, clears the softc owner, destroys the TX mutex and retires the
bridge. A mismatched or still-active owner fails closed.

Both pre-registration rollback and the post-registration journal now
release the real datapath **after IRQ and before RFKill/net80211 and DMA**.
The post-registration journal is NONE → IRQ → DATAPATH → RFKILL → NET80211.
The native successful-probe guard requires the actual prepared owner and
the context destructor asserts that no IRQ/datapath owner remains.

On legion (Linux x86_64), at `d8c7dadec637a3b574ed99e3513d87afa43b5a70`,
**49/49 permitted portable regression scripts passed** on a disposable
clone; 12 additional scripts were excluded as HP/NetBSD-only or dependent
on pinned reference checkout paths. The included C11/UBSan broker verifies
four compensators, all four failure injections and safe retry behavior.
**No HP NetBSD object/kernel link or hardware/race validation was run.**
The four Linux lifecycle callbacks remain intentionally unbound. See
`docs/DATAPATH_OWNER_UNWIND_20261025.md`.

## SOURCE CHECKPOINT — UNSTARTED PROBE ROLLBACK (2026-10-25)

The native PCI probe cleanup now reverses a partially registered but
**unstarted** interface, after a pure fail-closed owner/state preflight.
Order is real IRQ disestablishment, RFKill callout/workqueue drain,
net80211 unregister, BT-MP/H2C close, descriptor-ring/DMA release, BAR
unmap and PCI restoration. Each failure retains the remaining hardware resources and
returns an incomplete detach (EBUSY); an explicit per-device monotonic
journal records only confirmed reverse-release steps so a later serialized
retry can resume without guessing what was freed. Started, failed-start
and STOPPING/STOPPED paths remain barred.

The host also confirmed a DMA32 lease bug: releasing the owned
bus_dma subregion restored the parent DMA tag but left
`sc_dma_32bit` true. The release now clears this flag; an additional
regression checks the critical order and negative mutations. The post-
registration probe preflight now also refuses teardown while a
datapath dispatcher still owns the IRQ binding and its TX mutex.

A comprehensive Linux x86_64 test pass from
`4dd84afc877971aa415923945a9c3127113f9e75` executed all 60
Python test scripts: **48 passed**, **12 required HP/NetBSD or pinned
reference trees not present in this sandbox**, and there were no
other test failures. These results include C11/UBSan compensator retry
tests and source contract checks. These are source/portable tests;
no matching HP NetBSD object/kernel build or real RFKill/IRQ/net80211
runtime validation exists for this revision. Four lifecycle slots remain
unbound; the full source-closure/hardware gates are still OPEN.
See `docs/POST_REGISTRATION_PROBE_UNWIND_20261025.md`.

## SOURCE CHECKPOINT — PROBE ADMISSION (2026-10-25)

The native PCI attachment now performs a real 15-field softc ownership
admission before it reports successful probing: PROBED/nonrunning lifecycle,
original PCI snapshot, BAR/core/DMA32/rings, registered and softc-owned
net80211 with three methods, initialized/active RFKill, ready IRQ dispatch
and allocated hard/soft/PCI IRQ handles with operational interrupts disabled.
Every missing prerequisite suppresses the success announcement without
releasing potentially live post-registration resources.

The production predicate and a strict C11/UBSan test with 15 invalid-snapshot
cases and source-level negative controls are included in CI. A GitHub-source
readback confirms the mapping, admission ordering and CI wiring, but **native
NetBSD compilation, CI success and HP hardware tests have not been verified**
for this change. Four lifecycle owners remain intentionally unbound, and the
runtime start/stop rollback remains blocked. See
`docs/PROBE_ADMISSION_20261025.md`. F77 and i915 safeguards are unchanged.

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
