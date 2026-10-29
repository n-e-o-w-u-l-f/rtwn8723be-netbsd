# Fragmented TX: temporary fail-closed boundary

Base: ad43116daf3f5fed68152b699b56de89a44bebd8. Full port IN_PROGRESS.

The current per-frame path maps, encodes and publishes OWN immediately, then
advances the ring and polls the device. A later fragment can fail DMA loading,
crypto, linearization or encoding after earlier fragments are already visible.
Slot capacity/OWN preflight does not make this a transaction. Already published
fragments cannot safely be reclaimed as though the device never saw them.

For every m_nextpkt multi-frame chain, successful slot preflight is now converted
to EOPNOTSUPP. The existing pre-publication failure branch frees the entire
chain and its original node reference, increments if_oerrors and exits the
producer loop. Genuine EBUSY retains its backpressure flag; unsupported chains
do not newly set OACTIVE and therefore do not wait for a nonexistent completion.
Single-frame processing is unchanged. Preflight remains for precise existing
ring/bounds/OWN diagnostics and as a tested foundation for future transactions.

This deliberately disables fragmented MSDU transmission pending transactional
preparation. It is a safety restriction, not completed fragmentation support or
Linux parity. Future work must prepare all crypto/linearization, maps, encoded
descriptors and node/report owners before any OWN publication; failure must
unwind every unpublished resource. Tests must inject failure at each position.

Verification: new source regression RED on baseline, GREEN after patch; seven
mutations rejected (missing/commented/inverted guard, zero error, missing frame
or node release, unsupported error incorrectly setting OACTIVE). All 22 selected
pure Python gates PASS, including updated peer regressions previously recorded
NOT_RUN: 37552 ring model cases, 64 MGNT/BE policy combinations, plus 5100 BTC
mask cases. Raw stdout/exit results: evidence/HP_RTL_FRAGMENT_FAILCLOSED_RESULTS_20261016.json.
No compiled/native or hardware behavior has been tested.

PRE/POST owner: Agent-Governance state/events/HP-RTL-FRAGMENT-FAILCLOSED-20261016.jsonl.
No HP command/build/source synchronization/install/boot/network action occurred.
The HP source-fast-forward EXTERNAL_BOUNDARY/NOT_RUN remains effective. F77 is
only the last reported safe kernel, not a new live observation. No paid runner.
Native fragmented traffic, nonfragmented regression, WPA2, stop/restart, PM and
recovery remain OPEN. COV-RTL-014/009 remain IN_PROGRESS.
