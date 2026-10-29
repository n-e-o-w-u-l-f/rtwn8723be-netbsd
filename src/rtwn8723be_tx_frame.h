/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Source-shared, fail-closed NetBSD net80211 802.11 TX frame preflight.
 * Hardware queue numbers are selected separately by the native datapath;
 * this parser does not acquire an mbuf, node or DMA descriptor.
 */
#ifndef _RTWN8723BE_TX_FRAME_H_
#define _RTWN8723BE_TX_FRAME_H_

#include "rtwn8723be_tx_desc.h"

enum rtwn8723be_tx_frame_ac {
    R23BE_TX_FRAME_BK = 0,
    R23BE_TX_FRAME_BE = 1,
    R23BE_TX_FRAME_VI = 2,
    R23BE_TX_FRAME_VO = 3,
    R23BE_TX_FRAME_MGMT = 4,
};

struct rtwn8723be_tx_frame_plan {
    enum rtwn8723be_tx_frame_ac ac;
    uint8_t fw_queue;
    uint16_t seq;
    bool qos_data;
    bool multicast;
    bool management;
};

/*
 * frame is a complete, contiguous 802.11 MPDU (not Ethernet).
 * sw_crypto_complete is set ONLY by the caller after any required
 * ieee80211_crypto_encap has succeeded; the protected bit alone does
 * not demonstrate installed keys or completed software encryption.
 * No hardware CAM/security offload is selected by this parser.
 *
 * No ownership transfer on error. The resulting frame plan is copied
 * out only on success; this function never modifies an 802.11 frame.
 */
static inline int
rtwn8723be_tx_frame_plan(const uint8_t *frame, size_t len,
    bool sw_crypto_complete, struct rtwn8723be_tx_frame_plan *out)
{
    struct rtwn8723be_tx_frame_plan plan = { 0 };
    uint8_t type, fc0, fc1, tid;

    if (frame == NULL || out == NULL)
        return EINVAL;
    if (len < 24)
        return EINVAL;
    if (len > 9100)
        return EFBIG;

    fc0 = frame[0];
    fc1 = frame[1];
    if ((fc0 & 0x03U) != 0)
        return EOPNOTSUPP; /* Only legacy 802.11 protocol version 0. */
    type = fc0 & 0x0cU;
    if (type != 0x00U && type != 0x08U)
        return EOPNOTSUPP; /* Never submit control/reserved frames. */
    if ((fc1 & 0x03U) == 0x03U)
        return EOPNOTSUPP; /* Four-address/WDS unsupported. */
    if (type == 0x00U && (fc1 & 0x03U) != 0)
        return EOPNOTSUPP; /* Management frames cannot use DS bits. */
    if ((fc1 & 0x04U) != 0 || (frame[22] & 0x0fU) != 0)
        return EOPNOTSUPP; /* Fragment chaining not implemented. */
    if ((fc1 & 0x40U) != 0 && !sw_crypto_complete)
        return EACCES; /* Do not DMA a still-unencrypted WPA frame. */

    plan.seq = (uint16_t)(((uint16_t)frame[22] |
        ((uint16_t)frame[23] << 8)) >> 4);
    plan.multicast = (frame[4] & 1U) != 0;
    if (type == 0x00U) {
        plan.management = true;
        plan.ac = R23BE_TX_FRAME_MGMT;
        plan.fw_queue = RTWN8723BE_TX_FW_MGNT;
    } else {
        if ((fc0 & 0x40U) != 0)
            return EOPNOTSUPP; /* Null data/QoS-null have no payload. */
        plan.qos_data = (fc0 & 0x80U) != 0;
        if (plan.qos_data) {
            if ((fc1 & 0x80U) != 0)
                return EOPNOTSUPP; /* Unimplemented HT control header. */
            if (len < 26)
                return EINVAL;
            tid = frame[24] & 0x0fU;
            if (tid > 7)
                return EOPNOTSUPP; /* Not a normal WME TID. */
            if (tid == 1 || tid == 2)
                plan.ac = R23BE_TX_FRAME_BK;
            else if (tid == 4 || tid == 5)
                plan.ac = R23BE_TX_FRAME_VI;
            else if (tid == 6 || tid == 7)
                plan.ac = R23BE_TX_FRAME_VO;
            else
                plan.ac = R23BE_TX_FRAME_BE; /* TID 0 and 3. */
        } else {
            plan.ac = R23BE_TX_FRAME_BE;
        }
        switch (plan.ac) {
        case R23BE_TX_FRAME_BK:
            plan.fw_queue = RTWN8723BE_TX_FW_BK;
            break;
        case R23BE_TX_FRAME_VI:
            plan.fw_queue = RTWN8723BE_TX_FW_VI;
            break;
        case R23BE_TX_FRAME_VO:
            plan.fw_queue = RTWN8723BE_TX_FW_VO;
            break;
        default:
            plan.fw_queue = RTWN8723BE_TX_FW_BE;
            break;
        }
    }
    *out = plan;
    return 0;
}
#endif /* _RTWN8723BE_TX_FRAME_H_ */
