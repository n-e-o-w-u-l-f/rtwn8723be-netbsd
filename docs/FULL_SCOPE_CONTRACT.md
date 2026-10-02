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
| COV-RTL-000 | PCI/chip/efuse identification | rtl8723be PCI + chip/EEPROM paths | NetBSD PCI attach + ROM/efuse adapter | first | detach | OPEN | chip/ROM evidence |
| COV-RTL-001 | ASPM/power/reset/DMA-hang recovery | hw_init + rtl_hal_pwrseqcmdparsing + PCIe DMA reset | NetBSD PCI/PM + bus_space power-sequence executor | before MAC | rollback to powered-off/safe state | IN_PROGRESS | exact sequence audit |
| COV-RTL-002 | MMIO/register access | rtl_read/write helpers | bus_space adapter | after BAR mapping | unmap | OPEN | register access audit |
| COV-RTL-003 | DMA rings/LLT/descriptors allocation | LLT, rtlwifi PCI ring ownership | bus_dma rings preserving Linux descriptor layout/OWN semantics | before release/traffic | free/unmap/sync | IN_PROGRESS | descriptor/ring audit |
| COV-RTL-004 | Firmware file/header validation | rtl8723befw_36.bin, 0x5300 signature | firmware(9) loading/header validation | before transfer | close/reject invalid image | IN_PROGRESS | signature/size evidence |
| COV-RTL-005 | Firmware transfer/self-reset/ready | rtl8723_download_fw, rtl8723_write_fw, rtl8723_fw_free_to_go | page upload, self-reset, checksum, MCUFWDL_RDY/WINTINI_RDY | after MAC power, before BB/RF | disable/reset on failure | IN_PROGRESS | source implemented from pinned Linux; isolated -Wall/-Wextra/-Werror syntax/type check passed; NetBSD integration build and hardware-ready evidence pending |
| COV-RTL-006 | MAC init/table | _rtl8723be_init_mac + phy_mac_config | exact source-pinned 103-entry MAC register table + 0x04ca post-write and RCR postprocess wired | after power, around firmware order per Linux | MAC reset | IN_PROGRESS | all 103 MAC table writes, final 0x04ca=0x0b and RCR mask/write isolated C tests passed; BB/RF/NetBSD integration pending |
| COV-RTL-007 | BB/RF configuration | rtl8723be_phy_bb_config/phy_rf_config and rtl8723com/phy_common.c plus frozen rtl8723be/table.c | all 193 BB, 131 AGC, six PHY-PG and 136 Radio-A entries imported byte-identically; Linux conditional interpreter, standalone NetBSD BB/AGC hardware-writer bodies, portable A/B 8-bit-address/20-bit-data RF serial and RF6052 RFENV setup/restore are implemented and independently host-C tested. PHY-PG BCD/base/relative conversion is staged but **compiler-blocked** by a missing `<stddef.h>` correction whose previous repository update was externally denied. PHY identity (actual EFUSE/board/cut/package/RF type and OEM gate), bus_space-to-RF-serial adapter, RF mutex, powered-device lifetime, BB/RF state-machine callbacks and native build remain OPEN | after firmware/MAC and validated EFUSE/power state; BB->optional PG (if autoload valid)->AGC->crystal-cap, then RFENV/HSSI/Radio-A per selected path | RFENV restore on success and error host-C verified; actual RF lock/error recovery and kernel teardown unverified | IN_PROGRESS | 2026-10-02 actual Legion host tests: test_phy_tables.py (pinned byte match), test_phy_exec.py, test_phy_netbsd_writers.py, test_rf_serial.py, test_rf_path.py all PASS in their isolated/mock scope. This is NOT complete Linux PHY integration, native NetBSD object/kernel or physical WLAN proof |
| COV-RTL-008 | HW policy/configuration | frozen rtl8723be/hw.c:_rtl8723be_hw_configure | all 17 RRSR/ARFR/retry/TBTT/NAV/EDCA/aggregation policy writes ported exactly with width/order and wired; NAV=235 and retry-limit=7 callbacks also wired | after BB/RF and post-init | restore/reset | IN_PROGRESS | strict actual-body C mock verifies all 17 register addresses, values, widths and exact order plus NAV/retry; full NetBSD build, hardware and integration pending |
| COV-RTL-009 | Security/CAM/MAC address | rtl_cam_reset_all_entry() + HW_VAR_ETHER_ADDR + enable_hw_security | CAM reset writes 0xc0000000 to REG_CAMCMD; MAC identity writes all six EFUSE-derived bytes to REG_MACID; HW key/security and net80211 integration remain open | after HW config | CAM clear | IN_PROGRESS | strict isolated C tests pass for CAM command, byte order and EFUSE readiness; keys/kernel/hardware not tested |
| COV-RTL-010 | ASPM backdoor/BT coexistence | enable_aspm_back_door + bt_hw_init | PCIe/BT coexist adapter | after core HW config | coexist teardown | OPEN | coexist/state audit |
| COV-RTL-011 | IQK/LC/TX-power tracking/DM | PHY calibration + DM init | exact calibration/DM state | before final DMA release/normal runtime | calibration fallback | OPEN | calibration evidence |
| COV-RTL-012 | Final RX/PCIe DMA release | REG_RXDMA_CONTROL + REG_PCIE_CTRL_REG+1 | conditional RX-DMA clear followed by PCIe DMA release; callbacks wired | strictly after COV-RTL-001..011 as applicable | re-block DMA on failure | IN_PROGRESS | isolated C callback/order/register tests passed; prerequisites, error unwind and target verification pending |
| COV-RTL-013 | IRQ masks/handler | HIMR/HIMRE/HSIMR + recognized/enable/disable | PCI interrupt + exact masks | after rings/HW ready | mask/teardown | IN_PROGRESS | interrupt service evidence |
| COV-RTL-014 | TX/RX datapath descriptors | 40-byte TX + 32-byte RX query/fill | NetBSD mbuf/bus_dma adapter preserving layout/OWN | after DMA+IRQ | reclaim/unmap | OPEN | packet TX/RX evidence |
| COV-RTL-015 | H2C/C2H firmware protocol | rtl8723be fw.c/mailboxes | firmware command/event adapter | after firmware ready | mailbox reset | OPEN | command/event evidence |
| COV-RTL-016 | Media/QoS/channel/beacon/runtime state | rtl_init_rx_config() + HAL/PHY/channel paths | cached RX configuration copied from PCI receive_config to MAC rx_conf; other net80211 state/QoS/channel work remains open | normal runtime | state rollback | IN_PROGRESS | actual-body isolated C test verifies preconditions and receive_config transfer; association/traffic pending |
| COV-RTL-017 | RF power/LPS/IPS/suspend/resume/recovery | Linux PM callbacks + reset paths | NetBSD PM lifecycle + recovery ordering | runtime/final | full reinit/teardown | OPEN | PM/recovery verification |

