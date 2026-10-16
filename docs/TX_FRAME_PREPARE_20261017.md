# Separate net80211 frame preparation from publication

Base6f3e61a1e41ca7af0f7c39788f031e675c5d5d53; full port IN_PROGRESS.

r23be_tx_prepare_frame now performs existing validation, software crypto,
linearization, rate/protection parameters and optional report-ticket allocation
without calling the DMA datapath. A private prepared-frame record owns the
final mbuf, parameters, queue and exactly one node/report reference. Failed
preparation consumes original inputs as before and leaves a zero output record.
The extraction script compared the entire algorithm from input validation
through ticket allocation byte-for-byte against the pre-edit function: equal.

r23be_tx_abort_prepared releases an unpublished record: report tickets use the
existing enqueue_failed helper; ordinary nodes use their release callback with
completed=false. It clears the record after release, so repeated local abort is
harmless. Prepared report tickets retain dma_pending until enqueue failure or
actual completion, so timeout cannot prematurely free an unpublished owner.
This is an existing ticket convention, not a newly proven native race result.

The existing public rtwn8723be_net80211_tx_frame now prepares, then calls the
same single-frame datapath publication. Failure invokes the prepared abort once;
success transfers ownership to the ring and accounts sent reports as before.
Caller producer-lock requirements are unchanged. Successful records must never
be aborted; stack record lifetime does not control transferred ring ownership.
This changes the active source path, rather than leaving an unused helper.
Native build/stack/crypto/reclaim tests are still required.

Next: bounded all-frame preparation with runtime-owned records and separate
contiguous batch-frame array; unwind prepared records plus untouched chain on
any crypto/linearization/ticket failure. Only call datapath batch after every
frame is ready. Keep the existing fragment restriction until fault injection,
native compile and lifecycle verification are available. No fragmentation
activation or functional WPA2 claim is made here.

Verification: new source regression RED on baseline then GREEN; seven mutations
rejected (missing mbuf/ticket/owner, wrong completed flag, missing abort, wrong
report accounting guard, premature datapath call). All28 selected pure Python
source gates PASS. Existing fragment restriction, batch ownership/notification
models, closure inventory and17 negative controls remain passing. Evidence:
evidence/HP_RTL_FRAME_PREPARE_RESULTS_20261017.json. No compiler/native execution.

Governance PRE/POST: state/events/HP-RTL-FRAME-PREPARE-20261017.jsonl. No HP command,
source sync/build/install/boot/network/recovery action. Historical F77 remains
last known recovery; HP fast-forward EXTERNAL_BOUNDARY/NOT_RUN unchanged. No
paid runner. Full RX/TX/WPA2/PM/recovery acceptance remains OPEN.
