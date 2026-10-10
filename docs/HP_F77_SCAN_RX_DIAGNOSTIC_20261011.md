# HP F77 RTL8723BE live scan/RX diagnostic — 2026-10-11

Status: OBSERVED / DRIVER NOT FUNCTIONAL. Target: hp-tpnw121.fritz.box, NetBSD 11.0 amd64, boot identity `RTWN8723BE-F77-LINUX-EFUSE-MAP`. All observations are read-only, taken on the actual HP through its online Remote Desktop Commander connection. No new scan, interface reset, kernel installation or reboot was initiated by this audit.

## Runtime evidence

- `/sbin/ifconfig rtwn8723be0`: `UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST`, `ssid ""`, `status: no network`; no WLAN association or traffic.
- `/sbin/ifconfig -v rtwn8723be0`: 0 input packets, 0 output packets, **0 beacon frames**, 1 active scan started. These are framework counters and do not alone distinguish RF receive failure from IRQ/DMA/descriptor/dispatch failure.
- `/usr/bin/netstat -I rtwn8723be0 -n -b`: 0 input and output bytes.
- Kernel ring buffer shows `RTWN8723BE-SCAN` callout running in 200-ms channel steps; `set_chan_error=0` on each observed step. The scan reaches channels 1–14, including channel 14 at 2484 MHz, then loops. A successful channel-setting callback **does not** prove RF calibration, receive or beacon delivery.
- At the observation, `/sbin/dmesg | wc -l` yielded 959 and **all 959 lines** contained `RTWN8723BE-SCAN:`. Earlier boot/IRQ/RX diagnostics had aged out of the volatile kernel message ring. Persistent `/var/log/messages` also contained dense scan records. This is a diagnostic-retention defect; it is not itself proof of the root cause of absent RX.
- `vmstat -i` showed MSI/MSI-X counters without an unambiguous attribution to `rtwn8723be0`; **do not** claim the card is receiving interrupts from those aggregate counts.

## Source-level discrepancy and safety

- The F77 active source `/usr/src/sys/dev/pci/rtwn8723be.c` and the canonical port `src/rtwn8723be_net80211.c` both advertise 1–14 uniformly with `IEEE80211_CHAN_OFDM`. In the pinned Linux `rtlwifi/regd.c` reference, world regulatory policy distinguishes active 1–11, passive 12–13 and channel-14 restrictions. Advertising 14 with OFDM is not regulatory parity and must not be carried into a production candidate.
- `docs/RTL_EFUSE_REGULATORY_RF1T1R_20261010.md` already records the missing EFUSE channel-plan/state mapping and an externally rejected write to `src/rtwn8723be_netbsd.h`. This report does **not** retry that prohibited mutation or recommend an alternate transport.
- Native RTL runtime code remains split between the newer main branch (42+ selected objects) and separate historical 48-unit/WIP callback reconciliation. Compilation and relocatable links do not establish hardware readiness.

## Next source-derived, nonintrusive acceptance

1. Capture bounded per-stage RX descriptor-OWN transitions, hardware receive counter and the **specific** interrupt-source status/mask/ack path, with explicit rate limits and a recovery-safe persistent diagnostic record. Do not saturate dmesg with per-channel messages.
2. Compare actual physical RF path 1T1R, channel power/BB calibration, receiver-enable and packet filter registers against the pinned Linux `rtl8723be` init sequence, keeping hardware constant and NetBSD bus/IRQ/DMA semantics explicit.
3. Close the board EFUSE channel-plan and country/regulatory policy only through a legitimately authorized source change, with no OFDM exposure on channel 14.
4. After source, ABI, complete selected-kernel link and recovery gates pass, verify beacon RX, authenticated WPA2 association, IP/DNS and traffic on HP. The F77 recovery kernel remains unchanged.

Observation distinguishes **scan-state progress** from **RX/data-plane success**. No driver, F83/F84 boot or Wi-Fi readiness is claimed by this document.
