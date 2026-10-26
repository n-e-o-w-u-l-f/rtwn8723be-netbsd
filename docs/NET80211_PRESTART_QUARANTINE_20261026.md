# RTL8723BE NetBSD 11 — false-success hardware-start quarantine

Source checkpoint: 2026-10-26. This is a source/portable-C11
milestone, **not** native NetBSD or HP WLAN acceptance.

## Concrete defect

The net80211 `if_init` method called its real `hw_start` method,
then checked whether the Linux-order state machine had actually
reached `R23BE_STAGE_RUNNING` with `started` and `fw_ready`
both true. Previously, if `hw_start` returned zero while one of
those assertions was false, net80211 called `hw_stop` as a
compensator.

**That compensator is not generally valid.** The production Linux
`rtwn8723be_linux_adapter_stop` requires `started` and
`R23BE_STAGE_RUNNING` and refuses otherwise. A falsely successful
start might have enabled PCI DMA, reset firmware or enabled
interrupts while still being in a pre-RUNNING phase. A generic
STOP cannot prove that these resources are reverse-owned; it may
itself fail or conceal the stage needed for explicit recovery.

The old positive unit-test stub incorrectly allowed `hw_stop` to
manufacture `STOPPED` even when `hw_start` had left the device at
`PROBED` with `fw_ready = true`.

## Source changes

- `rtwn8723be_n80211_ifinit` now **returns EIO and leaves the
  actual Linux state intact** on a zero-returning but incoherent
  `hw_start`. It does not call normal `hw_stop`, does not
  set `IFF_RUNNING`, and does not claim a successful recovery.
- A source-shared
  `rtwn8723be_net80211_start_checkpoint_ok(state)` permits
  `ifconfig up` only when the adapter is **entirely quiescent**,
  in `PROBED` or `STOPPED`, with none of `started`,
  `being_init_adapter`, `fw_ready`, or `mac_func_enable` true.
  `if_init` also refuses an already marked `IFF_RUNNING`
  device with `EBUSY`.
- The existing `rtwn8723be_net80211_unstarted_detach_allowed`
  predicate now rejects an interface that is `!started` but
  still owns firmware, a live MAC or adapter-initialization
  state. Probe rollback cannot free this partial hardware owner
  as though it were an innocuous never-started interface.
- The genuine post-start RFKill failure path is unchanged: once
  the adapter has actually reached RUNNING and is firmware-ready,
  the owner may use its real normal `hw_stop`. Its errors remain
  visible and must retain the device's resources.

## Evidence

The production `if_init` and RFKill functions are executed
under strict C11/UBSan by
`tests/test_rfkill_net80211_start.py`. It now rejects both
a false success at `PROBED` after firmware preparation and
a falsely successful `RUNNING` without firmware readiness,
without ever calling normal `hw_stop`. Subsequent retries are
rejected, whereas a genuinely running adapter still uses real
`hw_stop` when RFKill changes during startup.

`tests/test_net80211_unstarted_rollback.py` compiles the
actual two source-shared checkpoint predicates and tests the
`PROBED`, `STOPPED`, pre-registration and partial-start cases.
`tests/test_net80211_prestart_quarantine.py` adds ten unsafe
source-mutation controls, and the updated checks are in CI.

## Remaining lifetime work

The pre-RUNNING recovery journal currently exists as a tested,
**unbound owner model**. The full production lifecycle must still
record real successful hardware acquisitions, serialise them with
net80211/IRQ/BT, and implement the matching reverse compensators
before a partially started adapter can be recovered or detached.

This source fix does **not** bind `register_ieee80211`,
`init_rfkill`, `bt_prepare`, `dm_init`, nor provide working
`hw_start`, `hw_stop` and 802.11 TX methods. A full native
48-unit NetBSD kernel link on HP, actual IRQ/firmware timing,
scan, association, WPA2 and TX/RX are still unverified.

Trusted F77 recovery `/netbsd`, `/boot.cfg`, i915 and
experimental kernel install/boot have not been altered.
