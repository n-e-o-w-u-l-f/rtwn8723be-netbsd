# RTL8723BE NetBSD project status

Date: 2026-10-11

## State

**Hardware bring-up is partial — not a functional WLAN release.**

Target hardware is HP TPN-W121 on NetBSD 11.0 amd64:

- RTL8723BE PCIe, 10ec:b723, subsystem 103c:81c1
- Firmware rtl8723befw_36.bin is validated and used by the F77 recovery kernel.
- Current live recovery kernel: RTWN8723BE-F77-LINUX-EFUSE-MAP.

## Observed HP behavior

F77 is the verified normal boot and keeps i915drmkms disabled. The RTL8723BE initialization path reaches firmware ready, DMA setup, interrupt setup and NetBSD net80211 attachment. The interface can be brought UP and drives the scan state machine through channels 1–14 without a reported channel-programming error.

This is not yet proof of working WLAN. No received BSS, authentication, association, protected data traffic, suspend/resume, recovery, or clean detach has been demonstrated on the target.

## Port scope

The full required order is maintained in docs/PORT-STATE-MACHINE.md. A complete port must preserve the frozen Linux behavior at fd179f8a05be3ccae366b9b96e176b51fbe54aab while replacing only Linux kernel-service boundaries with NetBSD equivalents.

The repository contains source-level lifecycle, DMA, firmware, RF/PHY, H2C/C2H, interrupt and net80211 adapter work. Source inventory or isolated host tests are not hardware acceptance.

Open closure areas include the actual ownership and integration of net80211 registration, RF-kill, BT preparation/initialization, dynamic-management initialization, calibration/card-disable paths, Bluetooth coexistence provider, MCU/event lifetime, receive delivery, power management, recovery and teardown. No count-based source manifest closes these runtime obligations without a native NetBSD build and HP test.

## Release gate

Do not publish an installer as a functional driver until the HP proves scanning with received BSS entries, authentication, association, stable traffic, error recovery, suspend/resume and detach on the final native NetBSD build.

After that hardware acceptance, the repository must build reproducible source and binary packages in .tgz, .tbz and .txz formats with pkgsrc/pkgin metadata. Packaging before this gate is development-only and must not be presented as an installable driver release.

## Safety

- F77 remains the fallback kernel.
- Never boot F16.0.
- Do not enable an unreviewed i915 test as part of RTL bring-up.
- Record every code change, build, hardware result and rollback in Git.