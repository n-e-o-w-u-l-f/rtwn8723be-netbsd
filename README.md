# rtwn8723be-netbsd

**Project version: 0.1.0**

Experimental native NetBSD driver development for the Realtek RTL8723BE PCIe WLAN adapter, based on the Linux `rtlwifi/rtl8723be` reference implementation.

## Versioning

- **0.1.x** — experimental development, hardware bring-up, diagnostics and driver construction.
- **1.0.0** — first functional software release proven on the target HP TPN-W121.
- Version 1.0 is therefore a **functional target milestone**, not merely a source/API milestone.

## Current state

The project is currently at **F8.3** and version **0.1.0**. The driver can safely identify the PCI device, inspect PCI configuration, map the existing MMIO BAR, perform one proven-safe MMIO read at `0x00f0`, defer and validate firmware access after mountroot, and perform a source-only PCI power-sequence dry-run.

No WLAN interface is functional yet. No power sequence has been executed against the hardware. No DMA, interrupt setup, bus mastering, firmware download, or production-kernel replacement has been performed.

The last boot-proven-safe experimental kernel is **F6 #6**. F7/F7a are preserved as failure evidence because additional MMIO reads caused a black screen on the target machine.

## Target hardware

- HP TPN-W121
- NetBSD 11.0 amd64
- Intel Celeron N3060 / Braswell
- Realtek RTL8723BE PCIe WLAN
- PCI ID: `10ec:b723`
- Subsystem: `103c:81c1`
- PCI location: `pci2 dev 0 function 0`
- MMIO BAR: `0x18`, 64-bit, base `0x91200000`, size `0x4000`

## Safety boundary

Experimental kernels are booted with `userconf disable i915drmkms*` because the integrated Intel graphics driver causes a black screen on this machine.

`/netbsd` production kernel is not replaced by this project. Experimental kernels are installed under separate `/netbsd.rtwn8723be-*` names.

See [`STATUS.md`](STATUS.md) for the complete verified state and test history.
