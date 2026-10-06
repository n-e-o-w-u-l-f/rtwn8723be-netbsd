/* SPDX-License-Identifier: GPL-2.0 */
/* Reference: Linux fd179f8a, rtlwifi/btcoexist halbtcoutsrc.c and rtl_btc.c. */
#include "rtwn8723be_btc_mp.h"

int
rtwn8723be_btc_mp_prepare(uint8_t opcode, uint8_t *command, size_t length)
{
    uint8_t sequence;
    if (command == NULL)
        return EINVAL;
    if (length < 2)
        return EMSGSIZE;
    switch (opcode) {
    case R23BE_BT_OP_VERSION: sequence = 0xe; break;
    case R23BE_BT_OP_AFH_L: sequence = 0x5; break;
    case R23BE_BT_OP_AFH_M: sequence = 0x6; break;
    case R23BE_BT_OP_AFH_H: sequence = 0x9; break;
    case R23BE_BT_OP_FEATURE: sequence = 0x7; break;
    case R23BE_BT_OP_SUPPORTED_VERSION: sequence = 0x8; break;
    case R23BE_BT_OP_ANT_DETECTION: sequence = 0x2; break;
    case R23BE_BT_OP_BLE_SCAN_PARAMETERS: sequence = 0x3; break;
    case R23BE_BT_OP_BLE_SCAN_TYPE: sequence = 0x4; break;
    case R23BE_BT_OP_DEVICE_INFO: sequence = 0xa; break;
    case R23BE_BT_OP_FORBIDDEN_SLOT: sequence = 0xb; break;
    default: sequence = 0; break;
    }
    /* Frozen OperVer=0; the caller's existing bits are OR-preserved. */
    command[0] |= (uint8_t)(sequence << 4);
    command[1] = opcode;
    return 0;
}

static uint32_t
rtwn8723be_btc_mp_le32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
        ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

int
rtwn8723be_btc_mp_decode(const uint8_t *payload, size_t length,
    struct rtwn8723be_btc_mp_reply *out)
{
    struct rtwn8723be_btc_mp_reply reply = {0};
    size_t needed = 4;

    if (payload == NULL || out == NULL)
        return EINVAL;
    if (length < 4)
        return EMSGSIZE;
    if (payload[0] != 1) {
        *out = reply;
        return 0;
    }
    reply.from_bt_firmware = true;
    reply.completes = true;
    reply.sequence = payload[2] >> 4;
    switch (reply.sequence) {
    case 0xe: reply.field = R23BE_BT_MP_VERSION; needed = 6; break;
    case 0x5: reply.field = R23BE_BT_MP_AFH_L; needed = 7; break;
    case 0x6: reply.field = R23BE_BT_MP_AFH_M; needed = 7; break;
    case 0x9: reply.field = R23BE_BT_MP_AFH_H; needed = 5; break;
    case 0x7: reply.field = R23BE_BT_MP_FEATURE; needed = 5; break;
    case 0x8: reply.field = R23BE_BT_MP_SUPPORTED_VERSION; needed = 5; break;
    case 0x2: reply.field = R23BE_BT_MP_ANT_DETECTION; break;
    case 0x3: reply.field = R23BE_BT_MP_BLE_SCAN_PARAMETERS; needed = 7; break;
    case 0x4: reply.field = R23BE_BT_MP_BLE_SCAN_TYPE; break;
    case 0xa: reply.field = R23BE_BT_MP_DEVICE_INFO; needed = 7; break;
    default:
        /* Includes0xb: preserve the frozen unreachable opcode49 case. */
        break;
    }
    if (length < needed)
        return EMSGSIZE;
    if (reply.field == R23BE_BT_MP_VERSION) {
        reply.value = (uint32_t)payload[3] | ((uint32_t)payload[4] << 8);
        reply.firmware_subversion = payload[5];
    } else if (needed == 7) {
        reply.value = rtwn8723be_btc_mp_le32(payload + 3);
    } else if (needed == 5) {
        reply.value = (uint32_t)payload[3] | ((uint32_t)payload[4] << 8);
    } else if (reply.field != R23BE_BT_MP_NONE) {
        reply.value = payload[3];
    }
    *out = reply;
    return 0;
}
