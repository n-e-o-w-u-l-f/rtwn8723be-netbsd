# Frozen Bluetooth MP wire protocol boundary

The native module compiles the actual H2C0x67 request encoder and BT_MP scalar
response decoder. Valid response behavior preserves rtl_btc_btmpinfo_notify and
halbtc_send_bt_mp_operation from Linux fd179f8a. Reads now check the precise
per-sequence byte extent and use byte loads instead of unaligned integer casts.
BLE32 uses unsigned shifts so all wire values have defined C behavior.

The frozen source switch uses BT_OP_GET_BT_FORBIDDEN_SLOT_VAL=49 against a
four-bit sequence; that case cannot execute. Sequence0xb therefore preserves
the frozen no-cache-update indication. It still signals a response just like
other unknown sequences. This is not evidence of a valid forbidden-slot value.
The full owner must make support/error policy explicit before runtime use.

No native H2C transaction submission, request serialization/matching, firmware
wait/completion lifetime, per-device BTC context, DM/state producers or antenna
algorithms are supplied by this wire module. Existing seven missing lifecycle
callbacks and two guarded/unbound owners remain OPEN. No interface is exposed
or kernel installed by this change. Full port and HP WLAN online remain required.
