# RTL8723BE NetBSD project status

Source checkpoint: 2026-10-27 (last verified HP native build: 2026-10-11)

## SOURCE CHECKPOINT — NET80211 FINAL ASYNC OWNER DETACH GATE (2026-10-29)

The production `rtwn8723be_net80211_unregister` now rejects
direct ifnet/net80211 detach with EBUSY when **any outstanding
NetBSD asynchronous owner** still refers to its native softc:
hard IRQ, SOFTINT_NET handler, PCI interrupt handles or IRQ
state flags; published RX/TX/power IRQ dispatch callbacks or
dispatch argument; native datapath and RX binding; RFKill
worker initialized/active state or its workqueue.

A successful Linux MAC STOP is **not evidence of net80211
callback quiescence**. This final owner check runs after
the existing hardware-stop/postcondition path but before
security policy clearing, `ieee80211_ifdetach`,
`if_detach` or clearing `registered`. It retains the
registered interface and callback methods on EBUSY;
the external lifecycle must drain owners and retry.
The existing failed-probe rollback already performs
IRQ -> datapath -> RX binding -> RFKill -> net80211,
and the public unregister now independently enforces
the matching final release precondition.

New strict portable C11/UBSan
`tests/test_net80211_owner_drained_unregister.py`
compiles **the actual production ifstop and unregister
C functions** and exercises fifteen independently live
async owners, one by one; none may permit net80211
detach. It also tests a genuinely RUNNING adapter whose
hardware STOP succeeds while IRQ/RFKill remain live,
requiring a subsequent explicit unregister. Nineteen
unsafe source mutations are rejected. The previous
false-success hardware STOP test remains active with
its complete mock owner fields; CI includes the new
script.

Disposable `legion` Linux x86_64 exact HEAD
`cf2e4c18135a861d3463055dbdd3322db375ba8b`:
**67/67 host-permitted tests PASS**, 0 failures,
12 of 79 NetBSD/HP or pinned-reference tests excluded;
`git diff --check` against stacked PR #21 succeeded.
See `docs/NET80211_FINAL_OWNER_DETACH_GATE_20261029.md`.

This is a fail-closed release state gate, NOT a complete
native IRQ/softint drain, automatic STOP retry, SMP
exclusion or fully linked HP Wi-Fi driver. Four native
Linux lifecycle callbacks remain unbound; native
NetBSD kernel and WLAN validation are still open.

## SOURCE CHECKPOINT — DATAPATH UNPREPARE LINUX HARDWARE STAGE PROOF (2026-10-29)

The native `rtwn8723be_datapath_unprepare` no longer
permits IRQ callback revocation and TX-mutex destruction merely
because IRQ/softint handles are disestablished, TX admission
is disabled and all RX/TX callback references are zero.

It now also checks **under the existing IPL_NET TX mutex**
that Linux has no remaining `started`, `fw_ready`,
`mac_func_enable` or `being_init_adapter` owner.
Linux stages beyond `PROBED` (except fully `STOPPED`)
are refused with `EBUSY`. This prevents release under
still-RUNNING hardware, partially completed `STOPPING`,
or an unjournalled pre-RUNNING hardware-start failure.
A genuinely firmware-free, unstarted probe rollback up
to `PROBED` and a completely STOPPED adapter remain
eligible, subject to all existing IRQ/callback guarantees.

New strict C11/UBSan
`tests/test_datapath_unprepare_linux_lifecycle.py`
compiles the **actual production unprepare function**
and imports the real Linux stage enum. It tests early
probe rollback, pre-RUNNING firmware phase, RUNNING with
TX already disabled, interrupted STOPPING, stale firmware/
MAC/initialization flags, callback references and an
active softint handle. Fourteen unsafe source mutations
are rejected. RX/TX lease harnesses now require a
real STOPPED transition before successful unprepare.

Disposable `legion` Linux x86_64 exact head
`7e268b2368bfd01f14b3f9e639ecee054276bc06`:
**66/66 host-permitted regression scripts PASS**,
0 failures, 12 of 78 target/pinned-source scripts not run.
`git diff --check` against stacked PR #20 succeeded.
See `docs/DATAPATH_UNPREPARE_LINUX_STOPPED_PROOF_20261029.md`.

