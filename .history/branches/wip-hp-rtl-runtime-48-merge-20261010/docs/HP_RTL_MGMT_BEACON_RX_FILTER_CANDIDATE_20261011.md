# HP RTL8723BE management-filter discrepancy — reference-based WIP patch (2026-10-11)

STATUS: **SOURCE-DERIVED CANDIDATE / HP NETBSD GCC VERIFIED / NO LIVE BEACON TEST.** No kernel installation or reboot.

## Reproducible physical HP evidence

The safe F77 `RTWN8723BE-F77-LINUX-EFUSE-MAP` boot's persistent RX diagnostic reports `RXFLTMAP=0x0000/0x0000/0xffff` with 0 net80211 RX beacons/frames during the earlier scan. Its hardware descriptor ring was allocated and DMA configured; channel scans alone were not proof of RF reception. At the latest 2026-10-11 inspection the HP's F77 `rtwn8723be0` is DOWN; enabling it as an unprivileged account was rejected. No live RX or WPA2 is claimed.

**Register semantics:**
- pinned Linux RTL8723BE `drivers/net/wireless/realtek/rtlwifi/rtl8723be/reg.h`, revision `fd179f8a05be3ccae366b9b96e176b51fbe54aab`: `REG_RXFLTMAP0=0x06a0`, `REG_RXFLTMAP1=0x06a2`, `REG_RXFLTMAP2=0x06a4`.
- independent Linux Realtek `rtl8xxxu/regs.h` reference identifies MAP0 as **management-subtype** filter (bit 8 admits beacon), MAP1 as control, MAP2 as data. Zero MAP0 can therefore reject all management subtype bits.
- frozen `rtlwifi/rtl8723be/hw.c:_rtl8723be_init_mac` writes only MAP2=0xffff; this is **not equivalent** to initialization on a chip where MAP0/MAP1 remain zero after hardware power-up.
- September 23, 2026 `rtw88` RTL8723B v4 proposal explicitly defines `WLAN_RX_FILTER0=0xffff`, `WLAN_RX_FILTER1=0x0400`, `WLAN_RX_FILTER2=0xffff` and writes them MAP2 -> MAP1 -> MAP0 in MAC WMAC init. **Proposed reference, not a proven working Linux installation on this exact HP.** The September 29 review further reports using shared `rtw8723x_mac_init` for this programming.

Reference URLs:
- https://raw.githubusercontent.com/torvalds/linux/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/rtl8723be/reg.h
- https://kernel.googlesource.com/pub/scm/linux/kernel/git/netdev/net/+/6b5a2b7d9bc156e505f09e698d85d6a1547c1206/drivers/net/wireless/realtek/rtl8xxxu/regs.h
- https://lists.openwall.net/linux-kernel/2026/09/23/3197
- https://lists.openwall.net/linux-kernel/2026/09/29/1437

## Code change, guards and HP acceptance

On the independent WIP branch `wip/hp-rtl-runtime-48-merge-20261010`, `src/rtwn8723be_f16_1.h` now owns 0x06a0/0x06a2/0x06a4 hardware symbols; `rtwn8723be_netbsd_init_mac` (after power-on, DMA ring allocation and RCR programming) writes MAP2=ffff, MAP1=0400, MAP0=ffff. There are no modifications to RF regulatory channel plan, country policy, EFUSE conversion, installed F77 or recovery boot config.

`tests/test_rx_management_filter_native.py` checks addresses, 16-bit widths, preflight placement and exact register ordering. Real HP NetBSD tests run in a separate clean shallow WIP checkout `/home/andreas/projects/netbsd-driver-recovery-20261011/rtwn8723be-filter-wip-20261011`:

- `test_rx_management_filter_native.py`: `RTL_MANAGEMENT_BEACON_RX_FILTER_SOURCE_ORDER_PASS`
- `test_full_runtime_callbacks_source.py`: `RTL_LINUX_STAGE_CALLBACKS_AND_IRQ_RESTART_SOURCE_PASS`
- strict F77 NetBSD GCC C ABI compile of `rtwn8723be_netbsd.c` and `rtwn8723be_linux_state.c`: both exit 0, `HP_F77_NATIVE_WIP_ABI_ONLY_PASS 2`
- owner artifacts `/home/andreas/projects/netbsd-driver-recovery-20261011/rtl-native-f77-rxfilter-20261011/status.json`.

The full 50-unit owner kernel `dependall` run already underway uses a **prepatch source snapshot** and is not claimed to contain this change. After its link, a new isolated owner build must incorporate and retest the filter. Do not silently change symlink-backed source while a prior Kconfig build is compiling it.

## Remaining acceptance (explicit)

1. Complete NetBSD kernel ELF link with all 50 native units and correct callback table.
2. Map management RX and RCR register readback after real attach, verify actual per-channel DMA descriptors, IRQ mask/cause/ack and delivered beacon counters.
3. Compare AP beacon reception and WPA2 handshake; no partial success counts as Wi-Fi online.
4. Resolve the separate EFUSE/regulatory channel policy without retrying a previously denied change.
5. Install/test only on HP with a live recovery path, keeping F77, genfb/i915 safe boot and `re0` stable.

This candidate is based on specific hardware/reference state, not trial-and-error bit twiddling; causation requires physical RX acceptance.
