/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Native PCI old-TRX TX DMA ring lifetime; source mapping:
 * frozen rtlwifi/pci.c:rtl_pci_tx(), rtl8723be/trx.c:tx_polling(),
 * NetBSD sys/dev/pci/if_rtwn.c DMA map/sync ownership conventions.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <sys/mbuf.h>
#include <sys/bus.h>
#include <sys/endian.h>
#include <sys/atomic.h>

#include "rtwn8723be_tx_native.h"

_Static_assert(sizeof(struct rtwn8723be_tx_desc) ==
    RTWN8723BE_TX_RING_STRIDE, "RTL8723BE TX PCI ring stride mismatch");

static int
r23be_tx_queue_check(unsigned int qid, unsigned int fwq, bool command)
{
    /*
     * Pinned Linux rtlwifi/pci.c only services TXCMD_QUEUE completion for
     * RTL8192SE, not RTL8723BE. Without a device-specific completion path
     * a command mbuf would remain permanently owned by this TX ring.
     * RTL8723BE H2C uses separate firmware mailboxes; keep this descriptor
     * path closed until a proven RTL8723BE command-frame lifetime exists.
     */
    /* H2C uses mailboxes. Only the pinned reserved-page beacon packet
     * has a command-descriptor TX path on this PCIe hardware. */
    if (command && qid != RTWN8723BE_BEACON_QUEUE)
        return EOPNOTSUPP;

    switch (qid) {
    case RTWN8723BE_BK_QUEUE:
        return fwq == RTWN8723BE_TX_FW_BK ? 0 : EINVAL;
    case RTWN8723BE_BE_QUEUE:
        return fwq == RTWN8723BE_TX_FW_BE ? 0 : EINVAL;
    case RTWN8723BE_VI_QUEUE:
        return fwq == RTWN8723BE_TX_FW_VI ? 0 : EINVAL;
    case RTWN8723BE_VO_QUEUE:
        return fwq == RTWN8723BE_TX_FW_VO ? 0 : EINVAL;
    case RTWN8723BE_BEACON_QUEUE:
        /* Linux old-TRX beacon delivery uses TX command descriptor slot0;
         * the reserved-page thread itself polls this ring for completion. */
        return command && fwq == RTWN8723BE_TX_FW_BEACON ? 0 : EINVAL;
    case RTWN8723BE_MGNT_QUEUE:
        return fwq == RTWN8723BE_TX_FW_MGNT ? 0 : EINVAL;
    case RTWN8723BE_HIGH_QUEUE:
        return fwq == RTWN8723BE_TX_FW_HIGH ? 0 : EINVAL;
    default:
        return EINVAL; /* HCCA and TXCMD are not regular frame queues. */
    }
}

int
rtwn8723be_tx_native_enqueue(struct rtwn8723be_softc *sc,
    unsigned int qid, struct mbuf *m,
    const struct rtwn8723be_tx_params *input, bool command)
{
    return rtwn8723be_tx_native_enqueue_owned(sc, qid, m, input,
        command, NULL, NULL);
}