This is a **fail-closed release precondition**, not a
new hardware STOP controller, a real IRQ/softint drain or
an automated EBUSY retry. Four unbound lifecycle callbacks,
native NetBSD 11 full 48-C-unit link and actual HP RTL8723BE
WLAN operation all remain OPEN.

## SOURCE CHECKPOINT — NET80211 TX-START CALLBACK LEASE (2026-10-29)

The native net80211 `if_start` queue consumer now holds
a real lifetime lease, not merely a RUNNING snapshot.
`rtwn8723be_datapath_tx_start_begin` checks active TX,
`!stop_pending`, matching PCI/IRQ owner, DMA/IRQ readiness,
and actual Linux RUNNING state **under dp->tx_lock**. It
increments `tx_start_active` within that same critical
section. Net80211 then executes the borrowed external
`methods.tx_start` **outside** the IPL_NET mutex and
releases its published reference under the mutex after
the callback returns.

Atomic `begin_stop` and `datapath_unprepare` now
refuse a destructive transition or callback owner
release with EBUSY while that external net80211
TX-start callback executes. A failed STOP closes TX
admission and latches `stop_pending`; an explicit
later retry can enter STOPPING after the reference
returns. There is no blocking/waiting under IPL_NET.

A new strict C11/UBSan harness compiles and executes
**the actual production if_start, native lease begin/end,
begin_stop and unprepare function bodies**. Its
reentrant TX callback attempts STOP and an IRQ-disestablished
unprepare, both refused; callback return permits
the later explicit retry and eventual safe teardown.
Twelve unsafe mutation controls enforce the lease,
owner and STOP gates. CI includes the new test; existing
RX, TX completion and atomic STOP partial C11 models
were updated for the additional counter.

Disposable Linux x86_64 `legion` exact HEAD
`d96fcb8eb31abd0f259b5fc1877c2653487e0636`:
**65/65 host-permitted regression scripts passed**,
zero failures, with 12 of 77 target/pinned-reference
scripts not run. `git diff --check` against stacked
PR #19 passed. See
`docs/NET80211_TX_START_CALLBACK_LEASE_20261029.md`.

A **sleepable automatic STOP retry**, actual IRQ/softint
drain and final net80211/PCI detach owner still
remain OPEN, as do the four intentionally unbound
lifecycle callbacks and native NetBSD 11/HP validation.

## SOURCE CHECKPOINT — NET80211 LATE RX/TX NATIVE OWNER GATE (2026-10-28)

The net80211 `ifstart`/RX-input entry points now use
the native `rtwn8723be_datapath_running_ready` contract
rather than relying on potentially stale `IFF_RUNNING`
and Linux RUNNING state alone. The `ifstart` callback
refuses dequeue when TX is disabled, `stop_pending`
is latched, the IRQ owner is foreign, or firmware/DMA
are not ready. `net80211_input` checks the same native
owner **before m_devget** and again **inside splnet**
after frame copying, before `ieee80211_find_rxnode`,
freeing the mbuf on late revocation.

The strict C11/UBSan
`tests/test_net80211_late_rx_stop.py` now compiles
the **actual native datapath_running_ready function**
together with production RX input and `ifstart`.
Its scenarios inject ten in-copy lifecycle/owner
changes and five pre-copy native admissions, plus
TX dequeue refusal despite stale IFF_RUNNING.
Eleven source mutation controls protect the native
and net80211 admission order. Portable CI reuses
the existing regression with an updated description.

Disposable `legion` Linux x86_64 exact-head
`34757db5ccccf4fc23273faade95537d07ec2940`:
**64/64 host-permitted scripts PASS**, zero failed;
12 of 76 NetBSD/HP or pinned-source scripts excluded.
`git diff --check` against stacked PR #18 passed.
See `docs/NET80211_RX_TX_NATIVE_RUNNING_ADMISSION_20261028.md`.

This adds an advisory **locked read-only admission
snapshot**, not a full net80211 callback lifetime lease
or hardware IRQ/softint drain. The four unbound probe/start
callbacks, 48-C-unit native kernel link and real HP WLAN
tests are still open.

## SOURCE CHECKPOINT — NATIVE RUNNING PUBLICATION AND RFKILL ROLLBACK (2026-10-28)

