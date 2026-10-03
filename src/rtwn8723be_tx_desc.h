/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_TX_DESC_H_
#define _RTWN8723BE_TX_DESC_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/*
 * Linux rtl8723be/trx.c: rtl8723be_tx_fill_desc() and trx.h bitfields.
 * PCI old-TRX uses a 64-byte ring stride; hardware packet fields occupy
 * the first 40 bytes, DW10 points to the mapped buffer, DW12 to next ring.
 * This pure encoder does NOT submit a packet or set OWN: the NetBSD ring
 * adapter must first map/sync the packet, sync the descriptor, then publish
 * OWN with the necessary bus_dma ordering. Never transmit an invalid entry.
 */
#define RTWN8723BE_TX_RING_STRIDE 64U
#define RTWN8723BE_TX_HEADER_LEN  40U
#define RTWN8723BE_TX_EARLY_HDR    8U

enum rtwn8723be_tx_fw_queue {
    RTWN8723BE_TX_FW_BE = 0x00,
    RTWN8723BE_TX_FW_BK = 0x02,
    RTWN8723BE_TX_FW_VI = 0x05,
    RTWN8723BE_TX_FW_VO = 0x07,
    RTWN8723BE_TX_FW_BEACON = 0x10,
    RTWN8723BE_TX_FW_HIGH = 0x11,
    RTWN8723BE_TX_FW_MGNT = 0x12,
    RTWN8723BE_TX_FW_CMD = 0x13
};

struct rtwn8723be_tx_params {
    uint16_t packet_len;
    uint16_t buffer_len;
    uint32_t buffer_dma;
    uint32_t next_desc_dma;
    uint16_t seq;             /* 0..4095 from IEEE80211_SCTL_SEQ >> 4 */
    uint8_t fw_queue;         /* validated caller selection (QSLT_*) */
    uint8_t macid;
    uint8_t rateid;
    uint8_t hw_rate;
    uint8_t rts_rate;
    uint8_t rts_sc;
    uint8_t security;         /* 0 none/SW; 1 WEP/TKIP; 3 CCMP */
    uint8_t ampdu_density;
    uint8_t subcarrier;
    bool first_segment;
    bool last_segment;
    bool qos_data;
    bool ampdu;
    bool short_gi_or_preamble;
    bool rts_enable;
    bool cts2self;
    bool rts_short;
    bool nav_use_hdr;
    bool use_driver_rate;
    bool disable_rate_fallback;
    bool rdg;
    bool data_bw_40;
    bool multicast;
};

/* Both encoders return zero or EINVAL/EFBIG without publishing OWN. */
int rtwn8723be_tx_encode(const struct rtwn8723be_tx_params *,
    uint8_t *descriptor, size_t descriptor_len);

/* Linux rtl8723be_tx_fill_cmddesc(): 1 Mbps/BEACON, forced rate. */
int rtwn8723be_tx_encode_command(uint16_t packet_len, uint32_t buffer_dma,
    uint32_t next_desc_dma, uint8_t *descriptor, size_t descriptor_len);

#endif
