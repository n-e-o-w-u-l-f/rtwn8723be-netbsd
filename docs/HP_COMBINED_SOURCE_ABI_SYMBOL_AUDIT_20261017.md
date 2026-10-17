# HP NetBSD 11: Combined i915drmkms + RTL8723BE source, Kconfig and link-owner audit

Date: 2026-10-17. Current verified RTL source commit: f84826e6fe8735d92bac1f082a689f85ad28b64a. Current i915 owner work branch commit: f536130b9ca049967ddf729954e3b32a69e33a96.

**Decision: WAIT_FOR_I915_RELEASE.** This is an integration source audit, not an HP build or native ABI proof. Both earlier i915 F83/F84 black-screen failure and the external denial of the previous HP source fast-forward remain unresolved. No HP command, kernel build, install, reboot, PCI, firmware or network mutation was performed.

## Frozen source graph (independent GitHub reads)

Source of truth: Linux/torvalds fd179f8a05be3ccae366b9b96e176b51fbe54aab, NetBSD/src 03d918f6d0e81fa05b8f1160eca0628ad39988a6, RTL WIP manifest and i915 work-branch coverage TSV.

| Scope | Source evidence | Actual state |
|---|---|---|
| PCI + display Kconfig | frozen NetBSD sys/arch/amd64/conf/GENERIC | Has effective i915drmkms PCI attachment and intelfb bus; genfb remains an ordinary additional fallback but is NOT substituted for i915. Legacy rtwn PCI remains; only evidence-driven conflict resolution allowed |
| i915 native selection | frozen NetBSD sys/external/bsd/drm2/i915drm/files.i915drmkms | 165 active C selection lines for i915drmkms/intelfb; explicit i915drmkms PCI device and intelfb bus owners |
| DRM native selection | frozen NetBSD sys/external/bsd/drm2/drm/files.drmkms | 71 active C selection lines in the i915/DRM/TTM selector audit (not necessarily unique native object count) |
| TTM native selection | frozen NetBSD sys/external/bsd/drm2/ttm/files.ttm | 10 active C selection lines in selector audit; actual generated kernel OBJS not observed |
| RTL PCI/net80211 | RTL config/files.rtwn8723be_native | 50 unique selected native C sources, device/attach entry; source graph successfully checked in earlier RTL source tests |
| Linux i915 reference | i915 docs/I915-STRUCTURAL-COVERAGE.tsv blob 993a63609ab2a9877786f1c787b952e560a8dee0 | 323 source records: 136 EXACT_ACTIVE_DIST, 13 ACTIVE_OVERRIDE_OR_MOVED, 7 PRESENT_NOT_BUILT, 167 UNRESOLVED_NO_BASENAME. These are path classes, not 167 proved missing functions |
| Linux→NetBSD semantic acceptance | same i915 TSV | 300 semantic_state=UNREVIEWED, 23 REFERENCE_INAPPLICABLE_CHV_UC_PXP; neither status is full native DRM/KMS closure |
| i915 native overlay + ownership | i915 governance/HP_I915DRMKMS_COMBINED_SOURCE_CLOSURE.json | ABSENT on actual owner work HEAD; cannot stage a real 323-unit semantic mapping and validated native source provider list |
| i915 combined release | i915 governance/HP_I915DRMKMS_KERNEL_RELEASE.json | ABSENT; production release gate REFUSED, no kernel build |

## Existing Combined stage and builder, now tested

The current RTL work branch already owned the new separate tools/configure_hp_combined_i915_rtl.py, tools/build_hp_combined_i915_rtl_candidate.sh, tools/verify_hp_combined_kernel.py, and tests/test_hp_combined_source_contract.py. Their Git SHA and contents were read before changes. They are independent of RTL-only scripts that deliberately select no i915drmkms.

