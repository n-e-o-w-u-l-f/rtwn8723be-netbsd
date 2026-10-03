/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_RX_DECODE_H_
#define _RTWN8723BE_RX_DECODE_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/*
 * Frozen Linux rtl8723be/trx.h descriptor: 8 little-endian DWORDs;
 * old-TRX-flow descriptor lives in the coherent ring, NOT in the buffer.
 * RX report type is DWORD2 BIT(28). C2H events begin at the same
 * drvinfo+shift offset as normal received frames.
 */
#define RTWN8723BE_RX_DESC_BYTES       32U
#define RTWN8723BE_RX_DRVINFO_UNIT      8U
#define RTWN8723BE_RX_C2H_HEADER_BYTES  2U
#define RTWN8723BE_RX_BUFFER_BYTES   9100U

enum rtwn8723be_rx_kind {
    RTWN8723BE_RX_FRAME = 0,
    RTWN8723BE_RX_C2H = 1
};

struct rtwn8723be_rx_packet {
    enum rtwn8723be_rx_kind kind;
    size_t packet_offset;
    size_t packet_length;
    bool crc_error;
    bool icv_error;
    bool software_decryption;
    uint8_t rate;
    uint8_t mac_id;
    /* Filled by native PHY decoding after the descriptor is validated. */
    bool rssi_valid;
    int rssi_dbm;
    uint8_t c2h_id;
    uint8_t c2h_seq;
    size_t c2h_payload_offset;
    size_t c2h_payload_length;
};

/*
 * desc points to 32 raw coherent descriptor bytes AFTER bus_dmamap_sync
 * POSTREAD; buffer points to the mapped packet-buffer data AFTER POSTREAD.
 * Return: 0 valid; EAGAIN OWN still set; EMSGSIZE malformed/truncated;
 * EINVAL missing/invalid arguments.
 * Parsing never changes descriptor OWN, copies data, or forwards a frame.
 */
int rtwn8723be_rx_decode(const uint8_t *desc, size_t desc_size,
    const uint8_t *buffer, size_t buffer_size,
    struct rtwn8723be_rx_packet *packet);

#endif /* _RTWN8723BE_RX_DECODE_H_ */
