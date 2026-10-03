/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Native RTL8723BE old-TRX RX ring consumer.
 * Descriptor parse is the source-identical host-tested rx_decode.c module;
 * DMA/barrier/mbuf ownership is NetBSD-specific and awaits native compile,
 * fault-injection, net80211 dispatch and HP runtime gates.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <sys/endian.h>
#include <sys/mbuf.h>
#include <sys/bus.h>

#include "rtwn8723be_rx_native.h"
#include "rtwn8723be_rx_phy.h"
#include "rtwn8723be_c2h.h"

int
rtwn8723be_rx_native_drain(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_rx_dispatch *dispatch, size_t *delivered)
{
    size_t seen = 0;
    unsigned int q;
    int first_error = 0;

    if (sc == NULL || dispatch == NULL || delivered == NULL)
        return EINVAL;
    *delivered = 0;
    /* Do not touch MMIO or bus_dma until BOTH packet paths can be serviced. */
    if (dispatch->frame == NULL || dispatch->c2h == NULL)
        return ENOSYS;
    if (!sc->sc_mapped || !sc->sc_rings_allocated ||
        sc->sc_dmat == NULL)
        return ENXIO;

    for (q = 0; q < RTWN8723BE_RX_QUEUE_COUNT; q++) {
        struct rtwn8723be_rx_ring *ring = &sc->sc_rx_ring[q];
        struct rtwn8723be_rx_desc *descs = ring->desc_dma.kva;
        unsigned int work;

        if (ring->count == 0 || ring->count > RTWN8723BE_RX_RING_COUNT ||
            descs == NULL || ring->slot == NULL ||
            ring->desc_dma.map == NULL ||
            ring->consumer >= ring->count)
            return EIO;

        /* Each IRQ runs at most one complete rotation per RX queue. */
        for (work = 0; work < ring->count; work++) {
            const unsigned int idx = ring->consumer;
            struct rtwn8723be_dma_slot *slot = &ring->slot[idx];
            struct rtwn8723be_rx_desc *desc = &descs[idx];
            const bus_size_t off = (bus_size_t)idx *
                sizeof(*desc);
            struct rtwn8723be_rx_packet pkt;
            const uint8_t *data;
            uint32_t d0;
            int error;

            rtwn8723be_f16_1_dma_sync_for_cpu(sc->sc_dmat,
                &ring->desc_dma, off, sizeof(*desc));
            d0 = le32toh(desc->d[0]);
            if ((d0 & R23BE_RXD0_OWN) != 0) {
                rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,
                    &ring->desc_dma, off, sizeof(*desc));
                break;
            }

            if (slot->map == NULL || slot->map->dm_nsegs != 1 ||
                slot->m == NULL ||
                slot->m->m_len < RTWN8723BE_RX_BUFFER_SIZE ||
                slot->map->dm_segs[0].ds_addr >
                    RTWN8723BE_DMA_MAXADDR)
                return EIO; /* Do not rearm a corrupt DMA slot. */

            bus_dmamap_sync(sc->sc_dmat, slot->map, 0,
                RTWN8723BE_RX_BUFFER_SIZE, BUS_DMASYNC_POSTREAD);
            data = mtod(slot->m, const uint8_t *);
            error = rtwn8723be_rx_decode(
                (const uint8_t *)desc, sizeof(*desc), data,
                RTWN8723BE_RX_BUFFER_SIZE, &pkt);
            if (error == 0 && !pkt.crc_error && !pkt.icv_error) {
                if (pkt.kind == RTWN8723BE_RX_FRAME) {
                    int phy_error;
                    phy_error = rtwn8723be_rx_phy_rssi(
                        (const uint8_t *)desc, sizeof(*desc), data,
                        RTWN8723BE_RX_BUFFER_SIZE, &pkt.rssi_dbm);
                    if (phy_error == 0)
                        pkt.rssi_valid = true;
                    else if (phy_error != ENODATA)
                        error = phy_error;
                }
                if (error == 0 && pkt.kind == RTWN8723BE_RX_C2H) {
                    struct rtwn8723be_c2h_event event;

                    /* Reject malformed v1 firmware events before callback. */
                    error = rtwn8723be_c2h_decode(
                        data + pkt.packet_offset,
                        pkt.packet_length, &event);
                    if (error == 0)
                        error = dispatch->c2h(dispatch->arg,
                            data + pkt.packet_offset,
                            pkt.packet_length, &pkt);
                }
                else if (error == 0)
                    error = dispatch->frame(dispatch->arg,
                        data + pkt.packet_offset,
                        pkt.packet_length, &pkt);
                if (error == 0)
                    seen++;
            } else if (error == 0) {
                error = EBADMSG; /* Reject corrupt RX/C2H frames. */
            }
            if (error != 0 && first_error == 0)
                first_error = error;

            /* The callback only borrowed data; this mbuf stays mapped. */
            bus_dmamap_sync(sc->sc_dmat, slot->map, 0,
                RTWN8723BE_RX_BUFFER_SIZE, BUS_DMASYNC_PREREAD);
            memset(desc, 0, sizeof(*desc));
            desc->d[6] = htole32((uint32_t)
                slot->map->dm_segs[0].ds_addr);
            d0 = RTWN8723BE_RX_BUFFER_SIZE | R23BE_RXD0_OWN;
            if (idx == ring->count - 1U)
                d0 |= R23BE_RXD0_EOR;
            desc->d[0] = htole32(d0);
            rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,
                &ring->desc_dma, off, sizeof(*desc));
            ring->consumer = (idx + 1U) % ring->count;
        }
    }
    *delivered = seen;
    return first_error;
}
