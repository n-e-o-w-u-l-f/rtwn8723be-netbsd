# RTL8723BE native manifest reconciliation — 2026-10-11

## Current source selection

`config/files.rtwn8723be_native` now selects **47 unique native C translation
units**. The 45th unit is `rtwn8723be_regdomain.c`, which applies only the
safe Linux-world 2.4 GHz channel baseline. The 46th is
`rtwn8723be_pre_running_recovery.c`, an unbound recovery journal for a
failed Linux-order adapter start before HAL START is published. It preflights
compensators, masks and drains start-local IRQ work before reverse cleanup,
and retains a failed recovery as quarantined state. Neither unit reads or
maps EFUSE, installs a country notifier, attaches hardware, or binds a
pending lifecycle callback. The 47th is `rtwn8723be_btc_policy.c`, an
unbound port of the Linux high-level BTC `get`/`set` decision policy. It
requires a future whole-driver context for its callbacks and does not bind a
PCI, DMA, IRQ, net80211, or lifecycle path.

The source inventory still deliberately reports four unbound lifecycle
owners:

- `register_ieee80211`
- `init_rfkill`
- `bt_prepare`
- `dm_init`

## Native build evidence

The previous 44-unit revision
`409d1b739ea96dcebe697d73c7d4b6c83ae4d00c` generated all selected compile
rules, excluded i915 from the private configuration, preserved the original
PCI manifest, and compiled all 44 objects nonempty. The ordered aggregate is
`1c588c7d4a6fb466ebe50232427b7e543ea52dfeeb67c3b6d59c54c2f31c14f0`.

That historical object result does not cover the then-current 45-unit selection.
Shadow E at `f57eaeadef553d04692231e283e400d61630c967` does: all 45 objects
are nonempty; its object aggregate is
`c76cc21790575f56d3c5d35db8ca7a25acc192362f7aa52acbbbeef7cbc84839`; the
original PCI manifest hash remains
`584bf78070c5868e2e48d0e563949cbf70a958b08166150f5363cfcbf5d7b707`; and
i915 is absent from both the private config and the generated Makefile.

The full private link also succeeded. Its `netbsd` SHA-256 is
`77be29c81d0f5a243f7c20cd54be857e46c323f6137ee6f46876d9826e6730f1` and
the embedded identity is `RTWN8723BE-NATIVE-SHADOW`. This is build evidence,
not a hardware test, installation, or boot authorization.

The historical 46-unit Shadow G checkout at
`8a85ab31b6ff2c478efb79529bc7141a5c0cba99` closed its matching private build
gate: 46/46 objects are nonempty, the ordered object record hashes to
`18b1b4b85b71af884e24b8e9199f2901a6bc7068be576dc1cac1fbc2aa7a6c23`, and
the complete kernel hashes to
`e3ac1437d70a910ab41550292a6d6dbe78118a6d0d8fd595fa1a9e0a5b2adef6`.
The generated config explicitly contains `no i915drmkms*`; the private PCI
manifest and rendered Makefile contain zero i915 lines. The original PCI
manifest hash remains
`584bf78070c5868e2e48d0e563949cbf70a958b08166150f5363cfcbf5d7b707`.
The candidate is a separate file from the live F77 `/netbsd`, was not
installed, and was not booted.

The current 47-unit Shadow H checkout at
`66fed5c6e732a373e4faa16f96b5742725c99d3b` closes the matching private build
gate: 47/47 objects are nonempty, the ordered object record hashes to
`d5835976634e14bdbb456f6d235d6b009f2a5e6f924fccca597d7be9a1b43847`, and
the complete kernel hashes to
`390a3905b41463dee6b0395138ed406dee37051d6506a696c8f764fb0024ac38`.
The config explicitly contains `no i915drmkms*`; the private PCI manifest and
rendered Makefile contain zero i915 lines, and the original PCI manifest hash
is unchanged. The candidate is separate from the live F77 `/netbsd`, was not
installed, and was not booted.

## Required next evidence

1. Retain the completed H result (and historical G record) only as private
   build evidence; do not promote either to an installed or bootable candidate.
2. Build and test a pure BTC context-preparation boundary, then close the four
   lifecycle owners with real NetBSD API integrations and
   reverse teardown before enabling PCI attach or IRQ binding.
3. Test scan with received BSS entries, association, traffic, recovery,
   suspend/resume and detach before packaging.
