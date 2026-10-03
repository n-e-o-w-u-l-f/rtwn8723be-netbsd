# RTL8723BE source/lifecycle checkpoint — 2026-10-03

Status: IN_PROGRESS / NOT NATIVE-BUILT / NOT HARDWARE-TESTED.

## Actual source changes
- `1b5d3bbe33477039e8f7f38ba3d9a5149a16b354`: `rtwn8723be_linux_adapter_start` enters RUNNING and sets started only after `mark_hal_start` succeeds; failure leaves RX_CONFIG for explicit recovery, not false success.
- `e36edef44b93f138a22ea3857cd1766d7073d41e`: `rtwn8723be_linux_probe` now refuses a repeated probe in any non-IDLE or started state before resetting ownership flags, preventing prior PCI/DMA resource state from being discarded.
- `ef93cd909682cc60249e791d14f04aa38eacc28a` and `b524f595e0561c4d13d748a6e0c6cab837752add`: original strict C11 lifecycle test extended with failing/successful final-start callback cases and non-IDLE re-probe guards; exact test source GitHub-readback confirmed. Published tests are NOT yet proven to execute successfully.

## Verification and distinct infrastructure blocker
- `70019b9994f8365b5c1221a32d8014342b4043da`: new GitHub Actions workflow `.github/workflows/portable-c-regressions.yml` requests actual C11/UBSan tests of lifecycle/RX/TX. GitHub created runs, but repeated runs (e.g. 37132686703 and 37132825430) finished FAILURE in seconds with **zero reported job steps**. Fetching the former job logs returned BlobNotFound (404); check-run metadata had two annotations that the available fetch route cannot retrieve. Precise cause UNKNOWN. No evidence of compiler/test failure or test pass. Do not blindly rerun, attribute failure to source, change runners to evade a provider restriction, or claim tested.
- Source revisions and tests fetched/read back match the published GitHub objects; this is source verification only. The local validation container lacks GitHub DNS resolution, so it did not obtain byte-exact source through Git directly.

## Unchanged completion blockers
- Native `rtwn8723be_native.c` probe still preflights ENOSYS with missing lifecycle callbacks; its previously safety-denied PCI PM restore/W1C correction remains OPEN. H2C production implementation, PHY-PG compiler correction, BB test sync and various other missing PHY/RF, firmware, net80211/BT/security, runtime and PM callbacks remain OPEN; actual net80211 device/runtime, kernel object/link, HP traffic and error recovery unverified.
- Intel i915 project main was independently observed at `b8101ecc54bf8f8970f44937bdcfaf40ecc26a52` in this continuation; no i915 source, overlay or candidate was changed in this step. i915/DRM/TTM closure and HP black-screen resolution remain OPEN.
- F77 recovery kernel and existing six-edit i915 overlay untouched. Canonical oversized governance `LAST_TASKS.md` update remains a previously externally denied operation; this project-local handoff does not claim LAST was modified.

NEXT: inspect the actual GitHub Actions annotations/provider status through an authorized supported route; if CI is unavailable, use a genuinely available independent test environment for *these* unsuppressed tests, not previously safety-denied equivalents. Only after verified tests advance guarded probe cleanup, net80211/rfkill integration, H2C and complete RF identity/lifecycle, plus separate i915 dependency closure and source-pinned native kernel build.
