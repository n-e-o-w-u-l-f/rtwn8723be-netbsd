/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Framing/node ownership: NetBSD/src 03d918f6d0e81fa05b8f1160eca0628ad39988a6,
 * sys/dev/pci/if_rtwn.c:rtwn_start/rtwn_tx and net80211/ieee80211_output.c.
 * Descriptor/report contract: Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab,
 * rtlwifi/base.[ch], wifi.h, pci.c and rtl8723be/trx.c.
 *
 * NetBSD's pinned net80211 ABI has no HT; the interface advertises no WME.
 * This is station 11b/11g framing with software crypto and selected legacy
 * rates. Firmware DMA completion is never represented as an air ACK.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <sys/mbuf.h>
#include <sys/endian.h>
#include <sys/kernel.h>
#include <sys/intr.h>
#include <net/if.h>
#include <net/if_ether.h>
#include <net/bpf.h>
#include "rtwn8723be_net80211_tx.h"
#include <net80211/ieee80211_var.h>
#include <net80211/ieee80211_proto.h>
#include <net80211/ieee80211_crypto.h>

static void r23be_tx_report_timeout(void *);

struct r23be_tx_notify {
    struct rtwn8723be_net80211_tx *tx;
    uint8_t special_kind;
};

static void
r23be_tx_accepted(void *arg, const struct mbuf *m)
{
    const struct r23be_tx_notify *notify = arg;

    if (notify->tx->accepted != NULL)
        notify->tx->accepted(notify->tx->sc, mtod(m, const uint8_t *),
            (size_t)m->m_pkthdr.len, notify->special_kind);
}

static void
r23be_tx_free_frames(struct mbuf *m)
{
    while (m != NULL) {
        struct mbuf *next = m->m_nextpkt;
        m->m_nextpkt = NULL;
        m_freem(m);
        m = next;
    }
}

static void
r23be_tx_node_release(void *arg, struct mbuf *m, bool completed)
{
    struct ieee80211_node *ni = arg;

    if (completed)
        if_statinc(ni->ni_ic->ic_ifp, if_opackets);
    if (m != NULL)
        m_freem(m);
    ieee80211_free_node(ni);
}

/* report_lock held. A ticket cannot die while hardware references it. */
static void
r23be_tx_report_retire(struct rtwn8723be_tx_report_ticket *ticket)
{
    struct rtwn8723be_net80211_tx *tx = ticket->tx;
    struct ieee80211_node *ni = ticket->ni;
    struct mbuf *m = ticket->m;

    KASSERT(ticket->in_use && !ticket->dma_pending && ticket->terminal);
    memset(ticket, 0, sizeof(*ticket));
    KASSERT(tx->pending_reports != 0);
    tx->pending_reports--;
    if (m != NULL)
        m_freem(m);
    ieee80211_free_node(ni);
}

static void
r23be_tx_report_dma_release(void *arg, struct mbuf *m, bool completed)
{
    struct rtwn8723be_tx_report_ticket *ticket = arg;
    struct rtwn8723be_net80211_tx *tx = ticket->tx;

    mutex_enter(&tx->report_lock);
    KASSERT(ticket->in_use && ticket->dma_pending && ticket->m == NULL);
    ticket->dma_pending = false;
    ticket->m = m;
    if (completed)
        if_statinc(ticket->ni->ni_ic->ic_ifp, if_opackets);
    if (!completed && !ticket->cancelled) {
        ticket->cancelled = true;
        ticket->terminal = true;
        tx->reports_cancelled++;
    }
    if (ticket->terminal)
        r23be_tx_report_retire(ticket);
    mutex_exit(&tx->report_lock);
}

static struct rtwn8723be_tx_report_ticket *
r23be_tx_report_allocate(struct rtwn8723be_net80211_tx *tx,
    struct ieee80211_node *ni)
{
    struct rtwn8723be_tx_report_ticket *ticket = NULL;
    unsigned int attempt;

