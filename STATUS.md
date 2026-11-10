# RTL8723BE NetBSD project status

Current checkpoint: 2026-11-10 Europe/Paris. PROJECT_ID: HP-RTL8723BE.
Parent driver port: **PARTIAL**. Corrected BTC/DM source/test/native-link and
independent evidence gates: **PASS**. Private kernel: **BUILT_NOT_TESTREADY**.
Hardware acceptance: **NOT_RUN / OPEN**.


## Genuine BTC preparation, full DM and native provider ownership

The current manifest selects 49 native C units and all 54 lifecycle callback
slots are bound. Genuine `bt_prepare` builds the parsed-board BTC context,
binds low-level and policy callbacks, and creates the actual native BTC owner.
The full DM initializer runs through the real native lease at its Linux-order
checkpoint. The seven required policy ports are copied once; the source does
not invent their genuine suppliers. The structural early gate still returns
ENOSYS before PCI/MMIO when required suppliers are absent.

Accepted synchronous and copied BTC work retain permanent admission tokens.
STOP returns EBUSY before destructive effects while such work or provider I/O
is live. Adaptive I/O acquisition reserves its owner before waiting, drops
Giant, claims the actual RF-change flag, and restores the exact Giant depth
after release. The first I/O/provider error suppresses later actions and
keeps its original error; external fault notification occurs once. Release
snapshots the native child's recorded `last_error`, preserving an observed
ENOBUFS even when the individual callback returns EINVAL or succeeds. The
caller's return is unchanged. This does not make the broker context an atomic
mirror of asynchronous faults arriving after that snapshot. Normal
STOP/restart preserves policy's 8-second aggregation history and warm DM/
thermal history; failed owners remain retained for recovery.

On the HP, 56 distinct regression scripts have PASS evidence: 53 were freshly
executed, while three pure context/policy/DM results were carried only after
their consumed inputs were verified unchanged. The actual provider integration
ran 12 logical cases in normal and NDEBUG builds (24 executions) and rejected
22 compiled, executed behavioral mutants. The pure DM oracle covered 768
vectors and rejected 12 executed mutants. Preserved owner/IRQ 18+13 and TX/
crypto 13+11 mutation controls passed again; 17 source controls are separate
static checks. No compile failure was counted as a behavioral mutation kill.

The tested 1016-file source map and all 33 implementation changes match the
physical source. Fresh dependency/object targets for all 49 native units passed
against the actual installed NetBSD 11 headers and tools; 119 selected project
inputs were captured. Each test batch kept its inputs unchanged; the validated
production and fixture identities match the corrected native gate inputs.

The final native job recompiled one runtime object and proved the remaining
48 byte-identical to the independently verified initial fresh 49-unit build.
It completed the 49-object relocatable link, dependency generation and full
private kernel relink. Independent verification passed all 4675 checks:
49 native units, 336 RTL globals, zero final undefined symbols, 115 staged
project dependencies and all 119 declared production inputs. The old archive
retains all 1585 files byte-exact; the nine original protected paths and new
kernel/map pair remained unchanged during verification.

Current corrected private kernel: 27,295,696 bytes; SHA-256
da4f6c19ef35c369ca977467426a8194b7d8cdca0bed03bdf9ee5c36a5b5a802.
Map: 12,479,929 bytes; SHA-256
5095dbfa020bc1bc26e95a576923a9f04e6360650534bba44c06a3a4972e74c0.
Final source-map SHA-256: 6ed170156fc04d868b6457b5da4d920a085f962d94cfa0a6e4a4850000dcc075.
Final independent receipt SHA-256:
22e32985120612ce6442c83cbd7c0794b05c5b3fa9939db4fa07b676a2aa9f4e.
The candidate is BUILT_NOT_TESTREADY, uninstalled and unbooted. The initial
49-unit kernel/map and their old-input proof are preserved as qualified
intermediate evidence; their hashes do not identify this corrected candidate.

[Current implementation and evidence limits](docs/BT_DM_PROVIDER_OWNERSHIP_20261110.md).
[Current machine-readable receipt](docs/evidence/BT_DM_PROVIDER_OWNERSHIP_20261110.json).


## Historical registration and native start/stop checkpoint

The real register_ieee80211 callback is bound. It publishes actual net80211,
RX binding and datapath ownership in order, with reverse failure compensation.
Native START/STOP use the real Linux lifecycle controller, short operation
claims and checked provider admission. STOP masks and retires IRQ work, drops
Giant across the actual SOFTNET cross-call barrier, then verifies the drain
before RF/hardware shutdown. IRQ/backing ownership survives for restart;
checked finalization refuses live or inconsistent owners.

At this historical checkpoint the table was 52/54 bound and genuine
bt_prepare/dm_init remained open. The current 49-unit checkpoint above closes
those two bindings. Genuine C2H TX/RA and RF/calibration/runtime suppliers
remain open, and absent suppliers still reject admission before PCI/MMIO.

On HP, 33 distinct regression scripts passed. The new compiled fixtures reject
18 runtime-owner and 13 IRQ/drain mutants by executed assertions; preserved
TX-consumer13/crypto11 mutant regressions also pass. All 48 native units compile,
and the full private kernel retains all 327 selected RTL global definitions
with zero final undefined symbols. Independent ELF, selected-source, dependency,
symbol and protected-input checks PASS. Each test batch kept its inputs unchanged; validated production and fixture
inputs match the final build. Target ABI/link proof and modeled concurrency checks do
not establish physical NetBSD SMP or WLAN behavior.

Historical registration private kernel: 27,292,816 bytes; SHA-256
d7760c619e828ea93701d22a9f20c380cb8206221ee97f128554c3487f614948.
Map: 12,483,060 bytes; SHA-256
f76543e91d026f86e2eeb783dc2d40d50683f9bf858e95ce9d3934515245a145.
This candidate remains BUILT_NOT_TESTREADY, uninstalled and unbooted.
F77 /netbsd, /boot.cfg, installed files.pci and both prior private kernel/map
pairs retain their exact hashes.

[Implementation and evidence limits](docs/NET80211_REGISTER_OWNER_20261110.md).
[Machine-readable receipt](docs/evidence/NET80211_REGISTER_OWNER_20261110.json).

## Native net80211 TX consumer

The native management/data queue consumer was introduced in the prior
48-unit selection and is preserved in the current 49-unit selection. A NULL TX method selects it; genuine hw_start and
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

## Previous TX consumer evidence

Previous TX source base: 54450113dc39567e2d81ba9e766edbed338620a9 plus the bounded TX patch.
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

Previous TX private kernel: 27,291,824 bytes; SHA-256
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
governance. NEXT: supply the genuine coherent snapshot and OS action ports,
C2H TX/RA, calibration and hardware-disable owners; establish real MP transport
activation; then close pre-RUNNING recovery and complete running-driver
detach/lifecycle ownership before separately authorized physical network
acceptance. Bound BTC/DM callbacks alone do not satisfy these provider gates.

The current TX parser intentionally rejects null-data/control/WDS/fragmented/
HT-control formats. Physical WLAN/WPA2, watchdog/recovery and PM acceptance
remain OPEN. Source publication and both canonical host receipts are maintained
separately in project governance.

Actual target headers identify NetBSD 11.0. Historical upstream reference
03d918f6d0e81fa05b8f1160eca0628ad39988a6 remains UNVERIFIED against the installed
tree, which has no Git metadata. Explicit pre-build project/protected anchors
qualify historical identity; other OS/tool hashes are endpoint observations.

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
