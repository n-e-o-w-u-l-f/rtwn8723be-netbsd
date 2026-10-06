# Linux firmware and NetBSD loading flow — 2026-10-06

The two RTL8723BE firmware images on HP are byte-identical to the decompressed
Arch Linux files on Legion. The changes below port driver behavior; no firmware
binary was modified. This is a bounded loading checkpoint. Complete device
initialization, kernel integration and physical WLAN acceptance remain OPEN.

## References

- Frozen Linux: fd179f8a05be3ccae366b9b96e176b51fbe54aab.
  rtlwifi/core.c selects the primary/alternative image and limits the whole
  file to 0x8000 bytes; rtl8723com/fw_common.c supplies header interpretation,
  reset and polling; efuse.c supplies the PCI byte-upload body.
- Frozen NetBSD: 03d918f6d0e81fa05b8f1160eca0628ad39988a6.
  [firmload(9)](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/share/man/man9/firmload.9),
  [firmload.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/firmload.c)
  and [if_rtwn.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/pci/if_rtwn.c).
  Use its firmware-resource lifetime and OS APIs with RTL8723BE-specific
  hardware semantics. The RTL8192C register sequence is not a replacement
  for RTL8723BE initialization.

## Actual firmware identity

| Image | Uncompressed bytes | SHA-256 | Decoded version |
|---|---:|---|---|
| rtl8723befw_36.bin | 31762 | adba42ade555a5e4383373b76706443f27bf0f006fbc296a640c7155192febf2 | 36.0 |
| rtl8723befw.bin | 30746 | 1bfa6d0910e072ed26d793ccf27889ebd774851be95d2d2543fd8de7cf31b969 | 15.17 |

HP files: /libdata/firmware/if_rtwn8723be/.
Arch files: /usr/lib/firmware/rtlwifi/, decompressed from the installed .zst
files for comparison. Both headers are 32 bytes; the actual transferred
payloads are 31730 and 30714 bytes respectively.

## Implemented differences

| Behavior | NetBSD implementation |
|---|---|
| Primary image unavailable | Open _36 first, then rtl8723befw.bin if the primary open fails. |
| Invalid loaded primary | Return its validation/read error; do not select an alternative after a successful open. |
| File-size limit | Reject empty files and whole files over 0x8000 before allocation or hardware access. |
| Header and raw images | Decode a bounded, zero-filled header without pointer casts. Strip 32 bytes only for a masked 0x5300 signature; reject a truncated recognized header. |
| Transfer extent | Use the actual file extent. Declared RAM-code size remains metadata, matching frozen Linux. |
| Version identity | Retain version, one-byte subversion, signature, RAM-code size and selected image in the device softc. Clear them on loading failure. |
| NetBSD file/memory lifetime | Use firmware_malloc/free; close the firmware vnode immediately after reading, before preload/upload/reset/polling. Preserve read errors and propagate a close error when reading succeeded. |
| Allowed loading phase | Require mapped firmware window, initialized H2C context, FIRMWARE_DOWNLOAD and being_init_adapter; reject running/ready/IRQ-enabled devices and interrupt/softinterrupt context before side effects. |
| Polling | Preserve both frozen postincrement loop boundaries and all register/delay observations. |
| Failure publication | Propagate positive NetBSD errno. Clear H2C readiness and firmware identity; do not announce firmware ready after a failed handshake. |

The PCI page upload already used the same **byte writes** as frozen Linux.
No dword-write change was required. An earlier register-width discrepancy
report was incorrect.

Frozen rtl8723_download_fw() logs a readiness failure but returns zero.
NetBSD intentionally propagates this failure instead of publishing a false
success. Invalid/truncated images are also rejected without emulating unsafe
header underflow. These are documented error/safety adaptations.

## Required initialization flow

The hardware phases remain ordered by the production lifecycle controller:

1. Probe prepares PCI/BAR, DMA, verified EFUSE identity, software context and
   rings before interface/IRQ ownership is exposed.
2. Start resets rings and prepares the real BTC context before MAC power and
   initialization.
3. At FIRMWARE_DOWNLOAD, a serialized sleepable NetBSD owner opens/reads/closes
   the file, validates the buffer, performs the existing antenna preload,
   uploads the MCU payload and verifies checksum/readiness. Only success
   enables the firmware command transport.
4. MAC/BB/RF configuration, channel state, security and ASPM precede BTC
   hardware initialization and RF calibration. DMA release and DM follow
   their required dependencies.
5. Retry policy, IRQ enable and RX configuration precede HAL/RUNNING
   publication. NetBSD IFF_RUNNING is set only after a complete successful
   start. Failure never authorizes later stages.

The seven real callback bindings are still absent:
register_ieee80211, init_rfkill, bt_prepare, bt_hw_init, dm_init,
bt_halt_deinit, wait_rf_change_idle. Calibration and card-disable still
require their real RF/BTC/DM/IRQ owners. Existing EFUSE-based BTC power-on and
preload gates do not establish frozen HAL-context parity. A serialized
initialization/recovery owner, failure rollback, stop/drain and detach must be
completed before those callbacks are enabled. This checkpoint supplies no
substitute owners and does not enable an incomplete attachment.

Firmware power/LPS, reserved-page delivery, P2P commands, native BTC request/
response completion and state producers also remain part of the full port.
See [FULL_SCOPE_CONTRACT.md](FULL_SCOPE_CONTRACT.md).

## Verification on HP

- Actual production firmware C and the exact native download-owner body:
  **113 scenarios PASS**, both normal and UndefinedBehaviorSanitizer.
  MMIO/delays, firmware(9), BT preload and H2C callbacks are explicit models.
- 42 polling traces and 32 upload/reset traces compare against byte-exact
  functions extracted from pinned Linux Git blobs. Padding, all page limits
  and the final readiness/checksum boundaries are exercised.
- Two semantic negative controls compile and execute the old actual source:
  old polling fails POLL_RESULT_PARITY; old loading fails FALLBACK_LOAD.
  Compile failure is not accepted as a semantic control.
- All **42 published regression scripts PASS** on HP.
- All **36 native NetBSD C objects PASS** in a fresh isolated object directory,
  with real kernel headers and warnings treated as errors.
- The first native attempt exposed missing sys/cpu.h declarations for the
  interrupt-context checks. The correct header was verified in the pinned
  NetBSD tree, added, and all 36 objects compiled fresh. Initial failed
  reports remain retained; fixture warning/shadow fixes are also recorded.

Exact commands, input hashes, artifact hashes, retained logs and failures:
[evidence/HP_NATIVE_FIRMWARE_LOAD_20261006.json](evidence/HP_NATIVE_FIRMWARE_LOAD_20261006.json).

These are source/model and native object proofs. No kernel link/install/boot,
physical MCU transaction, complete initialization, WLAN association/addressing/
traffic, PM/recovery or full-port acceptance occurred. HP remains on F77;
the boot/kernel hashes match the retained safe baseline.
