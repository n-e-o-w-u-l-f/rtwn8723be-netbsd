# HP-native i915 + RTL8723BE source synchronization

**Status:** SOURCE PREPARED / HP NOT_YET_EXECUTED / LOCAL FLEET UNKNOWN.
**Target:** HP TPN-W121, NetBSD 11 amd64 (the only authorized native driver compiler/kernel build/physical test host).
**No kernel installation, bootloader change or WLAN/KMS activation.**

## Canonical inputs (verified GitHub on 2026-10-23)

| Driver | Active development branch | Verified HEAD before this sync helper |
|---|---|---|
| i915 Cherryview/Braswell | `work/hp-native-drm-stage-replay-20261015` | `8a164f10c45c3d66f7648376ccd2177c8dfe81ba` |
| RTL8723BE | `wip/hp-rtl-runtime-48-merge-20261010` | `799a0fe2877f3210e8a3a981db82654795b547d0` |

**Important:** The RTL HEAD advances when this helper and report are published. The helper reads both current GitHub refs and verifies each staged checkout against the SHA observed immediately before cloning. It does not mistake the repository's older `main` for its active development branch. GitHub is the currently verified central publication point, NOT evidence that local worktrees on the HP or other computers are current.

## Actual host/tool preflight

The current ChatGPT SentinelX tool lists **Legion only** as operational. The HP is not directly enrolled with a callable SentinelX agent in this session. Historical strict SSH via Legion to HP was positively verified on 2026-10-21, but a later **caller-side provider refusal of remote SSH execution** prevents treating that prior success as authorization for new equivalent commands or a reason to reroute around a denied effect. A Tailscale online peer is not an authenticated command executor.

Therefore the helper was **committed for direct, owner-authorized execution on the HP**, not secretly run through Legion. No current HP Git worktree, live kernel, boot menu, i915 device or WLAN hardware status has been checked here. Avoid trying the equivalent denied remote effect via another script, host, identity or tool.

## Safe preparation and native execution on the HP console

If the user's HP session has Git and GitHub public HTTPS access, enter these commands **on the HP itself**. The initial clone uses a *new* directory; do not use a directory already containing work. All commands stop on failure:

```sh
git clone --single-branch --branch wip/hp-rtl-runtime-48-merge-20261010 \
  https://github.com/n-e-o-w-u-l-f/rtwn8723be-netbsd.git \
  "$HOME/rtl-hp-sync-bootstrap"
sh "$HOME/rtl-hp-sync-bootstrap/tools/hp_driver_source_stage.sh" --audit
sh "$HOME/rtl-hp-sync-bootstrap/tools/hp_driver_source_stage.sh" --stage
sh "$HOME/rtl-hp-sync-bootstrap/tools/hp_driver_source_stage.sh" --native-test
```

The script path is [`tools/hp_driver_source_stage.sh`](../tools/hp_driver_source_stage.sh). It refuses execution unless `uname -s` returns NetBSD, `uname -m` returns amd64, and the hostname matches `hp-tpnw121`. It reads only the exact two development branches, verifies live `git ls-remote` SHAs before each fresh clone, and aborts on races. It does not fetch or update *existing* local repositories in `--audit` mode. It finds named i915/RTL checkouts in two levels under `/root` and `/home/andreas`; optional extra absolute paths can be supplied to `--audit`.

Under the user's home directory the default stage is `$HOME/hp-driver-source-stage/{i915,rtl}`. The second clone never overwrites an existing destination, even if the earlier run failed partway. Set `HP_DRIVER_STAGE_ROOT` to a different absolute path only if an existing stage needs to be preserved.

The native `--native-test` gate requires a **clean staged RTL checkout**, matching GitHub HEAD, the NetBSD HP host, `python3` and `cc`. It runs the source-only negative suite and then the compiled C11/UBSan allocator mock fixture **on HP**; writes the verbose compiler/runtime log outside the checkout under `$HOME/hp-driver-source-stage/rtl-native-test.*`. A PASS is a native **userland failure-injection fixture**, not actual DMA hardware or a complete kernel.

## Decision table after HP readback

| Observed local status vs current GitHub | Required action |
|---|---|
| MATCH + CLEAN | Stage verified. Native isolated tests may begin. |
| MATCH + DIRTY | Preserve local edits. Inspect source and untracked files; do not overwrite. |
| LOCAL_AHEAD | Preserve local commits; review and publish safe local changes through authorized non-force Git before integrating. |
| REMOTE_AHEAD + CLEAN | After separately approved remote fetch/branch verification, local `git pull --ff-only` can advance an existing checkout. |
| DIVERGED | Stop automatic integration. Compare both histories and agree on review/merge branch before changes. |
| ANCESTRY_UNKNOWN_REMOTE_OBJECT_NOT_FETCHED | Cannot infer ahead/behind. Keep both copies; independently fetch when permitted, then re-evaluate. |

A fresh isolated clone is only an **additional current GitHub copy**, not a forced alignment of all historical worktrees or the NetBSD `/usr/src` tree. Treat locally newer unpushed work on Legion/HP/BMAX/PHOBOS/Spinnennet/Pi-hole as UNKNOWN until individually inventoried by legitimate direct executors. No force push, `git reset --hard`, `git clean`, silent stash, unreviewed merge or private-key movement.

## Next actual driver engineering gate

Once the HP reports the real staged HEADs and `--native-test` log, reconcile its existing source and pinned `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`, then produce a **native HP-only diagnostic compile** of the composed kernel. Native i915 DRM/GEM/PPGTT closure and RTL TX/RX DMA/IRQ/WPA2 remain open. Do not install or boot an experimental KMS kernel before independent early-console capture and a physically tested F77/stock recovery path.

**Truth boundary:** SOURCE_PREPARED on GitHub does not mean TRANSFERRED_TO_HP, NATIVE_BUILT, INSTALLED, BOOTED or VERIFIED.