The Combined configurator requires clean exact RTL+i915 Git sources, real i915-owned release and full-323 semantic closure; its private overlay mirrors frozen NetBSD unchanged source by symlink, copies owned RTL and i915 bytes, and constructs an effective i915/intelfb/RTL NetBSD Kconfig with a dual SHA identity. No fake i915 owner manifest or release was created. The HP-only builder validates current boot/recovery and native tools, runs NetBSD nbconfig, verifies actually selected OBJS, executes one full dependall when both external gates pass, and never installs or boots the resulting kernel.

### Corrections during this continuation

1. Previous final-link verifier accepted any one of the 50 RTL object names plus any one GPU/DRM object in netbsd.map. Fixed tools/verify_hp_combined_kernel.py in commit 4b0af0c6c0e1f8bf6ab1e9076de3ebfc328f02dc to require ALL 50 selected RTL and ALL selected i915/DRM object basenames in the real final linker map. Source regression tests/test_hp_combined_full_link_map_source.py committed 47b309ab1aeea85a29c6cee7a2ec3713bf978c2c: 59 deliberately incomplete or deceptive map mutations rejected.
2. New tools/run_hp_combined_preflight_tests.py selects every source/native test from the published RTL gate list and the two Combined ownership/link tests WITHOUT ever executing the RTL-only builder. Combined builder now invokes all 40 such gates before private staging, then re-checks the i915 release. Source commits 0f1c0062197d9f434656a2a96ad14d0e6d9048bb and f84826e6fe8735d92bac1f082a689f85ad28b64a.
3. Source-only test on Legion from an exact SHA checked-out temporary clean Git clone: 37/37 executable Python tests PASS, including both Combined tests. Three C-compiler tests were NOT_RUN and remain HP-only. /bin/sh -n of Combined builder PASS. No partial/native link was attempted.
4. Independently cloned the live i915 work branch at SHA f536130b9ca049967ddf729954e3b32a69e33a96 and invoked the Combined configurator --audit-only: exit 0 read-only status WAIT_FOR_I915_RELEASE, explicit release file absent and I915_323_NATIVE_SOURCE_CLOSURE_MISSING. This status is not an approval.

## ABI, object and lifecycle boundaries still OPEN

Native i915 LinuxKPI, DRM/TTM/GEM/GTT/UVM, net80211, PCI MMIO, bus_dma, IRQ ownership and teardown must be matched against the actual NetBSD 11 kernel headers, generated private obj/Makefile and linker symbol owners, not inferred from structural filename matches. The 165/71/10 NetBSD filelist source lines overlap conceptually and are NOT a 246-object compile proof. Their selected conditions and the complete i915 overlay must be verified from the actual i915 owner manifest and generated kernel.

Combined PCI attach must maintain independent 8086:22b1 (Intel CHV) and 10ec:b723 (Realtek RTL8723BE) BAR/interrupt/DMA lifetimes; user-space KMS handoff and wireless WPA2/EAPOL, DHCP and physical radio traffic are separate hardware gates. F83/F84 blackscreen still has unknown causal phase; stage/source parity does not prove functional display or GPU PM. Preserve physical independent recovery and previous fallback. Do not change root NetBSD source, existing /netbsd, boot.cfg, fallback or live network.

## Next owner artifacts and acceptance gates

The i915 project must publish the committed, actual approved release AND committed full source-closure manifest with 323 reference source semantics and exact native provider/filelist/C/H/INC SHA-256 evidence. The RTL owner cannot fabricate it. After the external HP source update refusal is genuinely cleared and fresh HP permissions/recovery are checked, the Combined builder may run only on that HP with real sources. A legitimate success must have 40/40 selected tests including the three native C cases, nbconfig-selected full GPU/DRM/TTM + RTL OBJS, a full zero-error ld link and complete object names in netbsd.map, ELF/what identity containing BOTH Git SHAs and final kernel SHA-256. Status would be COMBINED_KERNEL_LINKED_NO_INSTALL only then; installation/boot, KMS, WLAN and full acceptance are separate.
