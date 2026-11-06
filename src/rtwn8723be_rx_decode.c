/* SPDX-License-Identifier: GPL-2.0 */
/* Exact old-TRX 8723BE descriptor fields from pinned Linux trx.h/trx.c. */
#include "rtwn8723be_os_compat.h"

#include "rtwn8723be_rx_decode.h"

static uint32_t
rtwn8723be_rx_le32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
        ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

int
rtwn8723be_rx_decode(const uint8_t *desc, size_t desc_size,
    const uint8_t *buffer, size_t buffer_size,
    struct rtwn8723be_rx_packet *packet)
{
    uint32_t d0, d1, d2, d3;
    size_t off, len;

    if (desc == NULL || buffer == NULL || packet == NULL ||
        desc_size < RTWN8723BE_RX_DESC_BYTES ||
        buffer_size > RTWN8723BE_RX_BUFFER_BYTES)
        return EINVAL;

    /* Never return a partly initialized result after malformed input. */
    memset(packet, 0, sizeof(*packet));
    d0 = rtwn8723be_rx_le32(desc);
    if ((d0 & (1U << 31)) != 0)
        return EAGAIN;
    d1 = rtwn8723be_rx_le32(desc + 4U);
    d2 = rtwn8723be_rx_le32(desc + 8U);
    d3 = rtwn8723be_rx_le32(desc + 12U);

    len = (size_t)(d0 & 0x3fffU);
    off = (size_t)((d0 >> 16) & 0x0fU) *
        RTWN8723BE_RX_DRVINFO_UNIT + (size_t)((d0 >> 24) & 0x03U);
    /* Subtract only after checking the offset to avoid size_t wraparound. */
    if (len == 0 || off > buffer_size || len > buffer_size - off)
        return EMSGSIZE;

    packet->kind = (d2 & (1U << 28)) != 0 ?
        RTWN8723BE_RX_C2H : RTWN8723BE_RX_FRAME;
    packet->packet_offset = off;
    packet->packet_length = len;
    packet->crc_error = (d0 & (1U << 14)) != 0;
    packet->icv_error = (d0 & (1U << 15)) != 0;
    packet->software_decryption = (d0 & (1U << 27)) != 0;
    packet->mac_id = (uint8_t)(d1 & 0x7fU);
    packet->rate = (uint8_t)(d3 & 0x7fU);

    if (packet->kind == RTWN8723BE_RX_C2H) {
        /* Linux wifi.h GET_C2H_CMD_ID/SEQ and C2H_DATA_OFFSET=2. */
        if (len < RTWN8723BE_RX_C2H_HEADER_BYTES) {
            memset(packet, 0, sizeof(*packet));
            return EMSGSIZE;
        }
        packet->c2h_id = buffer[off];
        packet->c2h_seq = buffer[off + 1U];
        packet->c2h_payload_offset =
            off + RTWN8723BE_RX_C2H_HEADER_BYTES;
        packet->c2h_payload_length =
            len - RTWN8723BE_RX_C2H_HEADER_BYTES;
    }
    return 0;
}
