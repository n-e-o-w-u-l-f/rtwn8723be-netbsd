# FULL-SCOPE CONTRACT — Linux RTL8723BE -> NetBSD

Status: IN_PROGRESS

## OBJECTIVE
Port the complete pinned Linux RTL8723BE driver/firmware lifecycle to NetBSD for the HP target, preserving Linux hardware-visible PCIe power/reset, DMA/ring, firmware, MAC/BB/RF, IRQ, descriptor, H2C/C2H, coexistence, calibration, runtime-power, suspend/resume, and recovery behavior while adapting only the operating-system integration layer.

## REQUIRED_COVERAGE
All material RTL8723BE initialization, datapath, firmware protocol, runtime, power-management, and recovery phases. Existing firmware-header probes, F16.1 DMA code, interrupt work, and power-sequence code are partial inputs only.

## ACCEPTANCE_CRITERIA
Every required coverage row is CLOSED with Linux source/call-path evidence, NetBSD implementation evidence, correct phase ordering, error/unwind coverage, and integrated build evidence; the target attaches the RTL8723BE, loads/starts firmware, establishes interrupts and descriptor rings, exposes a working NetBSD WLAN interface, associates/transfers traffic reliably, and survives power/recovery paths without breaking the safe recovery kernel.

## EXPLICIT_EXCLUSIONS
No silent exclusions.

## SCOPE_CHANGE_AUTHORITY
none

## COVERAGE

