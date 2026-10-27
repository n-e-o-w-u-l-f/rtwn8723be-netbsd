# RTL8723BE — TX start and completion quiescence gate (2026-10-27)

**Scope:** production source change and executable C11/UBSan checks, not
native NetBSD compilation, a full 48-unit kernel link, or a functioning
RTL8723BE WLAN.

## Two actual TX owner defects

1. `rtwn8723be_datapath_start` checked the PCI bridge owner,
   IRQ argument and Linux RUNNING status **before** acquiring
   `dp->tx_lock`. The method then took the lock and unconditionally
   published `dp->tx_enabled = true`. A state or owner change in
   that interval could enable descriptor submission for an already
   stopping or orphaned device.
2. `rtwn8723be_dp_tx_done` reclaimed descriptor mbufs and then
   invoked the optional `tx_complete` callback without checking
   `tx_enabled`, active owner, actual Linux RUNNING stage, or the
   `rtwn8723be_tx_native_reclaim` result. A delayed completion
   could wake a stopped net80211 queue; failed partial reclaim
   could also trigger a success-like completion notification.

## Implemented corrections

- `datapath_start` now acquires **the existing IPL_NET TX lock
  before checking owner identity or runtime state**, and publishes
  `tx_enabled` only under that same lock following all checks.
  Incorrect ownership returns `EBUSY`; stopped/unready hardware
  returns `EAGAIN` without enabling TX.
- `dp_tx_done` refuses ring DMA-sync/reclaim when TX has been
  disabled, the PCI bridge/IRQ dispatch no longer points to this
  owner, or the Linux state is no longer truly
  `started && fw_ready && RUNNING`.
  Any remaining ring slots are retained for the explicit quiesce
  and recovery owner. Never manufacture a reclaim on STOPPING.
- Valid TX reclaim still occurs under `dp->tx_lock`; error and
  reclaimed counters are retained. The higher-level optional
  completion callback is captured only for **successful,
  nonzero reclaim**, and called after releasing the TX lock,
  because that callback could itself re-enter TX submission.
  In particular partial reclaim plus `EIO` does not wake net80211.
- A NULL callback argument and invalid queue are rejected before
  referencing the datapath or entering the TX lock.

## Executed regression

`tests/test_datapath_tx_completion_quiescence.py` extracts and
actually compiles the two **production** C function bodies
under `-std=c11 -Wall -Wextra -Werror -pedantic` and
`-fsanitize=undefined`. Instrumented `mutex_enter`
changes stage to STOPPING or revokes datapath/IRQ ownership
exactly at lock acquisition; the start must refuse to enable TX.
Completion cases cover correct reclaim callback, zero reclaim,
failed partial reclaim, STOPPING, disabled TX, missing owner,
unready firmware, invalid queue and an injected STOPPING
transition at the lock. Nine negative source mutations must fail.
The test is included in CI.

## Important limitations

The **Linux stop state transition itself still does not acquire
`dp->tx_lock`**. These checks fix the stale-before-lock and
late-snapshot admissions but do not prove full runtime exclusion:
a STOP beginning *after* the guarded snapshot, an already
executing `tx_complete` callback, and detach/ring destruction
still require a properly serialized external lifecycle owner,
PCI interrupt/softint drain and explicit TX-reference management.

Similarly, suppressing late ring reclaim does not free or
retry outstanding DMA maps; a proven hardware-quiesced recovery
owner must take care of them. The code does not bind the four
unimplemented Linux callbacks
`register_ieee80211`, `init_rfkill`, `bt_prepare`, or
`dm_init`, and cannot be used to claim working Wi-Fi.

Trusted F77 `/netbsd`, `/boot.cfg`, i915 and all kernel
install/boot paths remain unchanged.
