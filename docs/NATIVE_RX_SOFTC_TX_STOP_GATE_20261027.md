# RTL8723BE NetBSD 11 — datapath TX admission in STOPPING

Source checkpoint: 2026-10-27. This is a reviewed source change with
portable C11/UBSan tests. It is **not** a native NetBSD 11 kernel compile
or a test of the real RTL8723BE PCI device.

## Actual functional defect

The native `rtwn8723be_datapath_enqueue` held the TX mutex and
checked `dp->tx_enabled`, `sc_linux.started`, and
`sc_linux.fw_ready`, but **not** `sc_linux.stage`.

The Linux `rtwn8723be_linux_adapter_stop` state machine first changes
the stage from `RUNNING` to `STOPPING` and does not clear
`started` or `fw_ready` until the complete stop succeeds. A TX
submission during that interval could have passed the old datapath
admission checks and published a DMA descriptor despite the stop.
The ifnet TX entry gate added in PR #9 was not sufficient to secure
the lower, directly callable datapath API.

The new datapath `enqueue` gate checks all three Linux runtime
conditions **under the existing TX lock**:

- `sc_linux.started` is true;
- `sc_linux.fw_ready` is true;
- `sc_linux.stage == R23BE_STAGE_RUNNING`.

The same gate checks that the native `sc_datapath` identity is the
active bridge; a stale or foreign datapath does not forward mbufs.
A non-admitted call returns `EAGAIN` without invoking
`rtwn8723be_tx_native_enqueue` or transferring mbuf ownership.
The datapath `start` entry also requires both the published
`sc_datapath` and `sc_irq_arg` to identify its own bridge, returning
`EBUSY` otherwise.

## Native source header hygiene

`rtwn8723be_rx_binding.c` explicitly imports
`rtwn8723be_netbsd.h`, because it dereferences the complete
`struct rtwn8723be_softc` and invokes the native MP owner.

**Important qualification:** this complete definition was already
available transitively through
`rtwn8723be_rx_binding.h → rtwn8723be_c2h_native.h →
rtwn8723be_rx_native.h → rtwn8723be_netbsd.h`. The change
avoids reliance on a fragile unrelated header dependency; it does
**not** establish that the previous source failed to compile.

## Executed test contract

`tests/test_datapath_tx_stage_and_native_include.py` compiles the
**actual production datapath_start and datapath_enqueue functions**
extracted from the native translation unit under C11,
`-Wall -Wextra -Werror -pedantic -fsanitize=undefined`.

Positive and negative controls exercise:

- valid RUNNING TX, valid start and underlying `EBUSY` backpressure;
- `STOPPING` while `started && fw_ready` remain true, with no DMA
  descriptor handoff;
- foreign/unpublished datapath or mismatched IRQ dispatch owner;
- stopped TX flag, missing firmware, not-started controller and
  invalid mbuf/parameters;
- seven negative source mutations targeting missing owner/stage gates
  and an omitted direct softc header dependency.

The existing `tests/test_datapath_owner_lifetime.py` owner mutation
was updated to target the **unprepare** predicate specifically, since
the new start method contains a similar identity predicate.
The portable CI workflow runs the new test.

## Remaining closure requirements

This change alone does **not** prove that the STOPPING stage transition
and TX producer are serialized against each other: the Linux lifecycle
controller currently writes its stage without holding `dp->tx_lock`,
and the fully correct runtime stop/abort owner remains unbound.
A complete port needs a lifecycle lock with an explicit order for
`if_start`, RX/softint, TX enqueue, descriptor reclaim, IRQ drain,
DMA teardown and hardware stop. The stage predicate is an additional
fail-closed gate, **not** a complete race-free shutdown solution.

The four Linux callback slots `register_ieee80211`,
`init_rfkill`, `bt_prepare`, and `dm_init` stay deliberately
unbound. No native 48-object full-kernel link, firmware association,
WPA2 or actual PCI TX operation has been validated.

Recovery F77 `/netbsd`, `/boot.cfg`, i915 and experimental
kernel boot/install paths remain untouched.
