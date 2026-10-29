# RTL8723BE EFUSE regulatory plan and RF_1T1R path reconciliation
Date: 2026-10-10. Driver closure: OPEN. Native HP compile/runtime: NOT TESTED.

## Original hardware/OS references

Frozen Linux at torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab:
- rtl8723be/reg.h EEPROM_CHANNELPLAN = 0xB8;
- rtlwifi/efuse.c:rtl_get_hwinfo() copies eeprom_channelplan;
- rtl8723be/hw.c:_rtl8723be_read_adapter_info() publishes EFUSE channel
  plan; _rtl8723be_read_chip_version() unconditionally selects RF_1T1R,
  distinct from separate 1/2-BT-antenna coexistence configuration;
- rtlwifi/regd.c:channel_plan_to_country_code(), _rtl_regdomain_select(),
  RTL819x_2GHZ_CH01_11, CH12_13, CH14. Linux world domain uses channels
  1-11 for active scan, 12-13 only with passive constraints, and channel
  14 requires further regulatory/NO_OFDM protection.

Frozen NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6:
- sys/net80211/_ieee80211.h IEEE80211_CHAN_PASSIVE = 0x00000200;
- sys/dev/pci/if_rtwn.c advertises 1-14 with OFDM uniformly, which is
  not sufficient by itself to reproduce the pinned rtlwifi regulatory
  distinctions.

Canonical native RTL port before work:
- rtwn8723be_net80211.c advertises 1-14 uniformly without reading the
  board's EFUSE channel plan;
- rtwn8723be_netbsd.c reads physical EFUSE shadow and MAC/package/XTAL,
  but does not retain the channel-plan byte at shadow offset 0xB8;
- native BT provider permitted RF serial path B if its enum path was
  <= RTWN8723BE_RF_PATH_B, even though the initialized 8723BE physical
  RF inventory reports only one serial path.

## Production changes actually committed

1. 08ced13f7a2a67e3980469113ff0108720358fba:
   declare R23BE_EEPROM_CHANNELPLAN = 0x00B8 from frozen Linux reg.h in
   src/rtwn8723be_f16_1.h. This is a real hardware constant but, on its
   own, DOES NOT implement channel-plan selection.
2. d4d85b1fee8c702bab6d5d09d0cb7e71c78a0648:
   native BTC RF get/set providers now reject RF serial path numbers
   >= the successfully parsed physical sc_rf_path_count and decline IO
   when the inventory is not valid. This distinguishes antenna topology
   from RF serial-path count and records the failure through the native
   BTC owner.
3. c7ee063522bfa73f192d556153ff5ef8f833c80d:
   source inventory guard for both native RF read/write providers;
   d03700b363579050718e3e5b414325a9e3e105e2:
   negative source mutation specifically removing path inventory.
   These checks are COMMITTED but NOT EXECUTED in this continuation.

## External write refusal and scope

An attempt to extend src/rtwn8723be_netbsd.h with channel-plan/validity
fields was rejected at the connector/platform boundary:
"Dieser Tool-Aufruf wurde von den OpenAI-Sicherheitschecks blockiert.
Bitte überprüfe, was du sendest."
A direct GitHub readback showed that the native header blob did not
change and contains no new channel-plan fields. This was a write denial,
not a native compiler failure or proof of an invalid hardware constant.
Do not repeat the equivalent header write by alternate tool, host,
account, encoding or file transport without new permission evidence.
The independently scoped BT RF physical-path source change was made
through normal GitHub write capability and verified by readback.

## Unfinished, still required for full parity

- Once legitimately permitted, publish the actual EFUSE channel-plan byte
  and a trustworthy validity state only after successful native identity
  parsing; reject premature net80211 registration.
- Source-derived regulatory policy must distinguish chip availability,
  immutable board EFUSE, present country-domain authority and firmware
  powers/active/passive scan restrictions. Do not advertise channel14
  with OFDM. World-safe 1-11 active; 12/13 initially passive until
  country/channel hints authorize changes; country-specific channel14
  only with documented legal domain and NO_OFDM.
- Proven lifecycle for registration, RF-kill polling, channel power
  programming, TX/RX/WPA2, Bluetooth coexistence and PHY DM remains
  incomplete. The 53/49/four callback inventory is not advanced.
- The prior 2026-10-10 rejected remote source-test command means
  d823ae1 TX rollback and later changes still lack executed test
  evidence. Do not label this report a compiled or HP-verified driver.
- HP is unavailable on direct RDC; its recovery F77, kernel, WLAN and
  i915 KMS status have not been freshly verified. No build/install was
  attempted outside the HP or on its offline connection.
