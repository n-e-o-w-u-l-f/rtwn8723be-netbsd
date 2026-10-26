# RTL8723BE IRQ pending-bit quiescence — 2026-10-26

## Problem

The native RTL8723BE PCI hard interrupt and the SOFTINT_NET consumer
previously updated `sc_irq_pending[0/1]` without the common IRQ lock.
A permanent STOP could clear the requested-interrupt flag between a
hard IRQ's hardware status read and the later pending-bit publication.
The softint also dispatched RX/TX callbacks from its snapshot even when
STOP had already revoked `sc_irq_requested`. Finally,
`rtwn8723be_netbsd_disestablish_irq` freed both IRQ handles without
clearing leftover pending bits, permitting obsolete completions to
survive a future fresh firmware/RX lifetime.

## Implemented resource discipline

A portable, kernel-compatible `src/rtwn8723be_irq_pending.h` contains
three source-shared helpers that are called **only with the same
`sc_irq_lock` (IPL_NET)** from native IRQ code:

1. `rtwn8723be_irq_pending_record`: coalesces INTA/INTB only when the
   owner still requested IRQs and a complete RX/TX dispatch is published.
   The actual hard IRQ rechecks that admission after hardware status
   read and before scheduling SOFTINT_NET. A late hard IRQ from after
   STOP is not permitted to enqueue a fresh completion.
2. `rtwn8723be_irq_pending_take`: atomically snapshots and clears
   both pending words under the common mutex. If STOP was requested
   **before the softint snapshot**, it discards the old work and
   returns without calling RX/TX/power callbacks; no late rearm occurs
   unless the owner explicitly still requests IRQ delivery.
3. `rtwn8723be_irq_pending_clear`: clears the ledger under
   `sc_irq_lock` only **after** hard IRQ disestablishment followed by
   softint disestablishment. The context destructor asserts both pending
   words are zero before destroying the IRQ lock.

The helper itself never performs PCI MMIO, DMA or callback invocations.
It is a pending-event admission primitive, not a replacement for the
actual NetBSD hard/soft IRQ drain barrier.

## Executed verification

On a disposable Linux x86_64 checkout of source commit
`45cbeeeefd9c99813f2fb43cae248fbce27e47b5`:
**53 host-permitted regression scripts passed**, none failed or
timed out. Twelve scripts in the 65-script inventory were excluded,
because they require the HP/NetBSD host or specifically pinned Linux
reference checkouts not present on legion.

The new `tests/test_irq_pending_quiescence.py` compiles the **actual
production header** with strict C11, `-Wall -Wextra -Werror -pedantic`
and UBSan; it exercises coalescing, no-owner/STOP/dispatch-not-ready
rejection, output-pointer validation and reuse after clear. It also
checks the native code ordering and detects six deliberately unsafe
source mutations. The existing IRQ-stop/rearm source contract and
five-owner PCI-probe rollback regression also passed.

## Important remaining barriers

- The source-level stop guard only prevents work when STOP has already
  been acknowledged **at the snapshot**. If STOP begins after a
  softint has released the IRQ lock but while it is invoking RX/TX,
  only an external lifecycle owner waiting for actual softint drain
  can protect the lower DMA and callback lifetimes.
- Native NetBSD 11 compilation and full private 48-C-object kernel
  linking still have **not** been executed at this revision. HP is
  registered online through Desktop Commander but command execution
  was rejected due to the connected app's monthly tool usage quota.
- All four incomplete lifecycle callbacks
  `register_ieee80211`, `init_rfkill`, `bt_prepare`, `dm_init`
  remain unbound. No WLAN scan, association, WPA2, TX/RX or real
  device IRQ behavior is claimed.

F77 recovery `/netbsd`, `/boot.cfg` and the i915-disabled policy
remain unchanged. No experimental kernel was installed or booted.
