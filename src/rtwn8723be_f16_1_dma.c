#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/kmem.h>
#include <sys/mbuf.h>
#include <sys/bus.h>
#include <sys/endian.h>

#include "rtwn8723be_f16_1.h"

/*
 * DMA adaptation of pinned Linux rtlwifi/pci.c for RTL8723BE old-TRX flow.
 *
 * Hardware semantics remain Linux-identical:
 * - coherent descriptor rings;
 * - 256-byte ring alignment;
 * - one DMA address per TX/RX packet buffer;
 * - 64-byte TX PCI-ring stride with a linked next-descriptor pointer;
 * - two RX rings, each 512 entries;
 * - 9100-byte RX buffers;
 * - 32-bit DMA is enforced by the caller's NetBSD DMA subregion tag.
 */

int
rtwn8723be_f16_1_dma_mem_alloc(bus_dma_tag_t dmat,
    struct rtwn8723be_dma_mem *dma, bus_size_t size, bus_size_t alignment)
{
    bus_dmamap_t map;
    bus_dma_segment_t seg;
    void *kva;
    int nsegs;
    int error;

    memset(dma, 0, sizeof(*dma));
    dma->size = size;

    /*
     * bus_dma output arguments are not valid on failure.  Publish each
     * resource into dma only after its acquisition has succeeded, so the
     * common unwind never destroys an undefined map or unmaps stale KVA.
     */
    error = bus_dmamap_create(dmat, size, 1, size, 0,
        BUS_DMA_WAITOK | BUS_DMA_ALLOCNOW, &map);
    if (error != 0)
        goto fail;
    dma->map = map;

    error = bus_dmamem_alloc(dmat, size, alignment, 0, &seg, 1,
        &nsegs, BUS_DMA_WAITOK);
    if (error != 0)
        goto fail;
    dma->seg = seg;
    dma->nsegs = nsegs;
    if (dma->nsegs != 1) {
        error = EFBIG;
        goto fail;
    }

    error = bus_dmamem_map(dmat, &dma->seg, dma->nsegs, size, &kva,
        BUS_DMA_WAITOK);
    if (error != 0)
        goto fail;
    dma->kva = kva;

    error = bus_dmamap_load(dmat, dma->map, dma->kva, size, NULL,
        BUS_DMA_WAITOK);
    if (error != 0)
        goto fail;
    if (dma->map->dm_nsegs != 1) {
        error = EFBIG;
        goto fail;
    }

    memset(dma->kva, 0, size);
    dma->paddr = dma->map->dm_segs[0].ds_addr;
    bus_dmamap_sync(dmat, dma->map, 0, size,
        BUS_DMASYNC_PREREAD | BUS_DMASYNC_PREWRITE);
    return 0;

fail:
    rtwn8723be_f16_1_dma_mem_free(dmat, dma);
    return error;
}

void
rtwn8723be_f16_1_dma_mem_free(bus_dma_tag_t dmat,
    struct rtwn8723be_dma_mem *dma)
{
    /*
     * bus_dmamem_map() may have succeeded while bus_dmamap_load() failed.
     * NetBSD marks an unloaded map with dm_mapsize == 0; never synchronize
     * such a map.  Independently release the KVA and allocated segments.
     */
    if (dma->map != NULL && dma->map->dm_mapsize != 0) {
        if (dma->kva != NULL)
            bus_dmamap_sync(dmat, dma->map, 0, dma->map->dm_mapsize,
                BUS_DMASYNC_POSTREAD | BUS_DMASYNC_POSTWRITE);
        bus_dmamap_unload(dmat, dma->map);
    }

    if (dma->kva != NULL) {
        bus_dmamem_unmap(dmat, dma->kva, dma->size);
        dma->kva = NULL;
    }

    if (dma->nsegs != 0) {
        bus_dmamem_free(dmat, &dma->seg, dma->nsegs);
        dma->nsegs = 0;
    }

    if (dma->map != NULL) {
        bus_dmamap_destroy(dmat, dma->map);
        dma->map = NULL;
    }

    dma->paddr = 0;
    dma->size = 0;
}

