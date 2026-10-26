# RTL8723BE: net80211 RX/TX publication during stop — 2026-10-26

## Defect and scope

Native `rtwn8723be_net80211_input` checked `IFF_RUNNING`
**before** `m_devget` copied a borrowed RX DMA frame into an mbuf,
but passed that mbuf to `ieee80211_input` only **after** taking
`splnet`. A legitimate `ifconfig down` / hardware STOP could clear
`IFF_RUNNING` during this copying interval. The old code could then
deliver a stale frame into the 802.11 stack despite the stop.

Also, `rtwn8723be_n80211_ifstart` originally relied only on
`IFF_RUNNING`, `IFF_OACTIVE` and registration. An inconsistent
ifnet flag could permit a TX method call even if the actual Linux
lifecycle had already left `R23BE_STAGE_RUNNING`.

The stop entry itself also dereferenced `n->sc` without first
checking that the registered net80211 bridge still had its
actual device owner.

## Implemented (real production source)

- RX still validates/copies the bounded, checksum-validated received
  frame with `m_devget`. **After** copying, it acquires `splnet()`
  and rechecks live net80211 registration, the device owner,
  `IFF_RUNNING`, `sc_linux.started` and
  `sc_linux.stage == R23BE_STAGE_RUNNING` before looking up a node.
  Failure returns `ENETDOWN`, releases the copied mbuf and never
  calls `ieee80211_input`.
- The real `if_start` bridge refuses to dispatch TX unless there
  is a registered non-NULL owner, `IFF_RUNNING` without
  `IFF_OACTIVE`, and the actual hardware lifecycle is started
  in `RUNNING`.
- `ifstop` rejects a registered but orphaned net80211 bridge
  before dereferencing the device. During a legitimate stop it
  deliberately clears `IFF_RUNNING` and `IFF_OACTIVE` **before**
  invoking `hw_stop`; if hardware stop fails it propagates the
  error and retains the real Linux/device owner for explicit
  recovery. No fake STOPPED transition is introduced.

## Executable portable tests

`tests/test_net80211_late_rx_stop.py` compiles the **actual RX
ingress and if_start production functions** using strict C11 and
UBSan. A deterministic mocked `m_devget` can clear
`IFF_RUNNING`, unregister net80211, remove the owner, clear
`sc_linux.started` or move to another Linux lifecycle stage
mid-copy. All five late-stop scenarios must drop the mbuf and
avoid net80211 node lookup and ingress. The normal positive
frame and TX cases also run. Eight deliberately unsafe source
mutations must be rejected.

`tests/test_net80211_stop_failure_owner.py` compiles the
**actual ifstop production function**, using the real shared
NetBSD Linux-stage admission predicate. It injects a failed
hardware stop, a successful later retry, STOPPING,
unstarted-probe rollback and an orphaned owner. Five source
mutations guard the stop contract. These tests are wired into
the portable CI workflow.

The regression checks do not prove the NetBSD kernel's native
`splnet`/IRQ scheduler, concurrent `m_devget`, 802.11 node
reference lifetime or actual packet integrity.

## Outstanding integration gates

The registered net80211 interface still lacks **real bound**
`hw_start`, `hw_stop` and `tx_start` implementations and
a fully serialized runtime owner. In particular the adapter
lifetime must exclude concurrent RX softint / interface
detach, wait for the actual hard+soft IRQ drain and securely
release TX nodes/DMA before enabling full runtime.

The four deliberately missing Linux lifecycle callbacks
`register_ieee80211`, `init_rfkill`, `bt_prepare`,
`dm_init` remain unbound. The 48-unit NetBSD native kernel
compile/link and HP PCI/WLAN hardware validation remain
unexecuted, not inferred from Linux-host tests.

The trusted F77 `/netbsd`, `/boot.cfg`, i915 and other
recovery/boot objects were not modified. No experimental
kernel was installed or booted.