| ID | Phase/component | Reference/spec evidence | Target implementation/adapter | Ordering/dependencies | Error/rollback/teardown | State | Verification |
|---|---|---|---|---|---|---|---|
| COV-RTL-000 | PCI/chip/efuse identification | pinned rtl8723be/hw.c physical EFUSE 0x1fb and rtlwifi/wifi.h package enum | NetBSD PCI attach + logical 256-byte EFUSE shadow; separately guarded raw physical 0x1fb read with power-on/read/power-off, source-pinned package decode, package-valid flag reset before each probe and set only after successful read | PCI BAR mapping, verified shadow/EEPROM ID, then physical package identity before conditional PHY/RF tables | read and power-off errors propagate without publishing validated package identity; native attach/unwind unverified | IN_PROGRESS | 2026-10-03 independent strict host-C11/UBSan compile and execution of byte-exact GitHub package.c/.h (blob dfda6921/11503f7b) PASS: all 256 input bytes, 256 complete on/read/off callbacks, four failure paths and three invalid-argument guards; newer NetBSD MMIO binding verified by source inspection only. Full board/cut/RF identity, native NetBSD object and physical HP hardware still OPEN |
| COV-RTL-001 | ASPM/power/reset/DMA-hang recovery | hw_init + rtl_hal_pwrseqcmdparsing + PCIe DMA reset | NetBSD PCI/PM + bus_space power-sequence executor | before MAC | rollback to powered-off/safe state | IN_PROGRESS | exact sequence audit |
| COV-RTL-002 | MMIO/register access | rtl_read/write helpers | bus_space adapter | after BAR mapping | unmap | OPEN | register access audit |
| COV-RTL-003 | DMA rings/LLT/descriptors allocation | LLT, rtlwifi PCI ring ownership | bus_dma rings preserving Linux descriptor layout/OWN semantics | before release/traffic | free/unmap/sync | IN_PROGRESS | descriptor/ring audit |
| COV-RTL-004 | Firmware file/header validation | frozen core.c primary/alternative selection, rtl8723com/fw_common.c masked 0x5300 header, 0x8000 whole-file limit | native firmload(9), firmware_malloc/free, close-before-upload, per-device version/name, bounded raw/header decoding with actual file extent | serialized sleepable FIRMWARE_DOWNLOAD owner; H2C initialized, IRQ disabled and valid mapped window | open/read/close/allocation/validation failures clear identity/H2C; invalid primary is not hidden by fallback | IN_PROGRESS | 2026-10-06 HP: 113 actual-C normal/UBSan scenarios, old-source semantic controls, all42 scripts/all36 native objects PASS; lifecycle/kernel/physical acceptance OPEN; docs/FIRMWARE_LINUX_NETBSD_DIFFERENCES_20261006.md |
| COV-RTL-005 | Firmware transfer/self-reset/ready | frozen rtl8723_download_fw/write_fw/free_to_go and efuse.c PCI byte writes | 4-byte zero padding, eight4096-byte pages, reset and exact checksum/readiness postincrement boundaries; positive NetBSD errno propagation | after MAC power and allowed init context, before BB/RF and command readiness | download-enable cleared; failed handshake cannot publish H2C/firmware identity; complete MAC/power rollback owner remains OPEN | IN_PROGRESS | 2026-10-06 HP:42 poll traces and32 upload/reset traces match frozen actual Linux bodies; invalid input guards and113 actual-C scenarios PASS; all42 scripts/all36 native objects PASS; kernel/hardware OPEN |
| COV-RTL-006 | MAC init/table | _rtl8723be_init_mac + phy_mac_config | exact source-pinned 103-entry MAC register table + 0x04ca post-write and RCR postprocess wired | after power, around firmware order per Linux | MAC reset | IN_PROGRESS | all 103 MAC table writes, final 0x04ca=0x0b and RCR mask/write isolated C tests passed; BB/RF/NetBSD integration pending |
| COV-RTL-007 | BB/RF configuration | frozen rtl8723be/phy.c, hw.c, rtl8723com/phy_common.c and table.c | Native phy_bb_config binds exact setup widths/order, 193 BB writes with delays, TX-power initialization/group reset, six PG entries and BCD/base/relative conversion, 131 AGC writes, CCK-high-power and crystal-cap RMW. Guarded phy_rf_config and RF-channel state callback bind portable RF serial/RFENV/Radio-A; both A/B RF_CHNLBW reads publish atomically. All three additional C modules are selected by the native manifest. | serialized init before IRQ/DMA; firmware and validated EFUSE/PHY/antenna/crystal identity required; BB validity required before RF; every BB/AGC register preflighted before setup MMIO | invalid preflight performs no MMIO; table errors propagate; crystal programming follows Linux even on table failure; RF snapshot fails without partial publication; RF/runtime locking and recovery remain open | IN_PROGRESS | 2026-10-05 HP/NetBSD: actual new callback C11/UBSan tests PASS after missing-symbol negative controls; all 32 published RTL scripts PASS; all 28 native C objects compile with real pinned NetBSD kernel headers and -Werror. No physical MMIO callback, kernel link, WLAN or whole-port acceptance is claimed |
| COV-RTL-008 | HW policy/configuration | frozen rtl8723be/hw.c:_rtl8723be_hw_configure | all 17 RRSR/ARFR/retry/TBTT/NAV/EDCA/aggregation policy writes ported exactly with width/order and wired; NAV=235 and retry-limit=7 callbacks also wired | after BB/RF and post-init | restore/reset | IN_PROGRESS | strict actual-body C mock verifies all 17 register addresses, values, widths and exact order plus NAV/retry; full NetBSD build, hardware and integration pending |
| COV-RTL-009 | Security/CAM/MAC address | rtl_cam_reset_all_entry() + HW_VAR_ETHER_ADDR + enable_hw_security | CAM reset writes 0xc0000000 to REG_CAMCMD; MAC identity writes all six EFUSE-derived bytes to REG_MACID; HW key/security and net80211 integration remain open | after HW config | CAM clear | IN_PROGRESS | strict isolated C tests pass for CAM command, byte order and EFUSE readiness; keys/kernel/hardware not tested |
| COV-RTL-010 | ASPM backdoor/BT coexistence | enable_aspm_back_door + bt_hw_init + frozen halbtc_send_bt_mp_operation | PCIe backdoor and per-device native MP mutex/CV request provider; real BTC DM/STA, 27 callbacks and antenna algorithms remain open | fresh MCU handshake, old RX/IRQ drain and real BTC activation owner required; activation/consumer binding remain unbound | copied reply, one request/device, timeout/send/no-wait quarantine, cancel/drain before H2C release | IN_PROGRESS | HP:42 actual-native-C modeled scenarios/537 checks normal+UBSan, two semantic controls, all43 scripts/all37 objects PASS; full BTC/runtime OPEN; docs/BTC_MP_NATIVE_NETBSD_20261006.md |
| COV-RTL-011 | IQK/LC/TX-power tracking/DM | PHY calibration + DM init | exact calibration/DM state | before final DMA release/normal runtime | calibration fallback | OPEN | calibration evidence |
| COV-RTL-012 | Final RX/PCIe DMA release | REG_RXDMA_CONTROL + REG_PCIE_CTRL_REG+1 | conditional RX-DMA clear followed by PCIe DMA release; callbacks wired | strictly after COV-RTL-001..011 as applicable | re-block DMA on failure | IN_PROGRESS | isolated C callback/order/register tests passed; prerequisites, error unwind and target verification pending |
| COV-RTL-013 | IRQ masks/handler | HIMR/HIMRE/HSIMR + recognized/enable/disable | PCI interrupt + exact masks | after rings/HW ready | mask/teardown | IN_PROGRESS | interrupt service evidence |
| COV-RTL-014 | TX/RX datapath descriptors | 64-byte TX PCI ring stride + 32-byte RX descriptor, frozen RTL8723BE old-TRX | Partial NetBSD mbuf/bus_dma RX/TX producers/consumers, descriptor encoders, typed RX/C2H callbacks, explicit RX DMA mapping/segment/span preflight; full net80211/IRQ/TX-report ownership and teardown absent | after valid rings/DMA and full IRQ/firmware prerequisites | reverse unmap/reclaim/queue stop and callback lifetime still OPEN | IN_PROGRESS | Direct production RX DMA guard source readback and isolated strict C11/UBSan 12 boundary assertions PASS; exact published test script, native NetBSD objects/link, traffic and HP runtime NOT RUN |
| COV-RTL-015 | H2C/C2H firmware protocol | frozen rtl8723be fw.c/mailboxes + halbtcoutsrc.c/rtl_btc.c | H2C0x67 copied wire submission and native per-device matched scalar reply/CV completion provider | armed before send, sleepable requests, SOFTINT_NET replies; full RX/BTC consumer owner remains open | decreasing200ms budget, conservative uncertainty quarantine, fresh MCU generation required after stop/timeout; no wire nonce | IN_PROGRESS | HP normal/UBSan actual-C races/errors, compiled semantic controls, native37 objects/all43 scripts PASS; physical protocol and full integration OPEN |
| COV-RTL-016 | Media/QoS/channel/beacon/runtime state | rtl_init_rx_config() + HAL/PHY/channel paths | cached RX configuration copied from PCI receive_config to MAC rx_conf; other net80211 state/QoS/channel work remains open | normal runtime | state rollback | IN_PROGRESS | actual-body isolated C test verifies preconditions and receive_config transfer; association/traffic pending |
| COV-RTL-017 | RF power/LPS/IPS/suspend/resume/recovery | Linux PM callbacks + reset paths | NetBSD MP stop provider cancels and drains both submission and wait; full RF/LPS/IPS/PM/recovery owner remains open | stop before H2C/DMA release; owner excludes new entrants, drains RX/IRQ and performs real MCU restart before activation | stop during send/wait proven with pthread model; real full lifecycle/rollback binding remains open | IN_PROGRESS | HP actual-C stop races and37 native object compilation PASS; whole recovery/PM and physical verification OPEN |

