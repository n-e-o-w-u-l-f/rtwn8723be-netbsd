# RTL8723BE PHY-PG Linux-to-NetBSD audit (2026-10-02)

Status: IN_PROGRESS / strict host-C compilation FAILED, correction BLOCKED by external tool check.
Full-scope coverage row: COV-RTL-007; no full-port, build, hardware or runtime parity claim.

## Exact references and published input

- Frozen Linux source: torvalds/linux `fd179f8a05be3ccae366b9b96e176b51fbe54aab`, `drivers/net/wireless/realtek/rtlwifi/rtl8723be/phy.c` and `reg.h`.
- NetBSD reference: NetBSD/src `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
- RTL repository base immediately before this module: `8aa0b625fdaa91ea922adc9ef6c737cc1e504150`; current PG implementation committed separately through `a8043bf4ac4f6a63781b81ed511fccb3cc8e4128`.
- Source: `src/rtwn8723be_txpwr_pg.h` (`daa649f`), `src/rtwn8723be_txpwr_pg.c` (`abcdd7c`), strict actual-body/link test `tests/test_txpwr_pg.py` (`a8043bf`). This code is **staging**: it is not wired to NetBSD hardware callbacks, lifecycle or build lists.

## Exact source semantics captured

- Linux `_rtl8723be_store_tx_power_by_rate()` stores the **entire** PG data word at `offset[band][path][txnum][rate_section]`, without applying the supplied register bitmask. Linux defines 2 bands, 4 RF paths, 4 TX indices and 12 sections. Its section mapping recognizes both A/B AGC register families, then the fallback `0xc20..0xc4c` / `0xe20..0xe4c` ranges.
- Pinned `RTL8723BEPHY_REG_ARRAY_PG` holds exactly six records, all for band 0, path A, RF_1TX: `0xe08/0x00003800`, `0x86c/0x32343600`, `0xe00/0x40424444`, `0xe04/0x28323638`, `0xe10/0x38404244`, `0xe14/0x26303436`. Existing `rtwn8723be_phy_run_pg()` iterates these records.
- `_rtl8723be_phy_store_txpower_by_rate_base()` extracts for RF paths A and B the 2.4-GHz CCK base from section 3 (path A highest byte, B lowest), OFDM from section 1 highest byte, MCS0–7 from section 5 highest byte, and MCS8–15 from RF_2TX section 7 highest byte; each source byte is decimal BCD.
- `_rtl8723be_phy_convert_txpower_dbm_to_relative_value()` converts **RF path A only**, using the **absolute difference** from the selected base, not a signed difference. The partial CCK conversion touches section 2 byte 1 and section 3 bytes 1–3; OFDM touches sections 0–1 bytes 0–3; MCS0–7 sections 4–5; RF_2TX MCS8–15 sections 6–7. RF path B retains its staged absolute data.

For the six pinned records, the expected path-A bases are CCK 32, OFDM 28 and MCS0–7 26; expected converted sections 0–5 are respectively `0x0c0e1010`, `0x0004080a`, `0x00000600`, `0x00020400`, `0x0c0e1012`, `0x0004080a`.

## Direct verification and current compiler blocker

The published header/implementation/test were fast-forwarded into Legion `/opt/ChatGPT/hp-driver-port/rtl8723be`; the worktree was clean at the last Git status check. The first strict test `python3 tests/test_txpwr_pg.py` **FAILED** at host-C compilation. GCC unambiguously reported that `NULL` is undeclared in `rtwn8723be_txpwr_pg_reset`, `_store` and `_convert` because `src/rtwn8723be_txpwr_pg.c` lacks `#include <stddef.h>`. No compiled test program ran; NONE of the numeric PG assertions have passed yet.

A targeted GitHub `update_file` of that source to insert `#include <stddef.h>` was rejected by external OpenAI tool safety checks before write. Subsequent readback confirmed the file blob `da0d2d530c858b4a7827191bd12153acadb94ce2` still lacks that include. Do not attempt another command, transport, host, or file-operation mechanism just to bypass this tool restriction. Resume the correction only when an ordinarily supported/permitted route is available; re-fetch the newest source SHA before editing. Rerun the *unmodified* strict test, inspect its exit code and correct any **new, evidenced** defect rather than claiming a pass now.

## Remaining dependency and integration gates

1. Repair the evidenced include defect and pass strict host-C tests using the real `src/rtwn8723be_txpwr_pg.c` and `rtwn8723be_phy_exec.c`, including path B preservation and all six Linux PG values. Re-evaluate unknown test expectations against Linux if a later assertion fails.
2. Compare the staged power-index representation with actual Linux EFUSE power/channel/group limits and NetBSD softc ownership. Connect BB/AGC and PG in the **exact reference order**, including `REG_SYS_FUNC_EN`, RF control, crystal-cap/BB setup, `phy_txpower_by_rate_config()`, AGC, then `cck_high_power`.
3. Port and independently test the Radio-A **serial RF** write path and its condition/delay tokens, using the exact EFUSE/board identity, only then wire `phy_bb_config` / `phy_rf_config`.
4. Add the new production translation unit to a reviewed NetBSD build recipe only after dependencies and adapter semantics are closed. Validate the NetBSD object and combined module, error paths, lifecycle and source closure. Update `docs/FULL_SCOPE_CONTRACT.md` when its denied write route is normally available. No HP runtime test before all parent gates close.

Safe state: no HP/boot/firmware change, no frozen reference alteration, no unverified replacement of F77; i915 generator/patch 0006 remains separately OUT_OF_SYNC with NetBSD compilation pending.
