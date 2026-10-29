# RTL8723BE NetBSD: i915drmkms release dependency and bounded auto-porting

Date: 2026-10-17. The user's binding instruction is to **build no new HP kernel until i915drmkms is finished and explicitly approves the joint HP kernel build**. This is separate from the previously denied HP source-fast-forward, which remains an independent execution blocker. **Do not infer that source tests, an i915 commit, a selected partial DRM object, a firmware framebuffer boot, or silence is approval.**

## Current release finding

The actual i915 development branch `work/hp-native-drm-stage-replay-20261015` was read from GitHub and independently cloned to a temporary Legion directory at `f536130b9ca049967ddf729954e3b32a69e33a96`. The i915-owned release file `governance/HP_I915DRMKMS_KERNEL_RELEASE.json` does NOT exist at that commit. Running the new production verifier against this exact i915 checkout rejected the current RTL source `909a90820ca89e19ea08a6d89834868a02e20c59` with exit code **2**, before any native build. i915 `STATUS.md` still says *diagnostic recovery only* and F83/F84 blackscreen not resolved; project Governance `state/projects/HP-I915.md` still records full DRM/TTM/323-active-unit, native KMS and physical display acceptance OPEN.

## Enforced entrypoint gates

- `tools/build_hp_rtl50_next_candidate.sh` calls `tools/check_i915_kernel_release.py` twice, first **before** any source regression and later **before** output directory/configuration/compilation. A failed check returns 2.
- `tools/build_hp_native.py --target kernel` calls the same checker **before** creating the object directory or writing build-state files. The separate `--target objects` remains a compiler/ABI-only operation, never a kernel-link approval.
- The verifier requires a clean standalone Git checkout of the canonical `n-e-o-w-u-l-f/i915-cherryview-braswell-netbsd` repository, an i915-owned release JSON **committed at HEAD**, `APPROVED` for target `HP-TPN-W121-RTL8723BE-I915DRMKMS` and scope `HP_COMBINED_KERNEL_BUILD_ALLOWED`, **exact** current RTL SHA and validated ancestor i915 SHA, and actual i915-project release identity.
- All six i915 verification attributes must be `PASS`: full i915 DRM/TTM port, native NetBSD i915 kernel link, physical HP KMS display, F83/F84 black-screen resolution, boot recovery and i915 runtime PM. This is an explicit downstream *build* dependency, NOT an automatic signal that the RTL WLAN card works.
- The `governance/HP_I915DRMKMS_KERNEL_RELEASE.json` approval manifest is intentionally **not created** here. Only a future verified i915 owning-project release is eligible. The RTL project MUST NEVER grant itself approval.
- A manual direct `nbmake` outside the repository scripts is not guarded by this repository check. The operational user instruction still prohibits such builds; this is not an OS-wide mechanism.

The i915 release document, once legitimately produced by its owning project after its hardware acceptance, must have the following structure (the sample below is *not* approval and must not be committed as an actual release):

```json
{
  "schema": 1,
  "target": "HP-TPN-W121-RTL8723BE-I915DRMKMS",
  "decision": "APPROVED",
  "scope": "HP_COMBINED_KERNEL_BUILD_ALLOWED",
  "rtl_source_sha": "<exact RTL WIP 40-hex revision>",
  "validated_i915_source_sha": "<fully verified i915 40-hex ancestor>",
  "verification": {
    "full_i915_drm_ttm_port": "PASS",
    "netbsd_native_i915_kernel_link": "PASS",
    "hp_physical_kms_display": "PASS",
    "f83_f84_black_screen_resolved": "PASS",
    "hp_recovery_boot_verified": "PASS",
    "i915_runtime_pm_verified": "PASS"
  },
  "approval": {"owner": "HP-I915", "release_id": "<real i915 project checkpoint>"}
}
```

## Continued RTL source improvements while waiting

`tools/rtl_netbsd_autoport.py` supplies a **bounded**, source-driven Linux→NetBSD translation and error analysis path without requiring a kernel build. It selects exactly the 50 native RTL C units from `config/files.rtwn8723be_native` and offers safe direct-include swaps: `errno.h`, `stdbool.h`, `stddef.h`, `stdint.h`, and `string.h` to appropriate `sys/*` NetBSD kernel headers. Nested conditional includes are flagged for manual review rather than changed automatically. The tool analyzes optional compiler diagnostics, distinguishing safe include errors from missing Linux API providers, unresolved symbols, DMA/IRQ lifecycle failures and GPU KMS blackscreens. **Hardware register writes, bus_dma ownership, IRQ order, firmware sequencing, RF calibration, net80211 and PCI APIs are never patched automatically.**

Default mode is read-only. `--apply` requires a clean exact Git SHA and refuses changes on HP-NetBSD. Source changes are appropriate only in a permitted developer checkout and must subsequently pass all regressions and review. Its first test identified and corrected a real newline-loss bug in the include conversion. The final tests passed both release and auto-port validators.

### Real execution results on Legion (no native kernel)

At RTL WIP SHA `909a90820ca89e19ea08a6d89834868a02e20c59`, the complete temporary clean Git clone yielded **35/35 selected Python-only source regressions PASS**; **three C compiler tests were deliberately NOT RUN** (`test_calibration.py`, `test_calibration_native.py`, `test_linux_lifecycle_stop.py`). The guarded build-script list contains **38 unique names**. `test_i915_release_gate_source.py` passed 22 synthetic positive and negative release scenarios including wrong remote, dirty source, wrong SHA, missing full-KMS proof and both kernel entrypoints. `test_netbsd_autoport_source.py` passed a synthetic 50-unit/6-error-class translation/refusal fixture. The actual 50 selected RTL C files required **zero** safe include translations and contained **zero** flagged unsafe Linux include references in this audit. `/bin/sh -n` passed.

### Conditions before any future native build

Both independent gates must be met: **(1)** i915 owning-project release with complete physical KMS, native full DRM/TTM, recovery and PM proof, and **(2)** a genuinely permitted HP executor/source update (the historical external refusal may not be circumvented). Even then, verify the current HP boot identity and recovery, actual firmware availability, NetBSD native toolchain, source tree and repository SHA, run three C-only tests plus the complete release-gated regression suite, and perform one explicitly authorized, non-installing combined-driver kernel link. Kernel install, boot/default changes, WPA2 air acceptance and full i915 graphics commissioning require separate validation. The i915 gate alone performs **no** build and triggers **no** background work.
