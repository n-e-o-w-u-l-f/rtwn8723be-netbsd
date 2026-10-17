# RTL8723BE → NetBSD 11: frozen Linux lifecycle audit and kernel-link readiness

**Audit date:** 2026-10-17. **Scope:** HP RTL8723BE-only experimental kernel, keeping the safe F77/genfb fallback. A successful kernel link is NOT evidence of a functional WLAN, WPA2, power management, or i915 KMS.

**Pinned Linux reference:** [rtlwifi/pci.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/pci.c), [rtl8723be/hw.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/rtl8723be/hw.c), [rtl8723be/sw.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/rtl8723be/sw.c), [rtl8723be/dm.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/rtl8723be/dm.c), [btcoexist/halbtcoutsrc.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/btcoexist/halbtcoutsrc.c). These **exact original source files** were fetched during this audit; sequence strings below were checked independently against their actual function bodies.

**Pinned NetBSD framework reference:** NetBSD/src `03d918f6d0e81fa05b8f1160eca0628ad39988a6`. **Experimental implementation:** `src/rtwn8723be_linux_state.c` plus NetBSD-specific native callbacks, PCI DMA, IRQ, firmware-loader, RF, net80211 and runtime owner modules.

## Actual Linux-to-NetBSD ordered function mapping

| Phase | Frozen original Linux code | Experimental NetBSD equivalent | Evidence and closure |
|---|---|---|---|
| PCI probe/initial devices | `rtl_pci_probe`: pci_enable, 32-bit DMA mask, bus-master, softc/mac80211, BAR, adapter/EEPROM, software configuration, complete RX/TX ring allocation, stack registration | `rtwn8723be_linux_probe`: PCI_ENABLE → DMA_CONFIG → BUS_MASTER → SOFTC_ALLOC → BAR_MAP → PCI_D0 → ADAPTER_IDENTIFY → IO_INIT → EEPROM → SW_VARS → LEDS → ASPM_INIT → CORE_INIT → PCI_RINGS → IEEE80211_REGISTER → RFKILL → IRQ_ESTABLISH | Stage ordering source-checked. 50 C units exist; every defined callback (53/53) is bound. Native PCI probe not hardware-tested. |
| Adapter bring-up | `rtl_pci_start`: reset TRX ring → init BTC variables → `rtl8723be_hw_init` → retry limit → IRQ enable → RX configuration → `set_hal_start` | `rtwn8723be_linux_adapter_start`: reset TRX → BTC prepare → **reestablish masked PCI IRQ after NetBSD reset/drain** → hw_init → retry → IRQ enable → RX config → mark_hal_start → RUNNING | Original and port ordered-token sequences both checked. NetBSD extra IRQ step is a deliberate OS-specific requirement; not a Linux hardware-behavior change. |
| MAC/firmware/PHY | `rtl8723be_hw_init`: disable ASPM → CR check → DMA hang recovery/old MAC poweroff → MAC power-on → SYS_CFG bit7 clear → firmware download/ready → PHY MAC → RCR mask fix → PHY BB → PHY RF/channel → HW config → CAM/security/MAC address → ASPM restore → BTC HW init → calibration → NAV upper=235 → RX/PCIe DMA release → DM init | `rtwn8723be_linux_hw_init` follows those stages in the same dependency order, using NetBSD firmware/PCI DMA/MMIO/PHY callbacks with propagated error codes | Ordered-token comparison PASS. Firmware handshake, 1T1R RF path, RF IQK/LCK and register effects need real HP verification. Linux reads `rfreg_chnlval[1]` even though physical 8723BE path count can be 1: NetBSD explicitly avoids authorizing a nonexistent RF serial path. |
| TX/RX/802.11 framework | Linux `rtl_op_tx`, PCI `rtl_pci_tx`, descriptor/IRQ reclaim and mac80211; IEEE80211 TX/RX callbacks | NetBSD net80211 registration + frame processing, BE/MGNT separation, all-or-none multi-fragment DMA prepare/commit, RX/FCS, IRQ softint reclaim, STA-only software WPA2 crypto | 24 pre-existing Python-only tests PASS on SHA-verified Legion source; includes TX fragment model, RX management and EAPOL source guards. Native TX/RX/ACK and WPA2/air tests OPEN. NetBSD kernel net80211 ABI is not interchangeable with Linux mac80211. |
| Stop/recovery | `rtl_pci_stop`: BTC halt/deinit → HAL stop → IRQ mask → RF-change wait and ownership → hardware disable → ASPM restore | `rtwn8723be_linux_adapter_stop`, `runtime_shutdown`: same callback order, with NetBSD-specific drain of TX/softint/PCI DMA and ownership proofs before ring reset | Source sequence PASS. `rf_calibration` and `hw_disable` remain deliberately **guarded** pending native radio/poweroff proof. |
| Coexistence | `exhalbtc_init_hw_config` selects 1ant/2ant algorithm, `exhalbtc_init_coex_dm` initializes only after execution; provider callbacks also need C2H/firmware lifetime | NetBSD BTC engine/providers/MP notifications wired to runtime owner, RF 1T1R verified in source guards, events admitted after RUNNING | Algorithms and providers are SOURCE-present, but **BTC_FULL_PROVIDER_LIFETIME=OPEN**; native H2C/C2H/IRQ and teardown acceptance required. |