int
rtwn8723be_tx_native_enqueue_owned(struct rtwn8723be_softc *sc,
    unsigned int qid, struct mbuf *m,
    const struct rtwn8723be_tx_params *input, bool command,
    void *owner, void (*release)(void *, struct mbuf *, bool))
{
    struct rtwn8723be_tx_ring *ring;
    struct rtwn8723be_dma_slot *slot;
    struct rtwn8723be_tx_desc *desc;
    struct rtwn8723be_tx_params p;
    struct rtwn8723be_tx_desc saved_desc, prepared_desc;
    bus_addr_t next;
    bus_size_t offset;
    unsigned int idx;
    int error;

    if (sc == NULL || m == NULL || input == NULL ||
        qid >= RTWN8723BE_TX_QUEUE_COUNT ||
        ((owner == NULL) != (release == NULL)))
        return EINVAL;
    if (!sc->sc_mapped || !sc->sc_rings_allocated ||
        !sc->sc_dma_32bit || sc->sc_dmat == NULL)
        return ENXIO;
    if (qid == RTWN8723BE_BEACON_QUEUE &&
        (owner == NULL || release == NULL || !command))
        return EINVAL;
    error = r23be_tx_queue_check(qid, input->fw_queue, command);
    if (error != 0)
        return error;
    if (m->m_next != NULL || m->m_len != m->m_pkthdr.len)
        return EFBIG; /* DMA ring was allocated for one segment. */
    if (m->m_pkthdr.len <= 0 ||
        m->m_pkthdr.len > RTWN8723BE_RX_BUFFER_SIZE ||
        input->buffer_len != m->m_pkthdr.len ||
        (command && input->packet_len != input->buffer_len))
        return EINVAL;

    ring = &sc->sc_tx_ring[qid];
    if (ring->count == 0 ||
        ring->producer >= ring->count ||
        ring->consumer >= ring->count ||
        ring->slot == NULL || ring->desc_dma.kva == NULL ||
        ring->desc_dma.map == NULL ||
        ring->desc_dma.size < (bus_size_t)ring->count *
            sizeof(struct rtwn8723be_tx_desc) ||
        !rtwn8723be_dma32_range_valid(
            ring->desc_dma.paddr, ring->desc_dma.size))
        return EIO;

    /* Linux rtl_pci_tx() and prepare_bcn_tasklet always address beacon
     * descriptor zero. Descriptor one is allocated but never submitted. */
    idx = qid == RTWN8723BE_BEACON_QUEUE ? 0U : ring->producer;
    slot = &ring->slot[idx];
    desc = &((struct rtwn8723be_tx_desc *)ring->desc_dma.kva)[idx];
    if (slot->m != NULL)
        return EBUSY;
    if (slot->map == NULL)
        return EIO;

    /* The device may still own a descriptor whose mbuf was not published. */
    offset = (bus_size_t)idx * sizeof(*desc);
    rtwn8723be_f16_1_dma_sync_for_cpu(sc->sc_dmat,
        &ring->desc_dma, offset, sizeof(*desc));
    if ((le32toh(desc->d[0]) & R23BE_TXD0_OWN) != 0) {
        rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,
            &ring->desc_dma, offset, sizeof(*desc));
        return EBUSY;
    }

    /* Encode into private storage. Failures re-sync the original ring
     * descriptor and leave the caller's mbuf/owner untouched.
     */
    saved_desc = *desc;
    prepared_desc = saved_desc;
    error = bus_dmamap_load_mbuf(sc->sc_dmat, slot->map, m,
        BUS_DMA_NOWAIT | BUS_DMA_WRITE);
    if (error != 0)
        goto restore_desc; /* Original mbuf still belongs to caller. */
    if (slot->map->dm_nsegs != 1 ||
        slot->map->dm_segs[0].ds_len <
            (bus_size_t)input->buffer_len ||
        !rtwn8723be_dma32_range_valid(
            slot->map->dm_segs[0].ds_addr,
            (bus_size_t)input->buffer_len)) {
        error = EFBIG; /* Reject a packet straddling the 4-GiB limit. */
        goto unload_map;
    }
    if (slot->map->dm_mapsize != (bus_size_t)input->buffer_len) {
        error = EIO;
        goto unload_map;
    }

    next = ring->desc_dma.paddr +
        (bus_addr_t)(((idx + 1U) % ring->count) * sizeof(*desc));
    if (!rtwn8723be_dma32_range_valid(next, sizeof(*desc))) {
        error = EFBIG;
        goto unload_map;
    }

    p = *input;
    p.buffer_dma = (uint32_t)slot->map->dm_segs[0].ds_addr;
    p.next_desc_dma = (uint32_t)next;
    if (command)
        error = rtwn8723be_tx_encode_command(p.packet_len,
            p.buffer_dma, p.next_desc_dma,
            (uint8_t *)&prepared_desc, sizeof(prepared_desc));
    else
        error = rtwn8723be_tx_encode(&p,
            (uint8_t *)&prepared_desc, sizeof(prepared_desc));
    if (error == 0 &&
        (le32toh(prepared_desc.d[0]) & R23BE_TXD0_OWN) != 0)
        error = EINVAL;
    if (error != 0)
        goto unload_map;

    /* No encoder can partially modify the live DMA ring. This is still
     * a single-frame commit; whole-chain prepare/commit remains gated.
     */
    *desc = prepared_desc;
    /* Ownership changes only after the packet's DMA mapping is valid. */
    bus_dmamap_sync(sc->sc_dmat, slot->map, 0,
        slot->map->dm_mapsize, BUS_DMASYNC_PREWRITE);
    /* Publish the node/report owner with its packet DMA map and never
     * before the strict 32-bit range and map-size guards succeed. */
    slot->tx_owner = owner;
    slot->tx_release = release;
    slot->m = m;
    membar_producer();
    desc->d[0] = htole32(le32toh(desc->d[0]) | R23BE_TXD0_OWN);
    rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,
        &ring->desc_dma, offset, sizeof(*desc));
    ring->producer = qid == RTWN8723BE_BEACON_QUEUE ?
        0U : (idx + 1U) % ring->count;

    /* rtl8723be_tx_polling(): one PCIe control bit per HW queue. */
    rtwn8723be_write_2(sc, R23BE_REG_PCIE_CTRL_REG,
        (uint16_t)(1U << qid));
    return 0;

