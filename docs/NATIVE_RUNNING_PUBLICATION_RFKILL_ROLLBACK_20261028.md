# RTL8723BE — native RUNNING publication and RFKill rollback postcondition

2026-10-28 — Source checkpoint only; not a NetBSD 11 kernel build,
working Wi-Fi driver, HP PCI/DMA validation or successful association.

## Production defect 1: false-success hardware start

The real `rtwn8723be_n80211_ifinit` previously treated
`hw_start(sc) == 0` and the three Linux flags
`started && fw_ready && stage == RUNNING` as sufficient to publish
`IFF_RUNNING`. This did **not** prove that the native bridge had
actually activated TX, that `sc_datapath` and `sc_irq_arg` still
pointed to the same owner, or that a deferred `stop_pending` STOP
had not closed descriptor admission.

The new native `rtwn8723be_datapath_running_ready` reads
`dp->tx_enabled`, `!dp->stop_pending`, actual Datapath/IRQ
ownership, IRQ dispatch readiness, interrupt handle, mapped DMA,
allocated rings, and Linux started/firmware-ready RUNNING state
**under the existing IPL_NET `dp->tx_lock`**. Invalid or
unprepared pointers refuse immediately. The result is deliberately
**a snapshot, not a lifetime lease**; real enqueue and STOPPING
retain their own locked admission checks.

`n80211_ifinit` checks this predicate **twice**: once immediately
after the successful `hw_start`/Linux state verification and a
second time **after** the post-start RFKill sample, just before
publishing `IFF_RUNNING`. Any invalid datapath/owner produces
`EIO` while leaving actual hardware ownership intact for
explicit lifecycle rollback; it does not falsely claim that
generic `hw_stop` can compensate an incomplete startup.

## Production defect 2: falsely successful RFKill rollback

After a valid `hw_start`, the physical RF switch may turn off
or the second sample may fail. `ifinit` calls `hw_stop` and
previously returned the original `ENETDOWN` or `EAGAIN`
whenever `hw_stop` returned 0, even if the supposed STOP left
firmware/MAC or Linux RUNNING resources live.

The rollback now requires `stage == STOPPED`,
`started == false`, `fw_ready == false`,
`mac_func_enable == false` and
`being_init_adapter == false`. Otherwise it returns **EIO**
and leaves the actual hardware state for explicit recovery.
The original RFKill error is preserved only after successful
verification of the real STOPPED postcondition.

## Executed source tests

`tests/test_net80211_native_running_publication.py` compiles
**actual production bodies** of native
`datapath_running_ready` and `n80211_ifinit` under
strict C11 and UBSan. It injects false-success hardware start,
wrong IRQ owner, disabled TX, pending STOP, missing IRQ
dispatch, and owner/STOP changes specifically during the
second RFKill sample. None may publish IFF_RUNNING.
True RUNNING success and RFKill-triggered STOP/rollback cases
also execute. **Twelve unsafe source mutations** are rejected.

The existing C11 `test_rfkill_net80211_start.py` now tests
the double admission requirement and four false-success
hardware-stop variants (still RUNNING, firmware owned,
MAC active, or initialization active). Both tests run in
`.github/workflows/portable-c-regressions.yml`.

## Not yet completed

This is not a complete lifecycle owner. A read-only predicate
can become stale after it returns; only a complete outer
stop/drain serialization plus the producer's TX lock can
enforce full concurrent release safety. Running interrupts,
softint cancellation, sleepable automatic STOP retry,
firmware C2H during pre-RUNNING, production net80211 TX
framing/node references, full native kernel compile/link,
and actual HP RTL8723BE WLAN use remain unverified.

Four Linux lifecycle callbacks are still deliberately unbound
(`register_ieee80211`, `init_rfkill`, `bt_prepare`, `dm_init`).
There are still 48 native build .c units. No HP kernel
installation/boot occurred. Trusted F77 `/netbsd`,
`/boot.cfg`, i915, `main`, PCI recovery and all HP
recovery assets are untouched.
