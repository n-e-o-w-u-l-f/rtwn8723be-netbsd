# RTL8723BE native manifest reconciliation — 2026-10-11

## Current source selection

`config/files.rtwn8723be_native` now selects **45 unique native C translation
units**. The 45th unit is `rtwn8723be_regdomain.c`, which applies only the
safe Linux-world 2.4 GHz channel baseline. It does not read or map the EFUSE
channel-plan byte, install a country notifier, attach hardware, or bind a
pending lifecycle callback.

The source inventory still deliberately reports four unbound lifecycle
owners:

- `register_ieee80211`
- `init_rfkill`
- `bt_prepare`
- `dm_init`

## Historical 44-unit evidence

The previous 44-unit revision
`409d1b739ea96dcebe697d73c7d4b6c83ae4d00c` generated all selected compile
rules, excluded i915 from the private configuration, preserved the original
PCI manifest, and compiled all 44 objects nonempty. The ordered aggregate is
`1c588c7d4a6fb466ebe50232427b7e543ea52dfeeb67c3b6d59c54c2f31c14f0`.

That object result does not cover the current 45-unit selection. The next
complete private-kernel link stopped at `libkern.o` before `obj/netbsd`
existed because `collect2` could not locate `ld`. It is not a driver link or
hardware result.

## Required next evidence

1. Diagnose the toolchain's linker lookup without changing the system source
   tree or silently adding a local workaround.
2. Recreate an isolated 45-unit HP source/object stage from the Git revision.
3. Generate all 45 native rules and prove i915 exclusion/source integrity.
4. Compile and hash all 45 objects, then perform a complete private-kernel
   link.
5. Close the four lifecycle owners with real NetBSD API integrations and
   reverse teardown before enabling PCI attach or IRQ binding.
6. Test scan with received BSS entries, association, traffic, recovery,
   suspend/resume and detach before packaging.
