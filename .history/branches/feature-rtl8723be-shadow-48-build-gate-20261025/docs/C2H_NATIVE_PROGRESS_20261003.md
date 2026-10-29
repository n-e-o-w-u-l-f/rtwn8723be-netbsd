# 2026-10-03 C2H RX native continuation

STATUS: SOURCE-COMMITTED / ISOLATED-HOST-TESTED / NETBSD-NATIVE-BUILD-OPEN / HP-TEST-OPEN.

## Committed source delta
- `src/rtwn8723be_c2h.h/.c`: pinned Linux `rtlwifi/wifi.h` v1 firmware-event envelope, TX-report v1 fields and synchronous fail-closed event router. TX reports, rate reports, BT_INFO and BT_MP require real callbacks; unknown/debug/TXBF are no-op as in frozen Linux; v2 format returns EOPNOTSUPP. Existing H2C mailbox creation denial remains a distinct blocked task and was NOT retried.
- `src/rtwn8723be_c2h_native.h/.c`: validates RX report kind, CRC/ICV, packet length, payload offset, reported ID and sequence before routing into the typed C2H handler table. Does not retain RX DMA pointers.
- `src/rtwn8723be_rx_binding.h/.c`: gives the RX ring one stable dispatch.arg for NetBSD net80211 frames and typed C2H events, and fails closed if registration is absent, a binding is already active or mandatory TX/RA/board-specific BT handlers are missing. Corrected previous incorrect header wording that suggested the typed adapter had the raw RX callback signature.
- Opt-in `config/files.rtwn8723be_native` now lists 22 C translation units, including C2H native and shared RX binding. All new source and header blobs and manifest were read back from GitHub; existing native PCI attach does NOT yet instantiate/bind these structures, so interrupts are NOT authorized for the unfinished driver.

## Actual test evidence
- Portable C2H production .c reproduced byte-for-byte: host `git hash-object` = `1e9a31ee3af0bf455d837e80634ad07d79904d9f` equals the published GitHub blob. Strict C11/Wall/Wextra/Werror/pedantic/UBSan compiled and executed independent decode/route harness with valid v1 TX/RA/BT, missing handler, truncation and v2 rejection, exit 0 (`C2H_DECODE_AND_ROUTE_HOST_C11_UBSAN_OK`). Host test used an API-equivalent minimal header, not the original committed header; do not claim byte-identical header or published Python-test execution.
- Independently compiled and executed an extracted native C2H receive function with mock NetBSD RX packet structures and real portable C2H decoder, exit 0 (`C2H_NATIVE_BRIDGE_HOST_C11_UBSAN_OK`).
- Independently compiled and executed the current shared RX-binding functions with mocked NetBSD structures, exit 0 (`RTL_RX_BINDING_HOST_C11_UBSAN_OK`). Published `tests/test_c2h.py` (extended), `tests/test_c2h_native.py` and `tests/test_rx_binding.py` contain regression harnesses but the exact committed Python scripts have not yet been executed. Previous GitHub Actions job failures before any recorded step remain an unresolved CI infrastructure blocker; no claim of Actions success.
- Native NetBSD object compilation, link, DMA/IRQ concurrency, real net80211 registration, actual TX-status tracking and runtime HP hardware results NOT established.

## Safe next dependencies
1. Resolve prior externally denied H2C mailbox production implementation and PCI PM rollback correction through real authorization, without equivalent-tool rerouting; complete and test rfkill, net80211 and 16 lifecycle callbacks, full PHY/RF/BT/security/power interfaces and error unwind.
2. Implement real TX-report sequence/ACK ownership and rate/BT C2H consumers; their absence currently intentionally blocks RX-binding initialization.
3. Integrate RX-binding ownership into the native PCI probe in correct register/rings/IRQ lifecycle order, only AFTER complete reverse detach and failure unwind; run pinned NetBSD isolated candidate build and fault-injection tests.
4. Parallel i915 repo remains at baseline `b8101ecc54bf8f8970f44937bdcfaf40ecc26a52` in this step, without source edits; full 323-unit DRM/TTM dependency closure and HP Cherryview KMS display tests OPEN. HP direct access remains unverified this turn. F77 and the existing six-edit i915 overlay were not modified.

Canonical Agent-Governance LAST_TASKS remains at its prior verified state: its oversized in-place update path was previously externally refused. This scoped project handoff does not claim canonical synchronization.


## 2026-10-09: typed MP C2H consumer and fail-closed RX admission

- Native `rtwn8723be_btc_mp_native_c2h(void *, const struct
  rtwn8723be_c2h_event *)` is a real typed RX callback adapter for the
  per-device MP receiver. Its implementation delegates to the existing
  decoder/admission/completion logic; it neither synthesizes a reply nor
  activates a suspended MP channel. Added to the actual MP kernel object
  and exported by the existing header, not by a mock.
- Coexistence-board `rtwn8723be_rx_binding_init()` now requires a
  fully initialized BTC broker and initialized **active** MP channel,
  in addition to non-NULL BT_INFO and BT_MP consumers, before it publishes
  an RX dispatch context. The lifecycle owner must serialize this
  preflight and callback lifetime against STOPPING and IRQ/softint draining;
  this preflight does not by itself implement that ownership.
- `tests/test_rx_binding.py` gains negative-state scenarios for BTC
  uninitialized, MP uninitialized and MP inactive. This compiler-invoking
  test is **not run here** because target compilation/tests are restricted
  to HP. `tests/test_port_closure_inventory.py` now statically guards the
  production callback ABI and activation-before-publication order.
- Actual Spinnennet source-only inventory/check succeeded (exit0)
  at RTL GitHub `22a4d0fe542844c4ead2a46bda6f7ef31bda6418`:
  declared53/bound48/missing5; native manifest42; closure OPEN.
  Neither a native NetBSD object build nor hardware C2H/RX/IRQ verification
  occurred. Existing real init/start/stop/DM/provider and net80211 gates
  are **not** bypassed. F77 recovery boot remains last verified on
  2026-10-06, not a newly observed physical state.
