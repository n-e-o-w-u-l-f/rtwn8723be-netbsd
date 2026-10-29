# RTL8723BE NetBSD: ifstop failure-state defect (source only)

Date: 2026-10-12. Branch: `wip/hp-rtl-runtime-48-merge-20261010`.
State: **DEFECT CONFIRMED FROM SOURCE; PRODUCTION CORRECTION DENIED; PHYSICAL CRASH ROOT CAUSE UNKNOWN.**

## Exact observed source

`src/rtwn8723be_net80211.c`, unchanged Git blob `63efe291518d5909bc23ce394d1c6e3091c05ca1`, function `rtwn8723be_n80211_ifstop`, clears both `IFF_RUNNING` and `IFF_OACTIVE` and stops the ifnet timer **before** it checks whether the Linux-order hardware owner is RUNNING and whether `hw_stop` exists. It then propagates `EBUSY`, `ENOSYS` or the return status of `n->methods.hw_stop`. Consequently a failed hardware stop can leave active/partly initialized DMA/radio/interrupt ownership while exposing a software state that appears not running, even though the registered ifnet is retained.

Other source evidence: `rtwn8723be_n80211_ifstart` admits TX only when `(IFF_RUNNING | IFF_OACTIVE) == IFF_RUNNING`. `rtwn8723be_n80211_ifinit` sets `IFF_RUNNING` only after confirmed `R23BE_STAGE_RUNNING` and clears `IFF_OACTIVE`. `rtwn8723be_runtime_unregister` attempts `rtwn8723be_runtime_stop` before net80211 teardown and retains resources on error. The existing safe no-hardware-stop branch for exactly unstarted PROBED/RFKILL/etc. states must remain intact.

## Proposed invariant — NOT IMPLEMENTED

1. In the exactly unstarted/STOPPED lifecycle branch, mark `IFF_RUNNING` and `IFF_OACTIVE` clear and reset timer only after confirming that no active firmware/RX/TX engines exist.
2. For the RUNNING/uncertain branch, set `IFF_OACTIVE` **before** any potentially sleepable HW shutdown to block `ifstart` TX without lying about `IFF_RUNNING`.
3. Reject interrupted state or unavailable `hw_stop` with the original error, retaining `IFF_RUNNING` (if previously set), retaining `IFF_OACTIVE` quarantine and all backing resources. Do not report successful stop.
4. Call `hw_stop` outside `splnet()` (the existing 2026-10-12 earlier patch already handles that). On successful verified shutdown alone clear `IFF_RUNNING|IFF_OACTIVE` and stop timer.
5. Add a source regression with a negative fixture restoring old premature RUNNING-clearing, and verify actual HP NetBSD native compilation and safe runtime only after independent root/panic/recovery prerequisites.

The source-only defect is NOT evidence that the RTL50 user-reported **kernel panic** was caused by flag transitions. The crash still needs real DDB/crashdump and boot identity before a kernel test. No register trial-and-error or fabricated WLAN/association is allowed.

## Actual action and boundary

Attempted a narrowly scoped authenticated GitHub source update of `src/rtwn8723be_net80211.c` using its exact current blob SHA. The platform **refused the write before publication** with a safety rejection. Independent authorized readback confirmed the production source SHA **unchanged** at `63efe291518d5909bc23ce394d1c6e3091c05ca1`. This is `EXTERNAL_BOUNDARY` for that operation; do not retry the same effect through another transport, encoding, machine, account or shell.

FAILURE_FINGERPRINT: `GitHub update_file | WIP RTL net80211.c | external safety-check rejection before mutation | exact source sha 63efe291... | safe ifstop failure-state semantic correction`.

GOVERNANCE_REVIEW: `EXTERNAL_BOUNDARY`. Prevention: retain explicit separate source-diagnostic acceptance and block kernel image promotion; request genuine supported permission/review change before attempting the refused mutation. Continue independent reference-based i915 and RTL investigation that doesn't perform the denied update. No HP host access, compilation, install, boot or radio changes occurred.

## Frozen reference

NetBSD source `03d918f6d0e81fa05b8f1160eca0628ad39988a6`: `sys/dev/pci/if_rtwn.c`, `sys/net80211/ieee80211_node.c`; Linux source `fd179f8a05be3ccae366b9b96e176b51fbe54aab`. The target reference confirms RX node fallback to `ic_bss` for unknown frames, so `ieee80211_find_rxnode` returning NULL must not be assumed to be the cause of no beacon RX.
