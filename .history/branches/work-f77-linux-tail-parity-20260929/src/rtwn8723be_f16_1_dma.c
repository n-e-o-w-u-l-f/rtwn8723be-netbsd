#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/mbuf.h>
#include <sys/bus.h>

#include "rtwn8723be_f16_1.h"

/*
 * F16.1 DMA layer.
 *
 * The ownership model is taken from Linux rtl8723be/trx.h/trx.c; only the
 * kernel DMA API is changed.  Hardware descriptor layout is intentionally
 * unchanged.
 */

int
rtwn8723be_f16_1_ring_alloc(bus_dma_tag_t dmat, uint32_t count,
    size_t desc_size, void **kvap, bus_dmamap_t *mapp, bus_addr_t *paddrp)
{
    bus_dma_segment_t seg;
    int rsegs;
    int error;
    void *kva;

    kva = kmem_zalloc((size_t)count * desc_size, KM_SLEEP);
    error = bus_dmamap_create(dmat, (size_t)count * desc_size, 1,
        (size_t)count * desc_size, 0, BUS_DMA_WAITOK, mapp);
    if (error != 0) {
        kmem_free(kva, (size_t)count * desc_size);
        return error;
    }

    error = bus_dmamap_load(dmat, *mapp, kva,
        (size_t)count * desc_size, NULL, BUS_DMA_WAITOK);
    if (error != 0) {
        bus_dmamap_destroy(dmat, *mapp);
        kmem_free(kva, (size_t)count * desc_size);
        return error;
    }

    rsegs = (*mapp)->dm_nsegs;
    if (rsegs != 1) {
        bus_dmamap_unload(dmat, *mapp);
        bus_dmamap_destroy(dmat, *mapp);
        kmem_free(kva, (size_t)count * desc_size);
        return EFBIG;
    }

    seg = (*mapp)->dm_segs[0];
    *kvap = kva;
    *paddrp = seg.ds_addr;

    bus_dmamap_sync(dmat, *mapp, 0,
        (size_t)count * desc_size, BUS_DMASYNC_PREREAD | BUS_DMASYNC_PREWRITE);
    return 0;
}

void
rtwn8723be_f16_1_ring_free(bus_dma_tag_t dmat, uint32_t count,
    size_t desc_size, void *kva, bus_dmamap_t map)
{
    if (map != NULL) {
        bus_dmamap_sync(dmat, map, 0, (size_t)count * desc_size,
            BUS_DMASYNC_POSTREAD | BUS_DMASYNC_POSTWRITE);
        bus_dmamap_unload(dmat, map);
        bus_dmamap_destroy(dmat, map);
    }
    if (kva != NULL)
        kmem_free(kva, (size_t)count * desc_size);
}

int
rtwn8723be_f16_1_tx_sync(bus_dma_tag_t dmat, bus_dmamap_t map,
    size_t offset, size_t len)
{
    return bus_dmamap_sync(dmat, map, offset, len,
        BUS_DMASYNC_PREWRITE);
}

int
rtwn8723be_f16_1_rx_sync_for_cpu(bus_dma_tag_t dmat, bus_dmamap_t map,
    size_t offset, size_t len)
{
    return bus_dmamap_sync(dmat, map, offset, len,
        BUS_DMASYNC_POSTREAD);
}

int
rtwn8723be_f16_1_rx_sync_for_device(bus_dma_tag_t dmat, bus_dmamap_t map,
    size_t offset, size_t len)
{
    return bus_dmamap_sync(dmat, map, offset, len,
        BUS_DMASYNC_PREREAD);
}

/*
 * Packet DMA mapping follows the same ownership boundary as Linux:
 * map -> fill descriptor -> PREWRITE -> OWN=1 -> hardware -> OWN=0 ->
 * POSTWRITE/unmap.
 */
int
rtwn8723be_f16_1_map_tx_mbuf(bus_dma_tag_t dmat, struct mbuf *m,
    bus_dmamap_t map)
{
    return bus_dmamap_load_mbuf(dmat, map, m, BUS_DMA_NOWAIT);
}
