# HP Tailscale access and native RTL TX reclaim integrity
Date: 2026-10-10. Status: SOURCE-ONLY PARTIAL; HP compiler/WLAN still OPEN.

## Re-entry, explicitly requested access methods
Requested by user: Remote Desktop Commander or SSH with Tailscale.
Direct RDC device hp-tpnw121.fritz.box ID
c4b89acc-9a29-496e-b073-83ce42e2cdfd: offline,
last seen ~667h at observation. Spinnennet RDC online, Legion and
Pi-hole also online; this is not an HP command session.

On existing *authorized* spinnennet RDC device:
- tailscale status --json: self spinnennet BackendState Running;
  peer hp-tpnw121 Online=true, advertised IPv4 100.127.113.67.
- tailscale ping --c 2 hp-tpnw121: pong direct via
  10.1.0.44:65529 (LAN path; no DERP indicated).
- ordinary SSH to root@100.127.113.67, BatchMode=yes and 6s
  ConnectTimeout: Permission denied (publickey,password,
  keyboard-interactive), exit 255. No interactive password supplied.
- Legion ordinary BatchMode SSH as both root and andreas:
  Permission denied (publickey,password,keyboard-interactive).
- Pi-hole does not have tailscale CLI; SSH to the HP's Tailscale
  100.x address timed out, as expected without an authorized route.
- tailscale ssh root@hp-tpnw121 wrapper: refused host key check,
  'No ED25519 host key is known for hp-tpnw121.fluffy-bushmaster.ts.net.
  and you have requested strict checking. Host key verification failed.',
  exit 255. Did not disable strict checking, modify known_hosts,
  install keys, change sshd/policy, or bypass the security boundary.
- ssh-keygen -F 100.127.113.67 -l reported existing ordinary
  SSH ED25519 SHA256 fingerprint LXLzarFlja+KdbkPQ1zHFo/0itJ42rM8/2yRtZqChpI.
  That ordinary key is not evidence Tailscale SSH host key
  authentication succeeded; do not conflate those trust domains.

Interpretation: Target is ALIVE over WireGuard, but remote execution
is blocked by the **actual SSH authentication/host-trust** gates,
not by host reachability. This differs from an offline HP Tailscale
peer and does not authorize a native build.

## Separate legitimate RTL source work: TX reclaim map lifetime

Frozen Linux reference:
torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab,
drivers/net/wireless/realtek/rtlwifi/pci.c PCI TX DMA completion.
NetBSD reference:
NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6,
sys/bus_dma and sys/dev/pci/if_rtwn.c conventions.

Prior native source already checked full TX descriptor DMA ring
interval during reclaim, but did NOT verify that the TX packet's
actual bus_dmamap segment still covered the entire mbuf before
BUS_DMASYNC_POSTWRITE/bus_dmamap_unload/m_freem. It also did not
check sc_dma_32bit or sc_mapped at the completion boundary.
A corrupt short/out-of-aperture mapping must NOT be synchronized
or freed speculatively, or access to out-of-range bus addresses
may be submitted to DMA.

Production:
- 6f22f67cd5f854c5688224c3472bbc1a88b221f3
  src/rtwn8723be_tx_native.c:
  require mapped/real constrained 32-bit bus_dma tag, bounded
  ring count, slot map length == original immutable mbuf length,
  valid nonzero length/segment and full 32-bit bus address
  interval before any packet POSTWRITE, unload or free.
  On invalid map, return EIO with the slot still owned; the
  eventual explicit device stop/recovery owner must handle it.
- 60e585d2d21e95ca29d1fdadd841395942c28902
  tests/test_port_closure_inventory.py: new source owner guard
  verifies these invariants precede BUS_DMASYNC_POSTWRITE.
- 3f6ef619cf1bc68dc3768755ad4c140e1caea0e3
  tests/test_source_negative_guards.py: two new deliberately
  bad source-copy mutations, omitting DMA tag or full map span.

GitHub fetch_file readback checked:
src/rtwn8723be_tx_native.c
e156d1dd9e8fb4037d02dcc688e30a4f921fc551;
tests/test_port_closure_inventory.py
8ab6d082368ef99a71140da7207c56674b01d230;
tests/test_source_negative_guards.py
cbcf4407335eda2f37e2bb5daf60b054280efde9.
The added guard and correct source ordering exist. Seventeen
negative-control entries are DECLARED, NOT EXECUTED. This readback
is not C compilation and is not equivalent to a passing regression
run. An earlier Spinnennet source-test process was blocked by
external safety; no materially equivalent test execution was
retried or moved to another host.

## Acceptance still open
HP-only native C compile/link, PCI DMA/IRQ/MCU/BT/C2H,
full independent stop/recovery owner, net80211 registration
and WPA2/auth/TX/RX/regdomain/rfkill, real DHCP/DNS/user traffic
after HP Wi-Fi association, and full i915 DRM/KMS with UVM.
No kernel build, install, reboot or physical test this turn.
Retain HP F77 last authenticated recovery baseline.
