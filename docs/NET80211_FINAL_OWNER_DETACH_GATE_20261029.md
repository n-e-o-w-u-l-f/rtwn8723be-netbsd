# RTL8723BE NetBSD 11 — net80211 final owner detach gate

**2026-10-29.** Production-source checkpoint with strict C11/UBSan
Linux-host tests. This is **not** a native NetBSD 11 kernel compile/link,
concurrent SMP proof, PCI DMA validation or functional HP Wi-Fi driver.

## Concrete ownership mismatch

The native failed-probe unwind broker already explicitly reverses
post-registration owners in this order:

1. Disestablish PCI hard interrupt and SOFTINT_NET handler.
2. Unprepare the native datapath and revoke its RX/TX IRQ dispatch.
3. Unbind the RX/C2H callback, which can refer to net80211 storage.
4. Halt and drain the RFKill timer/workqueue.
5. **Only then** unregister net80211 and detach ifnet.

However, the public `rtwn8723be_net80211_unregister(n)` previously
only called `rtwn8723be_n80211_ifstop(n)` and verified its result.
A successful `hw_stop` establishes a Linux `STOPPED` state, but
does **not** prove that NetBSD IRQ/softint callbacks, native
datapath, RX binding or RFKill workers have been disestablished.
A direct unregister caller outside the probe journal could therefore
call `ieee80211_ifdetach` and `if_detach` while these asynchronous
owners still point to the registered network stack.

## Native production correction

The actual `rtwn8723be_net80211_unregister` now retains the
original hardware-stop result and its false-success STOPPED
verification, then checks the remaining producer/consumer owners
**before changing security policy, detaching either interface or
clearing registration**:

- IRQ owner flags `sc_irq_requested`, `sc_irq_enabled`, plus
  hard IRQ handle `sc_ih`, softint handle `sc_soft_ih` and
  PCI interrupt handle array `sc_pihp`.
- Published IRQ dispatch readiness, IRQ dispatch argument, and
  all RX, TX-completion and power-event callback pointers.
- Published native `sc_datapath` and `sc_rx_binding`.
- Initialized/active RFKill worker and its workqueue pointer.

If **any** owner remains, unregister returns **EBUSY**
after releasing the existing `splnet` boundary. It **preserves**
`n->registered`, `n->sc`, the net80211 method table and the
security policy. No `ieee80211_ifdetach` or `if_detach`
occurs. Once the outer owner actually drains/unbinds all
contributors, a later explicit unregister retry is allowed.

This does **not** invent or invoke a drain procedure from the
wrong context, and does not mistake a Linux STOPPED flag for
NetBSD callback quiescence. The probe-unwind broker already
performs the required ordering; this change makes the **public
last-release function fail closed as well**.

## Executed regressions

New `tests/test_net80211_owner_drained_unregister.py`
extracts and **compiles actual production**
`rtwn8723be_n80211_ifstop` and
`rtwn8723be_net80211_unregister` bodies with strict C11
`-Wall -Wextra -Werror -pedantic` and UBSan.
The runtime test independently injects **15 different**
live IRQ, softint, datapath, RX or RFKill owners into an
otherwise unstarted, firmware-free registered interface.
Each must cause EBUSY without destroying the net80211/ifnet
owner; clearing that owner after a simulated external drain
allows exactly one detach.

It additionally starts from genuinely RUNNING hardware,
lets the actual `ifstop` callback drive the Linux state
to STOPPED, and proves that existing IRQ/RFKill owners
still prevent detach. A later explicit unregister after
releasing both owners succeeds without redundantly
calling `hw_stop`.

The test also checks the source binding/order of the actual
native probe-unwind callbacks, and rejects **19 unsafe
source mutations** that remove owner gates, stop handling or
the final net80211 detach. Existing false-success STOP,
unstarted-probe rollback and post-registration unwind
regressions remain enabled. The new test is wired into
`.github/workflows/portable-c-regressions.yml`.

The older production C11 `test_net80211_false_stop_unregister.py`
mock was extended to include the actual new owner fields,
retaining its original false-success hardware STOP coverage.

## Explicit remaining limits

This is a fail-closed **state/ownership gate**, not an
automatic STOP retry worker, native SMP exclusion guarantee,
or IRQ/softint drain implementation. The outer driver
lifecycle must independently prevent fresh network entrants
while disestablishing IRQ handlers and RFKill work; merely
reading zero owner flags is not a substitute for that
synchronization. The current incomplete Linux callback
table still deliberately prevents real start/probe.

Four Linux callbacks are unbound:
`register_ieee80211`, `init_rfkill`, `bt_prepare`,
`dm_init`. No full native 48-C-unit NetBSD kernel link,
physical HP RTL8723BE PCI/RX/TX testing, firmware boot or
WLAN association was performed.

`main`, trusted F77 recovery `/netbsd`, `/boot.cfg`,
i915 and HP PCI recovery assets remain untouched.
No experimental kernel installation or boot occurred.
