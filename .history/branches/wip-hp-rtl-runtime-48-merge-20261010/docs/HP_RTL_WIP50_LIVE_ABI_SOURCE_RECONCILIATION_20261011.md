# Physical HP NetBSD 11 RTL8723BE WIP-50 checkpoint — 2026-10-11

STATUS: **SOURCE CALLBACKS BOUND, 50/50 NATIVE OBJECT BUILD PASS, RELOCATABLE LINK PASS, WIFI RECEIVE/WPA2 NOT VERIFIED.** This is not a release or a claim of functioning network. Local time used below: Europe/Berlin (CEST).

## New live boundary after 01:35 reboot

HP `hp-tpnw121.fritz.box`, LAN IP `10.1.0.44`, at approx 06:38:50 CEST boots **F77** `RTWN8723BE-F77-LINUX-EFUSE-MAP`; `/netbsd` and `/boot.cfg` retain safe F77 and F16.2 recovery, i915drmkms disabled. Earlier `/root/hp-driver-port-20261005`, `/home/andreas/projects/driver-port-20261010` and F84 image vanished after the independent 01:35 boot; they were not regenerated over root paths. F83 **and F84 were previously BOOTED** on HP and both black-screened despite backlight, as independently documented in the GPU repo `docs/HP_I915_BLACK_SCREEN_ROOT_CAUSE_20261011.md`.

HP F77 `rtwn8723be0`: flags 0x8802 (DOWN), SSID empty, no network, 0 RX packets, 0 beacons, 0 scan on this boot. Ethernet `re0` active. An attempted unprivileged `/sbin/ifconfig rtwn8723be0 up` returned `Operation not permitted` and made no change; `sudo -n` is denied by the authorized desktop tool and no privilege escalation/alternate channel was used.

## Actual WIP source changes

From the previously linked 50-unit WIP branch, now:
- all **53/53** Linux-order callbacks assigned by the reviewed NetBSD ops table, including previously NULL `register_ieee80211`, `init_rfkill`, `bt_prepare`, `dm_init`;
- PCI IRQ re-established after prior hard/soft IRQ drain and ring reset/BT preparation, **before** hardware IRQ enable; NetBSD `start` preflight demands `establish_irq`;
- NetBSD net80211 `ifinit`, `ifstop`, ENETRESET restart no longer run blocking firmware, I/O, worker calls with `splnet()` held;
- the native PCI detach calls real runtime stop/network unregister before releasing the PCI/BAR/rings;
- duplicate BTC INIT_HW/INIT_DM dispatch removed; frozen synchronous BTC hardware init followed by RF/runtime generation seed;
- source-level guards and original native DMA/node owner lifetime tests retained.
- Source closure inventory now prints `DECLARED=53 BOUND=53 MISSING=0`, `NATIVE_C_OBJECTS=50`, but **`GUARDED_CALLBACKS_WITH_OPEN_OWNER=rf_calibration,hw_disable`**, `BTC_FULL_PROVIDER_LIFETIME=OPEN`, `CALLBACK_AND_PG_CLOSURE=OPEN`. Source presence is not real device lifetime/PM proof.

## Recovered HP toolchain and real compiler artifacts

Rather than reuse deleted previous staging, new unprivileged checkout/workspace:

`/home/andreas/projects/netbsd-driver-recovery-20261011/rtwn8723be-netbsd`

The source lives on the isolated branch `wip/hp-rtl-runtime-48-merge-20261010`; no changes to `main` or installed F77 kernel.

1. `tools/compile_hp_wip_against_f77_abi.py` replays the strict native F77 NetBSD kernel GCC recipe from an unchanged F77 Makefile. The 5 changed callback units and all **50 of 50** selected C units compiled with `-Werror`, exit 0, owner-only output. Evidence `/home/andreas/projects/netbsd-driver-recovery-20261011/rtl-native-f77-all50-20261011/status.json`, `ABI_ONLY_PASSED`. Relocatable NetBSD `ld -r` exit 0, SHA256 `3c4e56ccae35bd7217fd446e8849628084f9c90c6581eedaa6f3a9087c044bf4`, **5,605,392 bytes**; 0 internal rtwn8723be symbols unresolved and 126 imported kernel/net80211 externals.
2. `tools/configure_hp_live_native_50.py` creates private read-only symlink overlay from available `/usr/src/sys`, `/usr/src/common` and native `/usr/tools`. Candidate identifies `HP-RTL-WIP50-SAFE-GENFB` and disables i915drmkms only **in this private candidate**. NetBSD `nbconfig` pass, 7 critical real generated C compile rules present.
3. The first complete 50-object selected Make build failed **because overlay omitted frozen generated `.inc` Bluetooth algorithm sources**. Root cause fixed in the generator by symlinking WIP `.inc` alongside C/H; no blind retry with old overlay.
4. Corrected owner overlay: `/home/andreas/projects/netbsd-driver-recovery-20261011/rtl-kconfig-live-inc-20261011`. Actual `nbmake-owner -j2` on all 50 native generated object targets **exit 0**, 50 objects present. Native `x86_64--netbsd-ld -r` **exit 0**, output `rtwn8723be_native50.o`, SHA256 `bf96dede97eabaf279956ae2fd6679cad07e21e13331f81592388805fe600e89`; `nm -u` **0 internal RTL imports, 126 external kernel imports**.

## External symbol owner resolution against actual HP F77

