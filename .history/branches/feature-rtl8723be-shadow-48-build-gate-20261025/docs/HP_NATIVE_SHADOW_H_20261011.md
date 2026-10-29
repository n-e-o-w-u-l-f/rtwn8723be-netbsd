# HP native Shadow H build record — 2026-10-11

## IST

- The live HP TPN-W121 system remains on the separate F77 recovery kernel:
  `NetBSD 11.0 (RTWN8723BE-F77-LINUX-EFUSE-MAP) #0: Sat Sep 26 19:13:52 CEST 2026`.
  Its `/netbsd` SHA-256 remains
  `9b65629c0527bbd40f7ffa0d4ef0c59a32b5edceb597a5df8c86d1e7be1c8fde`.
- Shadow H is an isolated private build at source revision
  `66fed5c6e732a373e4faa16f96b5742725c99d3b`; the source checkout was clean.
  It selects 47 native C units and all 47 produced nonempty objects.
- The ordered object-hash aggregate is
  `d5835976634e14bdbb456f6d235d6b009f2a5e6f924fccca597d7be9a1b43847`.
  `rtwn8723be_btc_policy.o` is 72,376 bytes and hashes to
  `64322ab1b87ab50db2fad6f594cca8128bb06960c719c2fde12710a2796de2c2`.
- The full private link exits `0`. Its kernel is 27,289,096 bytes with
  SHA-256 `390a3905b41463dee6b0395138ed406dee37051d6506a696c8f764fb0024ac38`
  and exactly one embedded identity:
  `NetBSD 11.0 (RTWN8723BE-NATIVE-SHADOW) #0: Sun Oct 11 20:11:59 CEST 2026`.
- The private config explicitly contains `no i915drmkms*`. The private PCI
  manifest and generated Makefile contain zero i915 lines. The original
  `/usr/src/sys/dev/pci/files.pci` remains
  `584bf78070c5868e2e48d0e563949cbf70a958b08166150f5363cfcbf5d7b707`.
- The candidate differs from live `/netbsd`. It was not installed or booted;
  `/boot.cfg` and the F77 environment were not changed. F16.0 was not booted.

## ÄNDERUNGEN

- Added the 47th selected unit, `rtwn8723be_btc_policy.c`. It is a tested,
  high-level port of Linux BTC `get`/`set` decisions. It does not provide the
  missing whole-driver lifecycle owner and does not activate PCI, DMA, IRQ,
  RFKill, net80211, or i915.
- The first H full-link attempt stopped before linking because the
  non-interactive environment did not expose `/usr/tools/bin` to the linker.
  The successful retry used that directory only in its command-local `PATH`;
  no system profile, symlink, source tree, installed kernel, or boot entry was
  changed.
- The object and successful-link logs hash to
  `4fb30b15df8b6c60e796407fa209e764d2eeb69a8391fc1a5551012df3318ff6` and
  `ed6955b3b5f4d38121ee4406262cedad12eff52e35c153e7d4519ae8581111fb`.
  The successful-link log has zero fatal/error-reference matches.

## NEXT

1. Retain Shadow H as build-only evidence; do not install or boot it.
2. Create and test a pure BTC context-preparation boundary that composes the
   existing low-level and policy callbacks atomically, without binding
   `bt_prepare` or hardware.
3. Close the real `bt_prepare`, `dm_init`, net80211/RFKill, PCI/IRQ, and
   reverse-cleanup lifecycle owners before any WLAN hardware test.
4. Keep i915 trace-only until a physical early serial capture exists. Never
   boot F16.0, F83, or F84.
