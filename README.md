# rtwn8723be-netbsd

**Project version: 0.1.0**

Experimental native NetBSD driver development for the Realtek RTL8723BE PCIe
WLAN adapter, based on the Linux `rtlwifi/rtl8723be` reference implementation.

## Versioning

- **0.1.x** — experimental development, hardware bring-up, diagnostics and
  driver construction.
- **1.0.0** — first functional software release proven on the target HP
  TPN-W121.

Version 1.0 is a hardware-proven target milestone, not a source/API milestone.

## Current state

Version **0.1.0** remains experimental. F77 is the verified HP recovery
kernel; it is not evidence that the current source tree is a working WLAN
driver.

The current private manifest selects 45 C units. The new conservative
world-regdomain unit represents Linux's safe baseline: channels 1–11 are
active CCK/OFDM, 12–13 are passive CCK/OFDM, and channel 14 is passive
CCK-only. EFUSE channel-plan mapping and the country-IE notifier are still
open. A small Net80211 rollback helper now permits an interface that was
registered but never started to unwind only the post-registration probe
stages; it does not bind PCI, DMA, IRQ, RFKill or net80211 to live hardware.

The first complete private HP kernel link has now succeeded for the 45-unit
Shadow E build at `f57eaea`: i915 was excluded, the original PCI source-tree
integrity check passed, all selected objects built, and the separate kernel
identifies as `RTWN8723BE-NATIVE-SHADOW`. Its SHA-256 is
`77be29c81d0f5a243f7c20cd54be857e46c323f6137ee6f46876d9826e6730f1`.
This was an isolated build only: no candidate was installed or booted, and it
does not establish a working WLAN driver. See [STATUS.md](STATUS.md) and the
[native object checkpoint](docs/HP_NATIVE_OBJECT_CHECKPOINT_20261011.md).

Complete native lifecycle ownership, callback binding, kernel link/install
and physical WLAN acceptance remain open. An object build or portable C test
is not a functional driver release. Packaging in `.tgz`, `.tbz` and `.txz`
formats begins only after hardware acceptance.

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

F77 remains the fallback kernel with `i915drmkms` disabled. The observed F83
and F84 screen failures (black panel with backlight after early boot text) do
not yet establish a root cause. No i915 candidate may be activated before a
physical early serial trace exists; never boot F16.0.

`/netbsd` is not replaced by this project. Experimental kernels, if ever
accepted for a test, use separate `/netbsd.rtwn8723be-*` names.
