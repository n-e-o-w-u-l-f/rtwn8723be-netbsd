# HP native object checkpoint — 2026-10-11

## IST

- HP TPN-W121 remains on the verified F77 recovery kernel with
  `i915drmkms` disabled. No current experimental kernel was installed or
  booted.
- The earlier owner-only Shadow B at
  `78ff3572071b54521d5d1f5c3d2fd11704ab9e30` compiled 43 selected objects;
  it is retained solely as a historical baseline.
- Shadow D at
  `409d1b739ea96dcebe697d73c7d4b6c83ae4d00c` compiled all 44 selected C
  objects nonempty with the HP NetBSD 11 toolchain. Its private configuration
  explicitly had `no i915drmkms*`, and the original `/usr/src/sys/dev/pci/files.pci`
  hash was unchanged.
- The ordered SHA-256 aggregate for those 44 objects is
  `1c588c7d4a6fb466ebe50232427b7e543ea52dfeeb67c3b6d59c54c2f31c14f0`.
  Selected object hashes include:
  - `rtwn8723be_runtime_owner.o`:
    `f349f604a587959eb192a735405464ffff48cb2eef07ff130a6f4dd028a4fbbf3`
  - `rtwn8723be_netbsd.o`:
    `60b4e0b48fbe3b576af7dd2f318ff906896a3aa60d087a5a8ef32dcb4521d2b0`
  - `rtwn8723be_native.o`:
    `21593184f1248b15f73bb4460450a08ceacffeff5db1dc381d22209ac028df3c`
- The subsequent full private `netbsd` link stopped before producing
  `obj/netbsd`, while linking the standard kernel library `libkern.o`:

  ```
  collect2: fatal error: cannot find 'ld'
  ```

  The prefixed linker exists and a direct linker probe succeeds. This is an
  unresolved toolchain lookup problem, not a successful kernel link and not
  evidence about RTL or i915 runtime behavior.

## ÄNDERUNGEN

- The current source selection is now 45 C units. The new
  `rtwn8723be_regdomain.c` supplies only the conservative Linux-world
  regulatory baseline. Its portable strict-C11 test passed; it has not yet
  been included in a native 45-object build.
- Net80211 registration now avoids publishing partial owner state before the
  fallible world-regdomain setup succeeds.
- A small header-only policy permits unstarted rollback only after successful
  net80211 registration and during RFKill/IRQ/probed/stopped states. It binds
  no callback and changes no hardware behavior.
- No i915, PCI attach, IRQ, DMA, RFKill, net80211 or workqueue activation was
  added. No kernel was installed or booted.

## NEXT

1. Reproduce and resolve the `collect2` linker-discovery failure with a
   documented toolchain fix, rather than a local PATH workaround.
2. Create a fresh 45-unit private shadow from the Git revision, prove the
   i915 exclusion and original-source integrity, then compile/hash every
   selected object.
3. Retry the complete private-kernel link only after the 45-object gate.
4. Implement the remaining real lifecycle owners and their reverse cleanup
   before any PCI probe binding or hardware test.
5. Keep i915 trace-only pending physical early serial evidence; never boot
   F16.0, F83 or F84.
