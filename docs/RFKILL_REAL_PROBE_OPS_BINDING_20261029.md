# NetBSD 11 RTL8723BE — real RFKill probe callback binding

**2026-10-29.** Incremental native Linux-order lifecycle port.
RFKill is now a **real bound callback**, not a simulated or stub success.
The other three unbound callbacks still block hardware activation
at the Linux probe/start preflight.

## Device-level reference mapping

The pinned Linux rtlwifi probe establishes net80211 ownership before
`rtl_init_rfkill`. The native Linux-stage controller follows exactly:

```
R23BE_STAGE_IEEE80211_REGISTER -> register_ieee80211
R23BE_STAGE_RFKILL -> init_rfkill
R23BE_STAGE_IRQ_ESTABLISH -> establish_irq
```

The existing real native `rtwn8723be_rfkill_native_init` already
owns a NetBSD kernel workqueue, GPIO RF-switch sampling, periodic
callout timer and rollback. RF GPIO must be sampled by sleepable
thread-context work rather than inside a hard/soft interrupt.
The worker updates a last-valid radio sample; a failed or busy
sample never authorizes an outdated radio-on result.

The new `rtwn8723be_netbsd_init_rfkill(void *arg)` adapter rejects
a null device, absent net80211 registration or an interface whose
stored softc pointer refers to another device. Only an owned
registered interface proceeds to real RFKill initialization.
The RFKill implementation independently verifies the active
Linux RFKILL stage, mapped BAR, core initialization, RF-PS
mutex and noninterrupt thread context.

`rtwn8723be_netbsd_ops.init_rfkill` is now bound to this
real adapter, reducing the missing Linux lifecycle callbacks
from **four to three**. It is not a no-op and does not set
the Linux hardware stage itself: `R23BE_CALL` sets that
stage immediately before invocation.

The already existing native probe-unwind owns:
`IRQ teardown -> datapath unprepare -> RX binding -> RFKill fini
-> net80211 unregister`.
The real `rtwn8723be_rfkill_native_fini` excludes new timer/work
entries, calls `callout_halt` outside the spin mutex, waits
for `poll_work`, destroys the workqueue, destroys the callout
and last destroys the RFKill mutex. Failed workqueue creation and
failed initial GPIO sampling destroy only the resources they own.

## Executed C11/UBSan contract

New `tests/test_rfkill_probe_ops_binding.py` extracts,
compiles and **executes actual production C bodies** for:

- `rtwn8723be_netbsd_init_rfkill`
- `rtwn8723be_rfkill_native_init`
- `rtwn8723be_rfkill_timer`
- `rtwn8723be_rfkill_worker`
- `rtwn8723be_rfkill_native_fini`

The portable test uses strict C11/UBSan and NetBSD source-shared
Linux state enum. It independently asserts:
- No init for null, unregistered or foreign net80211 owners
- No init from a wrong Linux stage, absent prerequisite RF-PS
  mutex, hard interrupt or softinterrupt context
- Failed workqueue creation and GPIO I/O return real errors
  and destroy initialized queue/timer/mutex resources
- EBUSY GPIO sample keeps RFKill active but radio validity
  false; timer can resample from thread context
- The timer cannot re-enqueue the same pending work item twice
- The real worker clears `work_queued` and reschedules a poll
- `fini` performs timer halt, workqueue wait and complete
  one-time resource release; repeat fini is idempotent
- Nine unsafe source mutations are rejected

The existing `test_native_probe_admission.py` is also updated:
RFKill **must be bound**, while missing register_ieee80211,
bt_prepare and dm_init callbacks must remain absent.
The portable CI includes the new strict C11 test.

## Non-goals and remaining blockers

**No complete probe can succeed yet.** The Linux preflight
requires all required probe callbacks before *any* PCI/MMIO
side effects; `register_ieee80211` is still unbound.
There is no complete native net80211 hardware-method adapter
and no authoritative full-scope TX/PCI/firmware recovery.
`bt_prepare` and `dm_init` are likewise unbound and
must be implemented from their actual Linux/NetBSD references.

Three callbacks remain unbound:
`register_ieee80211`, `bt_prepare`, `dm_init`.
Native NetBSD 11 full 48-C-unit compile/link, live HP RTL8723BE
IRQ/DMA/RFKill testing and WPA2 association remain open.
These portable tests **do not** establish that Wi-Fi works.

The HP is not currently connected through the available
SentinelX host roster. Only a disposable clone on `legion`
was used for host-side testing. `main`, F77 recovery
`/netbsd`, `/boot.cfg`, i915 and HP PCI recovery state
remain untouched; no experimental install/boot occurred.