## CURRENT_DELTA
2026-10-06 native BTC MP checkpoint: the per-device mutex/CV provider now
arms before H2C0x67 submission, matches copied scalar replies, serializes
requests, preserves a decreasing200ms wait budget and cancels/drains an
in-flight send or waiter before resources are released. Timeout, uncertain
send and no-wait submission quarantine the channel; reactivation requires a
fresh MCU-ready generation plus an owner-proven RX/IRQ drain. Generation is
not a wire nonce and cannot identify a duplicate older same-opcode reply.
42 actual-native-C modeled scenarios/537 checks pass normal and UBSan;
two compiled semantic controls fail as expected. All43 regression scripts
and all37 fresh native objects pass on HP. MP storage init/probe-cleanup are
bound, while activation and C2H consumer binding remain deliberately unbound
pending the real full BTC/lifecycle owner. COV-RTL-010/015/017 remain
IN_PROGRESS. See [native MP implementation](BTC_MP_NATIVE_NETBSD_20261006.md)
and [exact evidence](evidence/HP_NATIVE_BTC_MP_20261006.json).

2026-10-06 firmware-load checkpoint: HP and Arch-Linux firmware bytes match.
The actual native loader now ports fallback, bounded header/raw extent,
per-device version identity, NetBSD firmload resource order, loading-context
preflight and exact frozen polling boundaries.113 actual-C normal/UBSan
scenarios and two old-source semantic controls PASS; all42 scripts and all36
fresh native objects PASS on HP. The initial native missing sys/cpu.h error
was corrected; failed reports remain retained. See
[firmware differences](FIRMWARE_LINUX_NETBSD_DIFFERENCES_20261006.md) and
[exact evidence](evidence/HP_NATIVE_FIRMWARE_LOAD_20261006.json).
No real BTC/initialization owner was invented or enabled. COV-RTL-004/005
remain IN_PROGRESS pending lifecycle/kernel/hardware acceptance.

