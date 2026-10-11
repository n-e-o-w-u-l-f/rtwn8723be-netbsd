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

The current private manifest selects 46 C units. The conservative
world-regdomain unit represents Linux's safe baseline: channels 1–11 are
active CCK/OFDM, 12–13 are passive CCK/OFDM, and channel 14 is passive
CCK-only. EFUSE channel-plan mapping and the country-IE notifier are still
open. The 46th unit is an unbound, resource-journaled pre-`RUNNING` recovery
owner: it preflights compensators, masks and drains start-local IRQ work
before reverse cleanup, and quarantines any recovery failure. It does not
bind PCI, DMA, IRQ, RFKill or net80211 to live hardware.

The current 46-unit private Shadow G build has passed the full object and
kernel-link gate at source checkout `8a85ab31b6ff2c478efb79529bc7141a5c0cba99`:
i915 was absent from both generated inputs, all 46 selected objects are
nonempty, the original PCI source manifest stayed intact, and the separate
kernel identifies as `RTWN8723BE-NATIVE-SHADOW`. Its SHA-256 is
`e3ac1437d70a910ab41550292a6d6dbe78118a6d0d8fd595fa1a9e0a5b2adef6`.
This was an isolated build only: no candidate was installed or booted, and it
does not establish a working WLAN driver. See [STATUS.md](STATUS.md), the
[native object checkpoint](docs/HP_NATIVE_OBJECT_CHECKPOINT_20261011.md), and
the [Shadow G record](docs/HP_NATIVE_SHADOW_G_20261011.md).

Complete native lifecycle ownership, callback binding, PCI/IRQ admission and
physical WLAN acceptance remain open. An object build or portable C test is
not a functional driver release. Packaging in `.tgz`, `.tbz` and `.txz`
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
