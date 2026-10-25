# Native RTL8723BE datapath owner / reverse lifetime — 2026-10-25

## Exact change

The prepared softint RX/TX bridge owns an `IPL_NET` TX mutex, a borrowed
`softc` pointer and both RX/TX IRQ callbacks. Previously there was **no
explicit softc owner reference** and the post-registration rollback could
only refuse a bound dispatcher indefinitely.

This source checkpoint adds `sc_datapath`, a single prepared bridge owner:

- `rtwn8723be_datapath_prepare` rejects an existing owner, stale IRQ
  dispatch, outstanding PCI/soft interrupt handles and unconfigured DMA32/
  descriptor rings. It initializes the TX mutex, publishes `sc_datapath`,
  and only then binds the actual RX/TX dispatcher.
- `rtwn8723be_datapath_unprepare` requires the exact same owner and
  callback identity; explicitly excludes enabled/requested IRQ, live
  PCI/softint handles and enabled TX. Only then does it unbind IRQ callbacks,
  clear `sc_datapath`, destroy the TX mutex and zero the bridge.
  **External lifecycle synchronization is still required** to exclude
  concurrent software TX producers; this does not solve ifnet runtime stop.
- `rtwn8723be_native_unwind_datapath` calls that real unprepare function,
  never merely clears the pointer, and verifies all IRQ dispatcher pointers
  and flags were removed before lower DMA ownership is released.
- The unstarted post-registration source-shared C11 broker now has **four**
  monotonic owner-release stages: `NONE → IRQ → DATAPATH → RFKILL →
  NET80211`. The datapath owner and TX state are validated at admission,
  failed real-owner callbacks stop subsequent teardown, and the journal
  supports a later separately serialized retry. The pre-registration PCI
  cleanup also unprepares the bridge after verified IRQ teardown.
- A successful native PCI probe now requires a *prepared, same-softc*
  datapath with the exact IRQ argument, not just a `dispatch_ready` flag.
  `rtwn8723be_netbsd_context_fini` asserts there is no remaining datapath
  or IRQ dispatch owner.

## Verification

Fresh branch clone on the separately connected **legion Linux x86_64** host,
revision `d8c7dadec637a3b574ed99e3513d87afa43b5a70`, on 2026-10-25:
**49/49** permitted portable Python regression scripts returned exit code
zero. The total is 61 scripts: 12 intentionally excluded because their
own requirements restrict execution to HP/NetBSD or a specific pinned
reference tree unavailable on this host. This run includes:

- `test_post_registration_probe_unwind.py`: production C11 broker compiled
  with strict `-Wall -Wextra -Werror -pedantic -fsanitize=undefined`,
  all four legal checkpoints with bridge present or absent; 4 failure
  injections and four journaled successful retries; negative states for
  live TX, contradictory progress and missing callback.
- `test_datapath_owner_lifetime.py`: source owner identity and release
  order checks plus ten deliberately unsafe source mutations rejected.
- Existing net80211, IRQ, DMA32, pre-RUNNING rollback, manifest and
  callback inventory source/portable tests.

This is not proof of NetBSD 11 compilation, a running WLAN interface,
actual `splnet` serialization or a hardware interrupt/softint race.
No HP native build, kernel link, install, boot, device scan/association
or packet exchange was attempted. The four missing Linux callbacks
(`register_ieee80211`, `init_rfkill`, `bt_prepare`, `dm_init`)
remain **unbound**.

## Remaining gates

1. In a fresh private HP NetBSD 11 shadow, perform the guarded 48-unit
   object plus full kernel link; check native `struct` and symbol ABI.
2. Fault-inject IRQ establishment, RFKill workqueue, datapath prepare/
   unprepare and net80211 unregister on NetBSD, including actual
   concurrency with TX submission and device detach.
3. Implement the fully serialized runtime start/stop/recovery owner.
   **Do not activate callbacks or a bootable candidate before that
   contract is proven.**

Recovery F77 `/netbsd`, `/boot.cfg`, and i915 have not been changed;
F16.0, F83/F84 and experimental shadow kernels must not be booted.
