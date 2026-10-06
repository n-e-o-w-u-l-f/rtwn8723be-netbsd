/* SPDX-License-Identifier: GPL-2.0 */
/* Frozen rtlwifi Bluetooth MP wire protocol; no borrowed RX pointers stored. */
#ifndef _RTWN8723BE_BTC_MP_H_
#define _RTWN8723BE_BTC_MP_H_
#include "rtwn8723be_os_compat.h"

enum rtwn8723be_btc_mp_opcode {
    R23BE_BT_OP_VERSION = 0,
    R23BE_BT_OP_WRITE_REG_ADDR = 12,
    R23BE_BT_OP_WRITE_REG_VALUE = 13,
    R23BE_BT_OP_READ_REG = 17,
    R23BE_BT_OP_AFH_L = 30,
    R23BE_BT_OP_AFH_M = 31,
    R23BE_BT_OP_AFH_H = 32,
    R23BE_BT_OP_FEATURE = 42,
    R23BE_BT_OP_SUPPORTED_VERSION = 43,
    R23BE_BT_OP_ANT_DETECTION = 44,
    R23BE_BT_OP_BLE_SCAN_PARAMETERS = 45,
    R23BE_BT_OP_BLE_SCAN_TYPE = 46,
    R23BE_BT_OP_DEVICE_INFO = 48,
    R23BE_BT_OP_FORBIDDEN_SLOT = 49
};
enum rtwn8723be_btc_mp_field {
    R23BE_BT_MP_NONE,
    R23BE_BT_MP_VERSION,
    R23BE_BT_MP_AFH_L,
    R23BE_BT_MP_AFH_M,
    R23BE_BT_MP_AFH_H,
    R23BE_BT_MP_FEATURE,
    R23BE_BT_MP_SUPPORTED_VERSION,
    R23BE_BT_MP_ANT_DETECTION,
    R23BE_BT_MP_BLE_SCAN_PARAMETERS,
    R23BE_BT_MP_BLE_SCAN_TYPE,
    R23BE_BT_MP_DEVICE_INFO
};
struct rtwn8723be_btc_mp_reply {
    bool from_bt_firmware;
    bool completes; /* Frozen response indication, not request/owner rundown. */
    uint8_t sequence;
    enum rtwn8723be_btc_mp_field field;
    uint32_t value;
    uint8_t firmware_subversion;
};
/* Mutate only the first two bytes exactly as the frozen H2C0x67 encoder.
 * Actual H2C submission, admitted request lifetime and native completion
 * require the full BTC owner. No hardware is accessed by this function. */
int rtwn8723be_btc_mp_prepare(uint8_t, uint8_t *, size_t);
/* Decode the BT_MP event payload (without the two-byte generic C2H envelope).
 * Invalid lengths preserve output. Values are copied with aligned-safe
 * byte loads. A consumer must supply real request matching/serialization;
 * this reply does not claim that a firmware transaction completed.
 * Frozen sequence0xb does not update a forbidden-slot cache: the source
 * switch uses opcode49, unreachable by a four-bit sequence. */
int rtwn8723be_btc_mp_decode(const uint8_t *, size_t,
    struct rtwn8723be_btc_mp_reply *);
#endif