    mutex_enter(&tx->report_lock);
    if (!tx->reports_running)
        goto out;
    /* Increment-before-use matches Linux; never alias a pending sequence. */
    for (attempt = 0; attempt < RTWN8723BE_TX_REPORT_SLOTS; attempt++) {
        tx->next_sequence = (tx->next_sequence + 1U) & 0x3fU;
        ticket = &tx->report[tx->next_sequence];
        if (!ticket->in_use)
            break;
        ticket = NULL;
    }
    if (ticket != NULL) {
        memset(ticket, 0, sizeof(*ticket));
        ticket->tx = tx;
        ticket->ni = ni;
        ticket->sequence = tx->next_sequence << 2;
        ticket->sent_ticks = (uint32_t)getticks();
        ticket->in_use = true;
        ticket->dma_pending = true;
        tx->pending_reports++;
    }
out:
    mutex_exit(&tx->report_lock);
    return ticket;
}

static void
r23be_tx_report_enqueue_failed(struct rtwn8723be_tx_report_ticket *ticket,
    struct mbuf *m)
{
    struct rtwn8723be_net80211_tx *tx = ticket->tx;

    mutex_enter(&tx->report_lock);
    ticket->dma_pending = false;
    ticket->m = m;
    ticket->terminal = true;
    r23be_tx_report_retire(ticket);
    mutex_exit(&tx->report_lock);
}

static void
r23be_tx_report_timeout(void *arg)
{
    struct rtwn8723be_net80211_tx *tx = arg;
    uint32_t now = (uint32_t)getticks();
    unsigned int i;

    mutex_enter(&tx->report_lock);
    if (!tx->reports_running) {
        mutex_exit(&tx->report_lock);
        return;
    }
    for (i = 0; i < RTWN8723BE_TX_REPORT_SLOTS; i++) {
        struct rtwn8723be_tx_report_ticket *ticket = &tx->report[i];

        /* Frozen Linux ackqueue expires unreported packets after one HZ. */
        if (!ticket->in_use || ticket->terminal ||
            (uint32_t)(now - ticket->sent_ticks) < (uint32_t)hz)
            continue;
        ticket->terminal = true;
        tx->reports_timedout++;
        tx->reports_failed++;
        if_statinc(ticket->ni->ni_ic->ic_ifp, if_oerrors);
        if (!ticket->dma_pending)
            r23be_tx_report_retire(ticket);
    }
    callout_schedule(&tx->report_timeout, hz);
    mutex_exit(&tx->report_lock);
}

int
rtwn8723be_net80211_tx_report(void *arg,
    const struct rtwn8723be_c2h_event *event)
{
    struct rtwn8723be_net80211_tx *tx = arg;
    struct rtwn8723be_tx_report_ticket *ticket;
    int error = 0;

    if (tx == NULL || !tx->prepared || event == NULL ||
        event->id != R23BE_C2H_TX_REPORT || !event->tx_report_valid ||
        (event->tx_report_sequence & 3U) != 0)
        return EINVAL;
    mutex_enter(&tx->report_lock);
    ticket = &tx->report[event->tx_report_sequence >> 2];
    if (!ticket->in_use || ticket->sequence != event->tx_report_sequence) {
        tx->reports_unmatched++;
        error = ENOENT;
        goto out;
    }
    if (ticket->terminal) {
        tx->reports_unmatched++;
        error = EALREADY;
        goto out;
    }
    ticket->received = true;
    ticket->terminal = true;
    ticket->status = event->tx_report_status;
    ticket->retry = event->tx_report_retry;
    ticket->acked = event->tx_report_status == 0;
    if (ticket->acked)
        tx->reports_acked++;
    else {
        tx->reports_failed++;
        if_statinc(ticket->ni->ni_ic->ic_ifp, if_oerrors);
    }
    if (!ticket->dma_pending)
        r23be_tx_report_retire(ticket);
out:
    mutex_exit(&tx->report_lock);
    return error;
}

int
rtwn8723be_net80211_tx_prepare(struct rtwn8723be_net80211_tx *tx,
    struct rtwn8723be_softc *sc, struct rtwn8723be_datapath *dp)
{
    if (tx == NULL || sc == NULL || dp == NULL ||
        !dp->prepared || dp->sc != sc)
        return EINVAL;
    if (tx->prepared)
        return EALREADY;
    memset(tx, 0, sizeof(*tx));
    tx->sc = sc;
    tx->dp = dp;
    mutex_init(&tx->producer_lock, MUTEX_DEFAULT, IPL_NET);
    mutex_init(&tx->report_lock, MUTEX_DEFAULT, IPL_NET);
    callout_init(&tx->report_timeout, CALLOUT_MPSAFE);
    callout_setfunc(&tx->report_timeout, r23be_tx_report_timeout, tx);
    tx->prepared = true;
    return 0;
}

