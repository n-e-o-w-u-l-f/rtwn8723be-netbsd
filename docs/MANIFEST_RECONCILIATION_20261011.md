# RTL8723BE native manifest reconciliation — 2026-10-11

## Current source selection

`config/files.rtwn8723be_native` selects **44 unique native C translation
units**.  The closure inventory must therefore reject any 43-unit assumption.
The 44th unit is `rtwn8723be_runtime_owner.c`, an inert per-device lifecycle
foundation. It does not attach hardware or bind a pending Linux lifecycle
callback. The current selection also includes the real TX DMA, native
card-disable and RF-kill owners.

## What this does and does not prove

The documented 42-object HP build from 2026-10-10 remains valid only for the
then-selected sources. The 43-object private HP build from 2026-10-11 is a
compiler baseline for the prior selection. Neither is evidence that the
current 44-unit selection has linked into a kernel or worked on hardware.

The current tools now require 44 unique manifest entries.  A private HP
candidate configuration must generate a compile rule for **every** selected
unit before a 44-object build is attempted.  The existing source inventory
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
2. Generate all 44 native rules in that private stage.
3. Compile and hash all 44 objects, then perform a complete private-kernel
   link.
4. Close the four lifecycle owners with real NetBSD API integrations.
5. Test scan with received BSS entries, association, traffic, recovery,
   suspend/resume and detach before packaging.
