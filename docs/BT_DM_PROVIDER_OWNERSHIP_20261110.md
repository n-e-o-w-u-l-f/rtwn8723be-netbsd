# Genuine BTC preparation, full DM and native provider ownership

Project: HP-RTL8723BE / rtwn8723be0-netbsd. Date: 2026-11-10.
Version remains **0.1.0**. Parent driver port: **PARTIAL**.
Corrected source/tests, native kernel/link and independent evidence gates: **PASS**.
Physical hardware acceptance: **NOT_RUN / OPEN**.

## Source identity and scope

The implementation is based on source parent
`3d9c371488e5a4d93baca5939c2971be3360f35d`.
Its tested 1016-file source map has SHA-256
`6ed170156fc04d868b6457b5da4d920a085f962d94cfa0a6e4a4850000dcc075`.
The physical-source result is
`58eadafee022e56ab7da5bcda00a05d1156035bc703436ad96599c5806d117cd`.

The bounded implementation changes 33 paths: seven production C/header paths,
one native selection manifest, 24 test/fixture paths and one private-kernel
configuration tool. Four documentation paths are proposed separately. Tested
source identity is established by physical bytes, Git blobs and SHA-256;
this report does not use a circular publication commit or tree identifier.

The seven production paths are `rtwn8723be_runtime_owner.c/.h`,
`rtwn8723be_btc_native.c/.h`, `rtwn8723be_dm.c/.h` and
`rtwn8723be_netbsd.c`, all under `src/`.
The complete changed-file identities appear in the
[machine-readable evidence](evidence/BT_DM_PROVIDER_OWNERSHIP_20261110.json).

## Implemented behavior

The native lifecycle table now binds all 54 callback slots. Genuine
`bt_prepare` uses the actual parsed board identity, the atomic BTC context
builder, native low-level providers and the real high-level policy binder.
It initializes actual per-device BTC engine/workqueue ownership. Physical
Bluetooth absence selects the frozen one-antenna Wi-Fi-only argument; it does
not skip BTC preparation or replace it with a success stub.

Seven policy ports are mandatory: coherent snapshot, monotonic clock,
aggregation action, LPS enter, LPS leave, Bluetooth query and fault reporting.
Configuration copies their complete table once, with the owning softc as its
argument. Policy and DM storage belong to the outer device context. The
policy aggregation timestamp implements the frozen 8-second decision and
survives normal STOP/restart.

Permanent admission precedes mutable BTC child access. Accepted synchronous
calls and copied queue events retain real pending-work tokens until completion
or explicit fault discard. START/STOP/finalization refuse live accepted work
or provider reservations. STOP returns EBUSY before destructive effects and
can be retried after the owners complete; accepted events are not silently
dropped to make STOP succeed.

A provider I/O reservation is recorded before waiting for the adaptive mutex.
The lease drops Giant for its entire blocking/provider interval, claims the
actual RF-change flag under its short lock, rejects recursion/foreign context,
and restores the exact saved Giant depth after release. The RF wait is bounded
and never steals another owner's flag. Real START/STOP calls require the
accepted LWP and correct phase; runtime workers require genuine admitted work.
Hard/soft interrupt and pserialize contexts cannot run synchronous providers;
softint RX may copy and defer an admitted event.

The first I/O/OS-provider error suppresses later configured actions.
Repeated suppressed requests preserve the original error and notify the
external fault port only once. Pure caller event-validation errors are
returned without falsely poisoning the device. The corrected release path
snapshots the child's first recorded fault `last_error` under its queue lock
and releases the broker lease after unlocking. An observed ENOBUFS is preserved
when the individual callback returns EINVAL or succeeds; its per-call return
remains unchanged. This is a fault-observed-at-release guarantee, not a claim
that the broker atomically mirrors asynchronous faults arriving later.
Partial failures retain owners and state; no generic STOP or invented recovery
hides them.

The new 49th C unit implements full frozen `rtl8723be_dm_init`: DIG, rate
adaptation, EDCA, BB power saving, dynamic TX power, tracking initialization
and ATC. It reads actual BB AGC first and ATC last through the native lease,
then publishes the prepared state only after all reads/readiness checks pass.
Cold storage is constructed once. Warm DM/thermal history not assigned by the
frozen initializer is retained, including the similarly named but distinct
DIG fields. The native DM checkpoint validates the exact BTC owner, argument,
adapter and policy identity. The controller preserves the Linux
calibration-before-DM call order; the genuine calibration supplier remains
open and no circular DM-ready flag is used.