int
rtwn8723be_net80211_tx_set_accepted(struct rtwn8723be_net80211_tx *tx,
    void (*accepted)(struct rtwn8723be_softc *, const uint8_t *, size_t,
        uint8_t))
{
    int error = 0;

    if (tx == NULL || !tx->prepared)
        return EINVAL;
    mutex_enter(&tx->producer_lock);
    if (tx->enabled)
        error = EBUSY;
    else
        tx->accepted = accepted;
    mutex_exit(&tx->producer_lock);
    return error;
}

int
rtwn8723be_net80211_tx_run(struct rtwn8723be_net80211_tx *tx)
{
    int error;

    if (tx == NULL || !tx->prepared)
        return EINVAL;
    mutex_enter(&tx->producer_lock);
    error = rtwn8723be_datapath_tx_check(tx->dp, RTWN8723BE_BE_QUEUE);
    if (error == 0) {
        mutex_enter(&tx->report_lock);
        /* Start cannot discard an old still-DMA-owned report ticket. */
        if (tx->pending_reports != 0)
            error = EBUSY;
        else {
            tx->reports_running = true;
            tx->enabled = true;
            callout_schedule(&tx->report_timeout, hz);
        }
        mutex_exit(&tx->report_lock);
    }
    mutex_exit(&tx->producer_lock);
    return error;
}

void
rtwn8723be_net80211_tx_stop(struct rtwn8723be_net80211_tx *tx)
{
    unsigned int i;

    if (tx == NULL || !tx->prepared)
        return;
    mutex_enter(&tx->producer_lock);
    tx->enabled = false;
    mutex_enter(&tx->report_lock);
    tx->reports_running = false;
    callout_stop(&tx->report_timeout);
    for (i = 0; i < RTWN8723BE_TX_REPORT_SLOTS; i++) {
        struct rtwn8723be_tx_report_ticket *ticket = &tx->report[i];

        if (!ticket->in_use)
            continue;
        if (!ticket->cancelled && !ticket->terminal)
            tx->reports_cancelled++;
        ticket->cancelled = true;
        ticket->terminal = true;
        if (!ticket->dma_pending)
            r23be_tx_report_retire(ticket);
    }
    mutex_exit(&tx->report_lock);
    mutex_exit(&tx->producer_lock);
}

int
rtwn8723be_net80211_tx_fini(struct rtwn8723be_net80211_tx *tx)
{
    bool busy;

    if (tx == NULL || !tx->prepared)
        return EINVAL;
    mutex_enter(&tx->producer_lock);
    busy = tx->enabled;
    mutex_exit(&tx->producer_lock);
    if (busy)
        return EBUSY;
    callout_halt(&tx->report_timeout, NULL);
    mutex_enter(&tx->report_lock);
    busy = tx->pending_reports != 0;
    mutex_exit(&tx->report_lock);
    if (busy)
        return EBUSY;
    callout_destroy(&tx->report_timeout);
    mutex_destroy(&tx->report_lock);
    mutex_destroy(&tx->producer_lock);
    memset(tx, 0, sizeof(*tx));
    return 0;
}

static int
r23be_tx_legacy_rate(uint8_t rate, uint8_t *hw)
{
    static const uint8_t rates[] = { 2, 4, 11, 22, 12, 18,
        24, 36, 48, 72, 96, 108 };
    unsigned int i;

    for (i = 0; i < __arraycount(rates); i++) {
        if (rates[i] == (rate & IEEE80211_RATE_VAL)) {
            *hw = (uint8_t)i;
            return 0;
        }
    }
    return EOPNOTSUPP;
}

