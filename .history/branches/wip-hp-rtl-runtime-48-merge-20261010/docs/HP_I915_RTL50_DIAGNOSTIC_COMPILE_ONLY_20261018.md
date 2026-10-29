# HP NetBSD 11 combined i915 + RTL50 — compile-only diagnostic path

**Date:** 2026-10-18. **Owner:** RTL combined-kernel consumer with
i915 producer consent. **Status:** source-stage and shell safety
PASS, **NO HP NATIVE BUILD EXECUTED**.

## Reason for this separate build-only mode

The existing production
`tools/build_hp_combined_i915_rtl_candidate.sh` is **unchanged**:
it requires a genuine i915 owner release
`governance/HP_I915DRMKMS_KERNEL_RELEASE.json` and all 323 source
semantic ownership rows, 10 verified subsystem gates, physical KMS,
PM and recovery evidence. That file and complete i915 source closure
are absent. Do **not** falsify them to run the production script.

A first diagnostic native compilation is useful BEFORE physical KMS
acceptance. The **frozen NetBSD 11 GENERIC** already compiles its
native `i915drmkms` and `intelfb`, through the real
`sys/external/bsd/drm2/i915drm/files.i915drmkms` graph. This path
stages that existing NetBSD i915 with the **50 RTL native C units**,
all **63 RTL-owned header/inc dependencies**, G01–G09 NetBSD-only i915
trace (18 printf calls), DDB/msgbuf configuration, and a special
identity `HP-DIAGNOSTIC-COMPILE-ONLY-...`.

**Important:** It does NOT integrate the modern 323 Linux i915 units,
later DRM/TTM source overlays or their semantic parity; it may expose
real native linker/compiler failures. A successful ELF is NOT a
production-ready KMS kernel and is **never** approved for boot
through this build-only workflow.

## Artifacts

- `tools/stage_hp_combined_diagnostic_source.py`: pinned
  `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`;
  checks original `i915_drv.c` SHA256
  `88c9e4c4ffb0669fdec14fd6a3589ab4aae43b2ef32ad5f6deb78b86ffd1d8e8`,
  actual selected i915 PCI owner and GENERIC, complete RTL50 source
  inventory, headers/inc and producer-owned exact phase patch.
  The full source tree is mirrored into **new private paths**, with
  modifications copied as regular files, unchanged pinned references
  symlinked. The original NetBSD tree remains unmodified.
- `tools/build_hp_combined_diagnostic_compile_only.sh`: only
  runs on HP `NetBSD/amd64` as a **non-root** owner with existing
  `/usr/tools/bin/nbconfig`, `nbmake-amd64` and verified running
  kernel identity. Creates a new private output directory; executes
  native `nbconfig`, checks actual `nbmake -V OBJS` for RTL50 and
  five native i915/DRM owners (three i915 plus `drm_vblank.o` and
  `drm_vblank_work.o`), then `nbmake -j2 dependall`.
  Requires a linked `ELF64 x86-64`, immutable private source
  SHA256 and full `netbsd.map` linker map proving all 50 RTL +
  five i915/DRM C objects. Keeps detailed output under
  `diagnostic-build.log` and durable phase markers in
  `diagnostic-build-status.txt`.
- `diagnostic-source-manifest.json` sets
  `eligible_for_install=false`,
  `eligible_for_boot=false`,
  `no_release_authorization=true`,
  `i915_full_323_semantic_closure=NOT_VERIFIED`,
  and binds native C, RTL and 18-phase patch hashes.
  Its immutable `kernel_build=NOT_RUN` applies to *source staging*;
  the separate build status file records any actual later compile/link.

## Invocation after independently verified HP direct access

```sh
sh tools/build_hp_combined_diagnostic_compile_only.sh \
  /absolute/clean/i915-owner-checkout \
  /absolute/clean/pinned-NetBSD-src-git \
  /absolute/NEW/private/diagnostic-output
```

All three arguments are mandatory. Existing output directories are
refused. **Do not invoke this command on another host or use a proxy
to bypass an external HP effect denial.** No installation or reboot
commands exist in either the source stage or build script.
Keep the independently proved safe standard/F77 kernel and all
four boot menu selections unchanged. Any later physical diagnosis
requires a **different explicitly validated release/test-boot gate**
with real persistent logging, selected UEFI loader, and rollback.
The companion production builder remains the only route for a
fully qualified combined release after 323 source closure.

