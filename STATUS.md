# RTL8723BE NetBSD project status

Date: 2026-10-11

## IST

**Hardware bring-up is partial — this is not a functional WLAN release.**

Target hardware is HP TPN-W121 on NetBSD 11.0 amd64:

- RTL8723BE PCIe, `10ec:b723`, subsystem `103c:81c1`
- F77 is the verified recovery boot and keeps `i915drmkms` disabled.
- F77 must not be confused with acceptance of the current Git source tree.
- F16.0 must never be booted. F83 and F84 reached a black screen with
  backlight after early text; the root cause is unconfirmed.

The current private manifest contains 45 C units. It remains intentionally
unbound: `register_ieee80211`, `init_rfkill`, `bt_prepare`, and `dm_init` are
not live lifecycle owners, so the current source does not activate PCI, DMA,
IRQ, RFKill or a net80211 device on the HP.

Historical Shadow D evidence at commit
`409d1b739ea96dcebe697d73c7d4b6c83ae4d00c` is limited but positive:

- the original `files.pci` was unchanged;
- the generated private configuration explicitly excluded i915;
- all 44 selected C objects compiled nonempty; and
- their ordered SHA-256 aggregate is
  `1c588c7d4a6fb466ebe50232427b7e543ea52dfeeb67c3b6d59c54c2f31c14f0`.

The following complete private `netbsd` link failed before `obj/netbsd`
existed while building `libkern.o`:

```
collect2: fatal error: cannot find 'ld'
```

The target-prefixed linker exists and can link a direct probe; the failure is
therefore currently recorded as a toolchain linker-discovery issue, not as an
RTL/i915 compile result. No candidate was installed or booted from that link.

## ÄNDERUNGEN

- Added a conservative Linux-world 2.4 GHz regulatory baseline: 1–11 active
  CCK/OFDM, 12–13 passive CCK/OFDM, 14 passive CCK-only. The portable C11
  regression passed. This does not yet read EFUSE channel plan `0xb8`, map a
  country, or process country-IE notifier changes.
- Prevented partial Net80211 publication when the fallible policy setup
  fails.
- Added a tested whitelist for teardown of a registered but unstarted
  interface at `IEEE80211_REGISTER`, `RFKILL`, `IRQ_ESTABLISH`, `PROBED`, and
  `STOPPED`. Hardware-start failure states remain blocked for a future,
  explicit reverse-recovery owner.
- Kept NetBSD's reference-compatible `splnet()` detach scope after checking
  `if_rtwn.c`; no speculative locking change was made.
- CI now executes the new regulatory and Net80211 regression tests on source
  and test-only changes.

## NEXT

1. Diagnose and reproduce the isolated `collect2` linker-discovery failure;
   do not mask it with an unverified system-toolchain change.
2. From the resulting Git revision, create a fresh 45-unit private HP shadow,
   prove i915 is excluded and original source integrity is unchanged, then
   generate, compile and hash all 45 selected objects.
3. Retry the complete private-kernel link only after that object gate passes.
   A link result is still not permission to install or boot a kernel.
4. Close the real lifecycle owners in reverse-cleanup order before binding any
   operation to the PCI probe path. Preserve explicit recovery for failed
   hardware-start states.
5. Keep i915 trace-only until a physical early serial capture exists. Never
   use F16.0, F83 or F84 as a test kernel.
6. Test scan with received BSS entries, authentication, association, traffic,
   recovery, suspend/resume and detach only after full runtime closure.
   Package work follows that hardware acceptance.
