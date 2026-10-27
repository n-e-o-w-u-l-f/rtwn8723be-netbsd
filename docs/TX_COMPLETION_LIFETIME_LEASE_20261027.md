# RTL8723BE — in-flight TX completion lifetime barrier (2026-10-27)

## Concrete defect

The NetBSD native `rtwn8723be_dp_tx_done` callback correctly ran
`tx_complete` *outside* the `IPL_NET` TX mutex to avoid deadlocking a
net80211 callback which could reenter TX. But prior code retained only a
local copy of the function and argument: once the TX mutex was released,
nothing in the datapath tracked the borrowed lifetime.

`rtwn8723be_datapath_unprepare` checked that IRQ handles were gone
and TX was disabled before clearing callback pointers and destroying the
mutex, but had no independent check of an externally executing TX
completion. Its safety depended entirely on an external and currently
incomplete IRQ/softint drain protocol.

## Production change

The datapath now has a `tx_callback_active` reference counter
protected by the **existing `dp->tx_lock`**:

1. On successful nonzero ring reclaim, the TX handler increments
   `tx_callback_active` **before** releasing the lock and copying the
   callback pointer/argument.
2. The callback still executes **outside** the mutex.
3. Once it returns, the handler takes the TX mutex again, asserts a
   live reference and decrements the count.
4. `datapath_unprepare` checks IRQ disestablishment and disabled TX,
   then checks `tx_callback_active == 0` under the same mutex
   **before** unpublishing IRQ callbacks or destroying that mutex.
   A still executing callback returns `EBUSY` and all owners remain
   retained for a later retry. It never waits while holding a
   spin mutex needed by the completing callback.

This does **not** provide a new complete runtime drain function.
Unprepare still requires the external owner to prohibit new TX
entrants and disestablish **both** hard IRQ and SOFTINT_NET before
testing callback idleness. It only blocks a provably unsafe release
if an already published external notification remains live.

## Executable regression

`tests/test_datapath_tx_completion_lease.py` extracts and compiles
the **actual production** TX-done, atomic begin-STOPPING and datapath
unprepare function bodies under strict C11 with UBSan.

The test's completion callback itself enters STOPPING and calls
`unprepare` before returning. The production function must refuse
with `EBUSY`, leaving the dispatch, owner and TX mutex intact.
After callback return, the active count must be zero and a second
unprepare must succeed and destroy the mutex exactly once.
Nine negative source mutations reject removal of the reference
counting, mutex protections, IRQ preconditions, valid reclaim
admission or STOPPING serialization.

The prior `test_datapath_tx_completion_quiescence.py` was updated
to assert the new callback-reference acquire/release order, including
the extra TX mutex reacquisition after callback return.
Both are run by portable CI.

## Remaining constraints

The code still does **not** supply the outer serialized
ifconfig/RFKill/PCI detach owner, nor prove that
`softint_disestablish` and all interrupt/worker callbacks have
finished on the HP. TX descriptor DMA, RX callbacks, PCI mapping,
firmware operations, failed-start recovery, and net80211 node
references remain separate unclosed lifetime gates.

Four Linux lifecycle callbacks (`register_ieee80211`,
`init_rfkill`, `bt_prepare`, `dm_init`) remain unbound.
The native 48-C-object NetBSD kernel build/link and physical
RTL8723BE WLAN acceptance have not been carried out for this PR.

The trusted F77 recovery kernel, `/netbsd`, `/boot.cfg`, i915,
`main`, and any kernel install or boot operation are untouched.
