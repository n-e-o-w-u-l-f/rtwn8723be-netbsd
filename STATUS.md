# RTL8723BE NetBSD project status

Current checkpoint: 2026-11-10 Europe/Paris. PROJECT_ID: HP-RTL8723BE.
Parent driver port: **PARTIAL**. Current TX source/link gate: **PASS**.
Private kernel: **BUILT_NOT_TESTREADY**. Hardware acceptance: **NOT_RUN / OPEN**.

## Native net80211 TX consumer

The native management/data queue consumer is implemented in the existing
48-unit source selection. A NULL TX method selects it; genuine hw_start and
hw_stop methods remain mandatory. No missing Linux probe callback is replaced
with a successful stub.

- Management frames precede fresh Ethernet dequeue. Each dequeued frame and
  referenced net80211 node has one explicit CPU or DMA owner.
- Ethernet encapsulation and real NetBSD software-CCMP API preparation precede
  contiguous DMA submission. Reserved headroom avoids the target crypto API's
  pointer-by-value mbuf relocation hazard. Missing privacy keys never permit
  ordinary data to fall back silently to plaintext.
- Ring-full retains an already prepared frame/node pair. Completion wakes it
  without repeating encapsulation or consuming another CCMP packet number.
- Wrapped real key-update hooks and saved channel/BSS/security context reject
  stale pending ciphertext, including same-slot key replacement.
- Negotiated/fixed legacy rates, RTS threshold including FCS, and ERP CTS/RTS
  policy are checked immediately before DMA handoff.
- Existing TX-start/completion leases exclude destructive STOP. Failed STOP
  preserves pending ownership; proven quiescent STOP permits its release.

[Implementation, evidence boundaries and exact production hashes](docs/NET80211_TX_CONSUMER_20261110.md).

## Current evidence

Source base: 54450113dc39567e2d81ba9e766edbed338620a9 plus the bounded TX patch.
The publication contains the identical production file hashes recorded in the
[TX receipt](docs/evidence/NET80211_TX_CONSUMER_20261110.json); no circular
self-commit identifier substitutes for that tested-source identity.

On hp-tpnw121.lan / actual NetBSD 11 headers and tools:

- 24/24 focused regression scripts PASS on unchanged source/test inputs.
- The new fixtures execute production consumer, STOP and completion functions,
  and the exact installed NetBSD crypto API body. All 13 consumer and 11 crypto
  behavioral mutations were rejected. AES itself is a boundary mock.
- Fresh private configuration selected all 48 native C units, generated all
  dependency targets and compiled all 48 nonempty native objects successfully.
- The matching new full private kernel link and independent selection/symbol
  proof PASS: 48 RTL units, all 321 RTL global definitions, all three new TX
  exports and the RTL attachment, with zero final undefined symbols.
- The candidate defines the actual NetBSD ieee80211_crypto_encap implementation;
  the native TX object references that API. All 113 staged project dependencies
  match the stable source inputs. No i915 configuration, object or linked symbol
  is present.
- F77 /netbsd, /boot.cfg and all five protected input/artifact hashes remain
  unchanged in the independent terminal kernel receipt.

Current private kernel: 27,291,824 bytes; SHA-256
fc31520e392e615e0c546e4605f07548d42c4c628d3daccebf4da4d19912c5d7.
Map: 12,476,831 bytes; SHA-256
a7fe973fd9540d3b23fa6cbbbede7426f7bc77943eb1be1ec47051d34b05a9fb.
The candidate is uninstalled and was not booted.

Ten initial private mutation-test core artifacts were preserved with hashes;
the runner was corrected to disable core dumps. They are not source-publication
artifacts and do not constitute a hardware or native-kernel crash.

The new crypto fixtures require the inspected NetBSD target source tree;
they are not self-contained Ubuntu CI tests. The hosted workflow is unchanged,
and this checkpoint claims no hosted CI result.

## Earlier accepted native kernel gate

Production source d96edb70d9c0e5332f69ba8eb286fb86481e6370 passed the prior
48-object, relocatable-subset and complete private kernel-link gate. Independent
selection/symbol checks found 48 RTL units and all 318 then-existing global RTL
symbols, including rtwn8723be_native_ca; the final kernel had zero undefined
symbols and excluded i915.

That earlier private amd64 ELF is 27,291,000 bytes.
SHA-256: 21dccebbbbd92cc1fa185522489a766e515f1e8a062ed6aa99b2645a907ef4ca.

[Prior kernel gate, commands, hashes and limits](docs/HP_NATIVE_KERNEL_GATE_20261109.md).
[Prior machine-readable kernel receipt](docs/evidence/HP_NATIVE_KERNEL_GATE_20261109.json).
[Original native header repair](docs/HP_NATIVE_HEADER_GATE_20261109.md).

## OPEN and NEXT

Source publication and host-ref convergence are recorded separately in project
governance. NEXT: close the remaining genuine register_ieee80211, bt_prepare and
dm_init callbacks and their native lifecycle owners without enabling an
unverified hardware path.

register_ieee80211, bt_prepare and dm_init remain open. Native hardware
start/stop ownership, watchdog/recovery and physical network acceptance remain
separate whole-driver obligations. The current TX parser intentionally rejects
null-data/control/WDS/fragmented/HT-control formats; this checkpoint does not
claim those transmit formats or a functional WLAN release.

Actual target headers identify NetBSD 11.0. Historical upstream reference
03d918f6d0e81fa05b8f1160eca0628ad39988a6 remains UNVERIFIED against the installed
tree, which has no Git metadata. Exact observed source hashes govern evidence.

Installation, candidate boot, physical RX/scan, association, WPA2 traffic,
DMA/IRQ/STOP races and PM acceptance: NOT_RUN / OPEN.

## Safety and retention

Native kernel builds are HP-only. Legion is source/reference staging.
Preserve F77, /netbsd, /boot.cfg, EFI and current radio/network state.
Experimental boot requires independently verified console and F77/stock
physical recovery. Private build artifacts remain uninstalled and not TESTREADY.
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
the current source-specific gates and open acceptance above govern continuation.
