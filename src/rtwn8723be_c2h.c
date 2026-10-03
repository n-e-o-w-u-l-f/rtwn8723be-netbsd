/* SPDX-License-Identifier: GPL-2.0 */
/*
 * RTL8723BE C2H event decode from pinned Linux:
 * rtlwifi/wifi.h:GET_C2H_CMD_ID/SEQ/DATA_PTR and TX_REPORT_V1 fields,
 * rtlwifi/base.c:rtl_c2h_content_parsing/rtl_c2h_fast_cmd.
 */
#include <errno.h>
#include <string.h>
#include "rtwn8723be_c2h.h"

#define R23BE_C2H_ENVELOPE_SIZE 2U
#define R23BE_C2H_TX_REPORT_V1_SIZE 7U

int
rtwn8723be_c2h_decode(const uint8_t *data, size_t length,
    struct rtwn8723be_c2h_event *event)
{
    uint8_t id;
    size_t payload_len;

    if (data == NULL || event == NULL)
        return EINVAL;
    memset(event, 0, sizeof(*event));
    if (length < R23BE_C2H_ENVELOPE_SIZE)
        return EMSGSIZE;

    id = data[0];
    payload_len = length - R23BE_C2H_ENVELOPE_SIZE;
    event->id = id;
    event->sequence = data[1];
    event->payload = data + R23BE_C2H_ENVELOPE_SIZE;
    event->payload_length = payload_len;

    switch (id) {
    case R23BE_C2H_DEBUG:
    case R23BE_C2H_LOOPBACK:
    case R23BE_C2H_TXBF:
    case R23BE_C2H_BT_INFO:
    case R23BE_C2H_RA_REPORT:
    case R23BE_C2H_FW_SWITCH_CHANNEL:
    case R23BE_C2H_IQK_FINISH:
        event->recognized = true;
        break;
    case R23BE_C2H_BT_MP:
        event->recognized = true;
        event->fast = true;
        break;
    case R23BE_C2H_TX_REPORT:
        /* GET_TX_REPORT_SN_V1(payload) reads payload[6]. */
        if (payload_len < R23BE_C2H_TX_REPORT_V1_SIZE)
            return EMSGSIZE;
        event->recognized = true;
        event->tx_report_valid = true;
        event->tx_report_sequence = event->payload[6];
        event->tx_report_status = event->payload[0] & 0xc0U;
        event->tx_report_retry = event->payload[2] & 0x3fU;
        break;
    case R23BE_C2H_EXT_V2:
        /* V2 payloads use a distinct layout. Do not parse as v1. */
        event->recognized = true;
        break;
    default:
        /* Pinned rtl_c2h_content_parsing logs and ignores unknown IDs. */
        break;
    }
    return 0;
}
