# NetBSD RTL8723BE — fragmented BE TX slot preflight

Status (2026-10-16): **source published**, JS source oracle PASS (10/10 negative mutations), JS ring model PASS (37,552/37,552). The committed Python test, native NetBSD compiler, complete kernel link and physical WLAN acceptance have **NOT RUN** for these changes.

## Root cause and reference

Frozen NetBSD 11 `ieee80211_fragment()` in
[net80211/ieee80211_output.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/net80211/ieee80211_output.c)
creates a chain of separately allocated 802.11 fragment mbufs using
`m_nextpkt`. The WIP `rtwn8723be_net80211_tx_start()` previously
prechecked only one BE descriptor **before** `ieee80211_encap()`, then
published each fragment separately in the same producer iteration. If
the BE ring had fewer slots than fragments, a prefix could be placed
on the DMA ring while the remaining fragments were discarded.

The frozen [Linux rtlwifi/pci.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/pci.c)
owns its TX queue rings independently. This change preserves the
existing MGNT/BE separation and does not substitute Linux APIs for
NetBSD DMA/mbuf ownership.

## Source correction on experimental WIP

1. `src/rtwn8723be_datapath.h`: bounded
   `rtwn8723be_datapath_tx_check_slots(dp, qid, needed)` prototype;
   commit `f06766c5d1745864f71b349f0c143f950c38340c`;
   verified blob `60a19747cd5378175aa60f43db8ca27a6d8c4ab1`.
2. `src/rtwn8723be_datapath.c`: checks consecutive producer slots
   under `dp->tx_lock`, verifies lifecycle and ring index bounds,
   rejects occupied slots with `EBUSY`, oversized chains with
   `EFBIG`, and wraps indices precisely; commit
   `a8562cd087797127788e584541f5c71d8abe9159`;
   verified blob `d5a9c29b10a6d2faa7f455fc452633d68bfbe8f2`.
3. `src/rtwn8723be_net80211_tx.c`: after `ieee80211_encap()`
   and **before** enqueueing the first fragment, counts the chain
   bounded by the BE ring size and calls the slot preflight. Failed
   admission frees the *entire unsent fragment chain* and releases
   the single caller-owned original node reference; `EBUSY` also
   marks `IFF_OACTIVE` so TX resumes via existing completion wake.
   Successful admission retains one DMA-owned node reference per
   fragment; commit `da1caf5d8a59f9a63c65f3d0ef3c150e7abc3457`;
   verified blob `dc59f96705c86c7c60582fd0ed5ce23aab8859c2`.
4. Source-only regression
   `tests/test_net80211_fragment_slots_source.py`, committed
   `3702155f6b654764984a2c95cde95c3f267e7b37`; negative-test
   scope correction `8ab63d15e6d200e1c95c54cae490aa385bfd1b3e`,
   `b9bbe215b6c3f56af6ef8468742c17c39cb948eb`.
   Verified test blob `89320fd7bb419cb8e1efd743f1d033c8029012f9`.
5. The existing **HP-only, no-install** build script selects the new
   Python source regression before any native `dependall`, commit
   `1a9de130e6ec03e973a79565d3712eef77255e7d`,
   verified blob `61e577fbd564bce85b5657d8ee51d8d3fb2cb9e6`.

## Verification and limitations

A separate JS source-contract oracle re-fetched all three production
files and the Python regression directly from GitHub. It confirmed
the locks, guards, preflight before fragment transmission, bounded
count and cleanup ordering, and rejected all ten simulated source
mutations. The independent ring model covered 2-, 4- and 8-slot
rings, all producer indices, occupation bitmaps, 1..N+1 needed
slots and enabled/disabled states: **37,552 cases / zero errors**.
No NetBSD binary is implied by a JS/portable model pass.

**Not atomic DMA publication.** A per-fragment
`bus_dmamap_load_mbuf()`, encoder, descriptor OWN check or other
native error may still fail **after earlier fragments were published**.
This change only prevents the deterministic ring-*capacity*
failure from partially transmitting a fragmented MSDU. Additional
full-chain staging/rollback analysis is required before calling the
fragment path fully transactional. Its current fail-closed response
on preflight `EBUSY` discards the framed MSDU, rather than requeue
an already encapsulated Ethernet packet.

## Native acceptance still required

On an explicitly permitted HP executor, preserve the current
known-good F77 and recovery kernel, verify WIP source identity, then
run the new Python gate and build/link the 50 C units **on HP only**.
Do not automatically install or boot. Native stress should verify
BE ring sizes, wraparound, 2+ fragments, exact slot shortage,
descriptor OWN mismatches, software-crypto fragment handling, frame
and node release on every error path, and stop/detach races. Physical
RX beacons, management TX, WPA2/EAPOL, IP/DNS, traffic, PM and panic
recovery remain OPEN.

**The previous HP source-fast-forward external safety restriction is
unchanged**. No HP SSH command, kernel installation, network change,
paid GitHub CI or reboot was attempted here.
