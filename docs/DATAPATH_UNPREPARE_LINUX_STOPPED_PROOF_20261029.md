# RTL8723BE NetBSD 11 — prove Linux hardware shutdown before unprepare

**2026-10-29.** Production-source hardening and Linux-host portable
C11/UBSan test only; not a native NetBSD 11 kernel build, SMP timing
proof, PCI DMA test or live HP RTL8723BE WLAN test.

## Lifetime hole

Before this change, `rtwn8723be_datapath_unprepare()` refused
to clear the IRQ dispatch and destroy the datapath TX mutex
if any hard/soft IRQ handle remained established, if TX admission
was enabled or a STOP was pending, or if borrowed RX DMA,
TX completion or net80211 TX-start callbacks still executed.

**Those conditions were necessary but insufficient.** The native
`rtwn8723be_datapath_stop()` helper can independently set
`tx_enabled = false` without actually stopping MAC hardware.
An external owner might disestablish IRQs and then call
`datapath_unprepare()` even while
`sc_linux.stage == RUNNING`, `started == true` or
firmware is still owned. Similarly, `begin_stop()`
publishes `STOPPING` before BT/HAL/IRQ/MAC teardown;
after that transition all callback counters may be zero,
yet the hardware stop can still fail midway.

Releasing the native datapath and its callback storage before
the **real** Linux-order shutdown finishes can abandon live
MAC/firmware/ring resources with no safe recovery owner.

## Production change

Under the existing **IPL_NET `dp->tx_lock`**, the native
`rtwn8723be_datapath_unprepare()` now additionally refuses
release with **EBUSY** if any of these are still true:

- `sc_linux.started`
- `sc_linux.fw_ready`
- `sc_linux.mac_func_enable`
- `sc_linux.being_init_adapter`
- Linux stage is **beyond PROBED but is not STOPPED**.

The gate is evaluated before revoking IRQ callbacks or
destroying the datapath mutex, in the same locked condition
as `tx_enabled`, `stop_pending` and all three in-flight
RX/TX callback reference counts.

Two legitimate release categories remain possible, provided
IRQ/softint handles were **already disestablished**, no
callbacks are active and all live-hardware flags are false:

1. The real Linux stop controller finished and published
   `stage == STOPPED`.
2. An **unstarted, firmware/MAC-free probe rollback**
   at or before `stage == PROBED`.

A failed hardware start in a stage **after PROBED** is
not allowed to masquerade as early-probe cleanup merely
because firmware-ready has not yet been published. Such
partial-start recovery still needs its own resource-specific
journalled hardware unwind.

This change does **not** attempt automatic STOP retry,
write any MAC/MMIO teardown register or wait/sleep under the
IPL_NET spin mutex.

## Actual executable source regression

New `tests/test_datapath_unprepare_linux_lifecycle.py`
extracts and compiles the **actual production**
`rtwn8723be_datapath_unprepare()` body with strict
`-std=c11 -Wall -Wextra -Werror -pedantic` and UBSan.
The harness imports the actual Linux stage enumeration.
It exercises valid unstarted probe release, IRQ-establish
probe failure, partial firmware download, interrupted
STOPPING, fake RUNNING with closed TX, stale firmware/MAC/
initialization flags, the three live callback counters,
`stop_pending`, enabled TX, and an active softint handle.

All unsafe stage/owner states must return **EBUSY**
without clearing callback pointers, IRQ owner or the
native mutex. Only fully clean probe or STOPPED states
may unbind and destroy. **Fourteen negative source
mutations** enforce the new stage and resource checks.
The new test is included in portable CI.

The pre-existing strict C11/UBSan RX, TX-completion and
net80211 TX-start lease harnesses have been updated
to model the real Linux hardware finishing STOPPING
**before** expecting successful `unprepare`; they now
also require EBUSY at the intermediate STOPPING stage.

## Remaining limitations

This is a necessary fail-closed last-release check,
**not proof that hardware actually performs a safe STOP**.
The production STOPPED state is published by the Linux-order
controller after its own callbacks succeed. Native NetBSD
IRQ/softint draining, cross-CPU locks, net80211 detach,
automatic STOP retry, recovery from partial STOPPING
and PCI DMA bus-master quiescence remain unimplemented
or unverified. A clean stage/state flag combination cannot
by itself prove the absence of a future incoming callback;
the external teardown owner must still exclude new
entries before disestablishing the handlers and destroying
the mutex.

The native 48-C-unit NetBSD 11 kernel build and HP scan,
association and WPA2/RSN tests have not occurred.
The four intentionally unbound lifecycle callbacks remain
`register_ieee80211`, `init_rfkill`,
`bt_prepare`, `dm_init`.

`main`, trusted F77 recovery `/netbsd`,
`/boot.cfg`, i915 and HP PCI recovery files remain
untouched. No experimental kernel was installed or booted.
