# RTL8723BE NetBSD 11 — orphaned hardware RUNNING recovery through explicit DOWN

**2026-10-29. Production-source checkpoint.** All reported host tests are
strict portable Linux x86_64 C11/UBSan checks; none is a native NetBSD 11
kernel build, live HP PCI DMA/IRQ test, or successful WPA2 WLAN association.

## Confirmed recovery hole

The real net80211 `ifstop()` clears `IFF_RUNNING` and `IFF_OACTIVE`
**before** invoking the native hardware stop. That is necessary to stop
new network TX dequeue, but the Linux hardware may remain
`sc_linux.started && stage == R23BE_STAGE_RUNNING` when the stop is
refused or a callback returns a false success.

Before this change, an explicit `SIOCSIFFLAGS` DOWN with neither
`IFF_UP` nor `IFF_RUNNING` called `ifstop()` **only** when
`rtwn8723be_datapath_stop_retry_ready(dp)` was true, which requires a
previous `stop_pending` latch. A false-success `hw_start` followed by
refusal to publish IFF_RUNNING, or a failed/false-success post-start RFKill
rollback, can leave *real RUNNING hardware* while the ifnet is DOWN with
**no stop_pending latch**. The normal explicit DOWN recovery path then
did not call `hw_stop` at all. Repeated UP attempts are rejected by the
partial/live hardware start checkpoint. This made the adapter difficult
to recover through the supported net80211 interface.

The same stale ifnet flags allowed net80211 media changes and generic
`ENETRESET` to report apparent reconfiguration success despite an
unretired RUNNING MAC. Multicast `ENETRESET` also had an early
no-RUNNING flag path that silently swallowed the reset.

## Production correction

New source-shared C function
`rtwn8723be_net80211_running_hw_stop_needed(state)` returns true only
when the **actual Linux state is started and RUNNING**. It intentionally
does not promote a partially started firmware phase or an interrupted
STOPPING phase into a normal hardware-stop candidate. This predicate is
an advisory check; `datapath_begin_stop` independently validates
the datapath, IRQ and RX/TX callback owners under the native TX mutex.

The `SIOCSIFFLAGS` DOWN path now retries `n80211_ifstop` when either
the original `stop_pending` predicate is true **or** real Linux RUNNING
hardware requires STOP, even when IFF_RUNNING is already false. It does
not invent IFF_RUNNING, reenable TX, or bypass the native
`begin_stop`/EBUSY guard. If a callback holds DMA/TX resources,
the first retry returns EBUSY and latches stop_pending; after the caller
drains that callback, an explicit subsequent DOWN can finish STOPPED.

The net80211 media and generic `ENETRESET` paths likewise return
**EBUSY** instead of falsely confirming a reconfiguration while
the real RUNNING hardware remains behind a logically DOWN ifnet.
The separate multicast `ENETRESET` shortcut now drops the reset
only when no RUNNING MAC and no pending STOP exists.

All existing `ifstop` postconditions still apply: callback success
must produce STOPPED with started, fw_ready, MAC and initialization
ownership fully cleared. False-success callbacks still yield EIO.
Interrupted STOPPING/failed pre-RUNNING hardware phases are **not**
automatically recovered using the unsafe generic RUNNING stop.

## Executed C11/UBSan regression

`tests/test_net80211_deferred_down_retry.py` extracts, compiles and
runs the **actual production** `n80211_ifstop`, `n80211_ioctl`,
`n80211_media_change`, `datapath_stop_retry_ready` and
`datapath_begin_stop` function bodies. Extended scenarios include:

- Hardware started and RUNNING; ifnet already DOWN, no stop_pending:
  media changes, generic reset and multicast ENETRESET are refused
  with EBUSY; explicit DOWN executes the hardware stop.
- The same orphaned RUNNING state with an in-flight RX DMA reference:
  native begin_stop refuses and latches stop_pending, then an explicit
  later DOWN succeeds after release.
- A false-success `hw_stop` leaves the Linux state RUNNING:
  DOWN propagates EIO without clearing hardware ownership, and an
  explicit retry can subsequently finish.
- A foreign/unbound native IRQ argument is **not** an authorization
  to STOP; the attempt fails closed rather than returning false success.
- All earlier valid deferred DOWN, media/reset refusal, retry and
  no-second-stop-after-STOPPED cases continue to pass.

This existing test rejects **four new unsafe orphan-guard mutations**,
plus its previous 11 DOWN-retry and five media/reset source mutations.

New `tests/test_net80211_orphaned_running_hw_predicate.py` compiles
the real source-shared Linux-state helper and tests NULL, PROBED,
STOPPED, RUNNING, STOPPING and firmware-download combinations. Four
deliberate predicate source mutations are rejected. Both regressions
are wired into the portable C CI workflow.

## Remaining limitations and safety

This is **explicit** DOWN recovery, not an autonomous STOP retry worker.
There is still no justified automatic recovery of partially initialized
firmware, mid-STOPPING hardware teardown failure, or concurrent ifnet
and PCI detach without real NetBSD native IRQ/softint drains. A boolean
state snapshot alone is not a cross-CPU lifetime lease; the actual
begin_stop callback continues to validate every native owner.

Four Linux lifecycle callbacks remain unbound:
`register_ieee80211`, `init_rfkill`, `bt_prepare`, `dm_init`.
The full native NetBSD 11 48-C-unit link and physical HP WLAN/PCI
IRQ/DMA/WPA2 tests have not been performed. This is **not** yet a
functional Wi-Fi kernel driver.

`main`, the trusted HP F77 recovery `/netbsd`, `/boot.cfg`, i915
and PCI recovery state are untouched. No experimental boot/install.