unload_map:
    /* The mbuf has never been transferred to slot ownership. */
    bus_dmamap_unload(sc->sc_dmat, slot->map);
restore_desc:
    /* Restoring the complete 64-byte slot also restores NEXT_DESC. */
    *desc = saved_desc;
    rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,
        &ring->desc_dma, offset, sizeof(*desc));
    return error;
}


/* Caller holds the same TX lock used by single enqueue, reclaim and stop.
 * Preparation changes only unloaded packet maps and private descriptors.
 * Once publication starts, no operation returning an error remains.
 */
int
rtwn8723be_tx_native_enqueue_batch(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_tx_batch_frame *frames, unsigned int count,
    struct rtwn8723be_tx_batch_workspace *workspace)
{
    struct rtwn8723be_tx_ring *ring;
    struct rtwn8723be_tx_desc *descs;
    struct rtwn8723be_dma_slot *slot;
    struct rtwn8723be_tx_params p;
    const struct rtwn8723be_tx_batch_frame *f;
    bus_size_t offset, bytes;
    unsigned int start, idx, i, j, loaded = 0;
    int error;

    if (sc == NULL || frames == NULL || workspace == NULL ||
        count == 0 || count > RTWN8723BE_TX_BATCH_MAX)
        return EINVAL;
    if (!sc->sc_mapped || !sc->sc_rings_allocated ||
        !sc->sc_dma_32bit || sc->sc_dmat == NULL)
        return ENXIO;
    ring = &sc->sc_tx_ring[RTWN8723BE_BE_QUEUE];
    if (ring->count == 0 || ring->slot == NULL ||
        ring->producer >= ring->count || ring->consumer >= ring->count ||
        ring->desc_dma.kva == NULL || ring->desc_dma.map == NULL)
        return EIO;
    if (count > ring->count)
        return EFBIG;
    bytes = (bus_size_t)ring->count * sizeof(*descs);
    if (ring->desc_dma.size < bytes ||
        ring->desc_dma.map->dm_mapsize < bytes ||
        !rtwn8723be_dma32_range_valid(ring->desc_dma.paddr, bytes))
        return EIO;
    descs = ring->desc_dma.kva;
    start = ring->producer;

