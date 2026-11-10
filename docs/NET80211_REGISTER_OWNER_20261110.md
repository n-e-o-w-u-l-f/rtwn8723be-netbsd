# Native net80211 registration and runtime ownership — 2026-11-10

[Machine-readable evidence](evidence/NET80211_REGISTER_OWNER_20261110.json) records the exact tested source and artifact identities.

The native Linux-order ops table now binds the genuine `register_ieee80211` callback. It registers the actual NetBSD ifnet/net80211 interface, owns persistent RX/datapath backing, and supplies native hardware start/stop methods with the existing native management/data TX consumer. The table has 52 of 54 callbacks bound; `bt_prepare` and `dm_init` remain unbound. This is a bounded source implementation and ownership checkpoint. The parent full-port status remains PARTIAL; physical firmware/radio/WPA2 acceptance is NOT_RUN.

The native attach path remains fail-closed at IDLE before PCI snapshot, bus-master, BAR, DMA or MMIO effects. No real production supplier currently configures the required C2H table and RF/calibration/runtime providers. Binding the final probe callback therefore does not silently admit incomplete hardware initialization.

## Exact change scope

The source baseline is `369ca61e5a0a7d4bc783e81e2704da2fc1aa1efd`. Implementation changes comprise seven production paths and eleven test paths. Three new test files increase the frozen full source-input manifest from 1,007 to 1,010 files. Later publication adds only README, STATUS, this report and its JSON evidence companion: 22 changed paths in total.

Production paths:

- `src/rtwn8723be_runtime_owner.c`
- `src/rtwn8723be_runtime_owner.h`
- `src/rtwn8723be_native.c`
- `src/rtwn8723be_netbsd.c`
- `src/rtwn8723be_netbsd.h`
- `src/rtwn8723be_linux_state.c`
- `src/rtwn8723be_linux_state.h`

New test paths:

- `tests/runtime_owner_fixture.py`
- `tests/test_native_runtime_owner.py`
- `tests/test_irq_native_stop_drain.py`

Eight adapted test paths:

- `tests/test_native_probe_admission.py`
- `tests/test_net80211_owner_storage.py`
- `tests/test_net80211_registration_owner_admission.py`
- `tests/test_port_closure_inventory.py`
- `tests/test_post_registration_probe_unwind.py`
- `tests/test_rfkill_probe_ops_binding.py`
- `tests/test_runtime_owner.py`
- `tests/test_source_negative_guards.py`

No translation unit or kernel manifest was added. The native manifest remains 48 units. Existing TX-consumer/software-CCMP production files, RX descriptors, firmware, workflow triggers and boot/install paths are outside this change.

## Ownership and failure behavior

`rtwn8723be_runtime_owner_configure` allocates private zeroed bridge storage with KM_NOSLEEP and copies an immutable complete C2H table. All four handlers are required, and the argument must be the owning softc. Callback code and genuine provider bindings must outlive successful teardown. A second configuration cannot overwrite the first, and configuration refuses a live or non-IDLE device.

The structural probe gate calls no provider acquire/ready method and performs no hardware operation. It requires complete genuine START and STOP callback sets through the shared Linux validator, the actual mandatory calibration callbacks, and the HW-disable owner callbacks. Pointer completeness is an admission prerequisite; it is not proof that the missing production providers exist or have acquired a live RF/DM lifetime.

Registration follows actual ifnet/net80211 registration, RX binding, then datapath preparation. Before returning success it verifies the registered softc/methods, copied provider identities, RX/DP ownership and dispatch pointers, no live IRQ handles/request, no pending work and a quiet disabled datapath. Failure compensates in reverse order: datapath, RX binding, net80211. A failed compensator or false-success publication retains backing and marks the owner faulted.

A short IPL_NET lifecycle lock protects operation metadata and the accepted LWP cookie; no callback, allocation, MMIO or wait runs under that lock. Admission rejects concurrent operations, I/O leases, closing state, hard/soft interrupt context, pserialize read sections and borrowed initialized driver locks. The reserved sleepable I/O lock and I/O-depth metadata do not manufacture the remaining RF/BTC/DM provider leases. A future real provider must define same-operation nesting and exclude other callers.

Native start requires a genuine prepared bridge, complete providers, clean PROBED or verified STOPPED state, RFKill authorization and no CPU packet/key-update owner. It calls the actual Linux-order adapter start, then enables the actual datapath. Success additionally requires actual HAL-started state, desired IRQ ownership and the RUNNING datapath. A temporary hard-IRQ mask does not falsely invalidate a requested IRQ owner. Partial initialization preserves its failed stage and becomes quarantined; no generic RUNNING stop is used to guess away a pre-RUNNING failure.