## Actually executed read-only source tests (Legion)

- Exact producer i915 WIP
  `294414065551ea0fbeed0d9ad7139f0dd0a22412`
  and RTL consumer WIP
  `c6b48cebbc8cc787c6fe9af9d929a841e9f88805`:
  private mirror against **real frozen NetBSD 11** GENERIC,
  files.pci, files.i915drmkms, i915_drv.c, i915_module.c,
  i915_pci_autoconf.c; 50 RTL units, 63/63 headers/inc,
  18 trace calls and pinned source hash confirmed.
  Disabled i915 GENERIC correctly rejected; source unchanged.
- Subsequent build-script source checkpoint
  `21f3450486ae3b5791c5432e832845050d5ea63f`:
  `sh -n` PASS; Python syntax PASS; old Combined contract
  and 59 link-map negatives PASS; explicit off-HP invocation
  refused with exit 2 and created **no** build output.
  All install, boot and release-source safety invariants
  PASS under static/read-only regression.
- A new tracked regression file
  `tests/test_hp_combined_diagnostic_source.py` was **NOT
  published**: GitHub provider explicitly rejected its creation.
  The independent disposable Legion source fixture and negative
  tests listed above were executed, but do not replace a
  persistent tracked test. Do not retry the rejected write through
  a different tool/host. This is an **OPEN test-publication blocker**.

**NO HP native `nbconfig`, kernel compiler, netbsd ELF/linkmap
or physical KMS/WPA2 test occurred.** The direct HP RDC command
quota remained provider-reported 0% on the last check; no separately
callable direct Tailscale executor was available here.

## Cherryview hardware-order fixes in private diagnostic source (2026-10-18)

RTL WIP `edc591fd6a22cfd7ba44d9709e2ceb1e5b0f2d24` now SHA-pins and applies **existing i915-owner patches**, without modifying either frozen NetBSD source file:

- `0002`: `display/intel_display_power.c` defers the `DISPLAY_PHY_CONTROL` write from `chv_phy_control_init` to the Cherryview pipe power-well `.sync_hw` callback. Frozen source SHA256 `07b4d1fb…13993f730`; owner patch SHA256 `e75157d7…18823905`.
- `0004`: `display/intel_dp.c` selects **three 2-µs precharge units** for pre-SKL AUX instead of five. Frozen source SHA256 `7f79318f…29db0141`; owner patch SHA256 `9fe5facc…228662ee`.

The latter is applied to both pristine and G08-traced frozen source in separate temporary directories. Removing 14 G08 traces from the final DP source still reproduces byte-for-byte the **hardware-fixed** nontraced source; the G01–G09 18 prints are preserved independently. The private manifest binds the two owner patch hashes, 3 original C file hashes and final overlay hashes; both corrected native display C files are selected by the frozen NetBSD `files.i915drmkms` owner.

**Executed on Legion:** full private stage **PASS** with 50 native RTL C units, both CHV corrections and 18+14 guarded trace prints; frozen originals unchanged, final SHA values verified. Six negative cases correctly refused (mutated DP input, mutated power input, tampered patch, two missing NetBSD selectors, off-HP build). Shell syntax PASS. This is nonrelease source instrumentation and two source-level hardware sequence changes, **not** full 323 semantic parity, not a native HP compile/link, and not KMS/WPA2 acceptance. No production release gate, kernel, default boot entry or recovery image was changed.

## G08 producer overlay integrated (2026-10-18)

RTL WIP `867714f724610abe2816f09d8fa8ab67ecf6f7f5` now stages **both** exact i915 owner patches in separate private files: `0038` -> `i915_drv.c` (G01–G09, 18 prints) and `0039` -> `display/intel_dp.c` (G08 AUX/DPCD, Cherryview PHY/PLL, eDP panel and link, 14 prints). The latter is required by the native `files.i915drmkms` selector. Both original and staged SHA256 digests and patch hashes are bound to the private diagnostic manifest. The pinned NetBSD source is unchanged.

