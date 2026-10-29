# RTL8723BE / NetBSD 11 — TX DMA mbuf + ieee80211_node lifetime

**29 October 2026.** Actual native code change on the route to a
working NetBSD 11 net80211 TX method. This PR **does not** bind
`register_ieee80211`, enable a PCI WLAN probe, prove 802.11
encapsulation/CCMP or build a NetBSD kernel.

## Linux hardware constant / NetBSD resource owner

The existing RTL8723BE old-TRX TX queue maps a caller's `mbuf`
into one 32-bit DMA segment, fills a 64-byte descriptor, sets
OWN and polls the PCI TX queue. It holds the `mbuf` until
DMA completion, reset or ring free.

NetBSD net80211's TX contract also requires keeping a
**referenced `ieee80211_node` for the transmitted frame**.
The pinned NetBSD `if_rtwn.c` example stores `m` and `ni`
in one native TX slot, releases both on completed TX and on
ring reset. Before this change our native slots had **only m**.
An eventual `tx_start` could therefore lose or prematurely
free the destination node even if the DMA descriptor succeeded.

## Actual native implementation

`rtwn8723be_f16_1.h`: each DMA slot now has a
`struct ieee80211_node *ni`; only TX slots use it.
Forward declaration avoids pulling NetBSD net80211 headers
into the hardware descriptor definition.

`rtwn8723be_datapath_enqueue` and
`rtwn8723be_tx_native_enqueue` both now require
a **non-NULL referenced node**, along with the `mbuf`.
The caller already owns exactly one reference to `ni`,
which transfers to the ring **only after successful
DMA mapping, full 32-bit-span checks, descriptor encoding,
DMA PREWRITE sync and ownership publication**.
No extra node reference is manufactured. A failed
queue/slot/DMA load, encoding or STOPPING admission
returns an error **without freeing the caller's
`mbuf` or `ni`**.

The physical ring publication stores **`slot->m = m`**
and **`slot->ni = ni`** before the producer barrier
and OWN bit, and rejects a slot with either old field
still occupied. The TX serializer retains its existing
`IPL_NET` lock across this transfer.

The three actual native release paths now pair both
resources correctly:

- Normal `rtwn8723be_tx_native_reclaim`:
  after OWN clears and DMA POSTWRITE/unload succeeds,
  free `m`, then `ieee80211_free_node(ni)`,
  clear both fields, restore linked descriptor.
- Linux-order `rtwn8723be_netbsd_reset_trx_ring`:
  after quiescence, DMA POSTWRITE/unload, free
  `m`, free `ni`, clear both fields before reset.
- `rtwn8723be_f16_1_tx_ring_free`:
  after device teardown, DMA POSTWRITE/unload,
  free `m`, free `ni`, clear both fields before
  destroying the descriptor map.

Each path asserts that an occupied TX mbuf has an
owned non-NULL node reference; a cleared slot cannot
retain a node. On corrupt DMA metadata,
`tx_native_reclaim` still fails closed, retaining
both resources for explicit hardware teardown instead
of speculatively freeing an in-use DMA frame.

This is a **real resource-lifetime correction**,
not a new `net80211 tx_start` callback.

## Tests actually performed

Existing strict C11/UBSan production-function harnesses
`test_datapath_tx_stage_and_native_include.py`
and `test_native_stopping_tx_atomic.py` now supply the
required node pointer and still exercise the **actual
`rtwn8723be_datapath_enqueue` C function**.
The latter verifies that no TX is published once
`RUNNING -> STOPPING` closes admission.

New `tests/test_native_tx_node_dma_lifetime.py`
extracts the real native TX queue preflight and
**executes it under strict C11/UBSan**; production
`tx_native_enqueue`, `tx_native_reclaim`, ring
free/reset and the datapath forwarding are inspected
for admission, paired ownership transfer, post-DMA
release ordering and eight negative mutations.
It does **not** compile the NetBSD bus_dma/MMIO
functions in Linux userspace. The exact native PCI DMA
behavior remains a target-build/hardware requirement.
Portable CI runs the new check.

## Critical pending work — do not turn on probe yet

1. Actual `if_start/tx_start` for management/data:
   dequeue, `ieee80211_find_txnode`, 802.11
   encapsulation, WPA2 software-encrypted frame
   handling, frame/queue rate/priority selection,
   one-segment linearization, failed enqueue cleanup
   and restarting net80211 output after completion.
2. Actual hardware `hw_start/hw_stop` wrappers around
   Linux-order stages and the native TX/RX/IRQ bridge
   with proven late-softint/drain/STOP/restart owners.
3. Bind `register_ieee80211` only when all methods
   above exist and the outer PCI owner can undo
   registration safely; otherwise the Linux complete
   probe preflight must still fail with ENOSYS.
4. Implement real `bt_prepare` and `dm_init`,
   compile/link the 48 native NetBSD 11 C units,
   and test on HP TPN-W121 (PCI IRQ/DMA/RFKill/WPA2).

The callback inventory remains **51/54**. The HP
is not in the accessible SentinelX host roster;
only a temporary Linux x86_64 test clone on legion
was used. `main`, the trusted F77 /netbsd recovery
kernel, /boot.cfg, i915 and the HP's PCI recovery
state are unchanged. No experimental install/boot.
