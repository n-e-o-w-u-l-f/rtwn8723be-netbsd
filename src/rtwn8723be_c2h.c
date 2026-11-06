/* SPDX-License-Identifier: GPL-2.0 */
/*
 * RTL8723BE C2H event decode from pinned Linux:
 * rtlwifi/wifi.h:GET_C2H_CMD_ID/SEQ/DATA_PTR and TX_REPORT_V1 fields,
 * rtlwifi/base.c:rtl_c2h_content_parsing/rtl_c2h_fast_cmd.
 */
#include "rtwn8723be_os_compat.h"
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

int
rtwn8723be_c2h_route(const uint8_t *data, size_t length,
    const struct rtwn8723be_c2h_handlers *handlers)
{
    struct rtwn8723be_c2h_event event;
    int error;

    if (handlers == NULL)
        return EINVAL;
    error = rtwn8723be_c2h_decode(data, length, &event);
    if (error != 0)
        return error;

    /* Firmware event handlers execute before the RX slot is re-armed. */
    switch (event.id) {
    case R23BE_C2H_TX_REPORT:
        if (handlers->tx_report == NULL)
            return ENOSYS;
        return handlers->tx_report(handlers->arg, &event);
    case R23BE_C2H_RA_REPORT:
        if (handlers->ra_report == NULL)
            return ENOSYS;
        return handlers->ra_report(handlers->arg, &event);
    case R23BE_C2H_BT_INFO:
        if (handlers->bt_info == NULL)
            return ENOSYS;
        return handlers->bt_info(handlers->arg, &event);
    case R23BE_C2H_BT_MP:
        if (handlers->bt_mp == NULL)
            return ENOSYS;
        return handlers->bt_mp(handlers->arg, &event);
    case R23BE_C2H_EXT_V2:
        /* Unknown v2 layout is not safely interpretable as a v1 event. */
        return EOPNOTSUPP;
    default:
        /*
         * Pinned rtl_c2h_content_parsing() has no action for other IDs
         * (it logs and ignores debug/TXBF/unrecognized notifications).
         */
        return 0;
    }
}
