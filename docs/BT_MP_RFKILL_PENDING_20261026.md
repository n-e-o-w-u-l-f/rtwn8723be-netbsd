# RTL8723BE BT-MP RX admission and RFKill pending-sample gate

Source checkpoint: 2026-10-26. This is a *source / portable regression*
milestone, not NetBSD/HP kernel or WLAN hardware acceptance.

## Actual defects addressed

### Bluetooth MP active flag was read outside its owner lock

The prepared RX C2H callback runs from NetBSD SOFTINT_NET, while the
firmware MP transaction may be activated, faulted, cancelled or stopped
from the lifecycle thread. Reading `sc_btc_mp.active` directly from
`rtwn8723be_rx_binding_c2h()` raced the MP thread's lock-protected
state transition.

`rtwn8723be_btc_mp_native_rx_ready(sc)` now samples `active`,
`faulted` and `cancelled` under exactly the same `IPL_SOFTNET`
mutex used by MP activate, wait, fault and stop. The RX dispatch
calls this function, not the raw boolean. Uninitialized and hard-
interrupt callers return false. No MCU handshake, H2C request, work
submission or RX pointer retention is implied by a positive snapshot.

**Lifetime boundary:** the external owner must still exclude MP
`fini` until PCI IRQ handlers and RX softint are fully drained.
The checked snapshot is not a reference-counted lease, and the
firmware receiver may recheck or ignore an obsolete C2H after stop.

### Queued RFKill sampling still admitted an older radio-on sample

The two-phase net80211 start path already rejected invalid and failed
physical-radio samples. However a valid *previous* poll could still
be accepted while the callout had queued a newer GPIO read and the
worker had not completed it.

`rtwn8723be_rfkill_native_radio_on` now snapshots
`work_queued` under `n->lock` along with `active`, `last_valid`
and `last_error`. It returns `EAGAIN` while a newer poll is
pending/in flight. Only the worker's completed real GPIO result
can reauthorize `hw_start` and subsequent `IFF_RUNNING` publication.
No guessed radio-on state or callback placeholder was introduced.

**Remaining limitation:** an RF switch can still change between
polls or after `IFF_RUNNING`. The asynchronous RFKill-to-net80211
notification, serialized shutdown, and runtime recovery paths are
not yet present.

## Executed verification

At revision `eac9d8322de848272b7d4e64d40a1ae2bdea4eef`
a disposable repository checkout on **legion (Linux x86_64)**
executed all portable Python tests allowed on that host:

- **52 PASS, 0 FAIL, 0 TIMEOUT**;
- **12 excluded**, because those scripts are restricted to
  HP/NetBSD or require specific pinned local reference checkouts;
- **64 total** `tests/test_*.py` files.

New `tests/test_bt_mp_rx_gate.py` compiles the actual production
C function with `-std=c11 -Wall -Wextra -Werror -pedantic
-fsanitize=undefined`. It tests no-owner, inactive, active,
faulted, cancelled and hard-IRQ rejection, and asserts owner-lock
entry/exit discipline. The source contract refuses raw unlocked
RX-side `active` reads.

`tests/test_rx_binding.py`,
`tests/test_rx_binding_owner_lifetime.py`,
`tests/test_port_closure_inventory.py` and the production-extracted
C11/UBSan RFKill/net80211 start harness remain green. The latter
exercises queued/in-flight RFKill start refusal.

These tests do not cover actual NetBSD mutex or IRQ scheduling,
GPIO response timing or physical Wi-Fi. The private native 48-C-unit
full-kernel link remains unexecuted for this source tree.
The four lifecycle operations
`register_ieee80211`, `init_rfkill`, `bt_prepare`, and
`dm_init` remain intentionally **unbound**.

Recovery F77 `/netbsd`, `/boot.cfg`, i915 and experimental
boot/install targets have not been touched. Do not boot F16.0,
F83, F84 or unverified shadow kernels.
