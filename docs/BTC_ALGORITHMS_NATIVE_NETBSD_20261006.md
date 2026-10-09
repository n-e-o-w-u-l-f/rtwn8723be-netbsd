# RTL8723B algorithms and native notification owner

Status: IN_PROGRESS. This advances the full port; it is not whole-driver,
physical Bluetooth or WLAN acceptance. HP continues to run F77 with WLAN
DOWN/no network. No kernel was linked, installed or booted.

The Linux authority is `fd179f8a05be3ccae366b9b96e176b51fbe54aab`; the
NetBSD authority is `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.

## Source implementation

`tools/generate_btc_algorithms.py` verifies six exact frozen Git blobs before
mechanically importing the entire `halbtc8723b1ant.c` and `halbtc8723b2ant.c`
bodies and their types. All register values, conditions, H2C payloads,
calculations and ordering remain source-derived. `rtwn8723be_btc_source.json`
records the inputs, generated hashes and all 20 moved local static fields.
Only OS includes, diagnostics/delay routing and mutable storage placement
change. Immutable debug strings and version constants remain shared.

One `rtwn8723be_btc_state` owns both antenna DM/STA structures, histories and
the copied BTC context for one device. Every original 27 callback plus the
sleepable delay provider is mandatory. Missing providers or invalid board,
interface and event extents fail before IO. The original two-antenna source
has no RF-status entry; dispatch returns ENOTSUP there. The original one-
antenna source has no firmware preload hook. Neither case supplies invented
hardware behavior. BT information owns up to ten bytes, matching the frozen
cache extent; short messages preserve Linux's existing cached-tail behavior.

The NetBSD native broker provides a per-device, single-worker MPSAFE
workqueue, IPL_SOFTNET queue/admission mutex, IPL_NONE engine mutex and
call-drain CV. RX notifications are copied before returning; no RX-buffer
pointer or diagnostic sink crosses the asynchronous boundary. All actual
algorithm execution occurs in sleepable thread context. Initialization,
preload, HALT and display are synchronous owner operations.

The real RF/DM/MMIO/firmware owner must supply acquire/ready/release and
all 27 OS providers with valid state producers. Algorithm callbacks have
Linux's void IO ABI; fallible providers record the first native error and
decline subsequent IO. An accepted event whose resource acquisition fails
quarantines the device. Queue overflow retains ENOBUFS and drains copied
events without further algorithm execution. Faulted state is retained for
real whole-driver recovery; this layer does not fabricate a recovery path.

Stop closes admission while holding the queue mutex, disables notifications,
drains all already admitted synchronous calls, then uses native
`workqueue_wait` after preventing every new submission. HALT runs once with
hardware resources still owned. Worker/provider self-stop returns EDEADLK;
the pinned native wait API itself cannot establish a self-drain. Successful
fini destroys the queue/CV/mutexes after external entry/RX exclusion. Owner
and callback tables remain alive until fini finishes.

The softc owns native BTC storage and all four new C units belong to the
41-object manifest. Start/stop/C2H consumer activation stays unbound until
the real state/firmware/RX/RF owner and providers exist. EFUSE presence,
callback counts, IRQ-disabled flags or a compiled object are insufficient
substitutes for that owner.

## HP verification

`test_btc_algorithms.py` compiles the actual port and unchanged frozen Linux
algorithm bodies on HP against deterministic callback test models. In each
normal and UBSan run, 33 scenarios cover both antenna variants, main/aux
paths, auto-report choices, all notification types, short/full BT reports,
RSSI/busy/profile variations, provider rejection and per-step two-device
isolation: 41,280 executed events and 128,640 compared differential IO,
H2C, GET/SET, RF, delay and diagnostic-format operations. DM/STA and BTC
context are compared after every differential event. Restoring shared
function histories compiles and then fails the semantic isolation check.
The frozen sources already contain unused parameters; the probe retains
the native kernel's explicit `-Wno-unused-parameter`, with other warnings
treated as errors. Rendered Linux `%Nph` output remains a native sink gate.

`test_btc_native.py` compiles unchanged native broker and dispatch C with
explicit pthread-backed NetBSD mutex/CV/single-worker queue models and
modeled algorithm bodies. Both normal and UBSan runs pass ten scenarios
and 208 checks: copied soft-interrupt C2H bytes, simultaneous queued and
synchronous stop, admission closure, overflow quarantine, provider first-
error isolation, acquisition failure, missing resource ownership,
self-stop, hard/soft interrupt restrictions and workqueue creation unwind.
A compiled control that discards the C2H copy fails the payload assertion.
This proof does not execute actual NetBSD kernel primitives; the complete
algorithm bodies have their independent differential proof above.

All 45 regression scripts and all 41 actual native kernel objects pass on
HP. The aggregate evidence records source/artifact hashes and limitations.
Neither fixture substitutes modeled callbacks for production providers.

## Remaining full-port obligations

The full RTL contract remains IN_PROGRESS: actual 27 OS callback semantics,
state producers, unconditional Linux HAL BTC context, all notification and
MP consumer binding, MCU-ready/old-RX drain and activation; seven lifecycle
callbacks; real calibration/card-disable RF/DM/BTC owners; net80211 HT/AMPDU,
keys, datapath and runtime PM/recovery; full kernel and physical HP WLAN.
The sibling i915 full port and subsequent actual WLAN online objective
remain unchanged. Gates COV-RTL-010/015/017 are still IN_PROGRESS.


## 2026-10-09 BT hardware init lifecycle binding

Frozen source authority (same immutable Linux commit as above):
`rtl8723be/hw.c:rtl8723be_bt_hw_init` calls the actual BTC hardware
initializer conditionally on `get_btc_status()`.
`btcoexist/rtl_btc.c:rtl_btc_init_hw_config` invokes
`exhalbtc_init_hw_config(btcoexist, !bt_exist)` **then**
`exhalbtc_init_coex_dm(btcoexist)`, where the former selects the
one-/two-antenna 8723B algorithm and the latter sets the BTC context's
`initialized` flag. The original BTC context comes from `kzalloc`;
initialization must not be assumed from a caller-provided copy.

Production commits:
- `baafe4a` publishes the per-device `btc.initialized` flag only
  when `R23BE_BTC_INIT_DM` returns with no provider/owner error.
- `6958c3f` implements `rtwn8723be_netbsd_bt_hw_init` using
  the real native algorithm broker, in exact INIT_HW -> INIT_DM order.
  It checks the Linux HW_INIT stage, mapped MMIO, H2C, firmware-ready
  and existing prepared BTC owner. Non-coexistence boards honor the
  frozen get_btc_status() no-call branch; missing actual coexistence
  lifetime produces ENXIO instead of fabricated success.
- `4766174` declares the actual callback in the owning native header;
  `b3c71b0` binds it to `rtwn8723be_netbsd_ops.bt_hw_init`.
- `b3e9315` inventories the actual source-event order and callback
  binding. `49f2cbe` ensures the copied BTC context starts explicitly
  **uninitialized** before any hardware IO, as with frozen Linux
  `rtl_btc_alloc_variable` zero-initialization; `2ba2cc2`
  adds this safeguard to the source inventory.
- Spinnennet: source-only `python3 -B
  tests/test_port_closure_inventory.py --root .` PASS, exit 0,
  HEAD `2ba2cc212f8b782356b6c979af91ee01ad43680f`:
  53 declared, 49 bound, four missing, 42 native manifest units.
  **No C compiler** was run on Spinnennet.

This does **not** initialize BTC yet on the actual HP:
`bt_prepare`, one of the four unbound callbacks, must construct the
whole 27-provider context, authentic device/antenna state and real
RF/DM/MMIO/H2C exclusion owner. No BTC owner has been faked or registered.
Native MP/RX activation and the precise firmware/IRQ-generation
dependencies must be satisfied separately. `dm_init` (the actual
rtl8723be PHY dynamic mechanism) is NOT equivalent to BTC INIT_DM and
remains unbound. All kernel, WLAN/HT/keys/PM/recovery and i915
acceptance gates remain OPEN; HP F77 remains the last authenticated
2026-10-06 recovery state.
