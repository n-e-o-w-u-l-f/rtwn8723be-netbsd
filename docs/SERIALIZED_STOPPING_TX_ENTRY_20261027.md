# RTL8723BE NetBSD 11 — serialized STOPPING entry

2026-10-27 — Native source milestone, not a NetBSD kernel build.

## Bug fixed in the production lifecycle

Before this change, `rtwn8723be_linux_adapter_stop` updated
`state->stage = R23BE_STAGE_STOPPING` without holding the same TX
mutex as `rtwn8723be_datapath_enqueue`,
`rtwn8723be_datapath_start`, and TX-ring reclaim.

The explicit RUNNING checks added in previous draft PRs were
**not enough**. A TX producer could read RUNNING while the
stop controller concurrently wrote STOPPING; without a common
serializer, the driver did not establish a reliable ownership
order between a newly published TX descriptor and hardware stop.

## Implemented STOP owner and API

- `struct rtwn8723be_linux_ops` now declares mandatory
  `begin_stop(void *, struct rtwn8723be_linux_state *)`.
  `rtwn8723be_stop_ops_ready` rejects STOP before any mutation
  when this callback is absent.
- The Linux stop controller calls `begin_stop` *before*
  `bt_halt_deinit`, `mark_hal_stop`, interrupt masking or
  RF/MAC power-down. The callback itself must leave the state
  in STOPPING with `started` still true or the controller
  refuses further hardware stop actions.
- `rtwn8723be_netbsd_begin_stop` validates the precise
  device state's identity and a published datapath owner.
  It calls the native
  `rtwn8723be_datapath_begin_stop` routine.
- The native routine holds **`dp->tx_lock` at IPL_NET**
  while it validates `sc_datapath`, `sc_irq_arg`,
  `sc_irq_dispatch_ready`, started/firmware readiness
  and RUNNING stage. It then sets **`tx_enabled=false`
  and `state->stage=STOPPING` in the same critical section**.
  No producer can publish a new descriptor across this
  transition while using the same TX mutex.
- A foreign owner or inconsistent lifecycle returns
  `EBUSY`/`EAGAIN`; the stop controller does **not**
  proceed to destructive hardware callbacks. An incoherent
  but still owned state also revokes TX under the mutex.

This changes the native inventory from **53/49 to 54/50
declared/bound** lifecycle callbacks. The four Linux callbacks
`register_ieee80211`, `init_rfkill`, `bt_prepare` and
`dm_init` remain deliberately unbound. The native 48-source
kernel manifest is unchanged.

## Tests and precise scope

`tests/test_native_stopping_tx_atomic.py` extracts the **real
native datapath and NetBSD callback functions**, compiles them
with strict C11 and UBSan, and changes lifecycle state,
firmware readiness or owner at mutex acquisition. It verifies
that the transition closes the TX gate, prevents a subsequent
DMA submission and handles invalid state/pointer inputs.
Ten unsafe source mutations must fail.

`tests/test_linux_lifecycle_stop.py` compiles the full real
Linux lifecycle controller with a mock synchronized stop
callback; it checks a missing callback, callback failure,
false-success callback and valid reverse-order stop.

## Remaining safety limits

The new critical section serializes TX enqueue/start/reclaim
with the **entry** into STOPPING, but it is not a complete
running-driver teardown. In particular:

- TX completion notifications intentionally run *outside*
  `dp->tx_lock` to permit net80211 reentrancy; a callback
  that was already admitted before STOPPING can remain in
  flight. The external lifecycle owner must drain it.
- The NetBSD RX callback, IRQ dispatch and RFKill worker
  lifetimes still need a shared runtime/drain ownership
  protocol before any destructive DMA-ring or net80211
  free operation is allowed.
- Linux pre-RUNNING recovery and failed STOPPING rollback
  still require hardware-specific compensators.
- Native NetBSD 11 kernel compilation/link, PCI interrupt
  load testing and Wi-Fi association are not proven by
  the Linux-host C11 tests.

The trusted F77 `/netbsd`, `/boot.cfg`, i915, `main`,
kernel installs and boot paths were not modified.