static uint8_t
r23be_tx_basic_rate(const struct ieee80211_rateset *rs, uint8_t limit,
    bool lowest)
{
    uint8_t selected = 0, fallback = 0;
    unsigned int i;

    for (i = 0; i < rs->rs_nrates; i++) {
        uint8_t rate = rs->rs_rates[i] & IEEE80211_RATE_VAL;
        uint8_t hw;

        if (r23be_tx_legacy_rate(rate, &hw) != 0 || rate > limit)
            continue;
        if (fallback == 0 || rate < fallback)
            fallback = rate;
        if ((rs->rs_rates[i] & IEEE80211_RATE_BASIC) != 0 &&
            (selected == 0 || (lowest ? rate < selected : rate > selected)))
            selected = rate;
    }
    return selected != 0 ? selected : fallback;
}

static int
r23be_tx_rate_select(struct ieee80211com *ic, struct ieee80211_node *ni,
    bool basic, uint8_t *rate, uint8_t *hw)
{
    const struct ieee80211_rateset *rs = &ni->ni_rates;
    unsigned int i;

    if (rs->rs_nrates == 0)
        rs = &ic->ic_sup_rates[ic->ic_curmode];
    if (rs->rs_nrates == 0 || rs->rs_nrates > __arraycount(rs->rs_rates))
        return EINVAL;
    if (basic)
        *rate = r23be_tx_basic_rate(rs, 108, true);
    else if (ic->ic_fixed_rate >= 0) {
        const struct ieee80211_rateset *supported =
            &ic->ic_sup_rates[ic->ic_curmode];

        if (ic->ic_fixed_rate >= supported->rs_nrates)
            return EINVAL;
        *rate = supported->rs_rates[ic->ic_fixed_rate] & IEEE80211_RATE_VAL;
        for (i = 0; i < rs->rs_nrates; i++)
            if ((rs->rs_rates[i] & IEEE80211_RATE_VAL) == *rate)
                break;
        if (i == rs->rs_nrates)
            return EINVAL;
    } else {
        if (ni->ni_txrate < 0 || ni->ni_txrate >= rs->rs_nrates)
            return EINVAL;
        *rate = rs->rs_rates[ni->ni_txrate] & IEEE80211_RATE_VAL;
    }
    return r23be_tx_legacy_rate(*rate, hw);
}

/* A single dynamically allocated backing buffer satisfies the ring ABI. */
static struct mbuf *
r23be_tx_linearize(struct mbuf *m)
{
    struct mbuf *linear;
    int len = m->m_pkthdr.len;

    if (m->m_next == NULL && m->m_len == len)
        return m;
    linear = m_gethdr(M_DONTWAIT, MT_DATA);
    if (linear == NULL)
        goto fail;
    if (len > MHLEN) {
        MEXTMALLOC(linear, len, M_DONTWAIT);
        if ((linear->m_flags & M_EXT) == 0) {
            m_freem(linear);
            goto fail;
        }
    }
    m_copydata(m, 0, len, mtod(linear, void *));
    m_move_pkthdr(linear, m);
    linear->m_len = len;
    m_freem(m);
    return linear;
fail:
    m_freem(m);
    return NULL;
}

int
rtwn8723be_net80211_tx_frame(struct rtwn8723be_net80211_tx *tx,
    struct mbuf *m, struct ieee80211_node *ni, uint8_t special_kind)
{
    struct ieee80211com *ic;
    struct ieee80211_frame *wh;
    struct ieee80211_key *key;
    struct rtwn8723be_tx_params p;
    struct rtwn8723be_tx_report_ticket *ticket = NULL;
    struct r23be_tx_notify notify;
    uint8_t type, subtype, rate, protection_rate;
    bool is_null;
    bool eapol = special_kind == RTWN8723BE_TX_SPECIAL_EAPOL;
    unsigned int qid;
    uint16_t seq;
    int error = EINVAL;