Native stop admits only a real started RUNNING owner, including an orphan RUNNING obligation after a failed publication. After admission it clears logical RUNNING/OACTIVE and the interface timer, then runs the actual Linux stop controller. The existing atomic datapath begin-stop closes TX admission and refuses destructive STOP while RX, TX-completion or TX-start leases remain active. A busy refusal preserves RUNNING ownership for explicit retry.

The stop ops copy changes only `disable_interrupt`: the native wrapper masks/retire-epochs through the real NetBSD callback, captures IRQ lifetime, drops all held Giant depth, executes `xc_barrier(XC_HIGHPRI_IPL(IPL_SOFTNET))`, restores the exact Giant depth, then verifies unchanged epoch/handles, IRQ-off state and empty pending work. No lifecycle, I/O, datapath or IRQ mutex is held across the barrier. This drain occurs before RF wait and hardware disable, covering a complete old softint that already took pending bits and can still touch HSISR directly. Hardware IPL_NET is not substituted for the target software IPL.

Successful stop requires genuine STOPPED state, all Linux/HAL runtime flags retired, disabled quiet datapath and a matching IRQ-drain marker. IRQ handlers and bridge storage remain owned for restart. A failed STOPPING sequence retains its resources and fault state. The separate pre-RUNNING recovery journal and complete running-driver detach integration remain open work.

Context finalization returns a checked error in release builds before freeing storage or destroying outer IRQ/RF locks. It rejects every remaining operation, lease, registered interface, packet/key-hook owner, IRQ/DP/RX/RFKill/H2C/BTC/RF owner, PCI/MMIO/core/ring/DMA owner and provider back-reference. An inconsistent initialized=false owner with non-NULL context is retained without dereferencing that pointer. Only fully quiescent IDLE teardown frees the private context once. External detach must exclude new callers while mutexes are destroyed.

## Validation and its limits

On the final production hashes, 33 script entry points passed: ten focused owner/IRQ/legacy scripts and 23 preserved regressions. The new executable fixtures compiled and ran 18 runtime-owner mutants and 13 IRQ/drain mutants; each was rejected by an executed fixture assertion, rather than accepted as a compiler failure. The earlier native TX-consumer 13-mutant and software-CCMP 11-mutant proofs were rerun and preserved.

The tests compile the actual runtime owner and full Linux lifecycle controller, actual datapath admission routines, actual IRQ enable/disable/hard/soft bodies, and actual public structures/constants extracted from the project headers. OS primitives, interface/RX publication and hardware providers are explicit instrumented boundaries. The IRQ fixture runs the complete production softint in a POSIX worker paused at its HSISR read; the barrier stub must release and join that worker before the instrumented hardware shutdown. These fixtures prove source ordering and modeled ownership contracts. They do not prove NetBSD scheduling, real SMP, target ABI, firmware or physical radio behavior.

The surviving initial I/O-lease mutant exposed an incomplete bridge fixture. The accepted correction exercises isolated I/O-depth, operation and LWP-cookie guards on fully PROBED and RUNNING bridges and checks unchanged stage, TX/HAL/IRQ owners, flags/timer and effect counters. Production admission was not relaxed to satisfy a fixture.

All final fixture launches recorded the approved audit `fixture-tmp` as TMPDIR and cwd, Python `-B`, PYTHONDONTWRITEBYTECODE=1, and RLIMIT_CORE=(0,0). Generated C, executables and child working directories stay inside that private temporary tree. No fixture calls actual hardware MMIO or a system/device/boot write.

The final 48-unit native dependency/object build passed against the real NetBSD target headers and compiler. Its first A01 attempt failed on implicit declarations of `cpu_intr_p` and `cpu_softintr_p`; the corrected source adds exactly `<sys/cpu.h>`, with no runtime-body change. The failed inputs/logs remain preserved. Earlier configured/intermediate inputs are not represented as the final accepted source.

Two A02 auxiliary failures were stale assertions forbidding any `.register_ieee80211 =` binding. The separately authorized test migration preserves the original storage assertions except that obsolete slot ban, and preserves the complete admission contract, fourteen negative controls and C11/UBSan tail byte-for-byte. All 23 preserved regressions subsequently passed on the frozen A03 manifest; this is a fixture-contract migration, not an unexplained production fix.

A generic tool command rejection during test-text editing remains classified UNKNOWN because no matched token or effect-level reason was returned. The original rejected command and premature alternate-edit incident are preserved as non-executable audit data. Subsequent bounded fixture work resumed after independent content/scope review; no command replay, obfuscation or execution-filter change was used. This workflow incident is separate from source or runtime acceptance.

The A03 private kernel build passed. Its first independent verifier failed because the BSD make query `-V OBJS` returned an unexpanded expression. A read-only expanded query confirmed exactly 48 native objects; A04 corrects the query to direct argument `${OBJS}` and preserves every proof gate. The source, configuration and completed kernel stayed unchanged. The failed verifier script and receipt remain retained.

