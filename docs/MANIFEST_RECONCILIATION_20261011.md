# RTL8723BE native manifest reconciliation — 2026-10-11

## Current source selection

`config/files.rtwn8723be_native` selects **43 unique native C translation
units**.  The closure inventory must therefore reject any 42-unit assumption.
The 43rd unit is `rtwn8723be_rfkill_native.c`, added by Git commit
`08dcf79a83e9e6a7e4ee1196d4a41845dca4e341` on 2026-10-10.  The current
selection also includes the real TX DMA and native card-disable owners.

## What this does and does not prove

The documented 42-object HP build from 2026-10-10 remains valid only for the
then-selected sources.  It is historical compiler evidence, **not** evidence
that the current 43-unit selection has compiled, linked into a kernel, or
worked on hardware.

The current tools now require 43 unique manifest entries.  A private HP
candidate configuration must generate a compile rule for **every** selected
unit before a 43-object build is attempted.  The existing source inventory
continues to report four deliberately unbound lifecycle owners:

- `register_ieee80211`
- `init_rfkill`
- `bt_prepare`
- `dm_init`

Consequently this reconciliation does not authorize PCI attach, IRQ binding,
DMA enablement, WLAN association, an installer, or a booted experimental
kernel.

## Required next evidence

1. Recreate an isolated HP source/object stage from the GitHub revision.
2. Generate all 43 native rules in that private stage.
3. Compile and hash all 43 objects, then perform a complete private-kernel
   link.
4. Close the four lifecycle owners with real NetBSD API integrations.
5. Test scan with received BSS entries, association, traffic, recovery,
   suspend/resume and detach before packaging.
