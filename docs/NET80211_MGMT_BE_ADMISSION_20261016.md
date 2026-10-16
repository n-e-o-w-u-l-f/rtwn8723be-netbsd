# RTL8723BE: independent management/data ring admission — 2026-10-16

Status: PRODUCTION_SOURCE_PUBLISHED / JS_SOURCE_AND_POLICY_ORACLE_PASS /
COMMITTED_PYTHON_NOT_RUN / NATIVE_NOT_BUILT / HARDWARE_NOT_TESTED.

## Observed source defect

NetBSD11 `rtwn8723be_net80211_tx_start()` checked **both** the MGNT
and BE TX rings before removing a frame from `ic_mgtq`. A saturated BE
data ring could thus prevent a pending probe, authentication, association
or other 802.11 management frame from using its independent, free MGNT
descriptor ring. When the BE check had set the shared `IFF_OACTIVE` bit,
`rtwn8723be_n80211_ifstart()` and the TX producer also rejected further
management wakeups, even though NetBSD net80211 calls `if_start_lock()`
immediately after enqueueing management frames.

Frozen primary references:

- Linux [rtlwifi/pci.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/pci.c),
  `rtl_pci_tx()`: `hw_queue` selects exactly one independent
  `rtlpci->tx_ring[hw_queue]`, including the management queue.
- NetBSD [ieee80211_output.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/net80211/ieee80211_output.c):
  `ieee80211_mgmt_output()`, `ieee80211_send_nulldata()` and the
  probe-request path enqueue on `ic_mgtq` and invoke `if_start_lock()`.
- NetBSD [if_rtwn.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/pci/if_rtwn.c):
  transmit/reclaim ordering; this is a framework reference, not the
  actual RTL8723BE device implementation.

## Published bounded corrections

1. Commit `1a3f09d9f01c9f3d4a01a0d27796c10e641612cd`:
   `src/rtwn8723be_net80211_tx.c` selects MGNT when `ic_mgtq`
   is nonempty, or BE otherwise. Only that selected ring is checked
   before dequeue. Producer permits pending MGNT even with
   `IFF_OACTIVE` set; the data-only OACTIVE guard is retained.
   Verified source blob `8ffb45387e84589f3bab11e62e6600c841203bd4`.
2. Commit `62e54778626178b65acbdec5004fbe719457ba10`:
   `src/rtwn8723be_net80211.c` forwards pending MGNT through
   `if_start` with shared OACTIVE set; still checks RUNNING and
   callback presence. Verified blob `e2fc749bd158b940bf6fef5301aaa49265797e56`.
3. Commit `cbd6992bf170e5e0f6bc3135e3592ba4c87ce4f6`:
   existing `tests/test_net80211_management_wake_source.py`
   accepts the corrected admission guards without losing its
   wakeup/lock-order invariants.
4. Commits `aab1c891fcecb0d6a0ce8fbd862d8c89f5962a9a`,
   `1d39e027546c14bde6b22fc402a64610105b8f33`:
   source-only policy+mutation regression
   `tests/test_net80211_mgmt_be_independent_source.py`.
   Latest blob `af84f53e393ad8d5fb9b86fa3b71eed57c6da2cb`.
5. Commit `e850336b1269fcaa7c3af5e5fa9ad0754cf93632`:
   the HP-only no-install build preflight includes the new source test.
   Verified launcher blob `7980d6571daf8e1c4b00197fe275d604b1326827`.

## Verification limits

Current GitHub files were fetched and read back independently:
eight targeted JavaScript source assertions passed. A separate
64-combination policy model evaluated RUNNING, enabled, OACTIVE,
management-pending, MGNT-space and BE-space and detected no failed
policy invariant. The corrected policy admits three cases the former
combined-ring/OACTIVE policy rejected. Seven negative mutations are
authored in the committed Python regression but **were not executed**
on a NetBSD or other Python runner in this continuation. This is
source-only policy evidence, not proof of compiled C or hardware behavior.

This change does **not** claim that NetBSD `ieee80211_encap()`
fragment-chain backpressure is atomic. A data chain can still run
out of BE descriptors after some fragments have been queued.
A separate exact-owner study must address fragment slot reservation,
partial-error lifetime and rollback before claiming complete TX
correctness; changing MGNT admission does not solve it.

## Next acceptance

- Execute both source regressions and independent negative cases on a
  permitted source-only runner, then run NetBSD-native compiler/ABI
  checks **only on the HP** when the earlier external host-mutation
  restriction has genuinely changed.
- On HP, with F77 fallback preserved and no automatic kernel
  installation, fill BE while MGNT is free; enqueue management and
  observe that MGNT descriptor submission and air TX proceed without
  waiting for BE reclaim.
- Repeat when MGNT is full, across stop/detach/down/up and in WPA2
  authentication, then verify beacon RX, EAPOL, IP, traffic and PM.
- No hardware build/install/reboot, Tailscale/SSH configuration, paid
  GitHub Actions or F77 recovery changes occurred here.

The documented HP WIP fast-forward external safety boundary remains
active. Published GitHub source is not evidence that HP runs it.