2026-10-06 HP-only checkpoint: 46/53 lifecycle callbacks are bound; seven remain
missing and rf_calibration/hw_disable remain guarded by unassigned real owners.
The earlier wire-only checkpoint included 36 C units. The BT_MP wire module ports the
actual H2C0x67 byte encoding and C2H scalar decoding with precise per-sequence
bounds, unsigned32 wire shifts and copied values. It does not bind a native
BTC context or complete firmware transactions. The frozen unreachable opcode49
response case is preserved and documented in docs/BTC_MP_WIRE_SCOPE.md.

Earlier native security, ASPM backdoor, IQK/LCK/recovery, thermal tracking and
card-disable checkpoints are preserved. The full-scope controller still rejects
incomplete lifecycle transitions before hardware access. No coverage row is
CLOSED. Native object or portable protocol tests do not establish kernel link,
runtime ownership, physical MMIO, association/traffic or recovery acceptance.

## NEXT_UNRESOLVED
Implement register_ieee80211/init_rfkill; a real per-device BTC context, antenna
algorithms, activation/C2H binding of the tested native MP provider, full
H2C/C2H cache and consumer lifetime plus bt_prepare/
bt_hw_init/dm_init; and bt_halt_deinit/wait_rf_change_idle. Bind the two guarded
owners only with actual RF/DM/BTC/IRQ serialization and shutdown/drain evidence.
Complete net80211 channel/key/PM/datapath lifetimes, integrated kernel link and
HP association/traffic/recovery. Both complete ports and subsequent HP WLAN
online remain required. Build and install only on HP.

## Previous current projection (historical)
2026-10-05 HP-only checkpoint: 42/53 Linux lifecycle callbacks are bound and all 28 native RTL C units compile on HP against the complete NetBSD 03d918f6 source snapshot using the existing GCC 12.5.0 tools, an isolated source stage and object directory. The 32-script RTL regression batch passes on HP. New BB and RF-channel callbacks retain Linux ordering and failure handling; PG now uses the shared kernel/userspace compatibility header and is included in the native build. The earlier stale BB fixture, fixed Legion reference paths and NetBSD fake-errno recursion are repaired. These results supersede prior statements that PG, the matching BB regression or native compilation were blocked/unexecuted.

