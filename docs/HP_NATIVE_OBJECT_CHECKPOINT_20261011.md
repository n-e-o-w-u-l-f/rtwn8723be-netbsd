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
- Shadow E at `f57eaeadef553d04692231e283e400d61630c967` is the historical
  45-object private build result. It selected and built all 45 native objects
  nonempty, preserved the original PCI manifest hash
  `584bf78070c5868e2e48d0e563949cbf70a958b08166150f5363cfcbf5d7b707`, and
  explicitly excluded i915 both in the config and rendered Makefile.
- The full private `netbsd` link completed successfully in Shadow E. The
  kernel SHA-256 is
  `77be29c81d0f5a243f7c20cd54be857e46c323f6137ee6f46876d9826e6730f1`; its
  embedded identity is `RTWN8723BE-NATIVE-SHADOW`. The object aggregate is
  `c76cc21790575f56d3c5d35db8ca7a25acc192362f7aa52acbbbeef7cbc84839`, the
  object-build log SHA-256 is
  `ab71dbeeda83f72eed40bb45d506d0328e569d09f6c2c13c1c811a1f24aec955`, and
  the link-log SHA-256 is
  `8f84bc530a75aee1c217b6dca5f23cbd05097424da33a9dcf2bd37c76c9029f0`.
- The earlier linker lookup failure was resolved only for this command by an
  explicit `PATH=/usr/tools/bin:...`; no system-wide toolchain change was
  made. No kernel was installed or booted.
- Shadow G at source checkout `8a85ab31b6ff2c478efb79529bc7141a5c0cba99`
  is the matching historical 46-object result: all selected objects are nonempty,
  their ordered-hash record is
  `18b1b4b85b71af884e24b8e9199f2901a6bc7068be576dc1cac1fbc2aa7a6c23`,
  and `rtwn8723be_pre_running_recovery.o` is 28,976 bytes with SHA-256
  `41a34e2cb3f9c24a1fd9eaa3d90d295a86205972de64b48895d9df4c1096bb71`.
  The private kernel link completed with SHA-256
  `e3ac1437d70a910ab41550292a6d6dbe78118a6d0d8fd595fa1a9e0a5b2adef6`
  and identity `RTWN8723BE-NATIVE-SHADOW`. Its object and link logs hash to
  `0b630b14c0697ae482e3470a68bd57888e5d7b6190a57774c19ed54b585b2fbe`
  and `638274f03439d04bf82c8cdd89e132dedfc01675b4852a975fadce87ecbf32b5`.
  The configuration explicitly contains `no i915drmkms*`; the private PCI
  manifest and rendered Makefile have zero i915 lines, the original PCI
  manifest hash is unchanged, and `/netbsd` is a distinct live F77 file.
- Shadow H at source checkout `66fed5c6e732a373e4faa16f96b5742725c99d3b`
  is the current 47-object result. All 47 selected objects are nonempty; their
  ordered SHA-256 aggregate is
  `d5835976634e14bdbb456f6d235d6b009f2a5e6f924fccca597d7be9a1b43847`.
  `rtwn8723be_btc_policy.o` is 72,376 bytes and hashes to
  `64322ab1b87ab50db2fad6f594cca8128bb06960c719c2fde12710a2796de2c2`.
  The complete private kernel is 27,289,096 bytes, hashes to
  `390a3905b41463dee6b0395138ed406dee37051d6506a696c8f764fb0024ac38`,
  and contains exactly one `RTWN8723BE-NATIVE-SHADOW` identity:
  `NetBSD 11.0 (RTWN8723BE-NATIVE-SHADOW) #0: Sun Oct 11 20:11:59 CEST 2026`.
  Its object and link logs hash to
  `4fb30b15df8b6c60e796407fa209e764d2eeb69a8391fc1a5551012df3318ff6` and
  `ed6955b3b5f4d38121ee4406262cedad12eff52e35c153e7d4519ae8581111fb`.
  Its private config explicitly excludes i915; the generated PCI manifest and
  Makefile have zero i915 lines, the original PCI manifest hash is unchanged,
  and it differs from the live F77 `/netbsd`. No candidate was installed or
  booted.
- A fresh checkout at `84f1b9704e7fa1628b729a8da5ae6cb819155d38` passed all
  53 HP-only regression scripts. The runner's result directory is now passed
  to tests as their artifact work directory, replacing a stale hard-coded
  path. This validates the test batch execution, not a native kernel link or
  hardware operation.

## ÄNDERUNGEN

- The current source selection is 47 C units. The
  `rtwn8723be_regdomain.c` supplies only the conservative Linux-world
  regulatory baseline. `rtwn8723be_pre_running_recovery.c` adds an unbound
  recovery journal for a failed adapter start before HAL START: its C11/UBSan
  contract rejects incomplete compensation before effects, masks/drains
  start-local IRQ work first, uses reverse cleanup, and quarantines an error.
  The journal does not release probe-owned allocations or invoke normal stop
  callbacks. `rtwn8723be_btc_policy.c` is the 47th, unbound high-level Linux
  BTC get/set policy port. It requires a future genuine whole-driver context
  and neither creates that owner nor changes live hardware behavior. The
  completed Shadow H build covers all three current-source additions.
- Net80211 registration now avoids publishing partial owner state before the
  fallible world-regdomain setup succeeds.
- A small header-only policy permits unstarted rollback only after successful
  net80211 registration and during RFKill/IRQ/probed/stopped states. It binds
  no callback and changes no hardware behavior.
- No i915, PCI attach, IRQ, DMA, RFKill, net80211 or workqueue activation was
  added. No kernel was installed or booted.

## NEXT

1. Keep Shadow H (and the historical Shadow G record) as build-only evidence;
   do not install or boot either.
2. Build and test the pure BTC context-preparation boundary before implementing
   the real `bt_prepare` lifecycle owner, including actual MCU/RX
   drain and its reverse ownership, without a synthetic success path.
3. Implement the remaining real lifecycle owners and their reverse cleanup
   before any PCI probe binding or hardware test.
4. Keep i915 trace-only pending physical early serial evidence; never boot
   F16.0, F83 or F84.
