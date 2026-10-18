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
  the three real i915 owners, then `nbmake -j2 dependall`.
  Requires a linked `ELF64 x86-64`, immutable private source
  SHA256 and full `netbsd.map` linker map proving all 50 RTL +
  three i915 C objects. Keeps detailed output under
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

## G08 producer overlay integrated (2026-10-18)

RTL WIP `867714f724610abe2816f09d8fa8ab67ecf6f7f5` now stages **both** exact i915 owner patches in separate private files: `0038` -> `i915_drv.c` (G01–G09, 18 prints) and `0039` -> `display/intel_dp.c` (G08 AUX/DPCD, Cherryview PHY/PLL, eDP panel and link, 14 prints). The latter is required by the native `files.i915drmkms` selector. Both original and staged SHA256 digests and patch hashes are bound to the private diagnostic manifest. The pinned NetBSD source is unchanged.

**Executed on SentinelX Legion** with i915 owner `f56203a2` and exact NetBSD pinned source subset: two overlay/source-integrity checks PASS; private staging of 50 RTL native units and both 18+14 i915 traces PASS; 8 original pinned files hash-preserved; **5 deliberate failures refused** (phase mutation, bad context, duplicate marker, base SHA drift, unselected intel_dp.c); diagnostic shell syntax and off-HP execution refusal PASS. Native full NetBSD source build/link, HP boot, physical KMS and WLAN remain **NOT_RUN**. The earlier denied publication of `tests/test_hp_combined_diagnostic_source.py` was not retried.

## Next actions

1. Establish a genuinely permitted direct HP command executor,
   determine live NetBSD source/toolchain and standard kernel/UEFI
   state without changing boot selections.
2. Independently resolve the blocked persistent test publication
   through legitimate provider support/permissions; do not evade.
3. On HP execute build-only native command; capture first
   `nbconfig`/compiler/undefined-symbol failure and fix true
   NetBSD ABI/DRM/PCI issues in source, with PRE/POST evidence.
4. Continue modern 323-unit i915 semantic closure in the i915
   producer; this diagnostic source build does NOT waive it.
5. Only after real full production source/physical gate and
   independently verified early-recovery path consider a
   nondefault manual test boot of a separate kernel.

Source: https://www.netbsd.org/docs/guide/en/chap-build.html
