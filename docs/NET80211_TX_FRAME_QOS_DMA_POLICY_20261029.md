# RTL8723BE / NetBSD 11 — actual 802.11 TX frame-to-DMA policy

**29 October 2026.** An implemented pre-encapsulated net80211
frame submission layer, stacked on the referenced TX DMA node owner
of PR #30. It is not a complete NetBSD `if_start`/queue consumer
and does not yet publish a new PCI/WLAN interface.

## Reference behavior and separation

The NetBSD 11 `sys/dev/pci/if_rtwn.c` reference sends
management frames from `ic_mgtq` first (the mbuf's context owns
an existing `ieee80211_node` reference); for regular Ethernet data,
it obtains a TX node with `ieee80211_find_txnode`, invokes
`ieee80211_encap`, and optionally
`ieee80211_crypto_encap` for protected frames. The RTL8723BE
PCI TX queue accepts an **already-encapsulated contiguous
802.11 MPDU** together with that referenced node.
The earlier PR #30 implemented the ring's node lifetime.

This PR adds the real bounded step between those layers.
It explicitly **does not** implement or invoke the queue dequeue,
Ethernet encapsulation, WPA key installation, frame encryption or
packet linearization. Those are required before binding the
missing `register_ieee80211` callback.

## Source-shared 802.11 policy parser

New `src/rtwn8723be_tx_frame.h` provides
`rtwn8723be_tx_frame_plan(frame, len,
sw_crypto_complete, out)`, a pure portable C11 parser:

- Requires 24+ byte, <= 9100 byte 802.11 protocol-v0 frame
- Supports management and three-address data frames,
  refusing control/reserved, WDS/four-address, fragmented,
  null-data and unsupported QoS HT-control frames
- Extracts the real 12-bit sequence number, receiver address
  multicast bit, QoS flag and QoS TID
- Maps TID 1/2 to BK; 0/3 to BE; 4/5 to VI; 6/7 to VO
- Selects dedicated management firmware queue and
  the corresponding RTL8723BE data firmware queues
- Refuses a protected frame (`FC1_WEP`) unless its
  **caller attests real software crypto completion**;
  no hardware CAM cipher is enabled
- Does not modify the frame or output plan on rejection,
  and transfers no frame/node ownership itself

The last point is a trust boundary, not proof of installed
WPA2 keys. A future real `if_start` caller MUST explicitly
perform and check `ieee80211_crypto_encap` before setting
`sw_crypto_complete=true`.

## Actual native datapath handoff

`rtwn8723be_datapath_enqueue_80211` is now declared
and implemented in `rtwn8723be_datapath.c`, an existing
native NetBSD C unit. It requires:

- Prepared native datapath, a packet-header mbuf and an
  existing referenced net80211 node
- Already published software-crypto security policy,
  and NO hardware offload security request
- A single contiguous mbuf segment; incomplete or chained
  frames remain caller-owned and must be linearized upstream
- Successful frame header/software-crypto planner admission

It derives the hardware ring number and firmware queue,
validates and overwrites packet/buffer length, sequence,
QoS, multicast, segmentation, security and aggregation
flags. Management and multicast traffic use forced
CCK 1 Mbps; unicast data uses the actual rate policy
**supplied by the future rate-control owner**.
The result is submitted through
`rtwn8723be_datapath_enqueue`, which still serializes
native TX against RUNNING -> STOPPING at IPL_NET.

On successful lower-layer DMA enqueue, the existing ring
takes both mbuf and referenced node. On any error, this
function neither frees nor consumes either reference;
the upstream queue owner must handle the failure.

## Tests and evidence

New `tests/test_net80211_tx_frame_submission.py`
compiles and executes both the **real source-shared
frame parser and actual production
`datapath_enqueue_80211` C body** under strict
C11/UBSan with an instrumented lower-layer DMA mock.
It tests management CCK/MGNT routing, regular BE,
broadcast/multicast, TIDs 0-7/WME AC mapping,
protected frame rejection and successful attested
software crypto, policy/crypto failure, unsupported
control/WDS/fragment/QoS TID/short frame,
contiguous-mbuf rejection and EBUSY retention.
Eight deliberately unsafe bridge mutations are rejected.

Portable CI runs the regression. This is real C11
source execution, **not** NetBSD PCI bus_dma,
net80211 queue dequeue, crypto key exchange,
native kernel compile or HP WPA2 association.

## Remaining full-port requirements

1. Implement a real `tx_start` queue consumer that obtains
   management and data nodes, performs Ethernet->802.11
   encapsulation and appropriate software encryption,
   checks linearization and guarantees exactly-once
   ownership release or transfer on failure/success.
2. Prove the hardware rate/control policy, TX completion
   wakeup, net80211 TX queue restart and watchdog.
3. Complete hardware start/stop with full ring/IRQ/softint
   drain; then bind `register_ieee80211`.
4. Implement the real BTC `bt_prepare`, DM `dm_init`,
   native NetBSD 11 full 48-C-unit kernel compile/link
   and physical HP PCI/DMA/IRQ/RFKill/WPA2 tests.

`register_ieee80211`, `bt_prepare`, `dm_init`
remain unbound; 51/54 callbacks. `main`,
trusted F77 recovery `/netbsd`, `/boot.cfg`,
i915 and HP PCI recovery state untouched.
