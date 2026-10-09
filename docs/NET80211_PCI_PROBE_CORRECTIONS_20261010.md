# NetBSD 11 net80211 and native PCI failed-probe reconciliation
Date: 2026-10-10. Status: SOURCE_GATES_PASSED / NATIVE_KERNEL_AND_WLAN_OPEN.

## Immutable references

- NetBSD/src at 03d918f6d0e81fa05b8f1160eca0628ad39988a6:
  sys/net/if.c:if_initialize(), if_register(), if_percpuq_create(),
  if_detach(); sys/net80211/ieee80211.c:ieee80211_ifdetach();
  sys/net80211/ieee80211_crypto.c; sys/net80211/ieee80211_var.h;
  sys/dev/pci/if_rtwn.c:rtwn_attach() and rtwn_detach().
- Linux rtl8723be firmware/hardware unchanged at
  torvalds/linux fd179f8a05be3ccae366b9b96e176b51fbe54aab.
- Canonical owner n-e-o-w-u-l-f/rtwn8723be-netbsd main.

## Actual native source changes

### net80211 interface publication and WPA2

Commit a72e79c changes src/rtwn8723be_net80211.c.

The old if_percpuq_create() NULL branch incorrectly called
ieee80211_ifdetach() and if_detach() BEFORE if_register().
Frozen NetBSD if_detach() removes the interface from ifnet_list,
whose entry is not inserted until if_register(); executing this
branch can corrupt the list/panic, rather than perform rollback.
Frozen if_percpuq_create() uses kmem_zalloc(KM_SLEEP) and returns the
allocated object, not an ENOMEM result. The unreachable incorrect
branch is removed; the exact NetBSD if_rtwn.c publication order is
preserved, with an explicit non-NULL assertion.

The actual station capabilities now include IEEE80211_C_WPA2, backed
by NetBSD ieee80211_ifattach's software crypto and the existing
sc_sw_crypto=true/sc_use_sw_sec=true policy. No WPA1, hardware CAM or
working WPA2 4-way handshake is claimed. The production native
security callback must not access cipher-engine MMIO when software
crypto is selected; source inventory now checks the bypass order.
A complete key/node/PN/TX/RX/lifetime and physical association test
is still required before WLAN acceptance.

### PCI preflight and attaching RF lock

Commit 1d24342 changes src/rtwn8723be_native.c.

rtl8723be_linux_probe() returns ENOSYS at IDLE when its callback
preflight sees the four remaining missing callbacks. Previous native
rollback returned immediately for IDLE and did NOT clear the PCI
snapshot flag set by attach. A later detach therefore returned EBUSY
despite zero PCI/MMIO changes.

The corrected IDLE path retires the snapshot without modifying
PCI command, power state, BAR or device registers. Both the initial
pci_get_powerstate() failure and any fully unwound/IDLE failed probe
release the initialized RF-PS mutex via context_fini(). The
post-registration stage guard remains unchanged: driver objects and
their owners are retained rather than freed by an incomplete unwind.

This is not a successful attach. In its current deliberately incomplete
state the native driver still fails callback preflight and does not
register a WLAN interface or perform hardware operations.

## Validation evidence

- a267be1: static source regression for WPA2 and pre-if_register detach.
- 20ecdd2 and 023f8a9: IDLE PCI snapshot and RF-PS cleanup ordering
  guards; the initial regex-based guard had incorrectly escaped
  parentheses and failed on valid source. Replaced with a deterministic
  ordered-token check, not a repeat of the rejected mechanism.
- e742a1e and 124fda7: disposable source-copy negative controls.
  Five intentionally corrupt configurations are rejected: missing
  WPA2 capability, pre-registration if_detach, missing IDLE snapshot
  release, disabled software crypto bypass, and missing RF-PS mutex
  fini on power-state snapshot failure.
- e3f21e6: safeguards software-security return before any hardware
  SECCFG/CR write.
- Actual Spinnennet result at 124fda7571b815d4637c761a137da9c3906a5abb:
  `python3 -B tests/test_port_closure_inventory.py --root .` PASS;
  `python3 -B tests/test_source_negative_guards.py` PASS 5/5;
  `git diff --check 35dd9fa..HEAD` PASS; checkout clean.
  Source inventory: 53 declared / 49 bound / 4 missing callbacks,
  42 selected native C modules. ALL real HP kernel and WLAN gates OPEN.

## Next source/owner work

Complete and bind register_ieee80211, init_rfkill, bt_prepare and
the distinct rtl8723be PHY dm_init only after real full lifecycle
methods/owner, reverse-order rollback, IRQ/RX/MCU generation and
real NetBSD radio/regulatory/key/PM controls exist. No replacement
with no-op callback or fabricated device/hardware state. Compile,
link, install, boot and verify actual WPA2 association, DHCP, DNS,
packet transport, suspend/restart/recovery ONLY on the HP; preserve
its previously verified F77 safe boot.