    /* Reject aliases and invalid owners before loading even the first map. */
    for (i = 0; i < count; i++) {
        f = &frames[i];
        if (f->m == NULL || (f->m->m_flags & M_PKTHDR) == 0 ||
            f->m->m_next != NULL || f->m->m_nextpkt != NULL ||
            f->m->m_len != f->m->m_pkthdr.len ||
            f->m->m_pkthdr.len <= 0 ||
            f->m->m_pkthdr.len > RTWN8723BE_RX_BUFFER_SIZE ||
            f->params.buffer_len != f->m->m_pkthdr.len ||
            f->params.fw_queue != RTWN8723BE_TX_FW_BE ||
            ((f->owner == NULL) != (f->release == NULL)))
            return EINVAL;
        for (j = 0; j < i; j++)
            if (frames[j].m == f->m)
                return EINVAL;
    }
    for (i = 0; i < count; i++) {
        idx = (start + i) % ring->count;
        slot = &ring->slot[idx];
        f = &frames[i];
        if (slot->m != NULL) {
            error = EBUSY;
            goto abort;
        }
        if (slot->map == NULL || slot->map->dm_mapsize != 0 ||
            slot->tx_owner != NULL || slot->tx_release != NULL) {
            error = EIO;
            goto abort;
        }
        offset = (bus_size_t)idx * sizeof(*descs);
        rtwn8723be_f16_1_dma_sync_for_cpu(sc->sc_dmat,
            &ring->desc_dma, offset, sizeof(*descs));
        error = (le32toh(descs[idx].d[0]) & R23BE_TXD0_OWN) != 0 ?
            EBUSY : 0;
        rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,
            &ring->desc_dma, offset, sizeof(*descs));
        if (error != 0)
            goto abort;
        error = bus_dmamap_load_mbuf(sc->sc_dmat, slot->map, f->m,
            BUS_DMA_NOWAIT | BUS_DMA_WRITE);
        if (error != 0)
            goto abort;
        loaded++;
        if (slot->map->dm_nsegs != 1 ||
            slot->map->dm_mapsize != (bus_size_t)f->params.buffer_len ||
            slot->map->dm_segs[0].ds_len < (bus_size_t)f->params.buffer_len ||
            !rtwn8723be_dma32_range_valid(slot->map->dm_segs[0].ds_addr,
                (bus_size_t)f->params.buffer_len)) {
            error = EFBIG;
            goto abort;
        }
        p = f->params;
        p.buffer_dma = (uint32_t)slot->map->dm_segs[0].ds_addr;
        p.next_desc_dma = (uint32_t)(ring->desc_dma.paddr +
            (bus_addr_t)(((idx + 1U) % ring->count) * sizeof(*descs)));
        error = rtwn8723be_tx_encode(&p,
            (uint8_t *)&workspace->desc[i], sizeof(workspace->desc[i]));
        if (error == 0 &&
            (le32toh(workspace->desc[i].d[0]) & R23BE_TXD0_OWN) != 0)
            error = EINVAL;
        if (error != 0)
            goto abort;
    }

    /* All fallible preparation succeeded. Publish packet/owner metadata
     * for the entire batch before handing any descriptor to the device.
     */
    for (i = 0; i < count; i++) {
        idx = (start + i) % ring->count;
        slot = &ring->slot[idx];
        f = &frames[i];
        bus_dmamap_sync(sc->sc_dmat, slot->map, 0,
            slot->map->dm_mapsize, BUS_DMASYNC_PREWRITE);
        offset = (bus_size_t)idx * sizeof(*descs);
        rtwn8723be_f16_1_dma_sync_for_cpu(sc->sc_dmat,
            &ring->desc_dma, offset, sizeof(*descs));
        descs[idx] = workspace->desc[i];
        slot->tx_owner = f->owner;
        slot->tx_release = f->release;
        slot->m = f->m;
    }
    membar_producer();
    /*
     * Publish the tail first and the producer/head descriptor last.
     * The device may be consuming this BE ring concurrently: exposing
     * the first fragment before later OWN bits are visible could let it
     * encounter a not-yet-owned descriptor midway through the MSDU.
     * The final doorbell remains after the entire chain is device-owned.
     */
    for (i = count; i != 0; ) {
        i--;
        idx = (start + i) % ring->count;
        descs[idx].d[0] = htole32(le32toh(descs[idx].d[0]) | R23BE_TXD0_OWN);
        rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,
            &ring->desc_dma, (bus_size_t)idx * sizeof(*descs), sizeof(*descs));
    }
    ring->producer = (start + count) % ring->count;
    rtwn8723be_write_2(sc, R23BE_REG_PCIE_CTRL_REG,
        (uint16_t)(1U << RTWN8723BE_BE_QUEUE));
    return 0;

abort:
    /* No packet PREWRITE, slot transfer, descriptor write or OWN yet.
     * Only successfully loaded maps are ours to unload, in reverse order.
     * The caller still owns all mbufs and all node/report references.
     */
    while (loaded != 0) {
        loaded--;
        idx = (start + loaded) % ring->count;
        bus_dmamap_unload(sc->sc_dmat, ring->slot[idx].map);
    }
    return error;
}

