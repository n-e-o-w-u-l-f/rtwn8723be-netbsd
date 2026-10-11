# HP native Shadow G build record — 2026-10-11

## IST

- HP TPN-W121 remains on the verified F77 recovery kernel with
  `i915drmkms` disabled. F16.0 is prohibited; F83 and F84 remain rejected
  black-screen test kernels.
- The current RTL source remains intentionally unbound at the PCI, IRQ,
  RFKill and net80211 boundaries. The four missing real lifecycle owners are
  `register_ieee80211`, `init_rfkill`, `bt_prepare`, and `dm_init`.
- The isolated source checkout used for this build was
  `8a85ab31b6ff2c478efb79529bc7141a5c0cba99`. Its driver-source revision is
  `8f18a9295d2e86036b11d170e13ec2d3ecbf6a1f`.

## ÄNDERUNGEN

- Created a new private 46-unit NetBSD 11 amd64 shadow and generated all
  native rules with i915 excluded.
- Compiled 46/46 selected objects nonempty. The ordered object-hash record is
  `18b1b4b85b71af884e24b8e9199f2901a6bc7068be576dc1cac1fbc2aa7a6c23`;
  its object-build log is
  `0b630b14c0697ae482e3470a68bd57888e5d7b6190a57774c19ed54b585b2fbe`.
- The new `rtwn8723be_pre_running_recovery.o` is 28,976 bytes and hashes to
  `41a34e2cb3f9c24a1fd9eaa3d90d295a86205972de64b48895d9df4c1096bb71`.
- Completed the full private kernel link. The 27,288,000-byte kernel hashes
  to `e3ac1437d70a910ab41550292a6d6dbe78118a6d0d8fd595fa1a9e0a5b2adef6`
  and embeds `NetBSD 11.0 (RTWN8723BE-NATIVE-SHADOW) #0: Sun Oct 11
  18:45:02 CEST 2026`. The link log hashes to
  `638274f03439d04bf82c8cdd89e132dedfc01675b4852a975fadce87ecbf32b5`;
  no fatal compiler or linker line was found.
- Both generated configuration and Makefile contain zero i915 lines. The
  original `/usr/src/sys/dev/pci/files.pci` remains
  `584bf78070c5868e2e48d0e563949cbf70a958b08166150f5363cfcbf5d7b707`.
  The live F77 `/netbsd` remains a distinct file with SHA-256
  `9b65629c0527bbd40f7ffa0d4ef0c59a32b5edceb597a5df8c86d1e7be1c8fde`.

No candidate was installed or booted; neither the F77 kernel nor the boot
menu was changed.

## NEXT

1. Retain this as a build-only checkpoint and remove only superseded private
   E/F build outputs after this record is committed.
2. Replace the absent `bt_prepare` callback only with a real owner for the
   MCU/RX-drain, BTC context and reverse-release lifetime. The old runtime
   model is not sufficient evidence for such a binding.
3. Complete `dm_init`, net80211/RFKill, start/stop and recovery ownership
   before enabling PCI attach or IRQ binding.
4. Keep i915 trace-only until a physically attached early serial trace exists;
   do not boot F16.0, F83, F84, or any new display candidate before that gate.
5. Perform WLAN scan, association, traffic, recovery, suspend/resume and
   detach testing only after the complete runtime closure. Package work starts
   only after target-hardware acceptance.
