# RTL8723BE PHY/RF reference reconstruction and integration prerequisites

Status: RESEARCHED / implementation dependencies OPEN; this file documents an evidence-backed future step, NOT an implemented RF driver or a passed NetBSD build.
Coverage: COV-RTL-007 and dependent COV-RTL-000/001/005/006/010/011/012/016/017. Research performed 2026-10-02.

## Authoritative references

Frozen Linux `torvalds/linux fd179f8a05be3ccae366b9b96e176b51fbe54aab`, under `drivers/net/wireless/realtek/rtlwifi/`:
- `rtl8723be/phy.c`: `rtl8723be_phy_bb_config()` (approximately lines 92-123), `_rtl8723be_phy_bb8723b_config_parafile()` (approximately 488-535), `rtl8723be_phy_rf_config()` (around 126), `_rtl8723be_config_rf_reg()` (around 215-225) and `rtl8723be_phy_config_rf_with_headerfile()` (around 743-768).
- `rtl8723be/rf.c`: `rtl8723be_phy_rf6052_config()` and `_rtl8723be_phy_rf6052_config_parafile()` (around 400-488).
- `rtl8723com/phy_common.c`: `rtl8723_phy_rf_serial_read/write()` (around 54-126) and `rtl8723_phy_init_bb_rf_reg_def()` (around 152-237).
- `rtl8723be/hw.c`: EFUSE crystal-cap reading/fallback (around 2080-2082) and exact OEM identity selection (around 2125-2200).
- `rtl8723be/reg.h`: canonical numeric register and bit masks; frozen `rtl8723be/table.c` Radio-A table.

Target NetBSD reference `03d918f6d0e81fa05b8f1160eca0628ad39988a6`; canonical RTL repository `n-e-o-w-u-l-f/rtwn8723be-netbsd`, stage `1368416d8346b8500dd399ed170e9e369ceb6fbb` at audit start.

## Dependency-ordered Linux hardware state machine