    if (m == NULL || ni == NULL || tx == NULL || !tx->prepared ||
        !tx->enabled || tx->sc == NULL ||
        (m->m_flags & M_PKTHDR) == 0 || m->m_nextpkt != NULL)
        goto fail;
    if (special_kind > RTWN8723BE_TX_SPECIAL_EAPOL)
        goto fail;
    ic = &tx->sc->sc_ic;
    if (ic->ic_opmode != IEEE80211_M_STA) {
        error = EOPNOTSUPP;
        goto fail;
    }
    if (m->m_pkthdr.len < (int)sizeof(*wh) ||
        m->m_pkthdr.len > RTWN8723BE_RX_BUFFER_SIZE)
        goto fail;
    if (m->m_len < (int)sizeof(*wh)) {
        m = m_pullup(m, sizeof(*wh));
        if (m == NULL) {
            error = ENOBUFS;
            goto fail;
        }
    }
    wh = mtod(m, struct ieee80211_frame *);
    type = wh->i_fc[0] & IEEE80211_FC0_TYPE_MASK;
    subtype = wh->i_fc[0] & IEEE80211_FC0_SUBTYPE_MASK;
    if (type != IEEE80211_FC0_TYPE_MGT && type != IEEE80211_FC0_TYPE_DATA) {
        error = EOPNOTSUPP;
        goto fail;
    }
    if ((wh->i_fc[0] & IEEE80211_FC0_VERSION_MASK) !=
        IEEE80211_FC0_VERSION_0 || ieee80211_has_qos(wh) ||
        (wh->i_fc[1] & IEEE80211_FC1_DIR_MASK) == IEEE80211_FC1_DIR_DSTODS) {
        error = EOPNOTSUPP;
        goto fail;
    }
    is_null = type == IEEE80211_FC0_TYPE_DATA &&
        subtype == IEEE80211_FC0_SUBTYPE_NODATA;
    if (wh->i_fc[1] & IEEE80211_FC1_WEP) {
        if (!tx->sc->sc_security_policy_valid || !tx->sc->sc_sw_crypto ||
            !tx->sc->sc_use_sw_sec || tx->sc->sc_hw_security_enabled) {
            error = EOPNOTSUPP;
            goto fail;
        }
        key = ieee80211_crypto_encap(ic, ni, m);
        if (key == NULL) {
            error = ENOBUFS;
            goto fail;
        }
        if ((key->wk_flags & IEEE80211_KEY_SWCRYPT) == 0) {
            error = EOPNOTSUPP;
            goto fail;
        }
    }
    if (m->m_pkthdr.len > RTWN8723BE_RX_BUFFER_SIZE) {
        error = EFBIG;
        goto fail;
    }
    m = r23be_tx_linearize(m);
    if (m == NULL) {
        error = ENOBUFS;
        goto fail;
    }
    wh = mtod(m, struct ieee80211_frame *);
    memset(&p, 0, sizeof(p));
    p.packet_len = p.buffer_len = (uint16_t)m->m_pkthdr.len;
    p.multicast = IEEE80211_IS_MULTICAST(wh->i_addr1);
    seq = le16dec(wh->i_seq);
    p.seq = seq >> IEEE80211_SEQ_SEQ_SHIFT;
    p.first_segment = is_null || (seq & IEEE80211_SEQ_FRAG_MASK) == 0;
    p.last_segment = is_null || (wh->i_fc[1] & IEEE80211_FC1_MORE_FRAG) == 0;
    qid = type == IEEE80211_FC0_TYPE_MGT ?
        RTWN8723BE_MGNT_QUEUE : RTWN8723BE_BE_QUEUE;
    p.fw_queue = type == IEEE80211_FC0_TYPE_MGT ?
        RTWN8723BE_TX_FW_MGNT : RTWN8723BE_TX_FW_BE;
    p.macid = 0; /* Frozen Linux station peer uses MACID zero. */
    p.rateid = type == IEEE80211_FC0_TYPE_MGT || p.multicast || is_null ||
        special_kind != RTWN8723BE_TX_SPECIAL_NONE ? 7 :
        (ic->ic_curmode == IEEE80211_MODE_11B ? 6 : 4);
    error = r23be_tx_rate_select(ic, ni,
        type == IEEE80211_FC0_TYPE_MGT || p.multicast || is_null ||
        special_kind != RTWN8723BE_TX_SPECIAL_NONE,
        &rate, &p.hw_rate);
    if (error != 0)
        goto fail;
    /* No firmware rate-mask readiness is guessed: use stack-selected rate. */
    p.use_driver_rate = true;
    p.disable_rate_fallback = true;
    p.short_gi_or_preamble = p.hw_rate > 0 && p.hw_rate < 4 &&
        (ic->ic_flags & IEEE80211_F_SHPREAMBLE) != 0;
    protection_rate = r23be_tx_basic_rate(&ni->ni_rates,
        MIN(rate, 48), false);
    if (protection_rate == 0)
        protection_rate = rate;
    error = r23be_tx_legacy_rate(protection_rate, &p.rts_rate);
    if (error != 0)
        goto fail;
    p.rts_short = p.rts_rate > 0 && p.rts_rate < 4 &&
        (ic->ic_flags & IEEE80211_F_SHPREAMBLE) != 0;
    if (type == IEEE80211_FC0_TYPE_DATA && !p.multicast && !is_null) {
        if (m->m_pkthdr.len + IEEE80211_CRC_LEN > ic->ic_rtsthreshold)
            p.rts_enable = true;
        else if (p.hw_rate >= 4 && (ic->ic_flags & IEEE80211_F_USEPROT)) {
            p.cts2self = ic->ic_protmode == IEEE80211_PROT_CTSONLY;
            p.rts_enable = ic->ic_protmode == IEEE80211_PROT_RTSCTS;
        }
    }
    /* Crypto has already run in software; descriptor security stays zero. */
    if ((eapol || is_null) && p.first_segment) {
        ticket = r23be_tx_report_allocate(tx, ni);
        if (ticket == NULL) {
            error = ENOBUFS;
            goto fail;
        }
        p.special_report = true;
        p.report_sequence = ticket->sequence;
    }
    notify.tx = tx;
    notify.special_kind = special_kind;
    error = rtwn8723be_datapath_enqueue_owned_notify(tx->dp, qid, m, &p,
        false, ticket != NULL ? (void *)ticket : (void *)ni,
        ticket != NULL ? r23be_tx_report_dma_release : r23be_tx_node_release,
        r23be_tx_accepted, &notify);
    if (error != 0) {
        if (ticket != NULL) {
            r23be_tx_report_enqueue_failed(ticket, m);
            return error;
        }
        goto fail;
    }
    if (ticket != NULL) {
        mutex_enter(&tx->report_lock);
        tx->reports_sent++;
        mutex_exit(&tx->report_lock);
    }
    return 0;
fail:
    if (m != NULL)
        r23be_tx_free_frames(m);
    if (ni != NULL)
        ieee80211_free_node(ni);
    return error;
}

