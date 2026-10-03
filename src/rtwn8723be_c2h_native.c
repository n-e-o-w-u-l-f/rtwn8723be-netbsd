/* SPDX-License-Identifier: GPL-2.0 */
/* Validated old-TRX DMA C2H frame -> typed synchronous firmware callbacks. */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/errno.h>

#include "rtwn8723be_c2h_native.h"

int
rtwn8723be_c2h_native_receive(
    const struct rtwn8723be_c2h_handlers *handlers,
    const uint8_t *data, size_t length,
    const struct rtwn8723be_rx_packet *packet)
{
    if (handlers == NULL || data == NULL || packet == NULL)
        return EINVAL;
    if (packet->kind != RTWN8723BE_RX_C2H ||
        packet->packet_length != length || length < 2U ||
        packet->crc_error || packet->icv_error ||
        packet->c2h_payload_length != length - 2U ||
        packet->c2h_payload_offset != packet->packet_offset + 2U ||
        packet->c2h_id != data[0] || packet->c2h_seq != data[1])
        return EINVAL;

    /*
     * The RX ring owns data until this synchronous callback returns.
     * Higher-level handlers must copy data before deferring work, as in
     * frozen Linux rtl_c2hcmd_enqueue()'s skb-owned delayed queue.
     */
    return rtwn8723be_c2h_route(data, length, handlers);
}
