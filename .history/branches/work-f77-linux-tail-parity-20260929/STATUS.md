# RTWN8723BE NetBSD project status

**Project version:** 0.1.0  
**Status date:** 2026-09-14  
**Current stage:** F8.3 source-only dry-run  
**Last boot-proven-safe kernel:** F6 #6  
**Production `/netbsd`:** untouched

## Version policy

- **0.1.x:** experimental development and target hardware bring-up.
- **1.0.0:** first functional software release proven on the target HP TPN-W121.
- Version 1.0 is reached only when the resulting software is demonstrably functional on the target device, not merely when the source code is complete.

## Hardware

- HP TPN-W121
- NetBSD 11.0 amd64
- Intel Celeron N3060 / Braswell
- Realtek RTL8723BE PCIe WLAN
- PCI vendor/device: `10ec:b723`
- Subsystem: `103c:81c1`
- PCI location: `pci2 dev 0 function 0`
- PCI command observed: `0x0003` — I/O and memory enabled, bus mastering disabled
- BAR at `0x18`: 64-bit non-prefetchable MMIO, base `0x91200000`, size `0x4000`

## Firmware validation

Firmware filename: `rtl8723befw_36.bin`

Verified previously on the target:

- size: 31762 bytes
- header: 32 bytes
- payload: 31730 bytes
- signature: `0x5301`, accepted by Linux RTL8723BE signature mask `0x5300`
- version: `36.0`
- date bytes: `06-24 16:28`
- `svnidx`: `0xcccccccc`
- payload size equals header `ramcodesize`

The firmware binary is not committed to this repository. The project records its validated metadata and expects the firmware to be supplied through the NetBSD firmware mechanism.

## Development stages

### F1 — initial firmware access

Initial firmware access was too early during PCI attach. NetBSD `config_mountroot()` was identified as the correct mechanism for deferred firmware access.

### F2 — deferred firmware access

Firmware opening/reading was moved to a `config_mountroot()` callback. This remained hardware-passive.

### F3 — passive firmware validation

The firmware header and payload size are validated without PCI command changes, MMIO, DMA, interrupts, or firmware download.

### F4 — PCI configuration snapshot

A single read-only PCI configuration snapshot was added. Verified on target:

`command=0x0003`, I/O on, memory on, bus mastering off.

### F5 — MMIO BAR mapping

BAR `0x18` is mapped using NetBSD PCI mapping APIs. No register access was performed in F5.

F5 source SHA256:

`11b5c25bfa5ef1dc5adcab5380077830798b441d4b735b717d6a13683653a8ba`

F5 kernel SHA256:

`da0067f2083b564fd09d3a6e88d139f8e731ff79540afa3148795a65be263deb`

F5 was boot-tested successfully.

### F6 — single known-good MMIO read

F6 added exactly one read-only MMIO access at `0x00f0` (`REG_SYS_CFG`).

Observed value:

`0x05454139`

F6 kernel SHA256:

`a8be5ff9521c2f3251284f9ad1d83aa7240b0c7910de9831440982b4b2131356`

F6 was boot-tested successfully. This is the last proven-safe hardware-access kernel.

### F7 — multi-register read

F7 added reads at `0x00f0`, `0x00f4`, `0x00f8`, and `0x00fc`.

F7 caused a black screen during boot. The kernel is preserved as failure evidence.

F7 kernel SHA256:

`6b48a7a02f66eb8d14757cbcd2e71b46eae6cc9bad21314fabec9b1d3e2754a5`

### F7a — isolated `0x00f4` read

F7a isolated only the additional read at `0x00f4`. This also caused a black screen.

Important semantic correction: Linux `rtl8723be/reg.h` identifies `0x00f4` as `REG_GPIO_OUTSTS`, not `SYS_STATUS1`.

F7a kernel SHA256:

`cb0372b6f48d9c966716c6f0ddda72b5d15baf1316ad88356a6c5ac3455dbcf9`

Do not repeat F7/F7a or blindly probe `0x00f8`/`0x00fc`.

### F8 — source-only Linux power-sequence mapping

Linux `rtlwifi/rtl8723be` source research established the PCI power-sequence model and register map. No hardware access was added.

Relevant map includes:

- `0x00e4` `REG_PCIE_MIO_INTF`
- `0x00e8` `REG_PCIE_MIO_INTD`
- `0x00ec` `REG_HPON_FSM`
- `0x00f0` `REG_SYS_CFG`
- `0x00f4` `REG_GPIO_OUTSTS`
- `0x00f8` `REG_MAC_PHY_CTRL_NORMAL`
- `0x00fc` `REG_SYS_CFG1`
- `0x0100` `REG_CR`
- `0x0301` PCIe DMA control
- `0x0361` PCIe RPWM

Linux `_rtl8723be_init_mac()` invokes `RTL8723_NIC_ENABLE_FLOW` for the PCI interface. That flow is `CARDDIS_TO_CARDEMU + CARDEMU_TO_ACT + END`.

### F8.1 / F8.2 — source-only power-sequence table

`src/rtwn8723be_pwrseq_plan.h` models Linux `wlan_pwr_cfg` fields:

`offset / cut_mask / fab_mask / interface_mask / base / command / mask / value`

The documented `CARDEMU_TO_ACT` sequence is retained with Linux interface filtering. The source declares 23 steps but the currently visible macro body contains 21 explicit entries; no missing entries were invented.

### F8.3 — source-only dry-run

`rtwn8723be_pwrseq_dryrun()` enumerates only PCI-interface `CARDEMU_TO_ACT` steps and logs the selected/skipped entries. It performs no MMIO, PCI configuration writes, DMA, IRQ setup, delays, polling, or firmware download.

F8.3 source SHA256:

`rtwn8723be.c` — `1bdaddf7df7b5ae661bab1b01210c04521c3642bbf301369eeee5e2742706e53`

`rtwn8723be_pwrseq_plan.h` — `0d024902ab692dea89a4a0abd3a29f1e39f5710fb72d533247ddd02bcfb2351c`

F8.3 kernel SHA256:

`4baeb67564f0e912249c9673f84e1f06ca041e033332ffc5fd1dcccce380e678`

F8.3 was built successfully but **not boot-tested**.

## Safety constraints

1. Never overwrite production `/netbsd` during experimental work.
2. Experimental boots use `userconf disable i915drmkms*` on this target.
3. F6 is the safe hardware-access fallback.
4. Do not repeat F7/F7a and do not perform blind MMIO probing.
5. Do not enable PCI bus mastering, DMA, interrupts, firmware download, or power-sequence execution without a reviewed transition plan.
6. Port Linux RTL8723BE semantics exactly where possible; do not substitute unrelated Realtek sequences.
7. Record every actual change, test, verification, failure, decision, and blocker in `/root/LAST_TASKS` on the development machine.