void
rtwn8723be_f16_1_dma_sync_for_device(bus_dma_tag_t dmat,
    struct rtwn8723be_dma_mem *dma, bus_addr_t offset, bus_size_t len)
{
    bus_dmamap_sync(dmat, dma->map, offset, len,
        BUS_DMASYNC_PREREAD | BUS_DMASYNC_PREWRITE);
}

void
rtwn8723be_f16_1_dma_sync_for_cpu(bus_dma_tag_t dmat,
    struct rtwn8723be_dma_mem *dma, bus_addr_t offset, bus_size_t len)
{
    bus_dmamap_sync(dmat, dma->map, offset, len,
        BUS_DMASYNC_POSTREAD | BUS_DMASYNC_POSTWRITE);
}

int
rtwn8723be_f16_1_tx_ring_alloc(bus_dma_tag_t dmat,
    struct rtwn8723be_tx_ring *ring, uint32_t count)
{
    struct rtwn8723be_tx_desc *desc;
    bus_size_t size;
    uint32_t i;
    int error;

    memset(ring, 0, sizeof(*ring));
    ring->count = count;
    size = (bus_size_t)count * sizeof(struct rtwn8723be_tx_desc);

    error = rtwn8723be_f16_1_dma_mem_alloc(dmat, &ring->desc_dma, size,
        RTWN8723BE_RING_ALIGN);
    if (error != 0)
        return error;

    ring->slot = kmem_zalloc((size_t)count * sizeof(*ring->slot),
        KM_SLEEP);

    for (i = 0; i < count; i++) {
        error = bus_dmamap_create(dmat, RTWN8723BE_RX_BUFFER_SIZE, 1,
            RTWN8723BE_RX_BUFFER_SIZE, 0,
            BUS_DMA_WAITOK | BUS_DMA_ALLOCNOW, &ring->slot[i].map);
        if (error != 0)
            goto fail;
    }

    desc = ring->desc_dma.kva;
    for (i = 0; i < count; i++) {
        bus_addr_t next;

        next = ring->desc_dma.paddr +
            (bus_addr_t)(((i + 1) % count) *
            sizeof(struct rtwn8723be_tx_desc));
        KASSERT(next <= UINT32_MAX);
        desc[i].d[RTWN8723BE_TX_NEXT_DESC_DW] =
            htole32((uint32_t)next);
    }

    rtwn8723be_f16_1_dma_sync_for_device(dmat, &ring->desc_dma, 0,
        ring->desc_dma.size);
    return 0;

fail:
    rtwn8723be_f16_1_tx_ring_free(dmat, ring);
    return error;
}

void
rtwn8723be_f16_1_tx_ring_free(bus_dma_tag_t dmat,
    struct rtwn8723be_tx_ring *ring)
{
    uint32_t i;

    if (ring->slot != NULL) {
        for (i = 0; i < ring->count; i++) {
            if (ring->slot[i].m != NULL) {
                if (ring->slot[i].map != NULL &&
                    ring->slot[i].map->dm_nsegs != 0) {
                    bus_dmamap_sync(dmat, ring->slot[i].map, 0,
                        ring->slot[i].map->dm_mapsize,
                        BUS_DMASYNC_POSTWRITE);
                    bus_dmamap_unload(dmat, ring->slot[i].map);
                }
                m_freem(ring->slot[i].m);
                ring->slot[i].m = NULL;
            }
            if (ring->slot[i].map != NULL) {
                bus_dmamap_destroy(dmat, ring->slot[i].map);
                ring->slot[i].map = NULL;
            }
        }
        kmem_free(ring->slot,
            (size_t)ring->count * sizeof(*ring->slot));
        ring->slot = NULL;
    }

    rtwn8723be_f16_1_dma_mem_free(dmat, &ring->desc_dma);
    ring->count = 0;
    ring->producer = 0;
    ring->consumer = 0;
}

int
rtwn8723be_f16_1_rx_ring_alloc(bus_dma_tag_t dmat,
    struct rtwn8723be_rx_ring *ring, uint32_t count)
{
    struct rtwn8723be_rx_desc *desc;
    uint32_t i;
    bus_size_t size;
    int error;