Normal HALT/fini retires the BTC child after genuine native teardown. MP stop
is checked before clearing the prepared child; the outer policy clock and
DM/thermal history remain device-owned. Failed HALT/MP teardown retains its
owners. Existing registration, TX/CCMP, IRQ SOFTNET drain and finalization
contracts remain preserved.

## Completed source and test evidence

The aggregate receipt `fixtures-final-A02-R04.json` has SHA-256
`75e27c0f709d189f98b8a334a7b2fc04a986dca2d1233fdf932b74667a9f3212`.

- 56 distinct regression-script results PASS: 53 freshly executed, plus three
  pure context/policy/DM passes carried after their consumed inputs were shown
  unchanged. The qualification explicitly excludes a broad runtime-owner
  input that those pure tests do not consume.
- The provider fixture compiles the complete runtime broker, native BTC,
  native providers, both actual antenna algorithms, context, policy, Linux
  controller and DM. Twelve logical cases run in normal and NDEBUG builds:
  24 positive executions. All 22 behavioral mutants compile and execute,
  then fail their intended runtime assertions; zero compile failures count
  as mutation kills.
- The independent pure-DM oracle executes raw pinned Linux initializer
  equations with explicit logical storage adaptation. All 768 vectors and
  fallible-read/readiness cases pass; 12 executed mutants are rejected. These
  and the 22 provider controls give 34 newly executed behavioral mutants.
- Preserved runtime-owner/IRQ mutations (18+13) and consumer/crypto mutations
  (13+11) pass again. The 17 source-negative controls are static checks and
  are not represented as behavioral mutation executions.
- Each test batch kept its consumed inputs unchanged. The accepted production
  and fixture bytes match the physical tested-source result. All nine
  protected fallback/input/artifact hashes remain unchanged at completed gates.

The provider fixture uses explicit pthread/workqueue/CV, Giant, MMIO, H2C
and configured action boundaries. Its lock/queue handshakes, token accounting,
foreign identities, first-error suppression and exact Giant restoration are
executed; they do not emulate the NetBSD scheduler or establish native SMP.
The boundary/model and pure modules retain strict C11/UBSan checks. The actual
GNU empty-varargs dispatcher is compiled with its documented GNU11 exception.
No production body is replaced to make ownership or callback completion pass.

Early development receipts are retained separately: legacy model/API gaps,
obsolete inventory assumptions, the generated-fixture indentation failure and
the first R04 mutant's unused-local compile failure were not accepted as
driver/runtime proof or mutation kills. A process-format query failure was
also retained before the corrected old-input verifier passed. The final
provider and regression receipts govern the accepted execution counts.

## Corrected native build and independent proof

The initial fresh private HP build compiled all 49 native units and completed
a full GENERIC-based kernel in about 42 minutes. Its source map was
`6a4243bff493e44ac78c76037293efcb6a05becb4f752c1421f20b3b640c23ef`
and runtime source `7c7afeaf3c8e58cb459dbf17b4fd1c8567e58c98bd995fe7dbf9b8e186d0de8e`.
Old-input independent proof
`b8b08367a99e150728736b1e36fcb780daf79617ae1bb338dd2612b2b11c6827`
qualified that complete intermediate build.

Before changing its owned output, all 1585 declared archive files were
preserved with manifest
`981ebd01ded3ceecf0570d6b5c57ec6bf0c206e2999271ebbd46d357b7868599`.
The intermediate kernel SHA-256
`8e1454a74368f60b518d92fc32670cb9fa290382bba44a5cdc2702668d856c3c`
and map SHA-256
`1375833b05ff1e8af7ba1390338ee22f587903c9b7c5ecaf071fcf7975990fcc`
identify archived history, not the final corrected candidate.

The separately recorded deterministic red probe compiled successfully, passed
its no-fault invalid-input control, and produced two intended attribution
assertions on the old code. It showed callback EINVAL/native ENOBUFS recorded
as EINVAL, and callback success/native ENOBUFS recorded as zero. Pending work,
I/O depth, Giant restoration, RF ownership and no additional resource frees
were checked before those assertions. Its receipt
`0f8f626328c679bd5b09f6b8d54ea28cbdb8eeaf1e9ecaef5e98730447343f8b`
remains preserved; these diagnostic reds are not mutation kills or accepted
driver behavior.

