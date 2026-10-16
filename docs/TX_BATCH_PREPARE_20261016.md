# Bounded BE DMA batch preparation primitive

Base: d5b1ec5ad707bdee29f8378afea77d73cb5e1712. COV-RTL-014/009 IN_PROGRESS.

New additive API rtwn8723be_tx_native_enqueue_batch accepts 1..16 independent
already-encrypted, linear mbufs, per-frame descriptor parameters and owners.
It targets only BE, not management/command/beacon. The caller must hold the
existing TX lock against all other enqueue/reclaim/stop/reset/detach operations
for the entire synchronous call, and prove running lifecycle admission.
Caller-owned workspace stores16 private descriptors (1024 bytes); no heap
allocation or large automatic descriptor array occurs inside the API. Future
runtime storage allocation/lifetime is NOT yet wired.

All input/alias/owner-pair checks occur before loading the first map. Each slot
must be free, have an unloaded map and no stale owner callback; descriptor OWN
is read with paired CPU/device DMA sync. Then the packet map is loaded NOWAIT,
checked for one segment, exact size and DMA32 span, and encoded privately.
Any error unloads only successful maps in reverse order. Ring descriptors,
producer, slot ownership and caller mbufs/references remain unchanged on error.
No packet PREWRITE occurred on this abort route; no release callback is called.

Only after every entry is prepared does commit PREWRITE all packets, copy all
prepared descriptors, publish every owner, issue a producer barrier, set/sync
OWN for every descriptor, advance the producer and poll BE once. No operation
returning an error remains in this phase. This is a software preparation and
failure-unwind guarantee, not proof of atomic radio transmission or immunity
to device/reset faults. Descriptor publication follows the existing native
map/sync/owner/OWN convention. Caller serialization is mandatory.

The API is intentionally NOT connected to net80211. Existing single-frame
and beacon paths are unchanged. Fragmented MSDUs remain fail-closed. Next:
prepare every crypto/linearization result and node/report ticket under one
bounded owner, provide runtime workspace, invoke this API under datapath lock,
and release all caller-owned resources on any prepublication failure. Native
fault injection/build/stack/IRQ validation must precede lifting the guard.

Validation: source contract rejects old baseline, passes new implementation;
eight source mutations rejected. Independent Python ownership model covers
11136 combinations of1..16 entries,16 ring starts and slot/load/span/encode/OWN
failure positions or success. Model is not execution of the native C. All26
selected source-only Python gates PASS including existing closure/17 negatives,
fragment restriction,37552 ring cases,64 admission cases and5100 BTC cases.
Raw results: evidence/HP_RTL_TX_BATCH_RESULTS_20261016.json. No C compiler run.

Governance PRE/POST: state/events/HP-RTL-TX-BATCH-20261016.jsonl. No HP command,
source sync, kernel installation, boot or network change. EXTERNAL_BOUNDARY /
NOT_RUN on HP fast-forward remains effective. F77 only last known recovery
state. No paid runner. Full native WLAN/WPA2/PM/recovery acceptance OPEN.
