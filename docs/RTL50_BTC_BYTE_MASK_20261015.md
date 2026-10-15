# RTL50 Bluetooth coexistence byte-mask parity — 2026-10-15

Status: SOURCE_PATCH_PUBLISHED / MODEL_ORACLE_PASS / PYTHON_TEST_NOT_RUN / NATIVE_NOT_BUILT / HARDWARE_NOT_TESTED.

## Frozen reference and defect

Linux reference: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`,
`drivers/net/wireless/realtek/rtlwifi/btcoexist/halbtcoutsrc.c`,
`halbtc_bitmask_write_1byte()`. The Linux byte read-modify-write operation
preserves bits outside the register field with `& bit_mask` on the
shifted value.

WIP source `src/rtwn8723be_btc_provider_native.c:btc_mask1()` used to
compute `(old & ~mask) | (v << shift)`. For old=0xaa, mask=0x0c,
data=0xff, it produced 0xfe, modifying unrelated bits; Linux parity
requires 0xae. The fix computes `(old & ~mask) | ((v << shift) & mask)`.
No additional PCI/MMIO operations or hardware enable are introduced.

## Published commits (same WIP branch)

- `88076d898adef788e7a2a8cb84aa34d36f717712` — production
  byte-mask fix, verified blob `d68b4226e71f28203ecf6c49a41dcf81c46adff2`.
- `8373161ec0d0b68e4748858b931d68142f15493d` — portable
  source-contract test `tests/test_btc_byte_mask_linux_parity.py`,
  verified blob `d38e7398ebce3067d7e8b45508dab310b046c141`.
- `883c11fc82b082cfb5905d551a31bdc691868f0f` — the
  no-install HP-only kernel builder selects the new regression test,
  verified blob `673c916ddffe4d2519f4b90023e94ef13ac00473`.

Independent arithmetic-model verification passed 5,100 combinations.
The *committed Python test has not yet run*. An independent clean source
checkout attempted outside HP failed on DNS (`Could not resolve host:
github.com`), not on test assertions. No native C compile or
physical WLAN test has been executed for this changed source.

## Next exact acceptance gates

1. Read HP boot identity, recovery kernel and local WIP source state
   before any kernel build; the current running HP kernel is unknown.
2. Execute the Python source regression on HP, then the existing HP-only
   gates for PCI identity, source snapshot, runtime, IRQ, DMA, net80211
   and reverse cleanup.
3. Only with verified safe recovery, compile and link the complete
   selected 50 C units into a new commit-specific **private, uninstalled**
   NetBSD kernel via the existing HP-only build script.
4. Verify the earlier `DEVICE_XNAME_SIZE` cfdriver panic fix in the
   exact new ELF and ensure no i915drmkms/F83/F84 experimental graphics
   path is selected for this WLAN acceptance.
5. Later hardware evidence must show received beacons/BSS, scan, WPA2
   authentication, association, IP/DNS, real traffic, down/up, suspend
   and resume and panic-free detach. Until then FULL/WLAN_READY is OPEN.

Preserve the existing HP kernel and recovery path. No paid CI,
no `main` merge, no unverified install or reboot.