1. Confirm PCI/efuse identity, RF type and `RT_CANNOT_IO`/mapped-and-powered state. Linux derives `crystalcap` from EFUSE byte `EEPROM_XTAL_8723BE=0xB9`, substituting `0x20` for erased `0xff`; PHY ID also depends on actual cut/package, board type and GLNA/GPA/ALNA/APA configuration. A product name or assumed HP brand is NOT an identity substitute.
2. `rtl8723be_phy_bb_config` initializes the complete A/B `phyreg_def` register mapping, enables `REG_SYS_FUNC_EN`/RF/BB, updates register `0x4c` BIT(23), writes `REG_AFE_XTAL_CTRL+1=0x80), runs the BB table, initializes TX power-by-rate state, conditionally imports PG when EFUSE autoload succeeded, converts PG base/relative values, runs AGC, reads `cck_high_power`, and finally sets `REG_MAC_PHY_CTRL` mask `0xFFF000` from `crystalcap & 0x3f` duplicated into two fields. The existing NetBSD standalone BB/AGC writers and PHY-PG model are *not* a replacement for this complete ordered operation.
3. `rtl8723be_phy_rf6052_config` sets `num_total_rfpath` from the actual `rf_type`: one path for RF_1T1R, otherwise two. Each active path saves `rfintfs` RFENV, enables `rfintfe` (upper RFENV) and `rfintfo` (lower RFENV), with 1-us delays; clears `B3WIREADDREAALENGTH=0x400` and `B3WIREDATALENGTH=0x800` on `rfhssi_para2`, each followed by 1 us. It then invokes path-specific radio configuration and restores the saved RFENV **even if the radio table handler reported failure**. The target port needs the equivalent restore/unwind.
4. Path A uses the source-pinned 136-pair Radio-A table, with the Linux IF/ELSEIF/ELSE/ENDIF interpreter and actual EFUSE-derived conditions. The `0xfe` and `0xffe` radio table tokens mean a **50-ms delay without an RF write**. Other pairs go through the RF serial writer followed by 1 us. The Linux path B/C case of `rtl8723be_phy_config_rf_with_headerfile` does not run another Radio-A table; do not invent a path-B table. The path-B RFENV setup/restore in step 3 still applies when selected.
5. A special post-table path-A RF register `0x52=0x7e4bd` occurs *only if the parsed RTL OEM ID equals `RT_CID_819X_HP`*. Linux's observed mapping from the `EEPROM_CID_DEFAULT` branch to that ID requires **EEPROM DID 0x8176 and subsystem 103c:1629**, rather than an arbitrary HP brand. The historically registered target PCI subsystem is `103c:81c1`, which does not match this mapping; do not apply the RF 0x52 write merely because the laptop is HP. Verify actual EFUSE identity and any other applicable OEM-ID route before deciding that branch.

## Exact RF serial adapter semantics

- `rtl8723_phy_rf_serial_write()`: guard I/O readiness, mask register address to 8 bits, pack `((address & 0xff) << 20) | (data & 0xfffff)` (bounded to 28 bits), then write the full word to the path's `rf3wire_offset` via a full-mask BB write. A: `RFPGA0_XA_LSSIPARAMETER=0x840`; B: `RFPGA0_XB_LSSIPARAMETER=0x844`. The surrounding `rtl8723be_phy_set_rf_reg()` serializes updates with `rf_lock` and performs masked read-modify-write when the mask is not `RFREG_OFFSET_MASK`.
- `rtl8723_phy_rf_serial_read()`: guard I/O readiness, mask address to 8 bits, update `BLSSIREADADDRESS=0x7f800000` and toggle `BLSSIREADEDGE=0x80000000` on A `RFPGA0_XA_HSSIPARAMETER2=0x824` and path-specific HSSI2 (B `0x82c`); wait 120 us; read `BLSSIREADBACKDATA=0xfffff` from LSSI (`0x8a0` A, `0x8a4` B) or PI readback (`0x8b8` A, `0x8bc` B) depending on HSSI1 BIT(8). NetBSD must map its bus_space barriers, readback/poll timing and synchronization to these semantics, not trial-and-error registers.
- These numeric addresses and masks come from frozen `rtl8723be/reg.h`, not assumed from another Realtek generation. Validate under the actual power/BB/PCI MMIO state. Linux's `RT_CANNOT_IO` and `rf_lock` require explicit target-state and locking/lifetime translations.

## Target implementation gaps (direct source inspection)

- `src/rtwn8723be_netbsd.c` already provides bus_space MMIO primitives and `rtwn8723be_netbsd_get_bbreg/set_bbreg`; its standalone `phy_bb_write/phy_agc_write` callbacks check that the device is mapped before using those lower-level primitives; `src/rtwn8723be_phy_exec.c` supports the pinned conditional Radio-A traversal.
- Current `rtwn8723be_softc` holds EFUSE map and selected BT antenna flags, but no separate validated `crystalcap`, full PHY-table identity, `phyreg_def`/RF serial BB address descriptors or dedicated RF lock. Their source-derived initialization and teardown must precede safe table execution.
- `src/rtwn8723be_txpwr_pg.c` is a **staged** pure TX-power transform and is still compiler-BLOCKED by missing `<stddef.h>`; previous direct GitHub update to repair that exact file was rejected. Its host numeric tests have NOT passed and it is not wired. Do not bypass the rejection through another tool/host. `docs/PHY_PG_PORT_AUDIT.md` records the precise failure and repair requirement.
- A correct Linux-shaped `phy_bb_config`/ `phy_rf_config` NetBSD callback and native object/kernel compilation are still OPEN; no hardware-ready claim. The two pinned NetBSD source copies on Legion share HEAD `03d918...` but contain sparse `sys/` materialization; `sys/sys/types.h` exists in Git HEAD blob `1093b9d63e7a2af2f44a1872deb31c7baf678b9c` yet is absent on disk. The official NetBSD build guide requires matching materialized sources and toolchain before an AMD64 `build.sh` kernel build. Earlier attempted NetBSD build command was independently blocked by the tool safety layer; this file is not permission to reroute it.

## Next evidence gates

1. Repair the existing PG `<stddef.h>` defect **only when its ordinary authorized edit route is available**, then run the original strict host-C test and independently audit numeric results before declaring PG-tested.
2. Verify EFUSE crystal-cap, RF type, board/cut/package/amplifier identity and OEM conditions against exact frozen `hw.c/phy.c`, mapping all required state to NetBSD softc. Prove the NetBSD reader actually fills it and handles erased or invalid data.
3. Add isolated source-based tests for RF serial pack/read-edge/120-us/PI-vs-LSSI, RF path enable/restore on success/failure, delay tokens, conditional Radio-A table dispatch and exact OEM 0x52 gate, before wiring and hardware access.
4. Implement in the Linux source-defined order, with NetBSD mutex/bus_space and failure rollback. Compile/link in a separate complete, pin-matched NetBSD tree with verified toolchain after ordinary build-route permission; keep recovery F77 untouched and failed F82 excluded.
5. Update the stale `COV-RTL-007` contract only via permitted reviewed write and advance full-scope gates on actual compiler/integration/HP evidence.