Full lifecycle closure remains OPEN: probe lacks register_ieee80211/init_rfkill; start lacks bt_prepare/enable_hw_security/enable_aspm_backdoor/bt_hw_init/rf_calibration/dm_init; stop lacks bt_halt_deinit/wait_rf_change_idle/hw_disable. The explicit --require-closure test returns 1 and the controller continues to reject incomplete transitions before hardware access. Kernel link, native runtime locking, key/channel/PM ownership, association/traffic/recovery and all hardware acceptance remain unresolved. No row is CLOSED.

### Previous next steps
Complete the eleven missing callbacks and their firmware/BT/calibration/net80211/runtime dependencies, then prove complete source/adapter ownership, integrated kernel link and HP-only runtime acceptance. The unpublished Legion cda48e5 runtime patch was inspected: several phases duplicate already published code; its DBI/MDIO timeout paths silently return zero and its RF-change wait lacks native locking. Preserve it as source history; do not blindly import it as completed behavior. See docs/HP_NATIVE_CHECKPOINT_20261005.md for source provenance, exact commands and artifact evidence.

## PARENT_STATUS
IN_PROGRESS

## 2026-10-03 COV-RTL-000/007 physical package identity gate

Read-only frozen-Linux `rtl8723be/hw.c` audit verified that package type is selected by a separately powered **raw physical** `efuse_one_byte_read(hw, 0x1FB, &value)`, with failed-read value 0 and low-three-bit package selectors 4/5/6/7. A logical decoded `sc_efuse_map[0x1fb]` lookup is NOT an equivalent adapter. Linux's `RT_CID_DEFAULT` + `EEPROM_CID_DEFAULT` HP OEM route requires parsed **EEPROM DID=0x8176, SVID=0x103C, SMID=0x1629**, not simply the HP laptop name or the recorded target PCI subsystem `103c:81c1`. See `docs/PHY_RF_REFERENCE_AND_DEPENDENCIES.md`, published as commit b6eae4e190b7cfd81e376b907051e9ea57385bed. **COV-RTL-000 and COV-RTL-007 remain OPEN/IN_PROGRESS respectively**: the native softc has no completed physical-package read or full validated PHY identity; do not wire Radio-A conditional execution or the HP-only RF register 0x52 special write before source-driven identity and powered RF mutex/MMIO prerequisites. This checkpoint changes the dependency specification only, not production source, native object, kernel, HP hardware or previously tool-denied edits.

## 2026-10-03 RF serial/path source-identical host-C regression re-run

Current canonical GitHub `main` before the rerun was `d79c157fc7600aa864fb9d79d6c16c95475c63cf`. Legion's local RTL checkout was clean at older HEAD `419866fcad5fb322ddd11dfbbcaa7873f91a91de`; however, individual **working-tree Git blob hashes exactly matched current GitHub** for `src/rtwn8723be_rf_serial.c/.h`, `src/rtwn8723be_rf_path.c/.h`, `src/rtwn8723be_phy_exec.c/.h`, `src/rtwn8723be_phy_tables.h`, and both actual regression files `tests/test_rf_serial.py` and `tests/test_rf_path.py`. No Git synchronization was performed. The original tests were executed separately on Legion with real host C compilation and mock device callbacks. `test_rf_serial.py` printed `RF_SERIAL_C_TESTS_OK` (A/B packing, HSSI read edge, PI/LSSI, 120-us wait, masked read-modify-write, Radio-A and failure guards), **exit 0**; `test_rf_path.py` printed `RF_PATH_C_TESTS_OK` (A/B RFENV setup, four 1-us waits, table callback and success/failure RFENV restoration), **exit 0**. Both process completion exit codes were independently read. This strengthens only COV-RTL-007's *standalone source-identical host-C regression evidence*; no native NetBSD object, hardware register access, fully resolved PHY identity, wired lifecycle, target Wi-Fi, i915 changes or full-scope completeness are claimed. The previously safety-denied unrelated RTL PG/BB-test/XTAL edits and i915 sync were not retried.

