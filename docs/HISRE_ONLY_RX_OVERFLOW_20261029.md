# RTL8723BE NetBSD 11 — HISRE-only RX FIFO overflow delivery

**2026-10-29.** Native-source interrupt fix plus executable portable
C11/UBSan test. Not a native NetBSD kernel link, SMP hardware proof,
or an HP RTL8723BE WLAN/PCI DMA demonstration.

## Proven production logic error

The RTL8723BE mask selects two independent PCI interrupt banks.
`HISR/HIMR` provides the first-bank vector `inta`;
`HISRE/HIMRE` provides the second-bank vector `intb`.
The second-bank default mask includes `R23BE_IMR_RXFOVW`
(RX FIFO overflow), independently of first-bank RX OK/RDU.

The native hard-IRQ routine already reads and acknowledges **both**
status banks and records **both** in the pending ledger.
The native `SOFTINT_NET` consumer already handles
`intb & R23BE_IMR_RXFOVW` by calling the RX drain.
But the hard IRQ incorrectly performed an early return on
`inta == 0`, even with `intb != 0`. A pure RXFOVW event
was acknowledged in HISRE, discarded as a purported shared
interrupt and never delivered to the softint. Repeated
overflows could therefore silently avoid the corresponding
RX recovery/drain opportunity.

## Actual production correction

`rtwn8723be_netbsd_intr` now treats only a **both-banks
empty** vector as shared/non-device:

```c
if ((inta | intb) == 0 || inta == 0xffffU) {
    rtwn8723be_netbsd_irq_rearm_if_requested(sc);
    return 0;
}
```

The existing all-ones bus read rejection is retained.
The separate invalid `inta == 0xffffU` safeguard is
also preserved. Otherwise, a nonzero, masked HISRE
RXFOVW is recorded in `sc_irq_pending[1]` under the
shared `sc_irq_lock`, schedules SOFTINT_NET and reaches
the existing RX consumer without inventing a new
firmware/C2H interrupt.

No interrupts are rearmed on permanent STOP:
`sc_irq_requested` remains serialized under the
IPL_NET IRQ lock; a STOP between MMIO status reads and
pending record suppresses publication, while a STOP
after hard-IRQ pending publication causes the later
softint to discard stale events without calling RX or
reenabling HIMR/HIMRE.

## Actually executed production C regression

New `tests/test_hisre_only_rx_overflow_irq.py`
extracts and **compiles production bodies** for
`rtwn8723be_netbsd_intr`, `rtwn8723be_netbsd_softintr`,
`rtwn8723be_netbsd_irq_mask_locked`,
`rtwn8723be_netbsd_irq_arm_locked`,
`rtwn8723be_netbsd_irq_rearm_if_requested`,
`rtwn8723be_netbsd_enable_interrupt` and
`rtwn8723be_netbsd_disable_interrupt`, using the
production pending-ledger header and interrupt/register
macros extracted directly from `rtwn8723be_f16_1.h`.

Under strict C11 and UBSan it verifies:
- **HISRE-only RXFOVW**: status acknowledged only in
  HISRE, queued to softint, exactly one RX callback,
  IRQ mask restored only if the owner still requests it
- **Both banks active**: one RX and one TX-completion
  callback, each after acknowledging its correct bank
- Empty/shared vector, unmasked second-bank bits and
  all-ones bus read do not schedule a softint
- STOP during the second MMIO status read: no
  pending work is published
- STOP after IRQ publication but before softint
  execution: pending bits are discarded, no RX/TX
  callbacks fire and HIMR/HIMRE remain masked
- Already stopped: hard IRQ refuses an RX overflow
- Eleven deliberately unsafe source mutations reject
  the old `inta==0` drop, omitted HISRE handling,
  missing pending/softint publication, RX dispatch
  bypass or unsafe unconditional IRQ rearm

The prior pending-ledger source-order regression was
updated to require the new both-bank empty condition.
The new test is wired into the portable C11 CI matrix.

## Unresolved hardware/runtime obligations

This repairs one **real interrupt delivery predicate**,
not the whole IRQ/softint lifetime. Native NetBSD
hard/soft IRQ disestablishment, SMP thread scheduling,
RX overflow ring recovery, bus_dma synchronization,
DMA unmapping, automatic deferred STOP retry and
net80211/PCI detach ownership still require complete
native build and hardware validation. The host test
mocks MMIO, lock scheduling and softints: it cannot
prove behavior on an HP PCI bridge.

Four Linux probe/start callbacks remain intentionally
unbound: `register_ieee80211`, `init_rfkill`,
`bt_prepare`, and `dm_init`. The full native
48-C-unit NetBSD 11 kernel build and WLAN association
have **not** been performed. Do not enable/install
this driver as a working WLAN kernel module.

`main`, trusted F77 recovery `/netbsd`,
`/boot.cfg`, i915 and PCI recovery assets are
unchanged; no HP experimental install/boot occurred.