**Executed on SentinelX Legion** with i915 owner `f56203a2` and exact NetBSD pinned source subset: two overlay/source-integrity checks PASS; private staging of 50 RTL native units and both 18+14 i915 traces PASS; 8 original pinned files hash-preserved; **5 deliberate failures refused** (phase mutation, bad context, duplicate marker, base SHA drift, unselected intel_dp.c); diagnostic shell syntax and off-HP execution refusal PASS. Native full NetBSD source build/link, HP boot, physical KMS and WLAN remain **NOT_RUN**. The earlier denied publication of `tests/test_hp_combined_diagnostic_source.py` was not retried.

## Verified AUX IRQ-unavailable poll fallback 0013 (2026-10-18)

RTL WIP `004c06a35b65bd8dcb61575ae2591dddd918a345` applies the existing immutable i915-owned candidate `0013-i915-edp-aux-poll-when-irqs-disabled-netbsd11.patch` **after** `0004` precharge and `0039` G08 trace in a temporary private `intel_dp.c` copy. The exact producer patch hash is `3806db3f9ef738d1d1d79b3adc96237ea9e3cdf1f43fc4ec4c9ddeb0f591f997`. The new branch requires `!cold && i915->drm.irq_enabled && i915->runtime_pm.irqs_enabled` before the IRQ wait; otherwise it retains the existing NetBSD atomic polling and timeout path. No other driver statement may change.

**Actual Legion verification:** isolated exact frozen-NetBSD `intel_dp_aux_wait_done` 8/8 C11 ASan/UBSan fault conditions PASS, old code negative control aborts as expected; private real NetBSD staging with 50 RTL C files and 14 G08 marks PASS; three invalid cases (tampered patch, source drift, duplicate application) refused; trace preservation, final C hash and manifest SHA checks PASS. Final staged `intel_dp.c` SHA256: `7d9536d7a989a240fcb16595039297a72a894764c55df83fd86ac65ea189d250`. The off-HP compile-only builder still fails closed. **No HP compilation, kernel installation, boot, physical KMS, RTL/WPA2 acceptance or semantic Linux323 closure performed.** Full Linux reference lifecycle parity remains open.

## eDP link-rate short AUX read guard 0012 (2026-10-18)

The nonrelease private i915+RTL50 source stage now applies existing i915 owner `0012` after `0004`/ `0013`/ `0039` to `display/intel_dp.c`, preserving 14 G08 traces, the AUX IRQ fallback and the Cherryview precharge. The new guard clears all supported-link-rate entries on an incomplete or failed DPCD read, leaving the original default-rate decision active. The producer patch hash is `a50717c043eff10e31c5dd8d9582632d71197203c5a13738e12e7e520817a5fa`.

