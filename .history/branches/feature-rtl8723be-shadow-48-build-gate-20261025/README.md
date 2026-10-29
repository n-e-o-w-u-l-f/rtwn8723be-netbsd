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

The current private manifest selects 48 C units. The conservative
world-regdomain unit represents Linux's safe baseline: channels 1–11 are
active CCK/OFDM, 12–13 are passive CCK/OFDM, and channel 14 is passive
CCK-only. EFUSE channel-plan mapping and the country-IE notifier are still
open. The 46th unit is an unbound, resource-journaled pre-`RUNNING` recovery
owner. The 47th is a unit-tested, unbound port of the Linux BTC high-level
`get`/`set` policy; it does not supply the missing whole-driver lifecycle
owner or activate PCI, DMA, IRQ, RFKill, or net80211 hardware. The 48th is a
pure, atomic BTC context-preparation boundary: it accepts a fully parsed board
identity, maps the raw RTL8723BE antenna encoding, applies the Linux-shaped
BTC defaults, invokes low-level then policy callback binders in a temporary
context, and publishes only after the existing callback gate and invariants
succeed. It does not bind `bt_prepare`, PCI, DMA, IRQ, RFKill, net80211,
workqueues, or native hardware state.

Shadow H is the exact historical 47-unit private build at source checkout
`66fed5c6e732a373e4faa16f96b5742725c99d3b`; it does **not** cover the current
48th context unit. Its private configuration explicitly contains
`no i915drmkms*`; the private PCI manifest and rendered Makefile contain no
i915 input. All 47 selected objects are nonempty, the original PCI source
manifest stayed intact, and the separate kernel identifies as
`RTWN8723BE-NATIVE-SHADOW`. Its SHA-256 is
`390a3905b41463dee6b0395138ed406dee37051d6506a696c8f764fb0024ac38`.
The 48-unit source selection requires its own isolated private object and
kernel-link gate before any later runtime work. No candidate from this state
was installed or booted, and no i915 action occurred. See [STATUS.md](STATUS.md),
the [native object checkpoint](docs/HP_NATIVE_OBJECT_CHECKPOINT_20261011.md),
and the [Shadow H record](docs/HP_NATIVE_SHADOW_H_20261011.md). Shadow G
remains the retained historical 46-unit build record.

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
