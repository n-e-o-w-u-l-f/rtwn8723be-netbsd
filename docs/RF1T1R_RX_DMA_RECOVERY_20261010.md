# RTL8723BE RF_1T1R consistency and RX failed-slot DMA handling
Date: 2026-10-10.
Status: SOURCE PUBLISHED / READBACK INSPECTED / TEST EXECUTION OPEN.
HP-only build, link, install, and WLAN acceptance remain OPEN.

## Immutable references
- Original Linux rtl8723be/hw.c at
  torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab,
  _rtl8723be_read_chip_version(): rtlphy->rf_type=RF_1T1R.
  BT antenna count is not RF serial-chain count.
- NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6:
  sys/bus_dma, NET80211 driver DMA synchronization ownership.
- Prior native RTL source: src/rtwn8723be_btc_providers_native.c,
  src/rtwn8723be_rx_native.c and exact native source-only test inventory.

## Verified source problems

1. Previous code checked per-device physical RF path count in native
   btc_set_rf/btc_get_rf, yet btc_rf_ready still allowed count=2.
   This contradicted immutable RF_1T1R identity and could expose a
   nonexistent B-chain if count were wrong/stale.
2. The existing negative source mutation for the path count used a
   text fragment occurring TWICE (RF get and set), while the runner
   explicitly requires a UNIQUE mutation anchor. Thus that control
   was guaranteed to raise an anchor error rather than exercise the
   expected negative-checker diagnosis.
3. rx_native_drain delivered frames sequentially across two queues.
   When the second queue was corrupt it returned EIO with *delivered
   still set to zero, losing the record of earlier successfully
   dispatched frames.
4. When a slot mapping was invalid, the RX descriptor had already
   undergone DMA POSTREAD synchronization; the function returned
   without returning that unchanged OWN-cleared descriptor to DMA.
5. The RX ring admission test lacked complete 32-bit DMA address-span
   validation for the descriptor ring (although individual packet
   slots had a span check).

## Code / test commits

- bc8ef233d2cd1a99b98b62b17b669fb7f9f0e87d:
  hardware-backed btc_rf_ready requires exactly one physical RF
  serial path. It does not change original RTL chip identity.
- 723fbd3334cb33999b17683df78e5e340680d4de:
  fix path-count negative-control mutation to select uniquely the
  void-return RF SET provider (rather than also the RF GET provider).
- 954ba5c64564f52541d679d65d9965c193d082a7:
  RX ring admission checks the entire 32-bit descriptor address
  span; corrupted queues preserve prior delivery count; invalid
  packet map restores device-direction descriptor DMA sync without
  clearing/reasserting OWN, reports delivered frames, then aborts.
- 7e28e42d8a584e39fd451f1b6c22ccd6daeea3ad:
  source regression guard for all three RX error-path properties.
- d7561d80377d3971cf4b74746384779ae23769ac:
  two disposable-source negative mutations (lost RX count, missing
  descriptor resync).
- 9489c8e6093049562110ca775e9b29e9a3d9fdee:
  source guard rejects readiness permitting second RF path.
- 968fe437c0e32f855aaf56764c7322210c0ec733:
  RF-ready phantom-path negative source mutation.

## Readback and execution distinction

GitHub fetch_file readback verified four currently published key files:
btc_providers_native.c SHA 9d6de9ede688a7d7882e5c64a2ea4ea6a83a0701;
rx_native.c SHA 92b36743e056dcc194afe054a987dda7dde3e109;
tests/test_source_negative_guards.py SHA
31bb90bdd23272ed0859474d70764c40806ca8fa;
tests/test_port_closure_inventory.py SHA
8fc2052591f3de3334bf4233bc0ec6745b9ecb35.

Read-only inspection verified: one-chain condition present; two
provider path-count guards present; three RX delivery-count publication
sites; complete RX DMA descriptor ring span guard; RX invalid-slot
descriptor resync before EIO; fourteen declared negative-control
source entries. This is NOT an executed test or native compile.

Earlier Remote Desktop Commander start_process invocation of the
source-only Python tests was explicitly denied by platform safety.
This continuation did not repeat or reroute that denied execution.
Earlier GitHub write denial for netbsd.h channel-plan publication
also remains intact. No changed HP runtime/boot/KMS/WLAN state.

## Remaining acceptance

Complete and bind four actual RTL callbacks (register_ieee80211,
init_rfkill, bt_prepare, dm_init), including real owner/IRQ/firmware
and all net80211 RX/TX/802.11 WPA2/regulatory and board channelplan
lifetime. The RX error paths now return safely but do not independently
quiesce a corrupt device; the eventual owner must handle terminal
EIO/recovery. The i915 modern DRM adapter and native HP test gate
remain separate, mandatory and open. Preserve HP F77 recovery.
