# RTL8723BE — net80211 RX/TX gates use native RUNNING ownership

2026-10-28 — Source checkpoint only. No NetBSD native kernel link,
HP RTL8723BE WLAN association or physical PCI DMA test is claimed.

## Previously mismatched admission policy

The earlier source changes added a mutex-protected
`rtwn8723be_datapath_running_ready(dp)` to decide whether
`n80211_ifinit` may publish `IFF_RUNNING` after hardware startup.
But the **later entry points** `rtwn8723be_n80211_ifstart`
and `rtwn8723be_net80211_input` still checked primarily
`IFF_RUNNING`, `sc_linux.started` and `stage == RUNNING`.
Those values may remain temporarily stale when
`dp->stop_pending` is set and descriptor admission is
closed, or when the native datapath/IRQ ownership is lost.

In particular, a still-RUNNING ifnet could call the
net80211 TX source method even though native
`rtwn8723be_datapath_enqueue` would reject it, and the
RX stack admission path had no final native bridge check.

## Production change

- `n80211_ifstart` now calls
  `rtwn8723be_datapath_running_ready(n->sc->sc_datapath)`
  **before** invoking the external `tx_start` method.
  Missing/foreign IRQ owner, disabled TX, deferred
  `stop_pending`, missing hardware IRQ/DMA readiness, or
  non-RUNNING firmware state prevents TX queue dequeue
  even if `IFF_RUNNING` is stale.
- `net80211_input` checks the same native predicate
  alongside the original `IFF_RUNNING` test **before
  `m_devget`** to avoid unnecessary buffer copying on
  a denied RX frame. After copying, it checks again **inside
  the existing `splnet()` admission section**, before
  `ieee80211_find_rxnode`, and frees the copied mbuf with
  `ENETDOWN` when a native stop/owner revocation occurred
  during copying.
- The native predicate reads under **the same IPL_NET
  `dp->tx_lock`** used for `begin_stop`/TX descriptor
  enqueue. It is a **read-only snapshot**, not a callback
  reference. The producer and RX DMA drain retain their
  own atomic admission and lifetime checks.
  No network stack callback is executed while holding
  `dp->tx_lock` in the new code; the RX admission
  `splnet` path only takes/releases the datapath lock
  to evaluate state before delivering to the stack.

## Executable regression

The existing `tests/test_net80211_late_rx_stop.py`
now compiles the **actual production native RUNNING
predicate**, `n80211_ifstart` and `net80211_input`
under strict C11 and UBSan. It simulates late
stop/owner changes while `m_devget` copies a frame:
`IFF_RUNNING` cleared, registration invalidated,
softc missing, Linux started/stage invalidated,
`stop_pending` set, `tx_enabled` false,
IRQ argument revoked, firmware not ready, or
datapath pointer gone. It requires no delivery to
`ieee80211_input` after any of those transitions.

It also tests pre-copy refusal without any mbuf
allocation for invalid native states, and refused
`tx_start` callbacks despite stale IFF_RUNNING
on pending STOP, disabled TX, foreign IRQ owner and
non-ready firmware. Eleven mutation controls reject
missing IFF/started/stage or native RX/TX admission
checks. The existing test is already in the portable
C11 CI workflow; its CI name has been updated to
make the native bridge requirement explicit.

## Remaining safety boundaries

This change does **not** supply top-level ifnet,
hard IRQ/softint, or PCI detach serialization. The
check-and-use interval between releasing `dp->tx_lock`
and entering the full net80211/802.11 stack remains a
higher-level lifecycle responsibility. The native
RX softint already holds an `rx_callback_active` lease
for DMA/borrowed callback lifetime; the complete
sleepable drain and STOP retry owner are still open.

Four Linux lifecycle callbacks remain unbound:
`register_ieee80211`, `init_rfkill`, `bt_prepare`
and `dm_init`. The full 48-C-object NetBSD 11 kernel
build and real HP PCI, DMA, IRQ, WPA2/RSN and association
tests have not taken place. No boot or install was
performed; trusted F77 `/netbsd`, `/boot.cfg`, i915,
PCI recovery and `main` are untouched.