int
rtwn8723be_tx_native_reclaim(struct rtwn8723be_softc *sc,
    unsigned int qid, size_t *reclaimed)
{
    struct rtwn8723be_tx_ring *ring;
    struct rtwn8723be_tx_desc *descs;
    unsigned int work;

    if (sc == NULL || reclaimed == NULL ||
        qid >= RTWN8723BE_TX_QUEUE_COUNT)
        return EINVAL;
    *reclaimed = 0;
    if (!sc->sc_mapped || !sc->sc_rings_allocated ||
        !sc->sc_dma_32bit || sc->sc_dmat == NULL)
        return ENXIO;
    ring = &sc->sc_tx_ring[qid];
    if (ring->count == 0 ||
        ring->count > RTWN8723BE_TX_RING_BE_COUNT ||
        ring->consumer >= ring->count ||
        ring->slot == NULL || ring->desc_dma.kva == NULL ||
        ring->desc_dma.map == NULL ||
        ring->desc_dma.size < (bus_size_t)ring->count *
            sizeof(struct rtwn8723be_tx_desc) ||
        !rtwn8723be_dma32_range_valid(
            ring->desc_dma.paddr, ring->desc_dma.size))
        return EIO;
    descs = ring->desc_dma.kva;

    for (work = 0; work < ring->count; work++) {
        unsigned int idx = ring->consumer;
        struct rtwn8723be_dma_slot *slot = &ring->slot[idx];
        struct rtwn8723be_tx_desc *desc = &descs[idx];
        bus_size_t offset = (bus_size_t)idx * sizeof(*desc);
        uint32_t next;

        if (slot->m == NULL)
            break;
        /*
         * The original TX mbuf stays owned by the slot until POSTWRITE
         * completes.  Corrupt maps must remain quarantined for the real
         * device stop/recovery owner, not be synced/freed speculatively.
         */
        if (slot->map == NULL || slot->map->dm_nsegs != 1 ||
            slot->map->dm_mapsize == 0 ||
            slot->map->dm_mapsize !=
                (bus_size_t)slot->m->m_pkthdr.len ||
            slot->map->dm_mapsize > RTWN8723BE_RX_BUFFER_SIZE ||
            slot->map->dm_segs[0].ds_len <
                slot->map->dm_mapsize ||
            !rtwn8723be_dma32_range_valid(
                slot->map->dm_segs[0].ds_addr,
                slot->map->dm_mapsize))
            return EIO;

        rtwn8723be_f16_1_dma_sync_for_cpu(sc->sc_dmat,
            &ring->desc_dma, offset, sizeof(*desc));
        if ((le32toh(desc->d[0]) & R23BE_TXD0_OWN) != 0) {
            rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,
                &ring->desc_dma, offset, sizeof(*desc));
            break;
        }
        bus_dmamap_sync(sc->sc_dmat, slot->map, 0,
            slot->map->dm_mapsize, BUS_DMASYNC_POSTWRITE);
        bus_dmamap_unload(sc->sc_dmat, slot->map);
        rtwn8723be_f16_1_tx_slot_release(slot, true);

        /* Keep the linked 64-byte PCI descriptor ring intact. */
        next = (uint32_t)(ring->desc_dma.paddr +
            (bus_addr_t)(((idx + 1U) % ring->count) * sizeof(*desc)));
        memset(desc, 0, sizeof(*desc));
        desc->d[12] = htole32(next);
        rtwn8723be_f16_1_dma_sync_for_device(sc->sc_dmat,
            &ring->desc_dma, offset, sizeof(*desc));
        /* Reserved-page beacon completion is polled from slot zero.
         * Never advance its consumer to unused descriptor one. */
        ring->consumer = qid == RTWN8723BE_BEACON_QUEUE ?
            0U : (idx + 1U) % ring->count;
        (*reclaimed)++;
    }
    return 0;
}

/*
 * Reserved-page firmware join report: Linux RTL8723BE uses the beacon
 * queue, descriptor slot zero, command descriptor and explicit polling.
 * Caller holds the datapath TX lock and keeps the node/mbuf on failure.
 */
int
rtwn8723be_tx_native_enqueue_reserved(struct rtwn8723be_softc *sc,
    struct mbuf *m, const struct rtwn8723be_tx_params *p,
    void *owner, void (*release)(void *, struct mbuf *, bool))
{
    if (p == NULL || p->fw_queue != RTWN8723BE_TX_FW_BEACON ||
        owner == NULL || release == NULL)
        return EINVAL;
    return rtwn8723be_tx_native_enqueue_owned(sc,
        RTWN8723BE_BEACON_QUEUE, m, p, true, owner, release);
}

int
rtwn8723be_tx_native_reclaim_reserved(struct rtwn8723be_softc *sc,
    size_t *reclaimed)
{
    return rtwn8723be_tx_native_reclaim(sc,
        RTWN8723BE_BEACON_QUEUE, reclaimed);
}
