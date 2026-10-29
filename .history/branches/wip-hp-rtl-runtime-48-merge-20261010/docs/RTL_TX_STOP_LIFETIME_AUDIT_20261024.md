# RTL8723BE PCIe TX reclaim/stop ownership — source-only continuation (2026-10-24)

Status: **SOURCE_REVIEWED_PARTIAL / DOCUMENTED; HP_NATIVE_NOT_RUN; WLAN_NOT_ACCEPTED**.

## Auftrag, gesicherte Grenzen und Quellen

This checkpoint concerns only the **RTL8723BE PCIe WLAN** Linux-to-NetBSD port for HP TPN-W121 (PCI ID `10ec:b723`, subsystem `103c:81c1`, NetBSD 11 amd64). No i915/DRM implementation is in scope. The reference remains `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`, NetBSD `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.

Source read from the existing WIP branch at **`ec42c16969eb65839b27063c97db37b6cba13f81`**; these are GitHub source inspections, *not* fresh native HP execution:

| Component | Exact observed blob SHA | Source responsibility |
|---|---|---|
| `src/rtwn8723be_tx_native.c` | `9c6c9986a07254c56644f9e5dd265bc95d163e91` | TX enqueue and descriptor reclaim |
| `src/rtwn8723be_netbsd.c` | `73e74c1c7fe22432b1285ee676f81d534b041498` | PCI/DMA ring reset and IRQ ownership |
| `src/rtwn8723be_f16_1_dma.c` | `790e4c3cbd46cf6405b689023087d94e5b481050` | DMA slot ownership, release and ring free |
| `src/rtwn8723be_datapath.c` | `87b9c4c6ced82519403a8dee27114f28c0f3f215` | TX lock, reclaim callback, producer admission |
| `src/rtwn8723be_net80211_tx.c` | `76c9f155ed35207aa00b41c3efe7ca929310c610` | net80211 mbuf/node, TX report tickets and stop |
| `src/rtwn8723be_runtime.c` | `8a58ede4bf84ca30bdf132ce22977b24836d6e46` | Lifecycle stop, shutdown, resume and unregister |

Current canonical source of truth is this WIP branch, not `main`'s separate 48-unit history. The historical full native combined diagnostic kernel was built from older RTL `a06a74eec7ffdeca8f472cc5c9a28d89d4b2cd04`, not this HEAD. The latest native TX-rollback fixture on HP tested 20 C11/UBSan cases and four compiled negative controls, but it did not prove actual DMA, concurrent IRQ, WLAN association, suspend, or detach.

## Source-observed ownership transitions

1. **Normal reclaim:** `rtwn8723be_datapath.c:rtwn8723be_dp_tx_done` takes `dp->tx_lock`, calls `rtwn8723be_tx_native_reclaim`, updates counters, releases the lock, then calls `dp->tx_complete` only after unlocking. The reclaim owner validates ring index, descriptor extent, loaded packet map and its 32-bit DMA extent; if the hardware OWN bit remains set it re-arms descriptor sync without releasing the mbuf. Otherwise it performs packet `BUS_DMASYNC_POSTWRITE`, `bus_dmamap_unload`, and `rtwn8723be_f16_1_tx_slot_release(slot, true)` before recycling the linked descriptor. The reserved beacon queue retains consumer index zero.
2. **Owner callback:** `rtwn8723be_f16_1_tx_slot_release` atomically clears `m`, `tx_owner`, and `tx_release` before calling the prior callback. For net80211 TX-report packets, `r23be_tx_report_dma_release` acquires `report_lock`, clears `dma_pending`, retains the packet while awaiting air-report/timeout, and retires terminal tickets once. Descriptor completion is **not** treated as a positive air ACK.
3. **Stop admission:** `rtwn8723be_runtime.c:runtime_shutdown` disables net80211 TX and datapath admissions before Linux-ordered stop / BT halt; it then attempts hardware poweroff and interrupt disestablishment. With verified poweroff it invokes `rtwn8723be_netbsd_reset_trx_ring`, retires BTC and restores ASPM. `rtwn8723be_runtime_unregister` refuses net80211 unregister on a nonzero shutdown result.
4. **Ring teardown:** `rtwn8723be_netbsd_reset_trx_ring` rejects active IRQ handles and resets RX descriptors, then completes each outstanding TX mbuf with `POSTWRITE`, map unload, `tx_slot_release(..., false)`, and descriptor rebuild. `rtwn8723be_f16_1_tx_ring_free` likewise attempts map cleanup before owner release. `rtwn8723be_net80211_tx_stop` terminalizes report tickets, but defers freeing DMA-pending tickets; `rtwn8723be_net80211_tx_fini` rejects remaining `pending_reports`.

These are **source-path observations only**. The contract “hardware DMA actually quiesced before POSTWRITE/unload and callback release” is not established solely by checking IRQ handles, an in-memory poweroff flag or a successful link.

## Open proof obligations (do not auto-classify as bugs)

| Priority | Invariant to prove / falsify | Required evidence |
|---|---|---|
| P0 | DMA engines/bus master are really quiesced and outstanding IRQ/softint/work callbacks drained **before** ring reset, packet POSTWRITE/unload and owner callbacks | Pinned Linux/NetBSD call-path audit, native instrumented ordering/fault injection; later bounded HP PCI/IRQ evidence |
| P0 | Lock order `dp->tx_lock` -> TX release callback -> `report_lock` does not conflict with any `producer_lock`/report callback/stop path; callbacks cannot outlive owner state | Whole-call-graph lock map, preemption and stop/reclaim concurrency harness, witness of safe lock lifetime |
| P0 | All reclaim failures quarantine corrupt slots without premature callback or DMA free; partial reclaim preserves accurate counts and does not duplicate completion | Fault injection for NULL/zero/oversized/segmented maps, OWN retained, partial EIO and repeated IRQ/reclaim/stop |
| P1 | `TX report` success/failure/timeout and pre-start/failed-start/normal shutdown each release node/mbuf **exactly once**, with correct `completed` status | C11+UBSan native HP fixture with intentionally delayed TX-report and stop/restart interleavings; negative compiled mutants |
| P1 | Stop/failed-start recovery is error-preserving: nonzero ring reset/BTC retirement/ASPM failure cannot lead to detached live DMA; restart cannot admit unresolved prior tickets | Native owner-and-unwind harness and exact NetBSD kernel ABI object/link proof |
| P1 | RX rearm and TX reset failure paths are safe under malformed maps and preserve recovery state | Native fault injection and release ordering; avoid the previously provider-denied RTL0086 RX source-write effect |

Source risks are hypotheses until tests or traces prove them. No new low-level bit/register value should be invented, and no runtime patch should be declared accepted from this review alone.

## Fortsetzungsplan (HP vor GitHub-Ausführung)

1. **Current HP read-only gate:** once a legitimate HP executor becomes available, verify the running kernel, actual NetBSD version, owner, existing clean source checkout, `git status`, WIP HEAD and all retained recovery files. Do not assume the historical F77 readback is current. Do not retry or tunnel around the Desktop Commander monthly quota refusal.
2. **Narrow source tests on HP:** first compile/run the existing `tests/test_tx_enqueue_null_c11.py`, `tests/test_tx_queue_lifetime.py`, `tests/test_runtime_dma_reset_owner.py` and related TX/IRQ tests; then add an exact-current-production C harness for STOP versus RECLAIM versus REPORT and negative mutants without changing actual PCI registers.
3. **Ownership repair only if proven:** tie a minimal RTL-only patch to the evidence above; keep physical DMA disabled for source-model work. Preserve existing source and other branches. No unrelated i915, broader network, boot or firmware changes.
4. **Build on HP only:** verified NetBSD 11 object/whole private kernel link using an immutable exact source SHA and separate nonboot output; preserve Kconfig, logs, object hashes, complete ELF identity and source readback. Previous built artifact does not prove HEAD.
5. **Recovery acceptance before hardware:** establish an independently recoverable safe boot image, offline physical console/log capture and explicit TESTREADY review. Old RTL50 panic remains unresolved; never overwrite `/netbsd` or silently select an experimental kernel.
6. **Physical RTL acceptance:** after source/ABI/lifecycle gates, verify PCI match, firmware handshake, DMA+IRQ, *received* beacons and BSS entries, AUTH/ASSOC, WPA2-PSK four-way exchange, IP+DNS and sustained bidirectional traffic; then repeated stop/restart, failed-start, RFKill, suspend/resume and detach. Redact credentials and packet secrets.
7. **Publication:** commit each validated RTL change from the HP when permitted; push to the active WIP GitHub branch without force, independently compare remote HEAD with local commit, update the full-scope coverage/evidence ledger and governance PRE/POST. Do not merge diverged `main`/WIP automatically or invoke paid hosted CI.

## Execution and publication boundary (2026-10-24)

The Desktop Commander fleet overview reported BMAX-B6, Legion, Pi-hole, Spinnennet and HP online; Phobos and several stale duplicate registrations were offline. This is a connectivity **listing**, not authenticated filesystem or runtime inspection. A detailed six-host developer-root audit dated 2026-10-23 exists in private governance `state/inventories/hp-two-driver-direct-20261023.md`; it records several divergent local checkouts and preserves their dirty/unpublished changes. It is historical evidence only. This session's HP connector explicitly refused commands due exhausted monthly quota, instructing no retries/reconnects. No LAN endpoint was modified or used as an alternate executor.

This document is a **GitHub-only source-review and test-plan publication**. In this step: production source NOT_CHANGED; new tests NOT_RUN; native HP build NOT_RUN; hardware/firmware/DMA/IRQ/WPA2 NOT_RUN; i915 NOT_CHANGED; boot/EFI/`/netbsd` NOT_CHANGED. Parent full-port acceptance remains **IN_PROGRESS / NOT_COMPLETE**.
