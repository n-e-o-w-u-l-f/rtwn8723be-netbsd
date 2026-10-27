# RTL8723BE NetBSD 11 — RX DMA lease and in-flight STOP refusal

**Source checkpoint: 2026-10-27.** This is Linux-host strict C11/UBSan
evidence for extracted real kernel C functions, not a native NetBSD kernel
build or HP RTL8723BE PCI interrupt test.

## Concrete race closed

The native `rtwn8723be_dp_rx` softint callback previously entered
`rtwn8723be_rx_native_drain()` without holding any datapath lifecycle
reference. That function accesses RX DMA descriptors and invokes
borrowed net80211 frame/C2H consumers. The Linux-order stop controller,
since PR #13, atomically marked STOPPING and disabled TX under
`dp->tx_lock`, but **did not know if RX was already executing**.
A successfully accepted STOP could therefore proceed to interrupt/MAC
and eventually ring teardown while the RX callback was still using
borrowed DMA state.

PR #14 also established a lifetime count for the external TX
completion callback, but only `datapath_unprepare` checked it.
The hardware STOP itself could still start while such a TX callback
was executing.

## Native source changes

- `rtwn8723be_dp_rx` acquires the existing IPL_NET `dp->tx_lock`,
  checks that the published datapath and IRQ argument are its own,
  that RX frame and C2H handlers are present, and that
  `started && fw_ready && stage == RUNNING` and TX admission
  remain enabled. On failure it returns **before** any RX DMA
  synchronization or borrowed callback.
- On admission, it increments `rx_callback_active` under the lock,
  releases the mutex **before** executing `rx_native_drain`, then
  reacquires it to publish RX count/error and decrement the reference
  on **both success and failure**.
- `rtwn8723be_datapath_begin_stop` now refuses RUNNING → STOPPING
  with `EBUSY` while `rx_callback_active != 0` **or**
  `tx_callback_active != 0`. The Linux hardware stop controller
  stops at this error **before BT/HAL/IRQ/MAC teardown**.
  It closes further TX/RX admission while keeping the actual Linux
  stage RUNNING for a later explicit retry; it never pretends a
  failed STOP has completed.
- A new `stop_pending` latch under the same IPL_NET TX mutex
  prevents a subsequent `datapath_start` from reopening TX while
  STOP is deferred. This latch also blocks premature datapath
  `unprepare`. A successful retry into STOPPING clears the latch.
- `datapath_unprepare` now checks the RX callback count,
  existing TX completion count, disabled TX **and** the pending
  STOP latch under the mutex, in addition to prior hard/soft IRQ
  disestablishment preconditions. It never sleeps or waits inside
  the spin mutex.

The Linux lifecycle callback inventory is unchanged:
**54 declared, 50 bound, four deliberately unbound**. The native
manifest still selects 48 C objects.

## Actually exercised scenarios

`tests/test_datapath_rx_inflight_stop.py` compiles the actual
production RX softint entry, atomic STOPPING entry and unprepare
bodies under strict C11 + UBSan. Its mocked RX DMA drain invokes
`begin_stop` and `unprepare` **before the RX callback returns**:
both must report `EBUSY` and retain PCI/IRQ/DMAMAP ownership.
The test then checks the error-path RX lease decrement, late
RX rejection, pending-stop teardown refusal, successful STOP
retry, and subsequent safe unprepare. Ten unsafe source mutations
are rejected.

The prior production TX-completion lease harness now expects an
active external TX callback to *block hardware STOP itself* until
the callback returns. The native STOP atomic gate also tests both
RX and TX in-flight cases. The start/enqueue C11 harness verifies
`stop_pending` cannot be used to reopen TX. All are in portable CI.

## Remaining blockers

**EBUSY is not an automatic drain or retry.** The upper net80211
`ifstop` currently clears `IFF_RUNNING` before hardware stop and
does not provide a complete asynchronous retry/notification owner.
A transient RX or TX callback can therefore leave the physical
adapter in RUNNING with admissions blocked until a separately
serialized retry/recovery routine exists. Do not interpret this
change as fully working ifconfig down/up or native detach.

Likewise, the current gate deliberately blocks pre-RUNNING RX
processing; any firmware/BT C2H events required during device
start must receive their own explicitly verified staged owner
before real hardware startup is enabled.

Hard/soft IRQ dispatch, RX softint and detached `ifnet` lifetime
still require a real top-level owner and NetBSD-native SMP testing.
This code assumes `softint_disestablish` has excluded new RX/TX
callback entries **before** destroying the datapath mutex. DMA
quiescence, RFKill and BTC/DM, pre-RUNNING rollback, full-kernel
NetBSD 11 48-unit link and association/WPA2 on HP are still OPEN.
No kernel boot or install is authorized by these source tests.

Trusted F77 `/netbsd`, `/boot.cfg`, i915, `main`, and recovery
assets have not been changed.
