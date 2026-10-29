# RTL8723BE — net80211 if_start callback lifetime lease

**2026-10-29. Source-only checkpoint:** portable Linux-host C11/UBSan
execution, not a NetBSD 11 kernel build or an HP RTL8723BE PCI/WLAN test.

## Concrete lifetime hole

Stacked PR #19 gated `rtwn8723be_n80211_ifstart` with the native
`rtwn8723be_datapath_running_ready` function. That function takes
the existing IPL_NET `dp->tx_lock`, checks TX, PCI/IRQ and Linux
RUNNING ownership, **then releases the lock and returns a boolean**.

Net80211 then calls its external `n->methods.tx_start` with no
active lifetime reference. A simultaneous `begin_stop` can enter
STOPPING after readiness returned but **before or during** that
external callback. Hardware IRQ/MAC shutdown and, eventually,
reclamation of the ifnet owner could then overlap the code that
still drains net80211 queues or builds TX descriptors. The
external callback may also reentrantly invoke STOP.

## Production fix

- New `dp->tx_start_active` counter is protected **exclusively**
  by the existing IPL_NET TX mutex; the native datapath is
  still one published owner per PCI softc.
- `rtwn8723be_datapath_tx_start_begin(dp)` validates a
  prepared bridge, enabled TX, no `stop_pending`, matching
  sc_datapath/sc_irq_arg owners, IRQ dispatch and interrupt
  handle, mapped/allocated DMA and Linux
  `started && fw_ready && stage == RUNNING`. It increments
  `tx_start_active` **in the same mutex critical section
  as those admission checks** and returns whether acquired.
- `rtwn8723be_n80211_ifstart` now acquires that reference
  instead of using a read-only native RUNNING snapshot.
  The external `n->methods.tx_start(n->sc, ifp)` is invoked
  **outside** `dp->tx_lock` (so it can reenter net80211/
  the hardware controller without deadlocking the TX mutex).
  `rtwn8723be_datapath_tx_start_end(dp)` reacquires the mutex,
  asserts a live reference and decrements it only after the
  callback returns.
- `rtwn8723be_datapath_begin_stop` refuses RUNNING→STOPPING
  if **any** of `rx_callback_active`,
  `tx_callback_active` or `tx_start_active` is nonzero.
  The failed STOP closes TX admission, sets `stop_pending`
  and returns EBUSY; a later **explicit** retry may enter
  STOPPING after all callbacks release their references.
- `rtwn8723be_datapath_unprepare` also refuses the
  new counter when retiring the IRQ callbacks or destroying
  the TX mutex. It does **not** sleep or busy-wait under
  IPL_NET.

## Executed regression

`tests/test_net80211_tx_start_callback_lease.py`
compiles **the actual production** net80211 if_start,
native lease begin/end, begin_stop and unprepare function
bodies under strict C11/UBSan. The external TX callback
reentrantly attempts STOPPING, which must return EBUSY,
then attempts an IRQ-disestablished unprepare, which must
also return EBUSY **solely because its published TX-start
reference is still active**. The callback returns and the
lease is released. A subsequent explicit STOP retry
succeeds; a stale IFF_RUNNING flag cannot invoke
tx_start again, and the final owner release is permitted.

Twelve deliberately unsafe source mutations check
acquisition order, missing owners, pre-STOP state
admission, double release, omitted STOP/unprepare gates,
and whether the published counter is declared.
The regression is in portable CI.

The existing strict-C11 test harnesses for late net80211
RX/TX, RX DMA in-flight STOP, TX completion callbacks
and atomic STOPPING were updated to include the new
partial struct layout/real production functions. All
must continue passing before a Draft is ready.

## Still OPEN

This is **one borrowed-callback lifetime lease**, not a
complete ifnet, RFKill or PCI runtime controller.
An automatic completion notification and sleepable
STOP/retry worker are still missing; an EBUSY may leave
an internally RUNNING adapter logically DOWN until a
further explicit DOWN request. The external lifecycle
still must disestablish/drain both IRQ/softint handlers
and prevent new ifnet entrants before destroying the TX
mutex. Proper frame/node-owned net80211 TX, firmware C2H
during startup, four unbound Linux probe/start callbacks,
the native NetBSD 11 full 48-unit link and real HP WLAN
association all remain open.

No experimental kernel is installed or booted. Trusted
F77 `/netbsd`, `/boot.cfg`, i915, the HP PCI recovery
state, and `main` remain untouched.
