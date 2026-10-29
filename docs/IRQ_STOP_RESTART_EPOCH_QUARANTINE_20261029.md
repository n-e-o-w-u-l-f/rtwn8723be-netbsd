# RTL8723BE NetBSD 11 — IRQ pending STOP/restart quarantine

**2026-10-29.** Native-source IRQ lifetime hardening and executable
portable Linux-host C11/UBSan tests. This does not prove NetBSD 11
SMP scheduling, PCI bus_space behavior or HP hardware operation.

## Bug 1: stale queued softint crosses owner restart

Before this change, `rtwn8723be_netbsd_disable_interrupt` changed
`sc_irq_requested` to false and masked HIMR/HIMRE, but retained
`sc_irq_pending[0/1]`. The pending ledger is checked by SOFTINT_NET
at execution time, not when originally queued. If the device stopped,
then quickly reenabled IRQ before the scheduled old softint ran,
`sc_irq_requested` was true again and that old work was eligible
to enter the *new* RUNNING epoch.

STOP now clears **both pending banks under the same IPL_NET
`sc_irq_lock`** used by the hard-IRQ writer and softint consumer.
A newly requested IRQ owner also clears the ledger under that lock
before arming, but a repeated `enable_interrupt` within the **same
requested owner lifetime** retains legitimate already-published
pending work. No sleeps or callbacks execute while holding
`sc_irq_lock`.

## Bug 2: old hard IRQ resumes after STOP and new enable

The hard interrupt releases `sc_irq_lock` to read MMIO
HISR/HISRE. A permanent STOP and subsequent new enable can occur
while those reads execute. The old hard IRQ previously checked only
`sc_irq_requested` when publishing status; that bool might already
belong to a new owner, permitting an old sampled event into the new
ledger. Even with an epoch check before publishing, the old code
performed **write-one-to-clear HISR/HISRE acknowledgments first**,
possibly clearing status belonging to the new owner.

New `sc_irq_epoch` (uint32_t) is protected by the same IPL_NET
IRQ mutex. It changes on every STOP/disable, and when
`enable_interrupt` begins a **new** requested owner.
The hard interrupt captures the epoch under that mutex **before
dropping it to read MMIO**. On return it retakes the mutex,
rejects a changed epoch or revoked request/dispatch,
and only then performs W1C acknowledgments, both-bank
shared-IRQ classification and pending publication **under the
same mutex**. The STOP/new-owner transition can no longer
interleave between epoch validation, W1C ACK and pending record.

An empty shared interrupt remains `(inta | intb) == 0`; valid
HISRE-only RXFOVW still reaches SOFTINT_NET. Invalid all-ones
hardware reads still refuse service. The existing conditional
rearm checks `sc_irq_requested`, mapped BAR, IRQ handles and
dispatch readiness, so a permanent STOP never rearms IRQ.

## Executed real production C test changes

`tests/test_hisre_only_rx_overflow_irq.py` already extracts and
compiles the actual production NetBSD hard IRQ, softint, IRQ mask/
arm/rearm, enable and disable bodies, alongside the true
source-shared pending helper and register/mask macros. Its strict
C11/UBSan harness now executes these extra real-code scenarios:

- Pending HISRE RX overflow is queued; STOP clears it; fresh
  reenable precedes a late softint; **no old RX callback** fires
- Old hard IRQ is paused mid-MMIO read; STOP and fresh enable
  occur; old hard IRQ must not ACK, record or schedule an event
  from its obsolete epoch, despite requested being true again
- Repeated enable in the existing requested lifetime does
  **not** discard legitimate RX pending bits; softint still
  receives exactly one event
- Existing pure HISRE overflow, dual-bank RX/TX, invalid bus
  read, shared/non-device IRQ and permanent STOP cases remain
  intact

The source-negative controls also enforce the epoch increments,
pending clear on STOP and fresh enable, pre-MMIO epoch snapshot,
epoch rejection and the **lock-serialized ordering:
epoch check -> W1C ACK -> pending record**.
There are **18 deliberately unsafe source mutations** rejected
by this regression after the additional seven checks.
The existing `tests/test_irq_pending_quiescence.py` now asserts
the updated hard-IRQ critical section while retaining all its
pending, softint and final-handler-drain requirements.
Both tests are already in CI; their step titles now explicitly
mention STOP/restart and the IRQ generation.

## Remaining work / safety

These are deterministic synchronous interleavings in a Linux-host
mock of real C function bodies, **not** a proof of SMP memory ordering
or NetBSD hard/soft IRQ concurrency on HP hardware. IRQ epochs can
wrap after 2^32 owner transitions; hardware register state must
still be validated during a real long-running system test.
A softint that already consumed an event before STOP can still
be executing and requires actual softint/PCI drain and the
existing datapath callback leases. These fixes do not provide a
complete sleepable automatic STOP retry, firmware recovery,
new net80211 TX implementation or a complete PCI detach owner.

Four Linux callbacks remain unbound:
`register_ieee80211`, `init_rfkill`, `bt_prepare`, `dm_init`.
The full native NetBSD 11 48-C-unit kernel compile/link and
HP PCI/IRQ/DMA/WLAN association tests have not occurred.

`main`, F77 recovery `/netbsd`, `/boot.cfg`, i915 and
HP recovery assets are unchanged. No experimental boot/install.