/* Identify special Ethernet traffic before software encryption obscures it. */
static uint8_t
r23be_tx_special(struct mbuf *m)
{
    uint8_t packet[96];
    size_t len, iplen, udp;
    uint16_t ether_type, source, dest;

    len = MIN((size_t)m->m_pkthdr.len, sizeof(packet));
    if (len < sizeof(struct ether_header))
        return RTWN8723BE_TX_SPECIAL_NONE;
    m_copydata(m, 0, (int)len, packet);
    ether_type = ((uint16_t)packet[12] << 8) | packet[13];
    if (ether_type == ETHERTYPE_PAE)
        return RTWN8723BE_TX_SPECIAL_EAPOL;
    if (ether_type == ETHERTYPE_ARP)
        return RTWN8723BE_TX_SPECIAL_ARP;
    if (ether_type != ETHERTYPE_IP || len < 14U + 20U ||
        (packet[14] >> 4) != 4 || packet[23] != 17 ||
        (packet[20] & 0x1fU) != 0 || packet[21] != 0)
        return RTWN8723BE_TX_SPECIAL_NONE;
    iplen = (packet[14] & 0x0fU) * 4U;
    udp = 14U + iplen;
    if (iplen < 20 || len < udp + 8)
        return RTWN8723BE_TX_SPECIAL_NONE;
    source = ((uint16_t)packet[udp] << 8) | packet[udp + 1];
    dest = ((uint16_t)packet[udp + 2] << 8) | packet[udp + 3];
    return ((source == 67 && dest == 68) || (source == 68 && dest == 67)) ?
        RTWN8723BE_TX_SPECIAL_DHCP : RTWN8723BE_TX_SPECIAL_NONE;
}