The unprivileged HP inspected all **3,076 existing F77 native kernel objects** with `/usr/tools/bin/x86_64--netbsd-nm -g --defined-only`. From **126** undefined imports in the new relocatable 50-object WIP driver:
- **120** have actual strong/visible symbol definitions in those NetBSD F77 object files. The resulting provider map includes all **18** imported `ieee80211_*` functions with concrete `ieee80211.o`, `ieee80211_node.o`, `ieee80211_input.o`, `ieee80211_output.o`, `ieee80211_ioctl.o` and `ieee80211_crypto.o` object providers.
- The remaining **six** generic kernel/compiler primitives were independently **verified as defined text symbols inside the live F77 ELF kernel** `/netbsd.v1-f77-linux-efuse-map-20260926`: `atomic_inc_uint`, `membar_producer`, `memcmp`, `memcpy`, `memset`, `strlcpy`.

Thus **126/126 referenced symbol names have a known F77 kernel or NetBSD object provider**. This is not the full new `netbsd` executable link, ABI version proof, hardware RF, PM, attach or WLAN acceptance. No symbol was replaced with a dummy function or bypassed.

On the actual HP, seven separate source regressions passed in one clean run: `test_irq_mutex_single_owner.py`, `test_runtime_sw_owner_order.py`, `test_reserved_beacon_native_source.py`, `test_failed_probe_net80211_rollback.py`, `test_runtime_dma_reset_owner.py`, `test_full_runtime_callbacks_source.py`, `test_port_closure_inventory.py`. The last test still deliberately reports `CALLBACK_AND_PG_CLOSURE=OPEN` for real RF/BTC/hardware teardown acceptance.

## Full native NetBSD kernel `dependall` — diagnosed linker environment blocker

New owner source stage `rtl-kconfig-live-inc-20261011` first completed dependencies and proceeded to NetBSD library/kernel C builds. The initial full `dependall` failed **exit 2** at `obj/lib/kern/libkern.o` because **target cross-GCC's `collect2` could not locate executable `ld`**; the exact log says `collect2: fatal error: cannot find 'ld'`. The 50 RTL C source/object/partial-link tests remained sound and untouched. This was NOT a driver symbol, Linux callback or LLVM error.

FAILURE_FINGERPRINT: `NetBSD full kernel dependall | HP owner isolated libkern.o | cross-GCC collect2 target-ld PATH resolution | NetBSD11 + native /usr/tools + owner nbmake wrapper | executable netbsd ELF linked`. Class: technical build environment / **defective linker preflight**; a successful `gcc -c` does not validate `gcc -nostdlib -r`. Do not repeat that older owner wrapper as-is without the verified explicit linker PATH.

Remediation verified on the *actual* HP: owner-local `rtl-linker-preflight/tools/ld` symlink to `/usr/tools/bin/x86_64--netbsd-ld`, PATH prepended to the build environment. A real `x86_64--netbsd-gcc -nostdlib -r` emitted a valid ELF relocatable object. Fixed `tools/configure_hp_live_native_50.py` now automatically creates a private target `ld` and performs an executable GCC+link test before any full kernel build. A newly generated isolated Kconfig stage `rtl-kconfig-live-crossld-20261011/status.json` reports `target_linker_preflight_pass=true`, `CONFIGURED_50_WIP_RULES_PASS`; `cross-linker-probe-linked.o` exists (1152 bytes). The newly generated source overlay did not touch `/usr/src` or `/netbsd`.

Original full-log: `rtl-kconfig-live-inc-20261011/full-kernel-link.log`, state `FAILED:2`. In-place **incremental continuation** with the corrected linker lookup: `rtl-kconfig-live-inc-20261011/full-kernel-link-ldfixed.log` and `full-kernel-link-ldfixed.state`. At 07:21:53 CEST this job was `RUNNING`, already **585** combined kernel object files and no new compiler errors; the full ELF link had **not** occurred. This check is a real host-local process, not a claim of future ChatGPT asynchronous delivery.

The original 50-unit source snapshot is unchanged while this kernel compiles. Separately, the experimental RX management filter patch is committed in GitHub and HP GCC tested but **is not yet in the compiling source snapshot**. Preserve this distinction in all acceptance claims.

## Unmet acceptance gates

- Full selected executable kernel link and ELF identity (50-partial `ld -r` is NOT a kernel `netbsd` link), actual PCI attach, tested cleanup/failure injection, IRQ, DMA, RF/EFUSE regulatory, net80211 RX/beacons, association and WPA2 key handshake, DHCP/DNS, traffic, PM & recovery remain OPEN.
- In particular `rtwn8723be0` is currently DOWN and no authorized root-network control is available. DO NOT retry denied privilege operation via SSH/Tailscale or other transports.
- RTL EFUSE/regulatory channel plan remains incomplete. The earlier denied header write to `src/rtwn8723be_netbsd.h` is NOT reattempted.
- Physical i915 8086:22b1/KMS and modern 323-unit Linux DRM/TTM/GEM/UVM full graph remain OPEN. The separate GPU repository documents F83/F84 failure and requires durable off-screen GPU phase logs before a further hardware boot.
- Preserve F77/genfb and `re0`. No boot, firmware replacement, kernel install, WLAN configuration, credential read or reboot occurred here.

A source build may be considered a proven intermediate checkpoint, never WLAN or DRM/KMS complete.
