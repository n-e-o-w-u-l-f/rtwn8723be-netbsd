# RTL-owned combined NetBSD 11 kernel: i915 G01–G09 private source trace

Status: **SOURCE-ONLY INTEGRATED / PASS**. Date: 2026-10-18.
Physical host: HP TPN-W121, NetBSD 11 amd64. **No native kernel
compilation, complete ELF link, installation or boot was performed.**

## Frozen inputs

- i915 producer: `n-e-o-w-u-l-f/i915-cherryview-braswell-netbsd`,
  `work/hp-native-drm-stage-replay-20261015`, exact checked head
  `294414065551ea0fbeed0d9ad7139f0dd0a22412`.
- RTL combined-kernel consumer:
  `n-e-o-w-u-l-f/rtwn8723be-netbsd`,
  `wip/hp-rtl-runtime-48-merge-20261010`,
  tested source checkpoint `49ff6aa56f3c671bff026b6bce8b1e690c566383`.
- NetBSD kernel tree: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
  Native i915 source `sys/external/bsd/drm2/dist/drm/i915/i915_drv.c`
  has SHA-256 `88c9e4c4ffb0669fdec14fd6a3589ab4aae43b2ef32ad5f6deb78b86ffd1d8e8`.
- Producer-owned patch:
  `patches/0038-netbsd11-i915-g01-g09-boottrace.patch` (18 NetBSD-only
  phase BEGIN/END prints).

## New Combined integration

The existing `tools/configure_hp_combined_i915_rtl.py` now imports
`tools/hp_i915_boot_trace_overlay.py` and invokes
`build_private_overlay(...)` **after** the release, host,
semantic-source-closure, private-output and source-owner checks, and
**before** creating the output source mirror.

The overlay helper reads producer patch bytes and the precise frozen
source, requires exact SHA-256, parses unified-diff hunks in memory,
verifies canonical patch reproduction and strips all 18 guarded
messages to prove original C control flow/cleanup remains byte-identical.
It requires nine paired known phase names and correct return formatting.
Any mismatch, duplicate/missing phase, drift, source symlink, modified
owner i915_drv.c or ambiguous overlay refuses the integration.

If valid, `i915_drv.c` is inserted as actual **private replacement
bytes** into `replacements` and `mirror()` creates the private file.
Unmodified source files retain pinned symlinks. No in-place `git apply`
is ever run on a symlink, the upstream NetBSD checkout or an existing
owner source. A changed driver that needs both runtime porting and
diagnostics must be explicitly rebased and re-reviewed; diagnostics
may not erase functional fixes.

The manifest `combined-source-manifest.json` records original SHA,
patch SHA, private source SHA, i915 C path, 18 printf calls and producer/
consumer exact Git identities. The existing
`tools/verify_hp_combined_kernel.py::load_snapshot` refuses a missing
or inconsistent phase-trace manifest, missing/linked/tampered private
i915 source or missing i915 native object owner; it still requires
real NetBSD object list and final full link map/ELF later.

### Mandatory HP regression selection

The existing `tools/run_hp_combined_preflight_tests.py --run` now
receives `--i915-repo` and `--netbsd-src` from the existing
`tools/build_hp_combined_i915_rtl_candidate.sh`. Its selection
is extended from **40 to 42** tests, including:

- `tests/test_hp_i915_trace_overlay_source.py`: actual frozen original,
  exact patch, 18 messages and altered-source/patch negative refusals.
- `tests/test_hp_combined_trace_manifest_source.py`: synthetic private
  snapshot; rejects missing/mismatched digest, altered trace count,
  missing owner and symlinked source.

The other 40 existing combined/RTL tests, native HP-only restrictions,
recovery SHA checks, `-j2 dependall`, full ELF/linker map checks and
the unmodified owner `check_i915_kernel_release.py` guard remain.
The code does NOT create or forge
`governance/HP_I915DRMKMS_KERNEL_RELEASE.json`.

## Independent actual source test (Legion)

At exact consumer source checkpoint
`49ff6aa56f3c671bff026b6bce8b1e690c566383`:

- `sh -n tools/build_hp_combined_i915_rtl_candidate.sh`: PASS.
- Python AST of four changed source tools: PASS.
- `test_hp_combined_source_contract.py`: PASS (after correcting
  one test-only mirror helper vs real `main()`-call comparison).
- `test_hp_combined_full_link_map_source.py`: PASS,
  59 deliberate negative object/map cases.
- `test_hp_i915_trace_overlay_source.py`: PASS against exact
  NetBSD C and i915 producer branch, including altered-patch rejection.
- `test_hp_combined_trace_manifest_source.py`: PASS against
  synthetic transient private source, including tampered/symlink refusal.
- Combined `--list` and `--audit-only`: exit 0.
- `--audit-only` truthfully reports
  `WAIT_FOR_I915_RELEASE` and
  `I915_323_NATIVE_SOURCE_CLOSURE_MISSING`.

**Not run**: `--run` in its real NetBSD HP environment, native
`nbconfig`, all 42 tests on HP, native kernel dependall/full ELF,
G01-G09 in kernel memory or `/var/log/hp-kernel-boot.log`,
real display modesetting, RTL reception/WPA2, reboot or recovery.

## Follow-up acceptance

The i915 owner must complete true driver/DRM/TTM semantic source
coverage and produce an independently valid i915 release artifact
(or separately approved diagnostic build-only gate with explicit
limitations). Under legitimate HP execution, first check real host
identity, F77 safe kernel/UEFI boot chain, source clean state, dump/
syslog availability, then run 42 native/source preflights, configured
private mirror, real NetBSD kernel compile/link, artifact/trace hashes.
Keep entry 4 of the staged boot menu **nondefault**; physically validate
recovery independently before any diagnostic boot.
