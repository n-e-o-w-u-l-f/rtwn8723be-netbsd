# HP NetBSD 11 RTL8723BE: full 42-source native C ABI gate — 2026-10-10

State: **42 / 42 native NetBSD compiler objects compile, relocatable
link PASS. Complete kernel/Kconfig gate remains OPEN. WLAN NOT online.**

## Immutable references and current actual host

- HP host: `hp-tpnw121.fritz.box`, NetBSD 11.0, owner `andreas`.
- Linux frozen reference:
  `fd179f8a05be3ccae366b9b96e176b51fbe54aab`
- NetBSD frozen reference:
  `03d918f6d0e81fa05b8f1160eca0628ad39988a6`
- Current production-port source HEAD for 42-object proof:
  `89acbaccf7ad300987fd185e3e909d871a044b87`
- Default kernel: preserved F77, WLAN `rtwn8723be0` currently
  DOWN, empty SSID, **no functional Wi-Fi association**.
- No reboot, kernel install, firmware/driver enable, or system file
  mutation. Only `andreas`-owned separate source/test/build outputs.

## Regression and ABI evidence

Actual HP-only 46-script suite after corrected source/model fixtures:
`/home/andreas/projects/driver-port-20261010/rtl-regressions-final-20261010/status.json`
- state `PASSED`, 46 tests, **0 failures**.
- JSON SHA256
  `28863eb569e6e9321a4808178e6f339bc5084856baa544bbbdd59fdb27f376d2`.
- Includes native host-C/UBSan C2H, BTC, RX DMA32, RF,
  security, calibration, RF-PS teardown owner and source contracts.

New reproducible HP-only 42-source native compiler driver:
`tools/build_hp_owner_native_objects.py`
(original strict native generated-Makefile attempt and explicitly
flagged `--abi-only` alternative).

The original native Makefile generated before the latest source
closure selects **36** of the current 42 C translation units. The
six additional active native files have no generated compile rules
in that old configured NetBSD build tree:

1. `rtwn8723be_btc_mp_native.c`
2. `rtwn8723be_btc1.c`
3. `rtwn8723be_btc2.c`
4. `rtwn8723be_btc_engine.c`
5. `rtwn8723be_btc_native.c`
6. `rtwn8723be_btc_providers_native.c`

A strict 42-unit Makefile run rightly failed at the first missing
generated rule, NOT due to missing production code.
The explicit `--abi-only` mode uses the exact real generated
native kernel-C compiler arguments from a *known configured*
NetBSD C unit for each missing Makefile rule, and records such
rules individually as `ABI_ONLY_MISSING_GENERATED_MAKE_RULE`.
It **never claims** to have corrected the kernel config.

The initial 42 ABI-source compilation exposed a genuine native
production error under `-Werror=cast-qual`:
`src/rtwn8723be_hw_disable_native.c` discarded `const`
around the RF-PS lock owner. Commit
`dd8f73d437cd4510adeeaf33da5f51cd0630ab5f`
changes the private function argument from `const softc *`
to mutable `softc *` and calls the real lock owner without an
unsafe cast. No locking or radio behavior is bypassed.
Commit `89acbaccf7ad300987fd185e3e909d871a044b87`
adds strict `-Wcast-qual` to the native host-C regression.
Actual corrected HW-disable C compilation strict native PASS
(158,816 bytes) and host-C RF-PS regression PASS including all
fault-release and 15 revocation scenarios.

All other 41 C objects had succeeded and retained their exact
sha256-bound source/object proof. Each object was compared against
the latest Git source and the binary hash, then the one corrected
object was merged into a *new*, non-overwriting proof directory.
This avoids pretending the originally FAILED source-run was
successful or blindly rebuilding unchanged objects.

Final bounded, actually executed HP result:

```
RTL_HP_42_NATIVE_OBJECT_VERIFIED
42 generated 36 abi_only 6 ld_rc 0
state ABI_ONLY_PASSED_KCONFIG_OPEN
```

- 42 actual NetBSD amd64 C ELF objects: **42/42 successfully compiled**.
- Native `x86_64--netbsd-ld -r` of all 42 objects: **PASS**, output
  `rtwn8723be_native_42_all.o`, 3,969,776 bytes.
- Final merged evidence JSON:
  `/home/andreas/projects/driver-port-20261010/rtl-native-42-assembled-20261010/status.json`
- JSON SHA256:
  `843c8c875456038aeacb0695c6aeddb3cf1eed21cd4c8443351d9fe7ea45802c`.
- Includes six flagged unresolved *build configuration* rules,
  despite their code compiling to ABI-compatible NetBSD objects.

## Still necessary for TWO FUNCTIONING drivers

This is NOT a fully configured final kernel object list:
the NetBSD generated kernel Makefile/config must select all 42,
and the complete kernel must compile/link, load and initialize.
Production callback preflight still rejects enabling this
incomplete driver because **four native lifecycle owners are absent**:
`register_ieee80211`, `init_rfkill`, `bt_prepare`, `dm_init`.
Net80211 hardware start/stop/tx and reverse-order rollback,
radio GPIO polling/regulatory, BT/DM/MCU/IRQ/DMA/PM and
802.11 RSN/WPA2 association/data-path/recovery remain OPEN.

Next: implement each real callback and its lifecycle dependency
based on verified Linux/NetBSD reference; fix the six generated
Kconfig rules without removing F77 recovery; run real native
full-kernel link on HP only; then controlled driver install,
wireless scan/associate, WPA2 handshake, IPv4/IPv6 and DNS,
traffic, RF/radio-stop/resume/recovery tests. A native C
relocatable partial link is not a kernel image.