## 2026-10-03 COV-RTL-000 physical EFUSE package reader implementation

The frozen Linux reference `rtl8723be/hw.c:_rtl8723be_read_package_type()` reads the **raw physical EFUSE address 0x1fb**, separately powered, and decodes its low three bits. Frozen `rtlwifi/wifi.h` confirms Linux's numeric `enum package_type`: DEFAULT=0, QFN68=1, TFBGA90=2, TFBGA80=3, TFBGA79=4. This is different from decoded logical EFUSE shadow content; the old NetBSD low-level EFUSE reader limited every address to the normal 256-byte region and could not access 0x1fb.

**Actual new production implementation:** `src/rtwn8723be_package.h/.c` defines a source-pinned portable decoder, a separately powered physical read through callbacks, error propagation and mandatory power-off attempt on every post-power-on path (commits `be455a09d51afc595bd7a9204c259219e35b3c36` and `540a4c2b243b6a4717fdaa57ae9659be7c00159a`). `src/rtwn8723be_netbsd.h` retains `sc_package_type` and `sc_package_valid` (commit `424e4ace738060ae5cae171ac16501b93b285129`). `src/rtwn8723be_netbsd.c` now allows exactly one extra raw physical address (0x1fb) without expanding the 256-byte shadow traversal, maps the existing power and MMIO reader to the portable callbacks, and calls the decoder during EEPROM initialization after successful logical identity and BT parsing (commit `264233bea3f556df16dff2e2668a588f85461a36`). A follow-up `b79b3b44b1a40cbd31a4b6b3ec25773f29c235dd` invalidates the package identity **before all early failure paths** on re-probe. A failed physical read is intentionally returned as an error instead of accepting an unverified board identity; the output retains DEFAULT and the valid flag stays false. This stricter failure contract differs from Linux's silent DEFAULT fallback and requires eventual hardware verification.

**Actual verification performed:** The exact `src/rtwn8723be_package.c/.h` Git blob hashes `dfda692160073f47ee1d55cab6939cba4eeb1082` / `11503f7b49d57179e32cce509fc2c7a23a856c5d` match the independently compiled local C module byte-for-byte. Under `-std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=undefined -fno-sanitize-recover=all` an isolated standalone C harness using mocked callbacks passed all 256 physical byte values, 0x1fb read address, successful on/read/off order, failed power-on, failed physical read, failed power-off, simultaneous failures and invalid callbacks: `RTL_PACKAGE_C_TESTS_OK`, exit 0. Published `tests/test_package.py` reproduces the strict standalone C checks with frozen Linux source markers (commit `0cfc60341bac59cb6c8f42b410af6503811442bd`). Published `tests/test_package_adapter_source.py` inspects native integration shape/order (commits `c6cd0e0a636a7fd657f305e2480db8ed89cdf61c` and `1fa6273e22afcaab1fc920e64c5f0fbd0a0b0237`); this published Python runner and the native adapter have **not** been executed/compiled in a matching full NetBSD tree. Independently re-fetched all six actual current files and directly checked the raw-address exception, high address bits, old shadow bound, callback wiring, early invalidation and successful validation; all nine targeted source-contract predicates matched. This is verified partial production-source progress under COV-RTL-000/007, NOT full chip/PHY identity, object-link or target WLAN success.

