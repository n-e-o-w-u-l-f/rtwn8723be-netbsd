# RTL8723BE unstarted post-registration probe unwind — 2026-10-25

## Objective and exact scope

This change extends the previously quarantined PCI-probe rollback from
pre-registration stages through the four **unstarted** checkpoints:

- `R23BE_STAGE_IEEE80211_REGISTER`
- `R23BE_STAGE_RFKILL`
- `R23BE_STAGE_IRQ_ESTABLISH`
- `R23BE_STAGE_PROBED`

The Linux-order callbacks are **still not enabled**. In particular
`register_ieee80211`, `init_rfkill`, `bt_prepare` and `dm_init`
remain unbound. This is a reverse-lifetime capability with conservative
entry validation, **not** a working PCI/WLAN adapter.

## Owner and resource ordering

`src/rtwn8723be_probe_unwind.h` implements the source-shared admission
and compensator broker. It requires an original PCI snapshot, mapped BAR,
unstarted/uninitialized hardware, no firmware readiness, no active requested
IRQ, coherent interrupt handles, and consistent net80211 and RFKill owners
according to the saved probe stage. The broker verifies that all three real
compensators exist **before invoking any of them**.

The native attachment wires this broker to actual NetBSD operations:

1. `rtwn8723be_netbsd_disestablish_irq`: permanently mask/disestablish
   the hard/soft interrupt handlers, release the interrupt allocation, and
   verify that no interrupt handle or IRQ desire remains
2. `rtwn8723be_rfkill_native_fini`: deactivate the callout, wait for the
   queued worker to drain in sleepable thread context, destroy the queue,
   then release its timer/mutex
3. `rtwn8723be_net80211_unregister`: stop the **unstarted** interface,
   detach net80211 and the registered ifnet using the existing valid
   register/unregister API path
4. Only after (1)–(3) all return `0`, retain the existing reverse teardown:
   BT MP drain, H2C close, TX/RX ring freeing, DMA tag release, ASPM/PCI
   restore, BAR unmap, and final PCI config/power rollback

Errors are **first-error fail-closed**. A per-softc monotonic journal
(`NONE → IRQ → RFKILL → NET80211`) advances only after each actual owner
callback has returned success **and the native wrapper has verified its
postconditions**. An unsuccessful compensator skips all later owners and
**all underlying PCI/MMIO release**. The retained stage and PCI snapshot
ensure `native_detach` returns `EBUSY`, rather than acknowledging a
partly released device. A later explicitly serialized recovery attempt
can resume at the first unfinished compensator: the snapshot must match
the journal and independently prove already-released resources are absent.
Inconsistent or fabricated progress is refused, not inferred from a NULL
handle. On successful full PCI rollback the journal resets to `NONE`.

The preflight expressly rejects `RUNNING`, `STOPPING`, `STOPPED`, and
all failed pre-`RUNNING` startup stages: those paths need the separate
real DM/BTC, firmware and hardware stop/recovery owners.

## Executed source evidence

On 2026-10-25 the current branch at
`57cee09303f37bf80d83f23d3c5282c8cd26cd3a` was cloned into a
disposable temporary directory on **legion / Linux x86_64**. **Fourteen
portable regression scripts** completed with exit 0:

- `test_port_closure_inventory.py`
- `test_source_negative_guards.py`
- `test_native_probe_admission.py`
- `test_post_registration_probe_unwind.py`
- `test_net80211_unstarted_rollback.py`
- `test_kernel_source_integrity.py`
- `test_kernel_shadow_manifest.py`
- `test_irq_shutdown_race_contract.py`
- `test_pre_running_recovery.py`
- `test_dma_mem_unwind.py`
- `test_rx_dma_bounds.py`
- `test_net80211_unpublished_registration.py`
- `test_net80211_owner_storage.py`
- `test_net80211_rx_no_phy.py`

The new regression compiles the actual production C11 broker under
`-std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=undefined` and
tests all four admissible checkpoints, NULL/invalid ownership, rejected
running/failed-start states, all three injected compensator failures,
strict IRQ→RFKill→net80211 order, no downstream effects after a failure,
successful resumed unwind for every injection point, and rejection of
corrupt/stale journal states.
The source-contract portion validates the native adapters and physical
resource-release ordering.

This is **portable host evidence**, not a NetBSD native object/kernel link,
nor proof of actual HP workqueue/IRQ races, media detach or WLAN behavior.
The HP native 48-object link remains OPEN; the last verified private
full kernel link is still the historical Shadow H 47-object build.
GitHub Actions infrastructure has historically failed before executing
job steps; host regression success is not reported as CI success.

## Remaining gates

1. Run the complete native 48-source configuration/object/link gate in a
   fresh isolated HP NetBSD 11.0 shadow and retain compiler/link evidence.
2. Add native fault-injection tests at each partially acquired resource
   checkpoint, especially concurrent RFKill worker/callout, interrupt
   shutdown and net80211 unregister under NetBSD `splnet` semantics.
3. Close the real NetBSD method providers and start/stop ownership before
   binding any missing Linux lifecycle callback.
4. Only after hardware-safe admission and stop/recovery evidence can
   real device attach, scan, association and traffic tests begin.

F77 `/netbsd`, `/boot.cfg`, all boot entries and i915 remain untouched;
do not boot F16.0, F83, F84 or any experimental shadow build.