Private full-kernel SOURCE+LINK result: **PASS**.
Kernel ELF: 27,292,816 bytes; SHA256 `d7760c619e828ea93701d22a9f20c380cb8206221ee97f128554c3487f614948`.
Kernel map: 12,483,060 bytes; SHA256 `f76543e91d026f86e2eeb783dc2d40d50683f9bf858e95ce9d3934515245a145`.
All 48 selected native units and all 327 native global definitions, including the RTL attachment and new runtime exports, are retained. The final amd64 ELF64 ET_EXEC has zero undefined symbols. Independent dependency/source-selection and actual xcall/Giant-symbol checks pass.
Independent artifact/protected-input confirmation: **PASS**, frozen 1,010-file inputs, 113 staged dependencies and all seven baseline protected hashes unchanged.

No kernel installation, boot change, reboot, driver load, radio test or physical WPA2 result is claimed. The seven protected baseline artifacts remain unchanged in the terminal full-kernel and independent receipts. The new kernel/map pair is additionally protected for publication and synchronization.

## Frozen identities and private receipts

| Production path | SHA256 |
| --- | --- |
| `src/rtwn8723be_runtime_owner.c` | `62a75dac9ebfe857048fb1d892788425a3fe4cfa336e655b03480226a5688892` |
| `src/rtwn8723be_runtime_owner.h` | `4cf0d5cbf85a10d61d737b655495fa50ec7abe1f2f0bf84bf7ce45decd93ce9b` |
| `src/rtwn8723be_native.c` | `b7cb3d8166e63ea340627b906f87f61e7e3cba573a7f7fec6a6905a5be13b1f1` |
| `src/rtwn8723be_netbsd.c` | `e6d702dae90d7b4c7b39c84d704cec42177197d55a14d70bf939b83645737edc` |
| `src/rtwn8723be_netbsd.h` | `f63372600916c37b8ef7be39b481cb78fa5cd05495cfe24de3e7bb1d646c3c10` |
| `src/rtwn8723be_linux_state.c` | `974881bd1dd3d70e3569bcf610f2880d89dd035d1169d42fcf045347e003c680` |
| `src/rtwn8723be_linux_state.h` | `182e8a3a0aee9a9c78e5d2bfe5cc7132184ba8988428b4262aa15b6931be2a5b` |

Private audit root: `/home/andreas/rtwn8723be0-netbsd-20261109/audit/net80211-register-owner-20261110`. The public JSON companion should record final immutable receipt identities and acceptance limits without publishing raw private logs or machine data.

| Receipt | SHA256 | Scope |
| --- | --- | --- |
| `final-source-inputs-A03.json` | `e0e79a0e9469c4ac0f9044c4186d663869cdfa22776714f209f219dc94fb6bd8` | Frozen 1,010-file source inputs |
| `final-fixture-validation-A01.json` | `96f9fe7f339d217c2ad08fd38aa46c490fd61007b54bcc527eb7c9fbb05d0e1c` | Ten scripts; 18+13 executed new mutants; stable inputs |
| `preserved-regressions-A03.json` | `dd8f6f5109ea59251dd71c2439cf7962385a3cef886af24099727febd6fa4905` | All 23 preserved scripts pass on A03 inputs |
| `header-correction-A02.json` | `54cd4b2190465f65cf7950fa59802ea425f07c449b2991a983a40fb277c5848c` | Exact target-header correction and seven production hashes |
| `auxiliary-fixture-update-A01.json` | `f9907c8cce745c43f44c57d4e079b50b67b75818a7b30e10815df0dde690f430` | Two authorized stale-assertion migrations; unchanged production |
| `source-result.json` | `b22040a25981982a9072e2fe69d1cc58329e30a90e01a49421691b7089c1ca2f` | Terminal native SOURCE+LINK and exact18-change proof |
| `independent-kernel-proof-A04.json` | `53fc332b45adccb17e4a50afbcb4c6ee25818bd51ebfc85a29d7a5781b0c12e0` | Independent artifact/symbol/dependency/protection proof |

The actual NetBSD target was used; a canonical NetBSD-11 source-revision pin remains UNVERIFIED where previously recorded. The frozen Linux reference remains the existing project-selected `fd179f8a05be3ccae366b9b96e176b51fbe54aab`; this change does not claim a new upstream provenance verification.

Source publication and host-ref convergence are recorded separately in project governance. NEXT: supply the remaining genuine BT/DM, C2H TX/RA and RF/calibration/runtime providers; close pre-RUNNING recovery and complete running-driver detach/lifecycle ownership before any separately authorized hardware acceptance. The parent full-port task remains PARTIAL.
