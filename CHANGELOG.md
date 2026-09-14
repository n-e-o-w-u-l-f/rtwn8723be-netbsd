# Changelog

## 0.1.0 — 2026-09-14

Initial documented development release.

- RTL8723BE PCI identification
- Read-only PCI configuration inspection
- MMIO BAR mapping
- One proven-safe MMIO read at `0x00f0`
- Deferred firmware access and firmware-format validation
- Linux RTL8723BE power-sequence analysis
- Source-only PCI power-sequence table and dry-run
- F1–F8.3 hardware bring-up history documented
- F6 retained as the last boot-proven-safe hardware-access kernel
- F7/F7a black-screen failures preserved as diagnostic evidence
- Production `/netbsd` remains untouched

## 1.0.0 — planned

Version 1.0.0 will be declared only after the driver/software is **functionally working on the target HP TPN-W121**.

The exact 1.0 acceptance criteria will be established during development and will include real target-device operation rather than merely successful compilation or source completeness.