    memset(ring, 0, sizeof(*ring));
    ring->count = count;
    size = (bus_size_t)count * sizeof(struct rtwn8723be_rx_desc);

    error = rtwn8723be_f16_1_dma_mem_alloc(dmat, &ring->desc_dma, size,
        RTWN8723BE_RING_ALIGN);
    if (error != 0)
        return error;

    ring->slot = kmem_zalloc((size_t)count * sizeof(*ring->slot),
        KM_SLEEP);
    desc = ring->desc_dma.kva;

    for (i = 0; i < count; i++) {
        struct mbuf *m;
        uint32_t d0;

        error = bus_dmamap_create(dmat, RTWN8723BE_RX_BUFFER_SIZE, 1,
            RTWN8723BE_RX_BUFFER_SIZE, 0,
            BUS_DMA_WAITOK | BUS_DMA_ALLOCNOW, &ring->slot[i].map);
        if (error != 0)
            goto fail;

        MGETHDR(m, M_WAIT, MT_DATA);
        if (m == NULL) {
            error = ENOBUFS;
            goto fail;
        }
        MEXTMALLOC(m, RTWN8723BE_RX_BUFFER_SIZE, M_WAIT);
        if ((m->m_flags & M_EXT) == 0) {
            m_freem(m);
            error = ENOBUFS;
            goto fail;
        }

        m->m_len = m->m_pkthdr.len = RTWN8723BE_RX_BUFFER_SIZE;
        error = bus_dmamap_load(dmat, ring->slot[i].map,
            mtod(m, void *), RTWN8723BE_RX_BUFFER_SIZE, NULL,
            BUS_DMA_WAITOK | BUS_DMA_READ);
        if (error != 0) {
            m_freem(m);
            goto fail;
        }
        if (ring->slot[i].map->dm_nsegs != 1) {
            bus_dmamap_unload(dmat, ring->slot[i].map);
            m_freem(m);
            error = EFBIG;
            goto fail;
        }

        ring->slot[i].m = m;
        KASSERT(ring->slot[i].map->dm_segs[0].ds_addr <= UINT32_MAX);

        bus_dmamap_sync(dmat, ring->slot[i].map, 0,
            RTWN8723BE_RX_BUFFER_SIZE, BUS_DMASYNC_PREREAD);

        d0 = RTWN8723BE_RX_BUFFER_SIZE | R23BE_RXD0_OWN;
        if (i == count - 1)
            d0 |= R23BE_RXD0_EOR;

        desc[i].d[0] = htole32(d0);
        desc[i].d[6] = htole32((uint32_t)
            ring->slot[i].map->dm_segs[0].ds_addr);
    }

    rtwn8723be_f16_1_dma_sync_for_device(dmat, &ring->desc_dma, 0,
        ring->desc_dma.size);
    return 0;

fail:
    rtwn8723be_f16_1_rx_ring_free(dmat, ring);
    return error;
}

void
rtwn8723be_f16_1_rx_ring_free(bus_dma_tag_t dmat,
    struct rtwn8723be_rx_ring *ring)
{
    uint32_t i;

    if (ring->slot != NULL) {
        for (i = 0; i < ring->count; i++) {
            if (ring->slot[i].m != NULL) {
                if (ring->slot[i].map != NULL &&
                    ring->slot[i].map->dm_nsegs != 0) {
                    bus_dmamap_sync(dmat, ring->slot[i].map, 0,
                        RTWN8723BE_RX_BUFFER_SIZE,
                        BUS_DMASYNC_POSTREAD);
                    bus_dmamap_unload(dmat, ring->slot[i].map);
                }
                m_freem(ring->slot[i].m);
                ring->slot[i].m = NULL;
            }
            if (ring->slot[i].map != NULL) {
                bus_dmamap_destroy(dmat, ring->slot[i].map);
                ring->slot[i].map = NULL;
            }
        }
        kmem_free(ring->slot,
            (size_t)ring->count * sizeof(*ring->slot));
        ring->slot = NULL;
    }

    rtwn8723be_f16_1_dma_mem_free(dmat, &ring->desc_dma);
    ring->count = 0;
    ring->consumer = 0;
}