## Source-only tests actually executed

**Latest preceding source-test result:** 24 DISTINCT Python-only tests PASS at WIP `662adce3d47c64f7125a89f58d8286813d061f1b` in a temporary Legion fixture with every input Git blob verified. Evidence: `evidence/HP_RTL_PYTHON_SOURCE_GATES_20261017.json`.

**This audit:** `tests/test_port_closure_inventory.py` executed at WIP `e8d6a439af0c354565227d51ba7148a5ca4056b4` using 22 verified source files. Normal mode exit 0:
```text
DECLARED=53 BOUND=53 MISSING=0
PROBE= START= STOP=
NATIVE_C_OBJECTS=50
TX_POWER_PG_IN_NATIVE_BUILD=true
GUARDED_CALLBACKS_WITH_OPEN_OWNER=rf_calibration,hw_disable
BTC_ALGORITHMS_BUILT=1ant,2ant; BTC_FULL_PROVIDER_LIFETIME=OPEN
CALLBACK_AND_PG_CLOSURE=OPEN
```
Strict `--require-closure` correctly returned **exit 1** for still-guarded runtime functions. Do NOT force it green by deleting the guards; strict closure is an *operational readiness gate*, not a prerequisite for a safe kernel **link**.

**New source gate:** `tests/test_linux_netbsd_driver_order_source.py`, which enforces Linux-derived start, stop, probe and hw-init stage order together with NetBSD IRQ/drain and guard invariants. It ran on Legion at SHA `6e98dd0d7f04d49988b9609e039c6f0824f56513` and returned 0, including **10 deliberately injected negative mutations**. An initial test-only false negative on the PCI ring callback binding was fixed (commit `6e98dd0`).

**Manifest check:** exact GitHub WIP tree checked at SHA `6fab624ea9fdb739b6408c1e6d667fd32a2be629`: 50/50 `config/files.rtwn8723be_native` C source paths present, zero duplicates, zero missing units, and both new source tests present. All source-only preflight gates are selected by `tools/build_hp_rtl50_next_candidate.sh` (**30** test names total at that commit).

## Current native blockers — do not paper over them

1. **HP source not synchronized:** last observed clean HP WIP `531e1e09409bee6e6d03e9fa59ef07c0ff72b613`, historical F77 boot. The required HP source fast-forward was blocked by an external safety policy before execution, recorded in Governance `HP-RTL-WIP-FF-20261016.jsonl`. Do not retry the same effect using SSH pivots, other users/transports or script wrappers. Only a genuinely new authorized method can resolve this.
2. **NetBSD native tests NOT_RUN:** lifecycle C test attempted on Legion with incomplete temporary fixture (missing compatibility headers) and returned exit 1 *before successful compilation*; no HP build. Portable calibration and NetBSD-adapter calibration tests each invoke a C compiler and therefore remain queued for HP-only authorized native testing. No kernel build/link/boot performed for this HEAD.
3. **Hardware acceptance OPEN:** actual RF IQK/LCK, shutdown poweroff proof, BT 1/2-ant coexistence H2C/C2H lifetime, PCI DMA sync/IRQ races, management RX/TX, beacon reception, association/WPA2 EAPOL, DHCP/DNS, traffic, down/up, PM and panic recovery remain unobserved on HP.
4. **i915 is separate:** the safe RTL-only test kernel intentionally excludes `i915drmkms` and retains genfb to avoid confounding an unrelated graphics black-screen failure. This does not complete the separate i915 port.

## Three-stage remaining execution plan (hard gates, not a time guarantee)

**Stage 1 — source/evidence closure (this continuation):** collect actual Linux/NetBSD function order, run callback inventory and strict variant, add the sequence regression and immutable 50-unit Git-tree check; publish/update full evidence and governance. Result can be completed without HP access.

**Stage 2 — native-preflight readiness:** only on a *legitimately authorized* HP source state, verify exact WIP SHA, clean checkout, real active F77, fallback kernel, native `/root/netbsd-src-ref`, compiler version, space and both C-based calibration tests + lifecycle test. Re-run all 30 HP source gates, snapshot identity and dependency owner graph. Never use paid runners or build on Legion.

**Stage 3 — one HP-only full kernel link:** invoke the repo-provided `tools/build_hp_rtl50_next_candidate.sh` only after Stage 2 GO. Script creates an immutable snapshot, performs a single 50-C-unit NetBSD `dependall` and checks `netbsd` ELF, kernel identity `HP-RTL50-<SHA12>-SAFE-GENFB`, manifest/source SHA, `what` and sha256; it **must not** install, set the boot default, reboot or touch F77. Record actual build result and fix any new compiler/link error in a single coordinated pass.

If Stage 2 is denied by the previous external execution boundary, **Stage 3 cannot be honestly claimed** just because three user continuations elapsed. The strict runtime acceptance and later physical Wi-Fi testing remain separate from an ELF link.