## CURRENT_DELTA
Ten reference-derived lifecycle callbacks are implemented/wired and isolated C-tested: complete 103-entry MAC table with final 0x04ca write, RCR fixup, CAM reset, six-byte EFUSE MAC programming, MAC RX configuration cache, all 17 HW policy writes, NAV upper, conditional RX DMA release, PCIe DMA release, and default retry-limit programming. Full initialization still preflights as incomplete: 16 of 53 Linux lifecycle callbacks are absent from rtwn8723be_netbsd_ops. BB/AGC writer bodies, the portable RF serial protocol and per-path RFENV/HSSI protocol already pass isolated strict C tests; they are **not yet connected to a native NetBSD PHY/RF lifecycle callback**. Next verify actual EFUSE/board/cut/package/RF identity, source-derived crystal-cap/OEM gate, RF mutex and powered bus_space lifetime; then connect the adapter in Linux dependency order. Restore the staged PG module's missing `<stddef.h>` only through a permitted regular repository edit (previous direct repair denied), and run its original numeric test before integrating PG. net80211 registration, BT coexistence, calibration/DM, TX/RX, recovery and teardown remain open. Validate NetBSD integration, full dependency closure and runtime only after required gates; isolated C tests are not hardware verification.

## NEXT_UNRESOLVED
All COV-RTL-000 through COV-RTL-017 remain unresolved; COV-RTL-001, COV-RTL-003, COV-RTL-004, COV-RTL-005, COV-RTL-006, COV-RTL-007, COV-RTL-008, COV-RTL-009, COV-RTL-012, COV-RTL-013, and COV-RTL-016 are currently IN_PROGRESS. The partial callback verification is recorded in tests/test_late_hw_callbacks.py (ten functions, strict host C compilation; MAC table verified byte-identical to generated pinned reference); PHY/AGC/PHY-PG/Radio-A frozen tables are also imported and independently byte-tested in tests/test_phy_tables.py; Linux condition/traversal interpreter is tested in tests/test_phy_exec.py; actual BB/AGC NetBSD callback bodies pass tests/test_phy_netbsd_writers.py, and standalone RF serial/RFENV protocols pass tests/test_rf_serial.py and tests/test_rf_path.py. PG numeric tests remain blocked; actual EFUSE-selected radio branches, RF lock/bus_space integration, PHY/RF lifecycle callbacks and native NetBSD/hardware proof are absent. No row has been prematurely CLOSED.

## PARENT_STATUS
IN_PROGRESS
