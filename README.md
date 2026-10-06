# rtwn8723be-netbsd

**Project version: 0.1.0**

Experimental native NetBSD driver development for the Realtek RTL8723BE PCIe WLAN adapter, based on the Linux `rtlwifi/rtl8723be` reference implementation.

## Versioning

- **0.1.x** — experimental development, hardware bring-up, diagnostics and driver construction.
- **1.0.0** — first functional software release proven on the target HP TPN-W121.
- Version 1.0 is therefore a **functional target milestone**, not merely a source/API milestone.

## Current state

Version **0.1.0** remains experimental. The running HP recovery kernel is
**F77**; WLAN is still down and reports `no network`.

The separate native driver source now includes 36 C units. On 2026-10-06,
all 36 native objects and all 42 regression scripts passed on HP. The
firmware loader ports Linux fallback/version/polling behavior through the
NetBSD firmload API and passes 113 actual-C normal/UBSan scenarios.
The installed firmware images match the decompressed Arch Linux files.

Complete native BTC/lifecycle ownership, seven callback bindings, kernel
link/install and physical WLAN acceptance remain open. An object build is
not a functional release. See [the full-scope contract](docs/FULL_SCOPE_CONTRACT.md)
and [the firmware loading checkpoint](docs/FIRMWARE_LINUX_NETBSD_DIFFERENCES_20261006.md).

Earlier F8.x dry-run kernels and F6/F7 bring-up observations in
[STATUS.md](STATUS.md) are historical checkpoints.

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