On operational Legion: frozen NetBSD source-extracted C11/UBSan 5 cases, five mutation refusals, and actual git apply/reverse PASS; full private RTL50 pinned source-stage PASS with five independent tamper/drift/precondition rejections. Final private `intel_dp.c` SHA256 `712c7364f821320af523b140881cb64b00092e664c07706b7b8e884d57f6aecc` recorded in all dependent manifest SHA fields. Off-HP builder refusal, diff/shell/Python syntax PASS. **No HP native compile, kernel link/install/boot, complete Linux323 source/DRM/TTM closure, KMS or WLAN/WPA2 proof.** [i915 owner evidence](https://github.com/n-e-o-w-u-l-f/i915-cherryview-braswell-netbsd/blob/work/hp-native-drm-stage-replay-20261015/docs/HP_I915_EDP_DPCD_SHORT_READ_20261018.md).

## Native DRM VBlank core + 0018 staged from pinned NetBSD (2026-10-18)

The existing **private, nonrelease source mirror** now includes all five VBlank runtime-owner paths, in addition to its 50 RTL C units, G01–G09/G08 trace paths and Cherryview AUX/DPCD patches:

- `sys/external/bsd/drm2/dist/drm/drm_vblank.c`: original pinned NetBSD SHA256 `06434bfc9f6693a1b61069c5c0e839b24671a5ba4d826fb001b0a897ceac206e` → private overlaid SHA256 `5b6d2d601dbf1abea11a9fd35f90cdf670ceb360657acd495fd5ca4bd4981090`.
- `sys/external/bsd/drm2/dist/include/drm/drm_vblank.h`: core work-field additions;
- `sys/external/bsd/drm2/drm/files.drmkms`: selects the worker's translated C object;
- `sys/external/bsd/drm2/dist/drm/drm_vblank_work.c`: pinned i915-owned native worker, SHA256 `fe31c46d491a4b93589d6c8308895266de22ee66913864ddde8b1234c29b12be`;
- `sys/external/bsd/drm2/dist/include/drm/drm_vblank_work.h`: pinned API header SHA256 `f01168bf73570113b94cf07a2c424dd3c4cfcc4061db6c4f984f4c518e8e008d`.

The consumer applies two immutable i915-owned patches only in a **temporary copied NetBSD DRM tree**: core VBlank hooks SHA256 `0acc6a3e68a9276a734752b78d4e07d725efafc84ebc2bacaa11a0825832d919`, followed by the independent reference-pointer guard `0018` SHA256 `2a4cc2546abd9e9e7be38a7e972d619a49991a1f02cff8333cacc35db9a1dd0f`. Both patches are re-applied with genuine `git apply --check` and `git apply`, reversed, and the original three source bytes restored exactly. The worker's NetBSD system dependencies `include/drm/drm_wait_netbsd.h` and `include/drm_trace.h` are now explicitly presence- and SHA-bound to the frozen source, without copying unrelated headers into the owner project.

**Executed on Legion:** `VBLANK_0018_RTL50_G08_CHV_NONRELEASE_SOURCE_STAGE_PASS`, `I915_VBLANK_0018_STAGING_17_NEGATIVE_CASES_PASS` and `VBLANK_0018_OFF_HP_DIAG_BUILDER_FAIL_CLOSED_PASS`. The **17 negative controls** cover three corrupted native core inputs, four changed i915 owner inputs/patches, one symlinked owner hook, four missing/corrupted NetBSD header dependencies, and five missing/duplicate native-object or final-link-map cases. All five new files are materialized (not symlinks) in the private source mirror and have their hashes in `diagnostic-source-manifest.json`. Unmodified frozen input files and the existing 14 G08 trace marks are preserved. `kernel_build=NOT_RUN`, `eligible_for_install=false`, `eligible_for_boot=false` and `i915_full_323_semantic_closure=NOT_VERIFIED` remain mandatory.

**Open native limits:** New VBlank `SCHED_RR` vs Linux `SCHED_FIFO` deadline parity, NetBSD compiler `-Werror` for the *composed* core/worker, DRM internal `drm_trace.h` ABI and actual GPU interrupt timing are **not tested here**. This represents SOURCE STAGING, not a successful HP compile or functional KMS/RTL.


**Source graph versus compiled proof:** `required_native_i915_sources` now contains five native sources: the three original i915 owners, `drm_vblank.c`, and `drm_vblank_work.c`. The HP-only diagnostic wrapper now refuses an expanded native `OBJS` list lacking either VBlank object, and post-link `netbsd.map` ownership checks use the same five-object manifest. An entirely synthetic, bounded 55-object/ELF-map fixture on Legion passes selection and rejects both missing workers and a duplicate; **this does not assert that a real HP NetBSD 11 compiler/linker has succeeded**.

## Next actions

1. Establish a genuinely permitted direct HP command executor,
   determine live NetBSD source/toolchain and standard kernel/UEFI
   state without changing boot selections.
2. Independently resolve the blocked persistent test publication
   through legitimate provider support/permissions; do not evade.
3. **First complete all 323 i915 semantic owner/source rows** with
   DRM/TTM and native ABI dependencies in the i915 producer. This
   staged private diagnostic source alone does not authorize a build.
4. **After 323 source closure and legitimate HP access**, execute
   only the separately authorized native compile/link diagnostics and
   resolve actual `nbconfig`, C ABI, IRQ and undefined-symbol errors.
5. Verify kernel-independent recovery and keep standard `/netbsd`
   unchanged; install an isolated test kernel only after gate acceptance.
   The **user tests the installed kernel** before physical KMS/WLAN
   validation.

Source: https://www.netbsd.org/docs/guide/en/chap-build.html