After a nominally successful Linux `hw_start`, net80211
may now publish IFF_RUNNING only if the **actual native
datapath TX/IRQ/DMA owner** is ready. The new
`rtwn8723be_datapath_running_ready` checks the published
owner, enabled TX, `!stop_pending`, IRQ dispatch/handle,
mapped DMA, ring allocation and Linux started/firmware-ready
RUNNING state under `dp->tx_lock` at IPL_NET. Net80211
checks it both immediately after `hw_start` and again after
the second RFKill sample, immediately before publication.
A missing or revoked owner returns EIO, without inventing
a completed hardware STOP.

When post-start RFKill sampling requires `hw_stop`, its
nominally successful return now also requires actual Linux
`STOPPED` plus cleared `started`, `fw_ready`,
`mac_func_enable` and `being_init_adapter`; otherwise
`ifinit` returns EIO and retains recovery ownership.

A new strict C11/UBSan test compiles **real production
function bodies** for native RUNNING readiness and net80211
ifinit. It injects missing TX admission, foreign IRQ owner,
pending STOP, revoked dispatch and second-RFKill owner
changes, along with bogus RFKill rollback success.
Twelve unsafe source mutations must fail. The existing
RFKill start test now executes four false-success STOP
variants. At exact disposable Linux `legion` head
`f14e4c6f7b56e842f2b45c66d83385a40dba295e`,
**64/64 host-permitted scripts passed**, zero failures;
12 of 76 NetBSD/HP/pinned-reference scripts not run.
`git diff --check` against the stacked PR #17 passed.
See `docs/NATIVE_RUNNING_PUBLICATION_RFKILL_ROLLBACK_20261028.md`.

Readiness is a **snapshot, not a callback lifetime lease**.
The four unbound lifecycle callbacks, native 48-C-unit
full kernel link, top-level IRQ/softint drain, automatic
STOP retry and HP PCI/WLAN tests all remain open.

## SOURCE CHECKPOINT — REAL STOPPED POSTCONDITION AND MEDIA QUARANTINE (2026-10-28)

The production net80211 `ifstop` now checks the actual Linux
hardware lifecycle **after** a nominally successful `hw_stop`.
Only `STOPPED` with `started == false`, `fw_ready == false`,
`mac_func_enable == false` and `being_init_adapter == false`
counts as success. A false-success callback returns **EIO** and
retains all net80211 and PCI lifetime owners rather than
allowing `net80211_unregister` to detach a still-live interface.

Net80211 media-change and generic ioctl ENETRESET fallback
also refuse an attempted silent reconfiguration with
**EBUSY** when the locked native `stop_pending` retry
predicate shows an internally RUNNING but logically DOWN
adapter. The media-change entry verifies registered softc
ownership before accessing net80211 state.

A new C11/UBSan regression compiles and executes **actual
production** `n80211_ifstop` plus `net80211_unregister`
with a falsely successful hardware stop, failed EBUSY
stop and genuinely STOPPED runtime. It confirms that
`ieee80211_ifdetach`/`if_detach` never run on failed
postconditions; ten unsafe source mutations are rejected.
The existing DOWN retry test now compiles actual
`n80211_media_change` and verifies ENETRESET/media false
success suppression with five extra negative mutations.

Exact disposable Linux `legion` checkout of
`a151aec6fe4385bd3630fe73cb3bd298b8a1cfb6`:
**63/63 host-permitted regression scripts passed**, 0 failed,
12 of 75 scripts excluded for NetBSD/HP or pinned-source
requirements. The `git diff --check` against stacked PR
#16 was clean. Full native NetBSD 11 kernel build/link,
real WLAN/IRQ/DMA behavior and four missing probe/start
callbacks remain OPEN. See
`docs/NET80211_STOP_POSTCONDITION_MEDIA_QUARANTINE_20261028.md`.

## SOURCE CHECKPOINT — NET80211 EXPLICIT DOWN RETRY (2026-10-27)

The net80211 `SIOCSIFFLAGS` DOWN path can now explicitly
retry a previously deferred hardware STOP even though the
first `ifstop` already cleared `IFF_RUNNING`. A new native
`rtwn8723be_datapath_stop_retry_ready` predicate reads
the pending-stop latch, disabled TX, valid device/IRQ
ownership and still-RUNNING Linux state **under the IPL_NET
datapath TX mutex**. On another explicit DOWN ioctl with
both IFF_UP and IFF_RUNNING clear, net80211 calls its real
`hw_stop` method again; the hardware's begin-stop callback
rechecks callback references atomically and may return
`EBUSY` again. No fictitious IFF_RUNNING restoration occurs.