The corrected gate recompiled only the changed native runtime object:
`81d2130c405be3ad2b609877f22311ef315556e70f8203afa1cef233edc3b580`
became
`a41aa58961eabfe3577ab77aae487e95f9ac9de29153fd09e2d7ba6e21cd8882`.
The other 48 objects remain byte-identical to their independently proved
initial build. Normal dependency generation, the complete 49-object
relocatable link and the full `netbsd` target all passed. Existing system
objects are qualified from the completed fresh build; this is a corrected
relink, not a claim that the full GENERIC kernel was recompiled from scratch.

Final private kernel: **27,295,696 bytes**, SHA-256
`da4f6c19ef35c369ca977467426a8194b7d8cdca0bed03bdf9ee5c36a5b5a802`.
Map: **12,479,929 bytes**, SHA-256
`5095dbfa020bc1bc26e95a576923a9f04e6360650534bba44c06a3a4972e74c0`.
The 49-object relocatable output is 6,352,504 bytes, SHA-256
`dc118cabbe5880021e4456556996ba77bc2e11a5b0d5906949845119b14be962`.
Final output-manifest SHA-256:
`1bcb4b9302de8990626acce842e4c3a2062ad69645b162ecedbd6dd1e3c9ad2d`.

Final independent verification passed **4675/4675 checks**. Receipt:
`22e32985120612ce6442c83cbd7c0794b05c5b3fa9939db4fa07b676a2aa9f4e`.
It verifies all 1016 tested source files, 119 production/header/inc/config/tool
inputs, 115 staged project dependencies, all 49 selected native objects and
all 336 RTL global definitions, the actual system API references, native PCI
attachment, the full ELF/link map and zero final undefined symbols. No i915
input or linked i915 symbol is present. The changed runtime, unchanged 48,
cached system support, entire output inventory and archive all match their
declared identities. The original nine protected paths and final kernel/map
pair are preserved during verification.

The candidate remains **BUILT_NOT_TESTREADY**, uninstalled and unbooted. Native
header/link proof and the separate modeled concurrency tests do not establish
physical NetBSD SMP, firmware, WLAN or PM acceptance.

## Remaining genuine owners and acceptance

All 54 callback pointers being bound does not provide genuine external
snapshot/action, C2H TX/RA, calibration or hardware-disable suppliers.
The structural early admission gate still returns ENOSYS before PCI/MMIO
when those complete genuine owners are missing. No sample snapshot, successful
query stub, fabricated lease or hardware-ready flag is installed in production.

Real MP activation/reply-generation ownership remains OPEN. Complete partial
START recovery, running-driver detach/lifecycle integration, periodic
DM/thermal/watchdog scheduling, native SMP/IRQ/STOP races, power management,
physical scan/association and WPA2 traffic remain OPEN / NOT_RUN. Instrumented
firmware/OS actions in tests do not satisfy these hardware requirements.

Source publication and host-ref convergence are recorded separately in project
governance. NEXT: supply the remaining genuine state/action/C2H/calibration/
hardware-disable owners and MP transport activation, then close complete
recovery/detach and separately authorized physical network acceptance.

The actual target headers identify NetBSD 11.0. Historical upstream Git
reference `03d918f6d0e81fa05b8f1160eca0628ad39988a6` remains UNVERIFIED
against that installed, non-Git target tree. Exact observed target-source
hashes govern evidence. OS/tool files without explicit before-build anchors are
endpoint observations, not a complete historical GENERIC source/SDK map.
The declared Linux semantic reference remains
`fd179f8a05be3ccae366b9b96e176b51fbe54aab`; no newer source is silently
substituted.

## Safety and historical evidence

F77 remains the verified HP fallback. `/netbsd`, `/boot.cfg`, EFI,
installed `files.pci`, current radio/network state and previous private
kernel/map artifacts are preserved. This private work installs or boots no
candidate and claims no hardware WLAN result. It does not change i915 policy;
physical early serial evidence is still required before any i915 activation,
and F16.0 must never be booted.

Version 1.0.0 remains the first functional release proven on the target HP.
Packaging follows hardware acceptance. Legion remains source/reference
staging; builds remain HP-only.

Historical evidence remains available unchanged:
[registration/ownership](NET80211_REGISTER_OWNER_20261110.md),
[TX/CCMP](NET80211_TX_CONSUMER_20261110.md),
[prior native kernel gate](HP_NATIVE_KERNEL_GATE_20261109.md),
[Shadow H](HP_NATIVE_SHADOW_H_20261011.md) and
[complete status history](../STATUS.md#complete-historical-status).
The hosted workflow is unchanged and no hosted CI acceptance is claimed.
