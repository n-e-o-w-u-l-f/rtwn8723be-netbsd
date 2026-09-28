# LAST_TASKS

## 2026-09-29 — F77 Linux-tail parity

- **STATE:** IN_PROGRESS
- **OBJECTIVE:** Advance the proven HP TPN-W121 RTL8723BE F77 state to the remaining Linux hardware-init tail without regressing firmware download or scan.
- **CURRENT:** Live target runs `RTWN8723BE-F77-LINUX-EFUSE-MAP`. Firmware/scan work; RX completion remains the blocking path. The public repository is older than the live F77 source, so it must not be treated as the authoritative implementation tree.
- **NEXT:** Validate the exact Linux tail ordering against the real F77 source, then port one bounded F79 stage: BT/antenna status → IQK → TX-power tracking → LCK → NAV_UPPER → RX DMA release → PCIe TX/RX DMA release → DM init.
- **PLANNED_FILES:** `tests/test-f79-linux-tail-order.sh`, `docs/F79-LINUX-TAIL.md`, `STATUS.md`.
- **BLOCKERS:** Remote security filter currently blocks the SSH write/build path to HPTWN121. Do not fabricate F77 source from the stale public repo.
- **DO_NOT_REPEAT:** Do not replace the proven F77 recovery kernel; do not mix the i915 test patch into the WLAN test kernel; do not reorder the Linux tail without evidence.