The ioctl handler also rejects a registered bridge with a
NULL native softc before dereferencing it. A new strict C11/
UBSan regression compiles **the actual production** ifstop,
ioctl, native retry snapshot and atomic begin-stop functions.
It executes first/second EBUSY with RX DMA active, explicit
DOWN completion after RX drains, no redundant further STOP,
foreign-owner refusal and NULL-softc rejection. Eleven
unsafe source mutations must be rejected.

At a disposable Linux x86_64 checkout of
`da8728e45f353a5f200c4fe971711ca345b0e274`,
**62/62 host-permitted test scripts passed**; 12 of 74
target-/pinned-source tests were not run. The diff against
stacked PR #15 was clean. See
`docs/NET80211_DEFERRED_DOWN_RETRY_20261027.md`.

**This retry requires another explicit DOWN ioctl.** It does
NOT schedule a retry automatically after callback completion.
Hardware-specific softint/IRQ drain, automatic stop,
failed STOPPING recovery and native HP/net80211 testing
remain OPEN. Four probe/start callbacks remain unbound.

## SOURCE CHECKPOINT — RX/TX IN-FLIGHT STOP REFUSAL (2026-10-27)

The native SOFTINT_NET RX bridge now admits a ring DMA drain
only under the existing IPL_NET TX/STOPPING serializer. It
holds a new `rx_callback_active` reference across all RX DMA
and borrowed net80211/C2H callback operations, and releases
that reference on success or failure after reacquiring the
same lock.

The atomic native `begin_stop` now fails with `EBUSY`
**before hardware teardown** whenever an RX drain or external
TX completion callback is still running. It closes fresh
RX/TX admission and latches `stop_pending`; a concurrent
`datapath_start` cannot reopen TX in this state.
`datapath_unprepare` also refuses nonzero callback references
or an outstanding pending STOP. A subsequent successful
STOPPING entry clears the latch.

At a disposable Linux x86_64 checkout of
`bddf08bac056daf6e7012af3e0c6d7a6f993287e`,
**61/61 host-permitted tests passed**, zero failed, with
12 of 73 target/pinned-source tests not run. A new strict
C11/UBSan test compiles real RX softint, begin-stop and
unprepare functions; the RX drain recursively attempts STOP
and teardown, expects EBUSY, and verifies a safe retry after
the callback returns. Ten unsafe source mutations are rejected.
Existing TX lease, atomic STOP and start-pending tests passed.
See `docs/RX_TX_INFLIGHT_STOP_GATE_20261027.md`.

**Still not a complete runtime STOP:** an outer lifecycle owner
must retry after transient EBUSY, drain IRQ/softint and handle
pre-RUNNING firmware C2H, DMA and final net80211 references.
Native NetBSD compilation, hardware WLAN validation and four
missing lifecycle callbacks remain open.

## SOURCE CHECKPOINT — IN-FLIGHT TX COMPLETION LEASE (2026-10-27)

The native TX completion bridge now holds an explicit reference
(`dp->tx_callback_active`) from the successful, nonzero
reclaim publication through the **entire external callback**,
including the interval after releasing the IPL_NET TX mutex.
It decrements that reference only after reacquiring the mutex
when the callback returns.

`rtwn8723be_datapath_unprepare` now refuses to unpublish its
IRQ dispatch or destroy the TX mutex with `EBUSY` when that
reference is still held; neither owner nor callback storage is
released. It never waits under the IPL_NET spin mutex. The
external lifecycle must still drain/disestablish IRQ/softint
and exclude new ifnet entrants before an unprepare can succeed.

At a fresh disposable Linux x86_64 checkout at
`c5669990d837303dd70284fc126a691aa8d2562e`,
**60/60 host-permitted tests passed**, 12 of 72 scripts
excluded for NetBSD/HP or pinned-source requirements. The
new strict C11/UBSan regression compiles the **actual
production** TX done, begin-STOPPING and unprepare bodies;
the external completion callback itself attempts unprepare
and observes `EBUSY`, then full release succeeds only after
return. Nine negative source mutations are rejected.
The stacked PR #13 `git diff --check` passed. See
`docs/TX_COMPLETION_LIFETIME_LEASE_20261027.md`.

**Not a NetBSD kernel/HP hardware test.** The real
PCI/softint drain, RX callback lifetime, hardware shutdown
and the four unbound lifecycle callbacks remain open.

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
