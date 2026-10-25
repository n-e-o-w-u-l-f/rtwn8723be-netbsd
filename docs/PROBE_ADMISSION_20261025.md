# NetBSD RTL8723BE probe ownership admission — 2026-10-25

## Scope

The existing Linux-order probe controller can report `0` after invoking
callbacks, but that return code is not an independent proof of native NetBSD
resource ownership. The new `rtwn8723be_probe_admission_ok()` is a pure,
portable C11 predicate. The native attach adapter constructs its input from
**actual** softc state immediately after a successful `linux_probe()`.

A success announcement now additionally requires all of the following to be
true together: Linux lifecycle at PROBED with no started/init/firmware-ready
state; original PCI snapshot; mapped BAR; initialized core; configured DMA32
and allocated descriptor rings; real registered net80211 interface owned by
this softc with three nonnull hardware methods; initialized and active RFKill
owner; ready IRQ dispatch and allocated hard/soft/PCI interrupt handles;
operational interrupts still disabled during probe.

No field is inferred from a prior callback's reported return value. Failure
to satisfy even one of the 15 fields fails closed: attach **does not** print
a successful native-probe message, and does **not** guess at cleanup while a
post-registration owner could still reference PCI/MMIO. The existing hard
post-registration detach prohibition remains in place until reverse-order
cleanup is implemented and kernel-tested.

## Verification and limitations

`tests/test_native_probe_admission.py` compiles the production header with
strict host C11/UBSan. It checks an all-valid snapshot, 15 one-field-invalid
snapshots, NULL input and native source integration. Its source-level negative
controls require genuine state mapping, the mandatory post-probe guard,
and no speculative post-registration cleanup. CI includes this regression.

At this source checkpoint, the test and native object/kernel build still need
their external execution evidence. The existing four unbound lifecycle slots
(`register_ieee80211`, `init_rfkill`, `bt_prepare`, `dm_init`) are **not
implemented or bound** by this gate. No PCI attach, RFKill polling, WLAN
association, hardware initialization, install, boot, i915 or physical target
acceptance is claimed.

## Next

Implement the reverse-order post-registration probe rollback using real
resource ownership and NetBSD API semantics, including RFKill callout/workqueue
drain, IRQ masking/disestablishment, net80211 unregistration, BT/MP/H2C drain,
ring and DMA release, MMIO unmap and PCI configuration restoration. Keep all
four unbound slots blocked until failure-injection and real NetBSD build
evidence are available. The 48-object private build checkpoint is handled
separately by draft PR #2; the last verified full link remains Shadow H.
