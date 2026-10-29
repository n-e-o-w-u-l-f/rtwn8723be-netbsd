# Batch workspace and datapath serialization

Base1010e7e08c88fa0e0849e85083b4687ae76dd87d. Full port IN_PROGRESS.

The datapath now embeds its own rtwn8723be_tx_batch_workspace. In the existing
runtime this is heap-owned: runtime_init allocates sizeof(*r) with kmem_zalloc,
and r embeds datapath. No1024-byte descriptor array is put on the TX call stack,
and no new per-send allocation or independent cleanup path is introduced.
Prepare/unprepare zero the owning structure; runtime_fini refuses to free it
when datapath unprepare reports live TX or IRQ resources. External caller
exclusion of unprepare remains mandatory, as with existing enqueue functions.

New rtwn8723be_datapath_enqueue_batch_notify validates pointer/count bounds,
then holds the same tx_lock used by stop, single enqueue and reclaim. Under
that lock it checks tx_enabled, started, RUNNING stage and firmware readiness.
Rejected lifecycle returns EAGAIN without calling native batch or notification.
It passes the embedded workspace to native batch under the lock. On success
only, each mbuf is borrowed by the acceptance callback before releasing the
lock, preventing reclaim from freeing it during notification. Failure returns
native error without releasing caller-owned packets/references or notifying.
Callbacks must neither reenter TX nor free/retain packets or alter input storage.
Acceptance means DMA publication, never an air ACK.

This connects the native batch primitive to a serialized datapath API, not to
the net80211 fragment producer. Fragmented MSDUs remain rejected. The caller's
frame array, crypto/linearization preparation and node/report ticket ownership
must still be implemented and native-tested before enabling fragmentation.
The runtime grows by the embedded1024-byte workspace; full native build and
allocation/stop/restart/detach validation remain required.

New source regression RED before implementation then GREEN; eight mutations
rejected.192 independent lifecycle/notification policy cases PASS. Full27
selected pure Python gates PASS, including native-batch source/model checks,
11136 batch ownership cases,37552 ring cases and5100 BTC cases. These are source
contracts/models, NOT execution of the native C or physical WLAN.
Raw results: evidence/HP_RTL_BATCH_DATAPATH_RESULTS_20261016.json.

Governance PRE/POST: state/events/HP-RTL-BATCH-DATAPATH-20261016.jsonl.
No HP command/source sync/build/kernel install/boot/network change. The previous
HP fast-forward EXTERNAL_BOUNDARY/NOT_RUN remains effective; no alternative
executor retry. F77 is historical last-known recovery. No paid runner.
Native WPA2/traffic/PM/recovery and COV-RTL-014/009 full acceptance remain OPEN.
