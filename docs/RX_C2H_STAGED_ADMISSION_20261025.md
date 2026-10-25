# RTL8723BE native RX/C2H staged admission — 2026-10-25

## Critical probe/start dependency eliminated in source

The NetBSD PCI probe publishes net80211 before establishing interrupts.
The RX ring requires **both** a network-frame callback and a firmware
C2H callback. The previous `rtwn8723be_rx_binding_init` insisted that
native BTC and the Bluetooth MP request owner were **already active**.
However native BTC/MP owner activation depends on firmware and runtime
initialization, which follows the probe; this made prepared RX/IRQ
dispatch and genuine BTC startup mutually dependent.

This branch separates the lifetimes without fabricating success:

1. **Probe-time RX callback publication:** after real net80211
   registration, validate all required C2H handler pointers, then publish
   the shared `rtwn8723be_rx_binding` and its `softc.sc_rx_binding`
   owner atomically in the single-threaded attach context.
2. **BT_INFO consumption:** if Bluetooth coexists but its native policy
   owner is not initialized, return `EAGAIN` **before forwarding the
   borrowed DMA bytes**. Once initialized, the actual
   `rtwn8723be_btc_native_enqueue` must still inspect
   `events_enabled`, `closing`, `faulted`, queue capacity and
   workqueue ownership under its `IPL_SOFTNET` lock.
3. **BT_MP consumption:** return `EAGAIN` until the genuine native
   MP owner is both initialized and active. This does not manufacture
   the firmware/MCU activation handshake.
4. **Non-BT reports:** keep their required real C2H callbacks. No
   `tx_report`/`ra_report` callback is manufactured by this change.
5. **Symmetric reverse lifetime:** after IRQ and datapath/softint are
   fully quiescent, `rtwn8723be_rx_binding_fini` validates the exact
   callback context and device owner, forbids live IRQ and datapath
   owners, revokes the softc reference and erases callback storage.
   Failures retain all resources.

The source-shared post-registration broker journals FIVE real
compensators:

`NONE → IRQ → DATAPATH → RX_BINDING → RFKILL → NET80211`

The early PCI cleanup also unbinds RX after datapath and before
DMA. Native probe success and the native rollback preflight require
the datapath's callback argument, frame function and C2H function to
match the owned RX binding. The final `context_fini` asserts all
three dispatch/data owners have been retired.

## Actual executed verification

On **legion (Linux x86_64)** at revision
`cab2f716b532d00245c3fc22f4030b2227d5dd4f`, the branch
was cloned to a disposable checkout; **50/50 portable tests
permitted on this host passed**. Twelve more tests were explicitly
excluded as requiring HP/NetBSD or pinned local Linux reference
source trees absent on this host (total inventory: 62).

The production RX binding init/C2H/fini functions were extracted
and compiled as C11 with `-Wall -Wextra -Werror -pedantic` and
`-fsanitize=undefined`. Cases include early BT_INFO and BT_MP
rejection, actual owner activation, post-stop rejection, independent
non-BT C2H delivery, exact binding ownership and refusal to revoke
callbacks with live IRQ/datapath resources.

The real C11 post-registration broker was compiled with UBSan and
exercised with five injected compensator failures, stage and owner
negatives, and five resumable journal states. Separate source-contract
negative controls reject nine unsafe RX owner/event/teardown mutations.

**This evidence is not a NetBSD kernel compilation, kernel link, or HP
device test.** Kernel concurrency, firmware/C2H timing, unregistered
interfaces, 802.11 TX node lifetime, RFKill publication and BTC provider
lifetime remain unproven.

## Full port completion is still blocked by

- **48-unit native NetBSD 11.0 object and full kernel link:** must be
  performed on HP in an isolated shadow tree with the guarded gate;
  the historical Shadow H 47-unit link is NOT evidence for this tree.
- **net80211 hardware methods:** actual hardware start, stop, 802.11
  framing/transmit queue and per-packet node ownership are not bound.
- **Bluetooth coexistence and DM:** real provider/context lifecycle,
  firmware readiness/MP activation, DM initialization and stop/recovery
  must be implemented and fault-injected.
- **RFKill state publication:** the native callout/workqueue sampler
  exists, but asynchronous switch-state changes still need correctly
  serialized net80211 interface stop/notify logic.
- **Live callback closure:** `register_ieee80211`, `init_rfkill`,
  `bt_prepare`, `dm_init` remain intentionally **NULL** in
  `rtwn8723be_netbsd_ops`. No fake methods should close them.
- **Hardware acceptance:** actual PCI attach/IRQ and DMA bring-up,
  firmware, scan, authentication, association, WPA2 keys, RX/TX,
  coexistence, RFKill and restart remain untested on HP.

The F77 recovery `/netbsd`, `/boot.cfg` and i915 policy are
unchanged. Never boot F16.0/F83/F84 or experimental shadow kernels
without independent serial/recovery safety evidence.
