# RTL50 Bluetooth coexistence byte-mask parity — 2026-10-15

Status: SOURCE_PATCH_PUBLISHED / LEGION_SOURCE_ONLY_16_PASS / NEGATIVE_ORACLE_PASS / HP_NATIVE_NOT_BUILT / HARDWARE_NOT_TESTED.

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
The committed Python test **was executed** on Legion against the exact WIP
Git HEAD `7a770a9afd150c2705f092cdbdc422861246c2f6` and returned
`BTC_BYTE_MASK_SOURCE_ORACLE_OK: 5100 portable cases`, exit 0.

A larger Legion source-only gate initially returned 14 PASS, one SKIP and
one FAIL. The FAIL was a **test harness defect**, not a failed driver
hardware rollback: `tests/test_runtime_start_shutdown_error_source.py`
searched the first `r->transition = false` (normal-success branch)
rather than the failed-start `fail:` branch, incorrectly asserting that
cleanup must precede normal return. Commit
`c7ef37c0fcaf321c1dcaf5b1b4487a21c9e348d3` now scopes those
order checks to the unique `fail:` branch (verified test blob
`2fd72473c3fc6c70b23059cc933719b3411d20d4`).

A **second fresh Legion checkout at that exact commit** ran 16 selected
pure-Python/source-contract checks, all PASS with exit 0; includes BTC
masking, NetBSD config/i915 guard, PCI panic-inventory source, Net80211
unregister, interrupt restart, DMA reset, BTC events, regulatory world
policy, reserved beacon filters, pre-start reverse owners and start error
precedence. The test fixture was also deliberately corrupted **only in
the temporary checkout** to put `r->transition = false` before
`runtime_shutdown()`: the regression rejected the incorrect order
(expected failure), demonstrating a working negative gate. All temporary
checkouts were deleted. **No native C compiler or HP kernel build** was
invoked; no physical WLAN test followed.

A read-only SSH attempt from SentinelX Legion to HP address
`10.1.0.44` returned `No route to host`. This is a current **route
failure**, not evidence of HP kernel identity or a permission to replace
the existing fallback. The existing Legion project checkout was not
changed or rebased.

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
