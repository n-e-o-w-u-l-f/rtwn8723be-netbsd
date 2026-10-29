# Lossless branch ancestry consolidation — 2026-10-29

Step: HP-RTL8723BE-BRANCH-CONSOLIDATION-20261029-A01
State: PRE_RECORDED; POST requires ref and ancestor verification.

## Frozen observed refs before publication

- Previous main: `569d0d16cc307bfbef40aef9fd7b553322cadb1f`
- Active source baseline (stacked PR #31): `67bc78a945c3b20d5abb594bd8b64441ddce9c08`
- Divergent WIP native HP line: `438931eec65d6cf145f5ea2304e4bf12b9826ddd`
- Divergent F77 parity line: `e1686def62c8939c15b598b541e1e7f4760e32f8`
- Divergent Shadow-48 build-gate line: `3af8b86c12302ff88efd9d246c27c4d092f4ed41`

All other 29 feature branch heads and old main were independently compared and found ancestral to PR #31's head. Divergent history cannot be discarded or replaced with an `ours` merge.

## Source and history integration contract

The active root source tree is the exact PR #31 tree `26661306c5ae9899957b4df630abad5f135c9f4a`. It is extended **only** with `.history/` evidence and three complete branch snapshots.

| Divergent branch | Exact source-tree SHA | Snapshot directory |
| --- | --- | --- |
| WIP HP RTL 48 | `8ca5a38a5c5724b23d225977818349d1958552c6` | `.history/branches/wip-hp-rtl-runtime-48-merge-20261010/` |
| F77 Linux-tail parity | `3e0a953e31d6a98530782e4b95c2caa45429b4b3` | `.history/branches/work-f77-linux-tail-parity-20260929/` |
| Shadow-48 isolated build gate | `72620556c3dff0a4e3e004b76d8b23913c132b9e` | `.history/branches/feature-rtl8723be-shadow-48-build-gate-20261025/` |

The merge commit carries all four commits as first/additional parents, so **every historical commit** becomes reachable from main, while **every divergent head's complete file tree** is also reachable directly in the active checkout.

**IMPORTANT:** This is lossless HISTORY and SOURCE-SNAPSHOT consolidation; it is NOT a semantic conflict resolution, kernel link, native test or hardware acceptance. Older alternative implementations must be reviewed file-by-file before being activated; never silently overwrite the modern source. Archived snapshots are not active driver compilation inputs.

## Preconditions / safe state

- No branch deletions, no force pushes, no rewrite or squash.
- Existing kernel F77, HP files, boot configuration, i915 and physical WLAN untouched.
- Compare branch heads and expected old main before moving the ref; reject concurrent changes.
- Verify exact Git parents, embedded snapshot tree SHAs and reachability of all 33 preexisting branch heads.
- Only after positive verification create `debug` and `test` from consolidated `main`.

## Next technical work

Review unique Shadow-48 native build-gate files, WIP-only driver changes and F77 parity notes, and assess semantic forward-port candidates; run relevant host-approved source checks and native HP regressions before promoting any older behavior into the active source. Real net80211 TX queue consumer and 3 missing Linux callbacks are still open.
