# RTL8723BE / NetBSD 11 — unfinished STOPPING and firmware quarantine

**2026-10-29 — exact-source checkpoint.** This change is a bounded
fail-closed correctness gate. It does **not** implement an autonomous
hardware STOP worker, retry a partially initialized firmware controller,
build a native NetBSD kernel, or demonstrate hardware-level WLAN.

## Why PR #26 was not sufficient

PR #26 makes an explicit ifconfig DOWN reattempt normal hardware STOP
when the *actual* Linux MAC is still `started && RUNNING` but the
network interface has already lost IFF_RUNNING. It also stops normal
net80211 media / ENETRESET from falsely succeeding in that state.

Two other incomplete hardware lifetimes were still mishandled:

1. `RUNNING -> STOPPING` is published by the native TX-owner serializer
   **before** the Linux-order BT/HAL/IRQ/MAC shutdown completes.
   If a later teardown callback fails, the device remains STOPPING
   with real MAC/PCI/DMA resources owned. The normal
   `linux_adapter_stop` deliberately refuses STOPPING reentry.
   Yet if IFF_RUNNING was already cleared, an additional DOWN,
   media change or ENETRESET could appear to succeed.
2. A failed early hardware initialization may be parked at
   `FIRMWARE_DOWNLOAD` (or any stage after PROBED) without
   `started` or `fw_ready` ever being set. The generic RUNNING
   stop callback is inappropriate and the separate hardware unwind
   is not implemented. A downed ifnet could nevertheless hide the
   incomplete PCI/firmware ownership. A formally STOPPED stage with
   still-published `mac_func_enable`, `fw_ready` or
   `being_init_adapter` likewise cannot be considered clean.

## Actual production change

New static inline, source-shared
`rtwn8723be_net80211_hw_recovery_required(state)`
in `src/rtwn8723be_net80211_state.h` returns **true** for:

- Null/unknown state (fail closed)
- Published started, firmware-ready, MAC-active or initializing flags
- Any Linux stage **after PROBED other than STOPPED**

A firmware-free pre-PROBED stage or genuinely STOPPED adapter with
all these flags cleared is clean for the purpose of generic interface
control; separate PCI probe rollback still owns resource teardown.

The normal `SIOCSIFFLAGS` DOWN path **continues** using
`rtwn8723be_net80211_running_hw_stop_needed` and the native
`stop_pending` predicate to attempt an explicit real STOP when safe.
For a logically DOWN interface whose hardware remains dirty but
is **not eligible** for that normal STOP (STOPPING, failed early
hardware initialization, dirty STOPPED), it returns **EBUSY**
without calling `hw_stop`, restoring IFF_RUNNING or pretending
that PCI resources were released.

The down-ifnet `SIOCADDMULTI`/`SIOCDELMULTI` shortcut,
generic `ENETRESET`, and `ieee80211_media_change`
now use this **broader unfinished-hardware predicate** to refuse
false-success reconfiguration. Their existing runnable
`IFF_UP | IFF_RUNNING` stop/start path is unchanged.

This deliberately **retains** the Linux failure stage and all
native ownership for a future **journalled, sleepable** recovery.
It does not relabel a failed STOPPING as RUNNING or STOPPED.

## Executed C11/UBSan tests

New `tests/test_net80211_unfinished_hw_recovery.py` compiles
the **actual source-shared recovery predicate** with strict
`-std=c11 -Wall -Wextra -Werror -pedantic` and UBSan.
It tests NULL, early clean probe stages, PROBED, fully STOPPED,
failed FIRMWARE_DOWNLOAD, RUNNING, STOPPING and all four dirty
owner flags even with STOPPED or PROBED. Seven deliberately unsafe
source mutations are rejected.

The existing strict C11/UBSan
`tests/test_net80211_deferred_down_retry.py` still executes the
**actual production** `n80211_ioctl`, `n80211_media_change`,
`n80211_ifstop`, `datapath_begin_stop` and
`datapath_stop_retry_ready` function bodies.
Additional scenarios assert **EBUSY** on explicit DOWN,
media, generic ENETRESET and multicast ENETRESET during STOPPING,
while the corresponding stages stay untouched and **no hardware
STOP callback** is called. The same checks cover a failed early
firmware download and dirty STOPPED state.

The earlier PR #26 orphaned RUNNING and callback-borrow retry
scenarios remain valid. The source mutation tests now target
the actual ENETRESET branch after the new DOWN gate was added.
Portable CI runs the new regression.

## Automatic STOP retry: ownership prerequisite, not yet implemented

NetBSD 11's `workqueue(9)` allows executing deferred work
in a kernel thread, but expressly requires that **a work item
not be re-enqueued before its callback is invoked**, and
`workqueue_wait` assumes the work item will not be queued again.
See <https://man.netbsd.org/NetBSD-11.0/workqueue.9>.

Before connecting last-RX/TX-callback release to a STOP worker,
the real native owner must prove:

1. The worker is created **before** any producer can submit work.
2. The STOP request and callback-reference zero transition are
   synchronized with `dp->tx_lock`; no lost-last-wakeup race.
3. Hardware STOP runs only in **sleepable thread context**
   and never under `IPL_NET` or inside a NetBSD hard/soft IRQ.
4. Concurrent explicit ifconfig DOWN and automatic STOP cannot
   both own the same Linux-order teardown.
5. The worker cannot requeue itself illegally; errors retain
   recovery ownership rather than spin indefinitely.
6. The outer PCI/net80211 detach first excludes producers,
   then waits for an in-flight worker, destroys its queue,
   and **only afterward** releases callback/softc/MMIO storage.

The existing native RFKill worker is an API reference for
thread-context work, **not a safe shortcut** for this separate
hardware-owner contract.

## Outstanding acceptance criteria

- Implement a separately owned sleepable auto-STOP retry path
  with proven enqueue/drain/detach ordering and actual STOP
  postconditions; do not call `hw_stop` directly from callbacks.
- Implement journalled partial-FW/STOPPING recovery separately.
- Bind the four genuinely missing Linux lifecycle callbacks
  (`register_ieee80211`, `init_rfkill`, `bt_prepare`,
  `dm_init`) only after their hardware and rollback owners work.
- Compile/link all 48 native C units in NetBSD 11 on HP, then
  test PCI DMA/IRQ, RF switch and real WPA2 association.

`main`, trusted F77 recovery `/netbsd`, `/boot.cfg`, i915
and HP PCI recovery state remain untouched. No experimental
kernel was installed or booted. Only transient Linux-host
regression tests were run.
