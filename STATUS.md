# RTL8723BE NetBSD project status

Current checkpoint: 2026-11-10 Europe/Paris. PROJECT_ID: HP-RTL8723BE.
Parent driver port: **PARTIAL**. Private kernel state: **BUILT_NOT_TESTREADY**.

## Verified source and native build

Tested production source: d96edb70d9c0e5332f69ba8eb286fb86481e6370.
Later checkpoint changes are documentation-only.

- Two missing net/if_media.h dependencies repaired in the native DMA/TX units.
- All 48 native RTL objects and three focused DMA/TX regressions PASS on HP.
- Private 48-object relocatable link and complete native kernel link PASS.
- Independent generated selection/symbol checks: 48 RTL units, all 318 global
  RTL symbols including rtwn8723be_native_ca, zero undefined kernel symbols.
- i915 is excluded from this private GENERIC-derived RTL configuration.
- F77 /netbsd, /boot.cfg and installed PCI source hashes remain unchanged.

Private amd64 ELF: 27,291,000 bytes.
SHA-256: 21dccebbbbd92cc1fa185522489a766e515f1e8a062ed6aa99b2645a907ef4ca.

[Full kernel gate, commands, hashes and limits](docs/HP_NATIVE_KERNEL_GATE_20261109.md).
[Machine-readable kernel receipt](docs/evidence/HP_NATIVE_KERNEL_GATE_20261109.json).
[Original native header repair](docs/HP_NATIVE_HEADER_GATE_20261109.md).

## OPEN and NEXT

NEXT: real net80211 TX queue consumer with explicit management/data mbuf and
node ownership, software-CCMP preparation, rate/queue policy, ring-full pending
ownership, completion wakeup and the existing STOP lifetime lease.
The actual NetBSD crypto API can replace/free its local mbuf head without
returning an updated head; ownership must be proved before binding.
register_ieee80211, bt_prepare and dm_init remain open.

Actual target headers identify NetBSD 11.0. The historical upstream reference
03d918f6d0e81fa05b8f1160eca0628ad39988a6 is UNVERIFIED against the installed
tree, which has no Git metadata. Exact observed hashes are in the receipt.

Installation, candidate boot, physical RX/scan, association, WPA2 traffic,
DMA/IRQ/STOP races and PM acceptance: NOT_RUN / OPEN.

## Safety and retention

Native kernel builds are HP-only. Legion is source/reference staging.
Preserve F77, /netbsd, /boot.cfg, EFI and current radio/network state.
Experimental boot requires independently verified console and F77/stock
physical recovery. This private ELF is uninstalled and not TESTREADY.
Before future builds use fresh private output, or first verify/preserve the
current ELF and link-map backups. Earlier denied effects, including RX0086,
remain binding and must not be retried or rerouted.

Only verified normal source fast-forwards are used; old/divergent worktrees
remain preserved. Historical Legion cda48e5 is retained on
codex/archive-legion-runtime-cda48e5-20261109.

## Complete historical status

The full pre-compaction status is preserved byte-exact in the parent history:
[STATUS at ccb336ab](https://github.com/n-e-o-w-u-l-f/rtwn8723be-netbsd/blob/ccb336ab0a1b7cb8e300391e38aebe4a60aa333d/STATUS.md).

Original Git blob: dcff75ff9870b2f7a8bacee16f56b206424594b6.
Original SHA-256: 3b9cae3e1c6800d778b9f4c21d27e64cc487a4abc9f8e628a921a22849dfa7aa.
Original UTF-8 length: 64,647 bytes. Earlier entries are historical evidence;
the current native result and open acceptance above govern continuation.
