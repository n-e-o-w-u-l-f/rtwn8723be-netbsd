# RTL8723BE independent validation checkpoint — 2026-10-04

Status: SOURCE-BODY-COMPARED / ISOLATED-HOST-TEST-PASS / NATIVE-NETBSD-OPEN / HP-OPEN
Canonical RTL main before inspection: `27889cc6b18868bd46df10c8ecd50efb5ea7c70c`.
The verified older clean Legion checkout was `419866fcad5fb322ddd11dfbbcaa7873f91a91de` at `/opt/ChatGPT/hp-driver-port/rtl8723be`; it was NOT updated or promoted over GitHub. Target HP RDC remains offline. Historical i915/F77 artifacts untouched.

## Source identity checks

The actual local test blobs byte-match GitHub `main`:
- `tests/test_late_hw_callbacks.py`: `aa2e074eb1bf759732b341ea84be7973e5ce4307`
- `tests/test_phy_exec.py`: `353962f25dcb2b82e77a116d1745dfa846ad2e8f`
- `tests/test_phy_netbsd_writers.py`: `e03aa4280fa81c3332083700487394e53d46032f`
- `tests/test_phy_tables.py`: `7ae4a63596438b99afd5bbf10cc61e2996e277f1`

Local and current production `src/rtwn8723be_netbsd.c` **whole-file blobs differ** (`d94669c9a69918fc5d164c2ef3b2abbbc1768aa5` vs `afa0900c39730587c58615a9ed829bf6e8ddd987`). However, bounded read-only extraction from both GitHub revisions established **exactly identical 12 tested C function bodies**: `phy_mac_config`, `rcr_postprocess`, `cam_reset_all`, `set_mac_address`, `init_rx_config`, `hw_configure`, `set_nav_upper_235`, `release_rx_dma`, `release_pcie_dma`, `set_retry_limit`, `phy_bb_write`, `phy_agc_write` (all with the `rtwn8723be_netbsd_` prefix). The portable `phy_exec.c/.h` and PHY tables header match `main` by Git blob SHA. This establishes source identity **only for the specified test inputs and bodies**, not for the complete newer native driver.

## Tests actually executed on Legion

Each original local Python regression ran as a separate `python3 tests/<name>` command, and each returned explicit process exit code 0:
- `test_late_hw_callbacks.py`: `CALLBACK_TESTS_OK: MAC RCR CAM MACADDR RXCONFIG HW17 NAV RXDMA PCIE RETRY`.
- `test_phy_exec.py`: `PHY_INTERPRETER_C_TESTS_OK: BB193 AGC131 PG6 RF conditional branches and error paths`.
- `test_phy_netbsd_writers.py`: `PHY_NETBSD_WRITERS_C_TESTS_OK: BB6 delays, BB write+1us, AGC no delay, NULL/unmapped`.
- `test_phy_tables.py`: `PHY_TABLE_C_TESTS_OK: 193 BB 131 AGC 6 PG 136 RF; 16 RF conditions` and `PHY_TABLE_BYTE_MATCH_OK`, with the pinned Linux `fd179f8a05be3ccae366b9b96e176b51fbe54aab` reference.

## Coverage and remaining blockers

This strengthens the **isolated-host** evidence for PHY/RF table interpretation, native callback bodies, and late hardware callbacks under COV-RTL-007 and relevant initialization rows. It does not close any full-scope row: the current full `netbsd.c` differs outside these checked bodies, PHY/PG/board identity and lifecycle wiring remain incomplete, and the native NetBSD object/link/kernel build and physical HP WLAN/IRQ/DMA tests are absent. Previously safety-denied PHY-PG/BB/XTAL and RX error-path source edits were not retried or routed through local Git. The `LAST_TASKS.md` update remains independently blocked/out of sync; this is a subordinate project-local checkpoint, not a claim that central LAST has been changed.
