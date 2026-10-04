/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Frozen Linux rtl8723be/trx.c:_rtl8723be_query_rxphystatus() and
 * rtl8723be/trx.h:struct phy_status_rpt. No compiler bitfields are used.
 * Only the independently specified received-signal-power portion is
 * extracted here; PHY calibration, path-EVM and CCK signal quality
 * remain separate integration work.
 */
#include "rtwn8723be_os_compat.h"
#include "rtwn8723be_rx_phy.h"

#define R23BE_PHY_RX_DESC_BYTES 32U
#define R23BE_PHY_MAX_RX_BYTES 9100U
#define R23BE_PHY_INFO_UNIT 8U

static uint32_t
r23be_phy_le32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
        ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

int
rtwn8723be_rx_phy_rssi(const uint8_t *desc, size_t desc_size,
    const uint8_t *buffer, size_t buffer_size, int *rssi_dbm)
{
    uint32_t d0, d3;
    size_t phy_size, shift, offset, packet_len;
    uint8_t rate, agc, lan, vga, pwdb;
    int dbm;

    if (desc == NULL || buffer == NULL || rssi_dbm == NULL ||
        desc_size < R23BE_PHY_RX_DESC_BYTES ||
        buffer_size > R23BE_PHY_MAX_RX_BYTES)
        return EINVAL;
    d0 = r23be_phy_le32(desc);
    if (d0 & (1U << 31))
        return EAGAIN;  /* Hardware still owns this ring entry. */
    /* C2H reports are firmware events, not measurable WLAN frames. */
    if (r23be_phy_le32(desc + 8U) & (1U << 28))
        return EINVAL;
    if (!(d0 & (1U << 26)))
        return ENODATA; /* No actual PHY status: do not fabricate RSSI. */

    phy_size = ((size_t)(d0 >> 16) & 0x0fU) * R23BE_PHY_INFO_UNIT;
    shift = ((size_t)(d0 >> 24) & 0x03U);
    packet_len = (size_t)(d0 & 0x3fffU);
    if (phy_size < 6U || shift > buffer_size ||
        phy_size > buffer_size - shift)
        return EMSGSIZE;
    offset = shift + phy_size;
    if (packet_len == 0U || offset > buffer_size ||
        packet_len > buffer_size - offset)
        return EMSGSIZE;

    d3 = r23be_phy_le32(desc + 12U);
    rate = (uint8_t)(d3 & 0x7fU);
    /* Linux RX_HAL_IS_CCK_RATE: 1M, 2M, 5.5M, 11M => rates 0..3. */
    if (rate <= 3U) {
        agc = buffer[shift + 5U];
        lan = (uint8_t)(agc >> 5);
        vga = (uint8_t)(agc & 0x1fU);
        switch (lan) {
        case 6: dbm = -34 - 2 * vga; break;
        case 4: dbm = -14 - 2 * vga; break;
        case 1: dbm =   6 - 2 * vga; break;
        case 0: dbm =  16 - 2 * vga; break;
        default:
            /* Linux leaves rx_pwr_all at zero for these AGC indices.
             * Zero is an uninitialized sentinel, NOT a measured RSSI. */
            return ENODATA;
        }
    } else {
        /* Linux: ((cck_sig_qual_ofdm_pwdb_all >> 1) & 0x7f) - 110. */
        pwdb = buffer[shift + 4U];
        dbm = (int)((pwdb >> 1) & 0x7fU) - 110;
    }

    /* NetBSD net80211 input expects an RSSI in [-127, 0] dBm. */
    if (dbm > 0)
        dbm = 0;
    *rssi_dbm = dbm;
    return 0;
}
