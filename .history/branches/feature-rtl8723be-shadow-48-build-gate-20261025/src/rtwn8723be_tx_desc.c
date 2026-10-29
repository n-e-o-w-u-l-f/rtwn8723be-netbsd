/* SPDX-License-Identifier: GPL-2.0 */
/* Pinned Linux rtl8723be/trx.h descriptor layout and trx.c fill order. */
#include "rtwn8723be_os_compat.h"
#include "rtwn8723be_tx_desc.h"

static void
r23be_put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

int
rtwn8723be_tx_encode(const struct rtwn8723be_tx_params *p,
    uint8_t *out, size_t outlen)
{
    uint32_t d[16] = { 0 };
    uint8_t header_offset;
    unsigned int i;

    if (p == NULL || out == NULL ||
        outlen < RTWN8723BE_TX_RING_STRIDE)
        return EINVAL;
    if (p->packet_len == 0 || p->buffer_len == 0 ||
        p->packet_len > p->buffer_len || p->buffer_len > 9100U ||
        p->buffer_dma == 0 || p->next_desc_dma == 0 ||
        (p->next_desc_dma & (RTWN8723BE_TX_RING_STRIDE - 1U)) != 0)
        return EINVAL;
    if (p->seq > 4095U || p->fw_queue > 31U ||
        p->macid > 127U || p->rateid > 31U ||
        p->hw_rate > 127U || p->rts_rate > 31U ||
        p->rts_sc > 15U || p->ampdu_density > 7U ||
        p->subcarrier > 15U ||
        (p->security != 0U && p->security != 1U &&
        p->security != 3U))
        return EINVAL;
    if (!p->first_segment && p->buffer_len != p->packet_len)
        return EINVAL;
    if (p->first_segment &&
        p->buffer_len != p->packet_len &&
        p->buffer_len != (unsigned int)p->packet_len +
            RTWN8723BE_TX_EARLY_HDR)
        return EINVAL;
    header_offset = RTWN8723BE_TX_HEADER_LEN;
    if (p->first_segment &&
        p->buffer_len != p->packet_len)
        header_offset += RTWN8723BE_TX_EARLY_HDR;

    /*
     * The Linux fill path writes most policy only for first fragments.
     * DW12 (linked descriptor) is reestablished in every output, including
     * after clearing the first 40 bytes.
     */
    if (p->first_segment) {
        d[0] |= (uint32_t)p->packet_len;
        d[0] |= (uint32_t)header_offset << 16;
        if (header_offset > RTWN8723BE_TX_HEADER_LEN)
            d[1] |= 1U << 24; /* one 8-byte early-mode header */
        d[4] |= (uint32_t)p->hw_rate;
        d[4] |= 0x1fU << 8; /* DATA_RATE_FB_LIMIT */
        d[4] |= 0x0fU << 13; /* RTS_RATE_FB_LIMIT */
        d[4] |= (uint32_t)p->rts_rate << 24;
        if (p->short_gi_or_preamble)
            d[5] |= 1U << 4;
        if (p->ampdu) {
            d[2] |= 1U << 12;
            d[3] |= 0x14U << 17;
        }
        d[9] |= (uint32_t)p->seq << 12;
        if (p->rts_enable && !p->cts2self)
            d[3] |= 1U << 12;
        if (p->cts2self)
            d[3] |= 1U << 11;
        if (p->rts_short)
            d[5] |= 1U << 12;
        d[5] |= (uint32_t)p->rts_sc << 13;
        if (p->nav_use_hdr)
            d[3] |= 1U << 15;
        if (p->data_bw_40)
            d[5] |= 1U << 5;
        d[5] |= (uint32_t)p->subcarrier;
        d[2] |= (uint32_t)p->ampdu_density << 20;
        d[1] |= (uint32_t)p->security << 22;
        d[1] |= (uint32_t)p->fw_queue << 8;
        if (p->disable_rate_fallback)
            d[3] |= 1U << 10;
        if (p->use_driver_rate)
            d[3] |= 1U << 8;
        if (p->qos_data && p->rdg) {
            d[2] |= 1U << 13;
            d[0] |= 1U << 25;
        }
    }

    if (p->first_segment)
        d[0] |= 1U << 27;
    if (p->last_segment)
        d[0] |= 1U << 26;
    else
        d[2] |= 1U << 17;

    d[7] |= (uint32_t)p->buffer_len;
    d[10] = p->buffer_dma;
    d[12] = p->next_desc_dma;
    d[1] |= (uint32_t)p->rateid << 16;
    d[1] |= (uint32_t)p->macid;

    if (!p->qos_data)
        d[8] |= 1U << 15; /* Linux HWSEQ_EN, HWSEQ_SEL zero */
    if (p->multicast)
        d[0] |= 1U << 24;

    /* OWN bit is deliberately zero until the caller completes DMA sync. */
    memset(out, 0, RTWN8723BE_TX_RING_STRIDE);
    for (i = 0; i < 16; i++)
        r23be_put32(out + i * sizeof(uint32_t), d[i]);
    return 0;
}

int
rtwn8723be_tx_encode_command(uint16_t packet_len, uint32_t buffer_dma,
    uint32_t next_desc_dma, uint8_t *out, size_t outlen)
{
    uint32_t d[16] = { 0 };
    unsigned int i;

    if (out == NULL || outlen < RTWN8723BE_TX_RING_STRIDE ||
        packet_len == 0 || packet_len > 9100U ||
        buffer_dma == 0 || next_desc_dma == 0 ||
        (next_desc_dma & (RTWN8723BE_TX_RING_STRIDE - 1U)) != 0)
        return EINVAL;

    /* Pinned rtl8723be_tx_fill_cmddesc(): NO data/RTS fallback fields. */
    d[0] = (uint32_t)packet_len |
        ((uint32_t)RTWN8723BE_TX_HEADER_LEN << 16) |
        (1U << 26) | (1U << 27);
    d[1] = (uint32_t)RTWN8723BE_TX_FW_BEACON << 8;
    d[3] = 1U << 8; /* explicitly 1 Mbps, USE_RATE */
    d[7] = packet_len;
    d[10] = buffer_dma;
    d[12] = next_desc_dma;

    /* Source sets OWN before returning; NetBSD sets it only AFTER sync. */
    memset(out, 0, RTWN8723BE_TX_RING_STRIDE);
    for (i = 0; i < 16; i++)
        r23be_put32(out + i * sizeof(uint32_t), d[i]);
    return 0;
}