**Still OPEN before RF table/hardware activation:** native file/object build including `rtwn8723be_package.c`, actual package-read register/power lifecycle and failure-injection on NetBSD, crystalcap EFUSE offset/fallback, cut/board/amplifier/RF-type validation, accurate HP OEM selection, RF lock, PHY table integration, complete full-scope contract validation, authenticated live HP kernel and on-device Wi-Fi. The previously safety-denied unrelated XTAL header/BB regression/PG missing include, remote Git sync and HP ping have not been retried or rerouted. No firmware or kernel was installed, no frozen NetBSD/Linux source was altered and the six-edit i915 overlay/F77 recovery remains untouched.

## 2026-10-03 COV-RTL-007 HP OEM branch substep

- **IMPLEMENTED (isolated portable source, not wired):** Linux-default-branch HP OEM recognition in `src/rtwn8723be_oem.h/.c`, commits `15bf0554cc8d689c112059b50f11507a6f45f157` and `754ad5c175c643c093c6ad02de97933180dba484`; original published regression `tests/test_oem.py`, commit `70c935dd960ec5c3bcfadce6ab184f2831ca42f3`.
- **ACTUALLY VERIFIED:** production C/header Git blob SHA `61053121f4409247fe916c3b7124c46e9ccec9d9`/`8ee15edb9415ebd19392425b12add8fc440f4cdd` byte-match independently compiled test inputs. Strict C11, warnings-as-errors and UBSan host test **PASS**, 196,608 exact 16-bit field comparisons plus missing/invalid/default/customer/PCI mismatch checks. The exact published Python test blob `7695d9fc71a3025f94926acdc2c2ac72904cccb1` was independently `py_compile`-checked and executed in a disposable container against byte-identical production C/header: PASS, exit 0. Its optional `--linux-tree` source assertion was not run; the corresponding frozen/stable Linux source branches were directly inspected separately. Frozen Linux and stable v7.2.8 have the same HP default-OEM branch.
- **STILL OPEN:** Linux's complete OEM classifier, the actual EEPROM customer ID (`0xc5`) and full validated PHY identity in NetBSD softc, wired RF-path selection and gated path-A `0x52` operation, power/locking/error lifetime, original previously denied PHY-PG/BB/XTAL changes, native kernel compilation and HP hardware tests. This helper MUST NOT independently authorize any RF write or close COV-RTL-007.
- **UPSTREAM/FIRMWARE TRACKING:** official stable Linux v7.2.8 (2026-09-25), linux-firmware release 20260916. Latest tag's `rtl8723befw_36.bin` bytes/hash not yet verified. Newer `rtw88` RTL8723B v41.0.0 firmware is specific to the RTL8723BS SDIO path, not proof of RTL8723BE PCIe compatibility. Frozen Linux pin and F77 remain unchanged; see `docs/PHY_RF_REFERENCE_AND_DEPENDENCIES.md`.

## 2026-10-03 COV-RTL-003/014 RX DMA span hardening

Published production RX guard commits a7b04d7/e0e25d0 and regression commits f31d5ce/6b40726 establish descriptor-ring capacity and per-slot loaded DMA map, segment and full 9,100-byte 32-bit address span preflight BEFORE per-slot bus_dma synchronization. Exact GitHub source/test blob readback passed; an independently compiled isolated C11/UBSan copy of the actual guard logic passed 12 boundary assertions. The published Python test itself, native NetBSD build, integrated DMA/IRQ and physical HP runtime were NOT executed. This corrects the table's previously stale 40-byte TX descriptor claim: the implemented PCI TX ring stride is 64 bytes. Both COV-RTL-003 and COV-RTL-014 remain IN_PROGRESS, not CLOSED. See docs/RX_DMA_BOUNDS_20261003.md. No recovery kernel or i915 overlay was changed.

## 2026-10-03 COV-RTL-003/014 RX DMA follow-up

