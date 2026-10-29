# NetBSD 11 RTL8723BE — native net80211 preregistration admission

**2026-10-29.** A real fail-closed production change, before
any externally visible NetBSD interface registration operation.
This does not publish a WLAN ifnet on HP or bind the missing
`register_ieee80211` Linux probe callback.

## Why register_ieee80211 is not safely bindable yet

The already implemented `rtwn8723be_net80211_register`
requires all three real `rtwn8723be_net80211_methods`:
`hw_start`, `hw_stop`, `tx_start`. The repository has
a Linux-order start/stop state controller and native
PCI TX descriptor enqueue/reclaim, but lacks an actual
net80211 TX method mapping management/data queues,
802.11 encapsulation, security/key/cipher handling,
TX node reference retention and completion. Binding
a placeholder `tx_start` or pretending no TX work is
necessary would publish a nonfunctional interface and
may strand mbufs and net80211 nodes.

`bt_prepare` also requires complete BTC context,
27-provider resources, MCU/H2C readiness, a live
coexistence engine and a compensating start-failure
owner. `dm_init` requires actual dynamic mechanism
initialization; existing txpower-tracking helpers are
only one subsection. Neither is safe to bind as a stub.
The bound callbacks remain **51/54**.

## Production changes

New source-shared
`rtwn8723be_net80211_registration_checkpoint_ok`
in `rtwn8723be_net80211_state.h` requires:

- An actual Linux owner snapshot, not a null state
- Exactly `R23BE_STAGE_IEEE80211_REGISTER`
- No started, firmware-ready, MAC-powered or
  partially initializing hardware

The production `rtwn8723be_net80211_register`
now requires **before ifnet/80211 side effects**:

- `n == &sc->sc_net80211` (the stable unique device
  registration owner, not stack/foreign registration)
- The new clean, stage-exact Linux checkpoint
- A previously captured PCI snapshot, mapped BAR,
  initialized core and allocated PCI DMA rings
- A valid 32-bit DMA tag and initialized native IRQ mutex
- No requested/enabled IRQ, established PCI/soft IRQ
  handles, active dispatch/argument/datapath/RX owner
- No initialized/active/pending native RFKill poller

A stale, foreign or out-of-order registration fails
with `EBUSY`; absent mandatory methods still fails
with `ENOSYS`. These checks execute **before**
regdomain changes, `n->sc` publication,
`if_initialize`, `ieee80211_ifattach`,
`if_percpuq_create`, `if_register` and media
registration, so a denied request does not
register a half-initialized ifnet.

The existing same-device stop/unregister, reverse
probe journal and native IRQ/DMA owner work is
unchanged. No success callback was fabricated.

## Executed C11/UBSan test

New `tests/test_net80211_registration_owner_admission.py`
compiles and exercises the **actual source-shared**
Linux-stage admission helper under strict C11/UBSan,
for stages IDLE, CORE_INIT, PCI_RINGS,
IEEE80211_REGISTER, RFKILL, IRQ_ESTABLISH,
PROBED, RESET_RINGS, RUNNING, STOPPING and STOPPED;
it also tests each residual Linux firmware/MAC/init
owner flag.

The test extracts the **actual production
`rtwn8723be_net80211_register` body** for
source ordering/invariant checks (does not
compile NetBSD's ifnet API on Linux). It rejects
14 deliberately unsafe mutations removing
individual stage, core/DMA, IRQ, RFKill or unique
registration owner conditions. CI runs the test.
The existing net80211 owner storage, unstarted
rollback and native probe admission tests continue
to pass.

## Required next implementation (not simulated)

1. Implement the real net80211 hardware-method
   owner including management/data queue TX,
   802.11 encapsulation, actual descriptor rate/
   channel/key policy, mbuf ownership and TX node
   reference completion.
2. Connect full Linux-order hw_start/hw_stop with
   the actual datapath start/stop and ordered
   IRQ/softint/RX/TX drain; partial firmware startup
   must retain recovery ownership.
3. Bind `register_ieee80211` only when its real
   methods exist, probe rollback can reverse
   registration, and the hardware lifecycle
   admits the resulting runtime.
4. Complete real BT prepare and dynamic mechanism
   initialization, then test the 48 native C
   units under NetBSD 11 and on HP hardware.

The currently available host roster exposes only
`legion` for disposable **read/test clones**.
No RTL driver source was modified on this host;
all project edits and commits were made in GitHub.
`main`, trusted F77 recovery `/netbsd`,
`/boot.cfg`, i915 and HP PCI fallback are untouched.
No experimental kernel install/boot occurred.
