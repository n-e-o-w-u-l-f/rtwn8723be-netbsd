# RTL50 — Hardware OWN consistency in fragment-slot admission

Date: 2026-10-16. Status: **GitHub WIP source published / source-oracle PASS / Python NOT_RUN / native HP NOT_RUN / WLAN NOT_RUN**.

## Root cause, exact scope

The earlier `rtwn8723be_datapath_tx_check_slots()` classified a TX slot as available when `ring->slot[idx].m == NULL`. The actual Linux-order NetBSD enqueue path `rtwn8723be_tx_native_enqueue_owned()` also synchronizes the descriptor and rejects `R23BE_TXD0_OWN`, which can be set independently of the mbuf pointer. Consequently the preflight could accept an entire `m_nextpkt` chain but later enqueue could reject the second or subsequent fragment because a supposedly free descriptor still belonged to the device. That would cause prefix-only DMA publication.

Reference:
- Frozen Linux [rtlwifi/pci.c:rtl_pci_tx](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/pci.c) selects a queue and verifies the chosen descriptor's hardware ownership.
- Native `src/rtwn8723be_tx_native.c` at this RTL WIP implements `rtwn8723be_f16_1_dma_sync_for_cpu()`, checks `R23BE_TXD0_OWN`, then returns DMA descriptor to the device with `rtwn8723be_f16_1_dma_sync_for_device()` when necessary.
- NetBSD/src pinned `03d918f6d0e81fa05b8f1160eca0628ad39988a6`, `sys/net80211/ieee80211_output.c:ieee80211_fragment` constructs fragment chains with `m_nextpkt`.

## Changes

- `src/rtwn8723be_datapath.c` commits `5945c5104832ba835117ae9fd1bfb9ea8d20e000`, `affedde17ec9367da196d56ca228432bb6116eb8`:
  - Under the existing datapath TX lock, check live mapped/DMA/ring descriptor backing, 32-bit descriptor range and each candidate slot's map before reading descriptors.
  - For each required consecutive producer slot, reject an occupied mbuf OR a hardware-owned descriptor `OWN=1`; perform paired CPU/device DMA descriptor synchronization even when rejecting `OWN`; preserve the existing wrap check and lifecycle guards.
  - Include NetBSD `sys/endian.h` directly for `le32toh`.
  - Final source blob: `8bb3f2fe5c13beffd0a7118f3e1139653ee8e901`.
- `tests/test_net80211_fragment_slots_source.py` commits `265205471451c5c7b8fa399dbf657f61a48eb7d0`, `993bb66def63d77dd423a7cb51461976702b7136`: added source contracts and negative mutations covering OWN inversion, map/bounds guards and paired CPU/device sync. Final blob: `aaec6e94fc9560f62c003d683e6840371127ddf7`.
- Existing HP-only `tools/build_hp_rtl50_next_candidate.sh` already selects the updated `test_net80211_fragment_slots_source.py`; no build wrapper change was required.

## Verification

GitHub production/header/TX/test blobs read back and independent JavaScript source checks passed **8/8**, including OWN-read-after-CPU-sync, device-resync-before-exit, mapped descriptor guards and maintained whole-chain preflight. An adversarial source oracle rejected **7/7 distinct injected faults** (OWN inversion, missing CPU/device sync, reversed slot/map/bounds guards). The independently implemented 2/4/8-slot ring model passed **37,552/37,552** cases (wrap, capacity, mbuf occupancy, enabled state). The added OWN condition correctly rejects a hardware-owned but mbuf-empty slot.

**Limit:** This is not a full transactional fragment enqueue. A per-fragment `bus_dmamap_load_mbuf`, bounds check or descriptor encoding can still fail *after* earlier fragments have already been published. Closing that gap requires an explicit batch prepare–validate–commit architecture and full rollback of unpublished maps/descriptors/owner references. Do not infer source test success equals native ABI correctness or hardware functionality.

No HP host command, fast-forward, native kernel build, boot, network change or paid CI was invoked. The earlier provider safety rejection for HP source update is still effective. Preserve F77 and recovery.

## NEXT

Design and verify a bounded transactional **prepare all fragment DMA mappings / validate all descriptors / publish OWN only after every preparation succeeds** path, without touching unrelated RX/PM/wake behavior. Native build and hardware acceptance on HP remain gated by genuinely permitted executor, confirmed kernel/source identity, recovery, PCI RX beacons, management TX, WPA2/EAPOL, IP/DNS/traffic and suspend/resume.
