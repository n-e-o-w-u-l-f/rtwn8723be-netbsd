# HP-native i915 + RTL8723BE source synchronization

**Verified 2026-10-23:** SOURCES ON HP / NATIVE DMA FIXTURE PASS / FULL PRIVATE DIAGNOSTIC KERNEL COMPILED AND LINKED.
**Not installed, released or booted. Physical KMS, WPA2 and recovery acceptance remain OPEN.**

## Exact tested sources and executable route

| Input | Exact tested revision |
|---|---|
| i915 active branch `work/hp-native-drm-stage-replay-20261015` | `8a164f10c45c3d66f7648376ccd2177c8dfe81ba` |
| RTL active branch `wip/hp-rtl-runtime-48-merge-20261010` | `a06a74eec7ffdeca8f472cc5c9a28d89d4b2cd04` |
| NetBSD native source | `03d918f6d0e81fa05b8f1160eca0628ad39988a6` |

The assistant directly executed authenticated strict-host-key SSH from the Windows controller to HP `megal`, verified NetBSD 11.0 amd64 and F77, and performed all compiler/linker work on HP. Current SentinelX capability/state was also verified on Legion. No Legion/Arch build, paid runner, quota change, credential movement or policy weakening was used.

Historical caller-side refusals of specific old source/header/scratch/RX-write effects remain distinct and were not replayed. Historical absence of an executor was not presented as current fact: this session independently proved direct HP execution. No existing old worktree was fast-forwarded, reset, cleaned, stashed or force-merged.

## Preserved fleet state

A bounded developer-root/worktree inventory was executed on HP, Legion, BMAX, Spinnennet, Pi-hole and Phobos. No target driver checkout was found in Phobos's inspected roots; skipped/inaccessible paths remain UNKNOWN. Offline peers were not called synchronized. Main and development WIP are different histories, especially RTL; a clean main checkout is not an up-to-date WIP.

The original HP/peer trees were preserved, including large dirty NetBSD integration trees. One unpublished Legion RTL commit `cda48e590ae4e65db4aca3ecb3bb116a27c5cbbe` and three unpublished BMAX i915 commits ending `6ab2012403a93a752cb4261165210f6146e8e71b` were exported as verified bundles to HP and retained under separate `preserved/` refs. They were not silently merged into the current source.

[Detailed fleet reconciliation](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/main/state/inventories/hp-two-driver-direct-20261023.md).

## Actual HP artifacts and validation

Work is isolated beneath `/home/megal/hp-driver-source-stage-20261023`. Current tested RTL checkout is `rtl-native-a06`; i915 is `i915`; clean pinned native sys/common source is `netbsd-github-a02`. Previous stages and failed build logs remain separate.

The existing [source-stage helper](../tools/hp_driver_source_stage.sh) was read before execution. Its reviewed defects/limitations were identified: release11 was not explicitly enforced, and its two-level audit can omit repositories inaccessible to Git's owner checks. Explicit NetBSD11 validation was applied before initial execution and then fixed in source. Independent owner-aware inventory supplemented the helper; path-scoped read-only Git trust did not change global configuration.

Native HP C11+UBSan allocator fixture: **9 cases PASS**, with **5 unsafe source mutations refused**. Existing BTC async-event sequencing source regression PASS. This is a userland allocator failure-injection fixture, not physical DMA testing.

The actual native kernel build exposed and repaired three bootstrap issues: unqualified sysctl outside owner PATH, unexpanded `make -V OBJS`, and missing matching toolchain linker in process PATH. Native compilation then caught one unused DM-init variable; only that declaration was removed. Werror and all ownership/release guards were retained. Each original failure and successful retest is preserved in governance.

Fresh native config selected 3290 kernel objects, including all **50 RTL + 5 required native i915/DRM owners**. Those 55 objects compiled and linked with ld-r on HP. The subsequent **full native GENERIC dependall and final kernel link completed exit0**, including debug artifacts. Final source-hash, amd64 ELF and link-map ownership checks PASS. Final kernel has zero undefined symbols.

- Kernel: `diagnostic-a06/obj/netbsd`, 29689696 bytes.
- Kernel SHA256: `1aabcdee27654413382a1497e52e27b4ae4f4cd031ba478a47a233198fe4fbb4`.
- Map SHA256: `dd84c24ba71ca6c0a22f3878fb832168e82d5e6eaeea98c84752fb75354f7101`.
- Full native log: `a07-full-kernel.log`.
- Terminal native receipt: `a07-full-kernel-status.json`.

[Full native build report and retained failures](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/main/docs/HP_NATIVE_DIAGNOSTIC_20261023.md).
[Published full-kernel receipt](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/main/docs/evidence/HP_NATIVE_FULL_KERNEL_20261023.json).

## Safety and remaining acceptance

The private kernel combines pinned NetBSD GENERIC native i915 with project diagnostic patches and current RTL50. It is **not** proof of full modern Linux323 i915 semantic/DRM/TTM parity or working display/WLAN/PM.

No kernel was copied to a boot path, installed, selected or booted. EFI, boot.cfg, radio and old source/worktrees were not changed. Actual readback still reports `netbsd.v1-f77-linux-efuse-map-20260926`. The stage remains ineligible for install and boot. Read-only boot-menu inspection found F77 default and F16.2/safe-textmode recovery entries; that is not a physical recovery drill or stock-image proof.

Before any experimental boot: establish independent early-console capture and physically exercise F77/stock fallback. Then actual KMS display, PCI DMA/IRQ, WPA2 encrypted traffic and PM/recovery need separate verified acceptance. No background build remains after this terminal result.

The documentation commit following the tested source revision changes documentation only; the exact compiled source remains the revision above. **SOURCE_SYNCED and NATIVE_DIAGNOSTIC_LINKED do not mean INSTALLED, BOOTED, PHYSICAL_KMS_PASS or WLAN_PASS.**