Commit `10a4b95542a85def53699a6ee94e7d3087ca6c5d` corrected the isolated RX-DMA test's missing 64-bit host `bus_addr_t` declaration. A local standalone strict C11/UBSan guard reproduction now compiles and passes 13/13 cases; the exact published Python test has **not** run. The unchanged production receive routine still lacks the actual loaded descriptor-map size/segment checks before descriptor DMA synchronization and loses the previously accumulated `delivered` count on a later fatal ring/slot `EIO`. A targeted production-source edit was externally denied; its source blob remained `1a449bf9b3071ff0e2ea430dc2d9fa6451025026` on readback, and no equivalent-tool retry occurred. Resolve through an actual permission change, then native-function fault injection and NetBSD compilation. Both coverage rows remain IN_PROGRESS. Detailed verified handoff: `docs/RX_DMA_BOUNDS_20261003.md`.

## 2026-10-04 COV-RTL-003 DMA allocation failure unwind

Source `src/rtwn8723be_f16_1_dma.c` commit `8a57336` now gates DMA post-synchronization and unload on nonzero `dm_mapsize` (NetBSD bus_dma invalid-map contract) while independently freeing allocated KVA, memory segments and map handle on a failed `bus_dmamap_load()`. Production source SHA `f712c89a438e903ccea8f79786b78e945d865e43` was read back. New real-function extraction regression `tests/test_dma_mem_unwind.py` commit `ef69c29` covers six cleanup branches; an isolated C11/UBSan reproduction of the current function passed all six with exit 0. `.github/workflows/portable-c-regressions.yml` commit `01eb121` wires that published test and the RX bounds test to CI on relevant changes. The exact Python/Actions job has not yet been confirmed executed, and native NetBSD object/link, hardware and full ownership tests are still OPEN. This is COV-RTL-003 partial progress, not FULL/PARITY or COV-RTL-014 closure. See `docs/DMA_UNWIND_20261004.md`.

## 2026-10-04 COV-RTL-000/007 guarded native RF6052 integration

Actual NetBSD `bus_space` RF adapter `src/rtwn8723be_rf_native.c/.h` is committed and registered in `config/files.rtwn8723be_native` and `rtwn8723be_netbsd_ops.phy_rf_config` (commits `c6452b2`, `8fffd03`, compiler repair `d68fa3c`, `b3b44b5`, `5630a33`, `993430f`). The existing Linux-pinned `rf_serial.c`, `rf_path.c` and conditional Radio-A `phy_exec.c` are reused; 4-byte MMIO bounds, posted writes, 1/2-path sequencing and pre-IRQ initialization checks are in the native adapter. The physical PHY identity and RF path count are **invalid by default**, rather than guessed from PCI ID: actual cut/board/PA/LNA/RF parsing and RF locking remain parent dependencies. Other missing callbacks (notably `phy_bb_config`) still fail the Linux lifecycle preflight before unsafe hardware initialization.

The **exact published** `tests/test_rf_native_adapter.py` (Git blob `e12e54593b2ac34ef7973bb1d212716e78c85f18`) and current adapter source (blob `4c6c2c85281174c95769fa4b7cca4f3b480bf8f4`) were hash-matched on Spinnennet; the strict C11/`-Werror`/UBSan compiled production adapter mock test passed exit 0 after same-step correction of callback constness and the host-only RCSID macro. `.github/workflows/portable-c-regressions.yml` commit `76cf361` includes this test, but hosted CI startup remains independently unverified. See `docs/RF_NATIVE_20261004.md` for complete provenance and rollback boundaries.

An isolated Legion NetBSD build worktree at `/opt/ChatGPT/hp-driver-port/netbsd-build-20261004` was created at frozen commit `03d918f6d0e81fa05b8f1160eca0628ad39988a6`; the original clean sparse reference and six-edit i915 overlay remain unchanged. At last observation full-source restoration (191,063 entries) was IN_PROGRESS under PID 2048889 with durable `.status` and `.materialize.log` alongside the build worktree. Do not claim full source/toolchain/native object/kernel readiness until current status and exit evidence are checked. COV-RTL-000 and 007 remain IN_PROGRESS/OPEN; none of the full-port, HP WLAN or i915 gates are closed.
