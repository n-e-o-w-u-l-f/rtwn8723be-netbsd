# HP native kernel gate — verified 2026-11-10 Europe/Paris

Project: HP-RTL8723BE / rtwn8723be-netbsd. Parent port: **PARTIAL**.
Native build source: d96edb70d9c0e5332f69ba8eb286fb86481e6370.
Host: hp-tpnw121.lan, NetBSD 11.0 amd64, unprivileged approved workspace.
All receipt timestamps below are UTC.

## DONE — bounded source and native gates

The two net/if_media.h dependency additions passed all 48 generated native
object targets and three existing DMA/TX ownership regressions. The unchanged
source then passed the private 48-object relocatable link, complete kernel
dependency build, and full GENERIC-derived native kernel link with i915 excluded.

Independent readback confirmed:

- Final ELF64 little-endian amd64 executable; zero undefined symbols.
- All 48 RTL units selected in the generated kernel Makefile.
- All 318 global symbols from those native units retained in the kernel,
  including rtwn8723be_native_ca.
- Original tracked source, F77 /netbsd, /boot.cfg and installed PCI manifest
  unchanged during the build; the current source worktree was clean.

[Machine-readable receipt](evidence/HP_NATIVE_KERNEL_GATE_20261109.json)
records exact artifact, link map, input identity, commands, hashes and limitations.
Private kernel: /home/andreas/rtwn8723be0-netbsd-20261109/rtl-kconfig-20261109/obj/netbsd

Kernel size: **27291000 bytes**.
Kernel SHA-256: 21dccebbbbd92cc1fa185522489a766e515f1e8a062ed6aa99b2645a907ef4ca.
Build started 2026-11-09T22:34:34.965989+00:00 and finished 2026-11-09T23:16:45.472972+00:00.
The kernel remains private and uninstalled; TESTREADY is false.

## Source promotion and retained history

This gate permits controlled source-only debug -> test -> main fast-forwards.
The enclosing report commit changes documentation only relative to the tested
source. Remote refs and the canonical Legion source copy are verified separately
in the project PRE/POST record. Older/divergent worktrees remain preserved;
the historical Legion cda48e5 runtime tree is retained under
codex/archive-legion-runtime-cda48e5-20261109.

## UNVERIFIED / OPEN — parent acceptance

The actual installed target headers identify NetBSD 11.0. Their hashes are
recorded, but the historical upstream reference 03d918f6 cannot be freshly
confirmed because the installed source has no Git metadata.

Installation, candidate boot, physical RX/scan, association, WPA2 traffic,
DMA/IRQ/STOP races and PM acceptance are NOT_RUN. Physical independent console
and F77/stock recovery verification remain prerequisites for experimental boot.

NEXT: implement the actual net80211 TX queue consumer with explicit management/
data mbuf and node ownership, rate/queue policy, ring-full pending ownership,
completion wakeup and the existing STOP lifetime lease. The actual NetBSD 11
ieee80211_crypto_encap API can replace/free its local mbuf head without returning
a new head: naive reuse is unsafe. Target crypto source SHA-256:
76e242228e1adeddc21475ec0569e48f5b5e2547d57383dae560c88f7cf361da.
A future software-CCMP adapter must prove writable contiguous head/trailer
capacity and error ownership before binding. register_ieee80211, bt_prepare
and dm_init remain open. These runtime obligations remain separate coverage
from the completed native build gate.
