# Native NetBSD Bluetooth MP transaction checkpoint — 2026-10-06

Status: PARTIAL / full ports and actual HP WLAN acceptance remain OPEN.

Coverage: COV-RTL-010, COV-RTL-015, COV-RTL-017. The full parent objective
and every remaining lifecycle/kernel/hardware acceptance criterion are unchanged.

The production provider in `src/rtwn8723be_btc_mp_native.c/.h` owns per-device
request admission, copied response state and native mutex/CV completion.
`init_sw_vars` constructs the provider after H2C; a failed MP init unwinds
H2C. Current pre-registration probe cleanup finalizes MP before H2C and DMA.
Full activation and C2H consumer registration remain unbound until the real
BTC and serialized initialization/recovery/stop owners are implemented.

| Behavior | Frozen Linux reference | Native adaptation |
|---|---|---|
| Command | H2C0x67; existing opcode-specific four-bit sequence and zero operation version | Copy caller bytes, reuse actual wire encoder, submit through native H2C; caller input is unchanged |
| Admission | Shared completion; no explicit matching outstanding request in notify | One admitted request per device; concurrent caller gets EBUSY |
| Early response | Reinitialize completion before submission | Arm expected sequence/pending before send; release MP lock during H2C |
| Reply | extid1; response sequence selects BT scalar cache | Actual bounded wire decoder; copy values while RX bytes are borrowed; match pending device/sequence; full cache owner still open |
| Wait | Waiting consumers use200ms; generic0 means no wait | cv_timedwaitbt predicate loop with decreasing200ms budget; output unchanged on error; zero remaining duration cannot become an infinite wait |
| Stop | Full Linux BTC/adapter lifetime surrounds completion | Cancel and wake waiter; drain busy H2C submission as well as CV wait before resources are released |
| Uncertainty | Fixed sequence contains no transaction nonce | Timeout/send error/no-wait submission quarantine the MP channel; a new ready generation and owner-proven MCU restart/RX/IRQ drain are required |
| Synchronization | Linux completion primitives | Adaptive MUTEX_DEFAULT/IPL_SOFTNET mutex; requests/init/activate/stop/fini require sleepable threads; receive permits SOFTINT_NET and rejects hard IRQ |

The generation counter advances only on the fresh native H2C MCU-ready
handshake, is not reset by a mere mailbox-state reset, rejects duplicate ready
publication and checks overflow. MP activation refuses the same generation
after timeout/stop. This establishes an observed handshake boundary; the
future lifecycle owner must additionally prove real MCU restart, old RX ring
discard, softint/IRQ drain and exclusion of new users. Sampled IRQ flags cannot
prove that drain. No activation call or RX consumer binding is fabricated here.

Fixed opcode sequences cannot distinguish a duplicate older same-opcode
response within an active MCU lifetime. A host generation counter is not a
wire nonce. Existing frozen opcode49 forbidden-slot cache behavior remains
unchanged: that case is unreachable from the four-bit response sequence.
Matching, explicit errno, serialization and quarantine are deliberate native
lifetime/error adaptations, not claims that Linux itself implements them.

Verified on HP only:
- 42 scenarios/537 checks using unmodified actual native C, normal and UBSan;
  explicit pthread mutex/CV, CPU-context, softc and H2C models.
- Early reply during submission, borrowed-buffer reuse, mismatched/non-BT/
  malformed reply rejection, spurious wake/budget exhaustion, timeout boundary
  completion, send/CV error, no-wait quarantine, context/admission guards.
- Independent devices, same-device concurrent rejection, cancellation of a
  CV waiter and16 controlled stop-during-send races;16 asynchronous-reply races.
- Two source-mutated semantic controls compile and fail at the intended
  unmatched-response and arm-before-send assertions.
- All43 regression scripts PASS; all37 native C objects PASS using the frozen
  NetBSD kernel headers, isolated tree and existing HP toolchain.
- Strict callback closure gate still returns1:53 declared,46 bound,7 missing;
  calibration and card-disable owners are also unassigned.

Exact reports, source/object hashes and retained initial fixture failures are
in [the checkpoint evidence](evidence/HP_NATIVE_BTC_MP_20261006.json).
The pthread model establishes C-level admission/wait/rundown behavior.
Native object compilation establishes kernel-header/type compatibility.
Neither establishes a whole kernel link, active physical firmware exchange,
full BTC algorithms, WLAN traffic, PM/recovery or i915 KMS.

Remaining work: full per-device BTC DM/STA and all27 callbacks/antenna
algorithms/state producers; real activation/C2H/cache and start/stop/recovery
owners; the seven missing callbacks; net80211/HT/AMPDU, RF/keys/datapath and
firmware-power/LPS/reserved-page/P2P integration; full kernel and physical
acceptance. Both complete ports and subsequent actual HP WLAN online remain
required. Current live HP is F77 with WLAN DOWN/no network.

References:
- Frozen Linux `fd179f8a05be3ccae366b9b96e176b51fbe54aab`:
  [halbtcoutsrc.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/btcoexist/halbtcoutsrc.c),
  [rtl_btc.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/net/wireless/realtek/rtlwifi/btcoexist/rtl_btc.c).
- Frozen NetBSD `03d918f6d0e81fa05b8f1160eca0628ad39988a6`:
  [mutex.9](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/share/man/man9/mutex.9),
  [condvar.9](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/share/man/man9/condvar.9),
  [kern_condvar.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/kern_condvar.c).
