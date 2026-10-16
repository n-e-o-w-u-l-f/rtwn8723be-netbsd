# NetBSD 11 RTL8723BE — bounded fragment-chain to native BE batch

2026-10-17; experimental WIP **source integrated / source-oracle verified / NetBSD native NOT_RUN / HP WLAN NOT_RUN**.

## Reference-derived problem and solution

The frozen NetBSD net80211 `ieee80211_encap()` path fragments an MSDU into `m_nextpkt`-linked 802.11 frames. The previous RTL WIP treated such a chain as `EOPNOTSUPP` to prevent an earlier partial publication defect. The frozen Linux rtlwifi PCI path selects a hardware TX queue, and RTL8723BE must never expose a fragment prefix while a later fragment still needs fallible DMA mapping or descriptor encoding.

Authoritative pinned references:
- [NetBSD ieee80211_output.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/net80211/ieee80211_output.c) — `ieee80211_fragment()`, `m_nextpkt`, node and software crypto ownership.
- [Linux rtlwifi/pci.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/pci.c) — per-hardware-ring TX queue/descriptor ownership.

Existing native WIP `rtwn8723be_tx_native_enqueue_batch()` already stages per-slot DMA maps and private encoded 64-byte descriptors for up to `RTWN8723BE_TX_BATCH_MAX=16` frames. On any failure **before** committing, it unloads the maps in reverse order, never transfers frame ownership or publishes OWN. When all preparations succeed, it publishes descriptor/packet metadata, then OWN for every descriptor and a single BE doorbell. The native bridge `rtwn8723be_datapath_enqueue_batch_notify()` serializes this with IRQ reclaim using `dp->tx_lock`.

## Actual new integration

- `src/rtwn8723be_net80211_tx.h`, commit `46bf13c0fa35bd3e5654f64375ef2585946d715d`, SHA `a78b84634c30229d738394a32b74104188ac8d3f`: two 16-entry scratch arrays for prepared frames and report tickets, embedded in the existing heap-allocated runtime. No kilobyte-scale automatic arrays or new heap allocation in interrupt/producer context.
- `src/rtwn8723be_net80211_tx.c`, commits `0334f3e56593b056554b7e3f046b83ddb6e24b21`, `994ef9d815c70801dc579546cedd2fbfdba5bff2`, SHA `76c9f155ed35207aa00b41c3efe7ca929310c610`:
  1. The fragment producer requires no more than the live BE ring size **and** 16 frames; checks the hardware OWN, map and consecutive BE slots before handing off any frame.
  2. New `r23be_tx_submit_fragment_chain()` saves each `m_nextpkt`, detaches it before calling the existing `r23be_tx_prepare_frame()`, and acquires exactly one additional net80211 node reference per fragment.
  3. Each successfully prepared frame and optional first-fragment EAPOL/null report ticket goes into the scratch arrays. A failed frame preparation consumes that frame/reference, frees the untouched remaining chain and aborts every already prepared item in reverse order. A wrong queue does the same.
  4. Only after **all** frames have been software-encrypted, linearized and parameterized does the code call `rtwn8723be_datapath_enqueue_batch_notify()`. A native DMA map/validation/encode error returns without any published frame ownership; the net80211 abort path frees **all** prepared packet/node/report owners.
  5. Successful batch transfer clears scratch references without freeing DMA-owned packets. Existing report-sent accounting remains per allocated ticket; the producer frees its **original** node reference exactly once after the chain helper returns.
  6. Unfragmented management/data TX still follows the existing single-frame `rtwn8723be_net80211_tx_frame()`; the independent management-ring and `IFF_OACTIVE` behavior is unchanged.
- `tests/test_net80211_fragment_slots_source.py`, commit `442414c045f000711ee4ff84296a5136b8b4f339`, source blob `1143a4d19a79161e331fb1051289eecd8fa00933`: source contract now asserts both the descriptor-count and batch-count bounds.
- `tests/test_net80211_fragment_failclosed_source.py`, commit `1048b234daa5e9c00e3c0c6b362a2a407be940d5`, blob `9727d1bfa569950a4df7c6f6d6c469b82f943d9a`: the old unconditional `EOPNOTSUPP` gate was replaced with preparation/all-or-none publication and error-path ownership contracts, preserving the original test filename used by the existing no-install HP build launcher.

## Verification and boundaries

Direct GitHub source readback confirms 17 targeted independent structure/order contracts in the updated WIP, including exactly one original producer node release, per-fragment reference acquisition, preparation before native batch, release-on-failure and batch-native OWN publication only after all fallible mapping/encoding succeeds. A separate JS source oracle rejected 12/12 directed negative mutations; 540 bounded policy cases were examined. These are **source-level** checks, not execution of the committed Python scripts.

The preexisting native and datapath batch source contracts were also inspected. Their previous source-only test evidence does not establish correctness on this newer combined source revision. A NetBSD kernel compiler, real PCI bus_dma, net80211 lifetime, C2H, EAPOL/crypto and software/interrupt race tests have **not** run.

Remaining limitations: a failing fragment MSDU is consumed rather than automatically retransmitted or requeued; the complete 802.11 fragmentation/crypto acceptance needs native tests. Firmware/air TX ACK is not proved by a DMA acceptance callback. Until the HP source update restriction genuinely changes, do **not** attempt to install, compile on, reboot or modify that host through other accounts, scripts or transports. F77 recovery remains the last observed safe state, not a fresh boot claim.

## Required next acceptance sequence

1. Run the updated Python source tests and all currently selected source-only regressions using an independently permitted executor. Resolve any failure fingerprint before proceeding.
2. When legitimately permitted, compile/link the WIP with NetBSD's native headers/toolchain **on HP only** while leaving its working F77 and boot default untouched.
3. Exercise 1..16-fragment BE batches, ring wrap/OWN saturation, injected DMA map failure at every fragment, invalid descriptor/encoder, stop/IRQ races, node/report refcounts, and software crypto.
4. Confirm beacon RX, management TX, WPA2 EAPOL, DHCP/DNS, WLAN traffic, down/up and suspend/resume, and panic/black-screen recovery before declaring success.

No paid GitHub Actions, CI runners, HP host mutation or boot changes occurred in this step.
