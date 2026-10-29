# Private TX descriptor staging

Base 0cf285345ed2efe98a7cb8280d62eabb235bc2f2; source-only continuation.

Both ordinary and reserved-beacon descriptor encoders now write into a private
64-byte prepared_desc. The existing live descriptor snapshot initializes that
storage; map/span/next-pointer checks remain unchanged. A successful encoder
must leave OWN clear. Only then is the prepared descriptor copied into the
live ring, followed by packet PREWRITE, slot owner publication, producer barrier,
OWN publication, descriptor synchronization, producer advance and device poll.
On map or encode failure, the original rollback/synchronization remains intact;
no encoder can leave partial fields in the DMA-visible descriptor. This adds
64 bytes of automatic storage to the enqueue call; native stack/build validation
remains required. The old snapshot is retained for existing rollback invariants.

This separates descriptor preparation from the single-frame commit boundary.
It does NOT implement atomic whole-chain transmission. Packet maps, software
crypto, node/report tickets and all prepared descriptors must still be collected
under a bounded transaction owner before the first OWN bit is published.
Multi-frame m_nextpkt chains remain rejected by the previous fail-closed gate.
No fragmentation or full Linux-parity claim is made.

Verification: new source contract RED on baseline then GREEN, seven mutations
rejected (live encoder targets, absent/commented/early copy, inverted OWN check,
missing rollback). Expanded 25-test Python-only suite initially passed 24 tests.
The existing source_negative_guards control14 had a stale adjacency anchor
predating deferred-start initialization. Shortened only that anchor; the same
invalid early if_detach and expected failure diagnostic are preserved. Rerun
passes all17 negative controls. Final per-test results: 25/25 PASS. Both initial
failure and repair rerun are retained in evidence/HP_RTL_TX_DESC_STAGING_RESULTS_20261016.json.
The unchanged suite includes 37552 ring cases,64 admission combinations,5100 BTC
cases and the active fragmentation restriction. No C compiler was invoked.

Governance PRE/POST: state/events/HP-RTL-TX-DESC-STAGING-20261016.jsonl.
No HP command, source synchronization, install, boot or network change. F77 is
only the last observed recovery state. HP fast-forward EXTERNAL_BOUNDARY/NOT_RUN
is unchanged; no alternate executor retry and no paid runner. Native compile,
fault injection, WPA2/traffic, stop/restart, PM and recovery acceptance OPEN.
