# RTL8723BE NetBSD 11 — STOP postcondition and media reset quarantine

2026-10-28 — Stacked native-source security checkpoint; **not** a
NetBSD 11 kernel link, HP PCI/DMA test or working Wi-Fi driver.

## Two independent net80211 failure modes

**A. False-success `hw_stop`:** The production
`rtwn8723be_n80211_ifstop` historically returned the `hw_stop`
callback's status directly. A callback that incorrectly returned
`0` while the Linux lifecycle still owned firmware, MAC state or
a RUNNING adapter could make `rtwn8723be_net80211_unregister`
continue to `ieee80211_ifdetach` and `if_detach` even while the
actual hardware lifetime remained active.

**B. Deferred STOP and media reset:** Since the RX/TX stop lease
from stacked PR #15, an `EBUSY` during `ifstop` clears
`IFF_RUNNING` and records native `stop_pending` while retaining
the Linux `RUNNING` stage for explicit retry. A media change
returning `ENETRESET` while the interface was already logically
DOWN could be reported as `0` without reflecting the still-live
hardware. The generic `ENETRESET` ioctl handler had the same
silent-success gap.

## Implemented changes

- `rtwn8723be_n80211_ifstop` propagates any direct `hw_stop`
  error. On callback-reported success, it verifies:
  `sc_linux.stage == STOPPED`, `started == false`,
  `fw_ready == false`, `mac_func_enable == false`,
  and `being_init_adapter == false`. Any inconsistency returns
  **`EIO`**, preserving the actual Linux state for explicit
  error recovery rather than treating an incomplete hardware
  lifetime as detached.
- Because the existing net80211 `unregister` already retains
  its published ownership if `ifstop` returns an error, the
  new postcondition prevents a false-success hardware STOP
  from reaching `ieee80211_ifdetach`, `if_detach`, or
  `n->registered = false`.
- Both the `rtwn8723be_n80211_media_change` and ioctl
  `ENETRESET` fallback recognize a **currently pending STOP**
  via the native `rtwn8723be_datapath_stop_retry_ready`
  predicate, which samples the stop latch/owner/stage under
  `dp->tx_lock`. They return **`EBUSY`** rather than
  pretending a reset or media reconfiguration succeeded on
  a still-running adapter.
- `media_change` first validates `n`, registration and
  `n->sc`, returning `ENXIO` before dereferencing stale
  net80211 storage. Its normal `ENETRESET` restart path
  is retained only when IFF_UP and IFF_RUNNING are genuinely
  both set.

## Executed portable regression

`tests/test_net80211_stop_failure_owner.py` now executes
real `ifstop` with falsely successful hardware callbacks:
untouched RUNNING state, leftover firmware, MAC still
enabled, and initialization still in progress all return
`EIO`.

`tests/test_net80211_deferred_down_retry.py` now extracts
the **actual production** media-change callback alongside
ioctl, ifstop, native stop-retry and begin-stop functions.
It compiles the functions under strict C11/UBSan and checks
both media-change and `ENETRESET` ioctl while a deferred
stop is active. They must return EBUSY without restart,
yet return the normal quiescent result once STOPPED.
Five additional source mutations test false-success
reset bypasses and stale net80211 pointers.

New `tests/test_net80211_false_stop_unregister.py`
compiles **actual production** `ifstop` and
`net80211_unregister` with strict C11/UBSan.
A simulated `hw_stop` returns success with still-live
RUNNING/firmware, or EBUSY; the real `unregister`
must retain `registered`, `sc`, security state,
and its callbacks, and must not call any detach methods.
Only a true STOPPED transition permits both net80211
and ifnet detach. Ten negative source mutations enforce
the owner and teardown order. Portable CI includes
the new script.

## Safety limits — no autonomous runtime closure

These tests show correctness only of the extracted C
function bodies on a Linux host; they do **not**
establish native NetBSD 11 driver buildability, SMP lock
ordering, actual callback drain, PCI or DMA quiescence,
HP RFKill or WLAN association.

The driver still lacks a complete sleepable IRQ/softint
drain and automatic retry after an EBUSY, robust
media-change restart across failed partial STOP,
hardware frame TX and four lifecycle callback bindings
(`register_ieee80211`, `init_rfkill`, `bt_prepare`,
`dm_init`). The 48-unit native build has not linked.
The HP recovery F77 `/netbsd`, `/boot.cfg`, i915,
PCI recovery, experimental install/boot paths and
`main` remain untouched.
