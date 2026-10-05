# HP native RTL8723BE checkpoint, 2026-10-05

STATE: IN_PROGRESS. Build and installation host: HP only.

Two Linux-derived initialization callbacks are now wired: `phy_bb_config`
and `rf_channel_state_init`. BB setup preserves register widths/order,
antenna selection, BB/PG/AGC sequencing, power-group reset, CCK status and
crystal programming on both success and parafile failure. RF snapshots
read both paths and publish neither value until both reads succeed.
BB/RF callbacks require the correct serialized, pre-IRQ initialization
phase and validated firmware/EFUSE/PHY state. EEPROM reprobe invalidates
the new state flags. Native RF table programming additionally requires
successful BB initialization.

Verified on HP NetBSD 11, using Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab
and NetBSD 03d918f6d0e81fa05b8f1160eca0628ad39988a6:

- All 32 RTL regression scripts passed, including actual callback
  C11/UBSan tests, PG numeric conversion, frozen table identity and existing
  RX/TX/DMA/H2C/C2H lifetime cases. These remain mock/source regressions.
- Missing-symbol negative controls failed before implementing each new
  callback; their completed production modules then passed the same tests.
- All 28 manifest C units compiled as native NetBSD kernel objects with
  real kernel headers, `-nostdinc`, `_KERNEL` and warnings as errors, using
  HP's existing GCC 12.5.0 tools. Object sizes/hashes and copied source
  hashes are in [the evidence record](evidence/HP_NATIVE_RTL_20261005.json).
- `test_port_closure_inventory.py --require-closure` returned 1 as intended:
  DECLARED=53, BOUND=42, MISSING=11, PG included, closure OPEN.

The complete verified NetBSD source archive SHA256 is
`3645aca2c1ac9716558075b7747a98583a8e87435f00ff30c786b4b438dbe15b`.
Its writable `sys` copy is `/root/hp-driver-port-20261005/netbsd-native`;
other top-level directories refer to the separate immutable reference.
Objects are in `/root/hp-driver-port-20261005/native-obj`. Existing
`/usr/src`, tools, old object trees and unpublished overlays were preserved.

Actual regression invocation on HP:

```sh
python3 -B /root/hp-driver-port-20261005/rtwn8723be/tools/run_hp_regressions.py \
  /root/hp-driver-port-20261005/rtwn8723be \
  --linux-tree /root/linux-rtl8723be-ref-fresh \
  --output /root/hp-driver-port-20261005/rtl-packaged-tests
python3 -B /root/hp-driver-port-20261005/rtwn8723be/tools/build_hp_native.py \
  --netbsd-tree /root/hp-driver-port-20261005/netbsd-native \
  --objdir /root/hp-driver-port-20261005/native-obj --target objects
```

The source-owned `tools/run_hp_regressions.py` provides explicit Linux
reference and absolute repository/output paths, disables core files for
intentional negative tests, and rejects compilation outside HP/NetBSD.
The packaged wrapper itself ran after connection recovery: all 32 passed.
See [its completion record](evidence/HP_PACKAGED_REGRESSIONS_20261005.json).

Same-step repairs: stale positional BB fixture, fixed Legion-only source
paths, NetBSD fake errno-header recursion, kernel-compatible PG includes,
and identity-test fixtures for reprobe invalidation. The first build helper
preprocessed unrelated GENERIC dependencies serially; its own dependency
process was stopped and its log preserved. The corrected helper generated
the selected 28 dependency files and compiled all 28 units successfully.
An early regression invocation used relative paths twice after changing
the child working directory; the successful batch used absolute paths.

Scoped inventory found canonical clean mesh copies on Spinnennet, Legion,
BMAX and Pi-hole. Older/unpublished Legion trees, six i915 edits, the
554-file import, 31-file native compiler overlay and RTL cda48e5 runtime
commit were preserved. HP's separate 497-file i915 import and adapted
`/usr/src` were preserved. Phobos's bounded source search found no driver
checkout; the mobile device was unavailable. Root100 is the router.

The unpublished cda48e5 runtime source contains duplicated already-bound
phases and silently successful DBI/MDIO timeout paths; no blind cherry-pick
was made. Native RF locking and remaining runtime ownership require work.

Last confirmed recovery hashes:

| File | SHA256 |
|---|---|
| `/boot.cfg` | aaf16e4c185f59e925ab8cff9aaf1d45545896ab84a5cf46ddcb3d3c85ba6b1f |
| `/netbsd` | 9b65629c0527bbd40f7ffa0d4ef0c59a32b5edceb597a5df8c86d1e7be1c8fde |
| F77 kernel | b14ef473add01bbfa8523bc97aec9d0d9ea3ce38cd16663f221d33f323ab73de |

No kernel link, installation, reboot, WLAN association/traffic or physical
driver callback acceptance was performed. F77 remains the observed safe
boot selection with i915 disabled. Full COV-RTL-000..017 remains unresolved.

Remote status reads eventually returned HTTP 504 (`MCP request timed out`),
and Desktop Commander then reported all machines offline. No policy or
authentication denial occurred. Underlying outage cause is unknown.
After the user's continuation, all five main remote agents were online
again and the authenticated HP SSH route worked. Durable statuses were
read before restarting jobs. Fresh read-only mesh checks confirmed unchanged
canonical driver heads; recovery hashes above were rechecked unchanged.
HP's normal Git push lacks credentials (terminal prompts disabled); source
publication uses a verified HP commit transported to BMAX's normal Git route.

NEXT: complete the eleven missing
callbacks and their net80211/BT/calibration/runtime dependencies, then
validate complete kernel/ownership and HP hardware acceptance. The owning
governance START record is published at 6ca329b7; BMAX's isolated worktree
has been fast-forwarded to current governance before the scoped follow-up.
