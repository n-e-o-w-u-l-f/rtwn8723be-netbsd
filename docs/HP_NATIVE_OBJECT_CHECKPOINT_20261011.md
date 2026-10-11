# HP native object checkpoint — 2026-10-11

## IST

- HP TPN-W121 remains on the verified F77 recovery kernel with
  `i915drmkms` disabled. No experimental kernel was installed or booted.
- Git revision `78ff3572071b54521d5d1f5c3d2fd11704ab9e30` configured a new
  owner-only source/object shadow at `rtl-kconfig-20261011-b`.
- All 43 entries selected by that revision generated real NetBSD 11 compile
  rules. The original `/usr/src/sys/dev/pci/files.pci` hash was unchanged.
- All 43 selected C objects compiled nonempty with the HP NetBSD 11 toolchain.
  The ordered SHA-256 aggregate of their individual SHA-256 values is
  `3d7a471dfdb7f3bd3ddb0152dcfd97320b841338811dca02f309eb50b83853ea`.
  `rtwn8723be_native.o` is
  `15ab18002fdd6ee8fe08832754074ee627f7f0a18e49444aeb1d6a0cd4f24e46` and
  `rtwn8723be_netbsd.o` is
  `1f9ab689dc73c98ccbdbdf300965cb8314594013fdee168c6765ea8217337633`.
- This is compiler evidence only. It does not establish a private-kernel link,
  runtime callback closure, PCI attach, IRQ handling, WLAN scan/association,
  traffic, recovery, suspend/resume, detach or package readiness.

## ÄNDERUNGEN

- The private shadow now supplies the immutable sibling `common/` tree needed
  by generated NetBSD compiler flags such as `sys/../common/include`; it never
  writes to the system source tree.  Its preflight validates every required
  `common` subtree and rejects generated rules with a direct `/usr/src/`
  source fallback.
- The native manifest now has 44 units. The new
  `rtwn8723be_runtime_owner` is only a per-device lifecycle-lock foundation:
  no PCI, DMA, IRQ, net80211, workqueue, coexistence, callback or register
  path is enabled by it.
- Its source contract checks initialization after softc zeroing, teardown
  after existing IRQ/RF-PS quiescence, `IPL_NONE` mutexes, zero outstanding
  I/O depth, and rejects accidental hardware-lifetime bindings.

## NEXT

1. Make a fresh 44-unit private HP shadow from this Git revision and build the
   new owner together with the context/native micro-closure.
2. Repeat the full 44-object compile/hash gate before attempting a private
   kernel link.
3. Close the four real lifecycle owners (`register_ieee80211`, `init_rfkill`,
   `bt_prepare`, `dm_init`) with proper NetBSD lifetimes; do not import the
   stale frozen runtime or enable an attach path early.
4. Keep i915 trace-only until a physical early-console capture is available;
   never boot F16.0 and do not use an i915 candidate as an RTL test vehicle.
5. Hardware acceptance and package work remain after full runtime closure and
   a recovery-safe private-kernel test.
