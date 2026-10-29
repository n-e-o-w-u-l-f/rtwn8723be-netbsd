# RTL8723BE NetBSD — ordered fragmented BE TX DMA ownership

Status: 2026-10-17, **GitHub WIP source correction and Legion Python-only regression PASS**. Native NetBSD compiler, HP link/boot and actual WLAN/WPA2 **NOT RUN**.

## Root cause and bounded change

The existing `rtwn8723be_tx_native_enqueue_batch()` already stages **all** packet DMA maps, encoded descriptors and software owners without transferring the chain to the hardware until no fallible preparation remains. The prior publication loop nevertheless assigned `R23BE_TXD0_OWN` in ascending producer order (`i=0 .. count-1`). On a currently running PCIe BE queue, this can expose the producer/head descriptor before subsequent fragments' descriptor OWN flags have been synchronized to device memory. The NIC could follow the chain while a later descriptor remains CPU-owned, interrupting a multi-fragment MSDU. This is a concurrency-risk correction, not a claim that such a failure was observed on hardware.

Source-only fix in `src/rtwn8723be_tx_native.c`: retain the existing all-or-nothing DMA preparation and packet owner handoff under `dp->tx_lock`; after `membar_producer()`, publish `OWN` from `i=count-1` down to `0`, device-syncing each descriptor; only then advance the producer and ring **one** BE doorbell. No new DMA load, encoder, packet allocation or failure branch is introduced after the first OWN flag. Existing NetBSD `m_nextpkt` fragmentation, native `bus_dmamap` and ring-wrap semantics are unchanged.

## Linux/NetBSD reference parity

- Frozen [Linux rtl8723be/trx.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/rtl8723be/trx.c) derives `firstseg` from the 802.11 fragment number and `lastseg` from `IEEE80211_FCTL_MOREFRAGS`, then encodes FIRST_SEG/LAST_SEG and MORE_FRAG. The NetBSD `r23be_tx_prepare_frame()` and `rtwn8723be_tx_encode()` already match this reference. **Do not change them to FS=LS=1 per fragment.**
- Frozen [NetBSD net80211_output.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/net80211/ieee80211_output.c) materializes successive fragments using `m_nextpkt`; the existing producer detaches each fragment and prepares the full chain before native DMA handoff.

## Evidence and limitations

- Driver commit: `81e5c9343cf602caa8ea0d7fbd490b251c998fba`; read-back `src/rtwn8723be_tx_native.c` blob `3d174a0485caabd516395439fc9ff6940882ee8a`.
- Regression: `tests/test_tx_batch_source.py`, correction commits `fb68ae304416fc44145eff7e1e07df761a28614d` and `bab2cd6a8902c96082ca208f412a97846ab0f59d`; read-back blob `d6b41cbeba18c4f59ebe37ac6230069dda03d450`.
- Legion `host_d8c4b538b1dc403f`, Python 3 source-only transient execution from the **exact fetched GitHub blobs**, `returncode=0`: TX batch 10/10 negative mutations, 11,136 model cases, **2,510 ring/start/count/release intermediate publication states**; descriptor staging additional 7/7 negative mutations. No persistent runner, host checkout mutation, GitHub hosted CI or paid execution.
- During test authoring, the Python raw regular expression was initially doubly escaped by the JS generation wrapper. It was explicitly corrected at `bab2cd6a`; the actual Legion Python PASS is **after** that correction.
- This is a stronger publication ordering condition, **not** a physical air-ACK, a fully verified hardware atomicity guarantee, or completion of NetBSD native build, i915 KMS, WPA2 and network acceptance. The prior externally rejected HP source fast-forward remains blocked. No equivalent operation was attempted.

Next: retain this guard in the HP source preflight; when legitimately permitted and i915-owner release is complete, run the native combined-kernel build and hardware acceptance on HP only with the known-good F77 recovery still available.