void
rtwn8723be_net80211_tx_start(struct rtwn8723be_net80211_tx *tx,
    struct ifnet *ifp)
{
    struct ieee80211com *ic;
    struct ieee80211_node *ni;
    struct ether_header *eh;
    struct mbuf *m;
    uint8_t special_kind;
    int error;

    if (tx == NULL || !tx->prepared || ifp == NULL ||
        ifp != &tx->sc->sc_ec.ec_if)
        return;
    mutex_enter(&tx->producer_lock);
    ic = &tx->sc->sc_ic;
    if (!tx->enabled ||
        (ifp->if_flags & (IFF_RUNNING | IFF_OACTIVE)) != IFF_RUNNING)
        goto out;
    if (ic->ic_opmode != IEEE80211_M_STA)
        goto out;
    for (;;) {
        /* Stop before dequeue: pending stack queues keep their references. */
        error = rtwn8723be_datapath_tx_check(tx->dp, RTWN8723BE_MGNT_QUEUE);
        if (error == 0)
            error = rtwn8723be_datapath_tx_check(tx->dp, RTWN8723BE_BE_QUEUE);
        if (error != 0) {
            if (error == EBUSY)
                ifp->if_flags |= IFF_OACTIVE;
            break;
        }
        special_kind = RTWN8723BE_TX_SPECIAL_NONE;
        IF_DEQUEUE(&ic->ic_mgtq, m);
        if (m != NULL) {
            ni = M_GETCTX(m, struct ieee80211_node *);
            M_CLEARCTX(m);
            if (ni == NULL) {
                r23be_tx_free_frames(m);
                if_statinc(ifp, if_oerrors);
                continue;
            }
        } else {
            if (ic->ic_state != IEEE80211_S_RUN)
                break;
            IFQ_DEQUEUE(&ifp->if_snd, m);
            if (m == NULL)
                break;
            if (m->m_len < (int)sizeof(*eh)) {
                m = m_pullup(m, sizeof(*eh));
                if (m == NULL) {
                    if_statinc(ifp, if_oerrors);
                    continue;
                }
            }
            eh = mtod(m, struct ether_header *);
            special_kind = r23be_tx_special(m);
            ni = ieee80211_find_txnode(ic, eh->ether_dhost);
            if (ni == NULL) {
                m_freem(m);
                if_statinc(ifp, if_oerrors);
                continue;
            }
            bpf_mtap(ifp, m, BPF_D_OUT);
            m = ieee80211_encap(ic, m, ni);
            if (m == NULL) {
                ieee80211_free_node(ni);
                if_statinc(ifp, if_oerrors);
                continue;
            }
        }
        /* net80211 fragmentation chains packets with m_nextpkt, not m_next. */
        while (m != NULL) {
            struct mbuf *next = m->m_nextpkt;

            m->m_nextpkt = NULL;
            bpf_mtap3(ic->ic_rawbpf, m, BPF_D_OUT);
            error = rtwn8723be_net80211_tx_frame(tx, m,
                ieee80211_ref_node(ni), special_kind);
            if (error != 0) {
                if_statinc(ifp, if_oerrors);
                r23be_tx_free_frames(next);
                if (error == EBUSY)
                    ifp->if_flags |= IFF_OACTIVE;
                m = NULL;
                break;
            }
            m = next;
        }
        ieee80211_free_node(ni);
        if ((ifp->if_flags & IFF_OACTIVE) != 0)
            break;
    }
out:
    mutex_exit(&tx->producer_lock);
}

void
rtwn8723be_net80211_tx_complete(void *arg, unsigned int qid, size_t count)
{
    struct rtwn8723be_net80211_tx *tx = arg;
    struct ifnet *ifp;

    if (tx == NULL || !tx->prepared || count == 0 ||
        qid >= RTWN8723BE_TX_QUEUE_COUNT)
        return;
    mutex_enter(&tx->producer_lock);
    ifp = &tx->sc->sc_ec.ec_if;
    if (tx->enabled && (ifp->if_flags & IFF_RUNNING) != 0) {
        ifp->if_flags &= ~IFF_OACTIVE;
        if_schedule_deferred_start(ifp);
    }
    mutex_exit(&tx->producer_lock);
}
