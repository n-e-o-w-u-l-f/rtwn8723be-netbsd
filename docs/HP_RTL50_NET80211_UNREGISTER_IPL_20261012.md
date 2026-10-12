# RTL8723BE native net80211 teardown: no sleepable stop under splnet

Date: 2026-10-12. Branch: `wip/hp-rtl-runtime-48-merge-20261010`.
Status: SOURCE CHANGE PUBLISHED; physical RTL50 panic/root cause, new HP-native compile, scan/beacon RX, WPA2, and runtime suspend/restart remain OPEN.

## Exact defect and source constraints

The NetBSD 11 RTL 50-unit bridge previously entered `splnet()` **before** calling `rtwn8723be_n80211_ifstop(n)` inside `rtwn8723be_net80211_unregister()`. The native callback can invoke `hw_stop`, which can drain firmware commands, asynchronous BTC/H2C work, DMA/soft IRQ resources and timers. A sleepable shutdown cannot run while holding the raised net IPL. This defect is an independent, source-reproducible risk; no crash trace from the user's reported RTL50 kernel panic has been obtained, so the panic must **not** be attributed to this defect.

The frozen target reference `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/pci/if_rtwn.c` performs net80211 detach and ifnet detach after driver stop and uses `splnet` to serialize native net80211 state. This source is a concurrency/lifecycle guide only: RTL8723BE firmware, DMA and rfkill still require their specific Linux-reference owner graph.

## Minimal correction

In `src/rtwn8723be_net80211.c`, the only changed production function is `rtwn8723be_net80211_unregister`. It now executes:

1. Validate the registered net80211/softc owner.
2. Run `rtwn8723be_n80211_ifstop(n)` **without `splnet()` held**; if a hardware stop fails, return the actual error and retain the net80211 and underlying PCI/ring resources.
3. After successful stop, raise `splnet()`, clear software security flags, `ieee80211_ifdetach`, `if_detach`, release owner pointers, and call `splx(s)` exactly once.
4. `rtwn8723be_runtime_unregister` continues to call `rtwn8723be_runtime_stop` before this net80211 unregister, with a failure gate protecting PCI/DMA resources.

No hardware register, IRQ mask, firmware, regulatory channel, WPA2 key logic, PCI configuration or build/boot setup was changed. The separate driver critical sections are intentionally not refactored under this narrow change.

## Evidence and tests

- Source-before blob `0b56cb0fee2e20d87eb745c4b2121714898a02d3`.
- Source-after blob `63efe291518d5909bc23ce394d1c6e3091c05ca1`, production change commit `ab4fa97b9e4a5f95549bdb3721e650ae30743bc5`, verified by independent GitHub readback.
- New source regression `tests/test_net80211_unregister_sleep_ipl_source.py`, original blob `f5c6632c025f0eeeee8ceb5d9ba95ec8bc9026b5` and corrected blob `a40efeb51caf607161aa5e1fb1396cc394439465`, latest commit `adb592924c606453e971d119efd83592013cbf47`. It asserts exact lifecycle order, failure-before-IPL, sole `splx`, and native ifdetach/if_detach bracketing. Negative fixture reinstates premature `splnet()` and must be rejected.
- Test-specific defect caught during independent verification: initial Python test searched any `rtwn8723be_net80211_input(` string; source also calls this function, causing an erroneous double-match. Corrected the boundary to exact function definition (`int` line + name); complete amended test content read back.\n- Independent **JavaScript static source-contract check** against exact GitHub files: new order PASS, deliberately restored unsafe old order FAIL, runtime_stop before unregister PASS. This is **not** actual execution of the committed Python regression and not a compiler or hardware result.
- `PRE` and `POST`: `docs/evidence/HP_RTL50_UNREGISTER_IPL_GATE_20261012.jsonl`; scope/data source IDs and observed outcome retained.

## Runtime and recovery restrictions

Read-only RDC account quota remains zero. The user specifically requested Tailscale when RDC cannot execute. However this session exposes no authenticated Tailscale SSH command executor, and plugin discovery found no connected executable Tailscale connector; a known tailnet IP, old SSH key path or `@Tailscale` mention cannot grant this runtime tailnet access. Never reuse a denied RDC action through an equivalent unverified source. If independent user-authorized tailnet/SSH execution becomes available, establish target identity/host key/kernel recovery and the actual **HP-only** build checkout before running any test; do not infer an active GENERIC/F77 kernel from older documents.

Mandatory next gates: obtain actual RTL50 DDB/crashdump cause, verify real HP boot/recovery, run the **Python source test on the authorized HP** together with other frozen-source regressions, build a new HP-native 50-unit/full-kernel candidate only after diagnostics and builder recovery gates close, and validate RX beacons/scan, 802.11 association/EAPOL WPA2 and real IP traffic. i915 F83/F84 black-screen cause and G01–G09 early serial trace remain separately OPEN.

Official pinned NetBSD reference: https://raw.githubusercontent.com/NetBSD/src/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/pci/if_rtwn.c
