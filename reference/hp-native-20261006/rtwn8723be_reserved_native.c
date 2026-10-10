/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Frozen Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab:
 * rtl8723be/fw.c:rtl8723be_set_fw_rsvdpagepkt, hw.c:download_rsvd_page,
 * core.c:rtl_cmd_send_packet and rtl8723be/trx.c:tx_fill_cmddesc.
 *
 * Adapt the fixed reserved-page layout to the actual NetBSD station BSS.
 * No synthetic HT/WME advertisements are copied from Linux's sample SSIDs.
 * The firmware's reserved QoS-null templates retain their source layout;
 * this does not advertise a NetBSD WME/HT transmit capability.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <sys/mbuf.h>
#include <sys/endian.h>
#include <sys/cpu.h>
#include <sys/intr.h>
#include "rtwn8723be_reserved_native.h"
#include <net80211/ieee80211_var.h>
#include <net80211/ieee80211_proto.h>

#include "rtwn8723be_h2c_native.h"

#define R23BE_RESERVED_PAGE 128U
#define R23BE_RESERVED_PSPOLL 2U
#define R23BE_RESERVED_NULL 3U
#define R23BE_RESERVED_PROBE 4U
#define R23BE_RESERVED_QOS_NULL 6U
#define R23BE_RESERVED_BT_NULL 7U
#define R23BE_RESERVED_HEADER 40U

static void
r23be_reserved_put16(uint8_t *out, uint16_t value)
{
    out[0] = (uint8_t)value;
    out[1] = (uint8_t)(value >> 8);
}

static void
r23be_reserved_put32(uint8_t *out, uint32_t value)
{
    out[0] = (uint8_t)value;
    out[1] = (uint8_t)(value >> 8);
    out[2] = (uint8_t)(value >> 16);
    out[3] = (uint8_t)(value >> 24);
}

/* Device packet-buffer descriptor: no PCI DMA/next pointers live here. */
static void
r23be_reserved_descriptor(uint8_t *out, uint16_t len, bool pspoll, bool bt)
{
    memset(out, 0, R23BE_RESERVED_HEADER);
    r23be_reserved_put32(out, len | (R23BE_RESERVED_HEADER << 16) |
        R23BE_TXD0_OWN | R23BE_TXD0_FIRST_SEG | R23BE_TXD0_LAST_SEG);
    r23be_reserved_put32(out + 4, RTWN8723BE_TX_FW_MGNT << 8);
    if (bt)
        r23be_reserved_put32(out + 8, 1U << 23); /* frozen BT_INT */
    r23be_reserved_put32(out + 12, R23BE_TXD3_USE_RATE |
        (pspoll ? R23BE_TXD3_NAV_USE_HDR : 0));
    if (!pspoll)
        r23be_reserved_put32(out + 32, R23BE_TXD8_HWSEQ_EN);
}

static void
r23be_reserved_header(uint8_t *out, uint8_t fc,
    const struct rtwn8723be_reserved_peer *peer, bool beacon)
{
    out[0] = fc;
    if ((fc & IEEE80211_FC0_TYPE_MASK) == IEEE80211_FC0_TYPE_DATA)
        out[1] = 1; /* source null templates: ToDS */
    if (beacon)
        memset(out + 4, 0xff, 6);
    else
        memcpy(out + 4, peer->bssid, 6);
    memcpy(out + 10, peer->mac, 6);
    memcpy(out + 16, peer->bssid, 6);
}

/* At most two pages before the next frame's 40-byte descriptor. */
static int
r23be_reserved_beacon(uint8_t *out, uint8_t fc,
    const struct rtwn8723be_reserved_peer *peer, uint16_t *length)
{
    const size_t maximum = 2U * R23BE_RESERVED_PAGE - R23BE_RESERVED_HEADER;
    size_t pos = 36, base_rates = MIN(peer->rate_count, 8);
    size_t needed = pos + 2 + peer->ssid_length + 2 + base_rates + 3 + 3;

    if (peer->rate_count > base_rates)
        needed += 2 + peer->rate_count - base_rates;
    if (fc == 0x80)
        needed += 6; /* minimal TIM with real DTIM period */
    needed += peer->wpa_ie_length;
    if (needed > maximum)
        return EFBIG;
    r23be_reserved_header(out, fc, peer, fc == 0x80);
    r23be_reserved_put16(out + 32, peer->beacon_interval);
    r23be_reserved_put16(out + 34, peer->capability);
    out[pos++] = 0; /* SSID */
    out[pos++] = (uint8_t)peer->ssid_length;
    if (peer->ssid_length != 0)
        memcpy(out + pos, peer->ssid, peer->ssid_length);
    pos += peer->ssid_length;
    out[pos++] = 1; /* supported rates */
    out[pos++] = (uint8_t)base_rates;
    memcpy(out + pos, peer->rates, base_rates);
    pos += base_rates;
    out[pos++] = 3; out[pos++] = 1; out[pos++] = peer->channel;
    if (fc == 0x80) {
        out[pos++] = 5; out[pos++] = 4; /* TIM */
        out[pos++] = 0; out[pos++] = peer->dtim_period;
        out[pos++] = 0; out[pos++] = 0;
    }
    out[pos++] = 42; out[pos++] = 1; out[pos++] = peer->erp;
    if (peer->rate_count > base_rates) {
        size_t extra = peer->rate_count - base_rates;
        out[pos++] = 50; out[pos++] = (uint8_t)extra;
        memcpy(out + pos, peer->rates + base_rates, extra);
        pos += extra;
    }
    if (peer->wpa_ie_length != 0)
        memcpy(out + pos, peer->wpa_ie, peer->wpa_ie_length);
    pos += peer->wpa_ie_length;
    *length = (uint16_t)pos;
    return 0;
}

int
rtwn8723be_reserved_build(const struct rtwn8723be_reserved_peer *peer,
    uint8_t *out, size_t outlen, uint8_t locations[5])
{
    static const uint8_t legacy_rates[] = { 2, 4, 11, 22, 12, 18, 24,
        36, 48, 72, 96, 108 };
    uint16_t beacon_length, probe_length;
    unsigned int i, j;
    uint8_t any_mac = 0, any_bssid = 0;
    int error;

    if (peer == NULL || out == NULL || locations == NULL ||
        outlen < RTWN8723BE_RESERVED_SIZE || peer->aid == 0 ||
        peer->aid > 2007 || peer->beacon_interval == 0 ||
        peer->channel == 0 || peer->channel > 14 || peer->ssid_length > 32 ||
        (peer->ssid_length != 0 && peer->ssid == NULL) ||
        peer->rates == NULL || peer->rate_count == 0 || peer->rate_count > 15 ||
        (peer->mac[0] & 1U) != 0 || (peer->bssid[0] & 1U) != 0 ||
        (peer->wpa_ie_length != 0 && (peer->wpa_ie == NULL ||
        peer->wpa_ie_length < 2 ||
        peer->wpa_ie_length != (size_t)peer->wpa_ie[1] + 2)))
        return EINVAL;
    for (i = 0; i < 6; i++) {
        any_mac |= peer->mac[i];
        any_bssid |= peer->bssid[i];
    }
    if (any_mac == 0 || any_bssid == 0)
        return EINVAL;
    for (i = 0; i < peer->rate_count; i++) {
        for (j = 0; j < __arraycount(legacy_rates); j++)
            if ((peer->rates[i] & IEEE80211_RATE_VAL) == legacy_rates[j])
                break;
        if (j == __arraycount(legacy_rates))
            return EOPNOTSUPP;
    }
    memset(out, 0, RTWN8723BE_RESERVED_SIZE);
    error = r23be_reserved_beacon(out, 0x80, peer, &beacon_length);
    if (error != 0)
        return error;
    error = r23be_reserved_beacon(out + R23BE_RESERVED_PROBE *
        R23BE_RESERVED_PAGE, 0x50, peer, &probe_length);
    if (error != 0)
        return error;
    /* Beacon's PCI descriptor is supplied by tx_encode_command outside skb. */
    (void)beacon_length;
    r23be_reserved_descriptor(out + R23BE_RESERVED_PSPOLL *
        R23BE_RESERVED_PAGE - R23BE_RESERVED_HEADER, 16, true, false);
    out[R23BE_RESERVED_PSPOLL * R23BE_RESERVED_PAGE] = 0xa4;
    out[R23BE_RESERVED_PSPOLL * R23BE_RESERVED_PAGE + 1] = 0x10;
    r23be_reserved_put16(out + R23BE_RESERVED_PSPOLL * R23BE_RESERVED_PAGE + 2,
        peer->aid | 0xc000U);
    memcpy(out + R23BE_RESERVED_PSPOLL * R23BE_RESERVED_PAGE + 4, peer->bssid, 6);
    memcpy(out + R23BE_RESERVED_PSPOLL * R23BE_RESERVED_PAGE + 10, peer->mac, 6);
    r23be_reserved_descriptor(out + R23BE_RESERVED_NULL *
        R23BE_RESERVED_PAGE - R23BE_RESERVED_HEADER, 24, false, false);
    r23be_reserved_header(out + R23BE_RESERVED_NULL * R23BE_RESERVED_PAGE,
        0x48, peer, false);
    r23be_reserved_descriptor(out + R23BE_RESERVED_PROBE *
        R23BE_RESERVED_PAGE - R23BE_RESERVED_HEADER, probe_length, false, false);
    r23be_reserved_descriptor(out + R23BE_RESERVED_QOS_NULL *
        R23BE_RESERVED_PAGE - R23BE_RESERVED_HEADER, 26, false, false);
    r23be_reserved_header(out + R23BE_RESERVED_QOS_NULL * R23BE_RESERVED_PAGE,
        0xc8, peer, false);
    r23be_reserved_descriptor(out + R23BE_RESERVED_BT_NULL *
        R23BE_RESERVED_PAGE - R23BE_RESERVED_HEADER, 26, false, true);
    r23be_reserved_header(out + R23BE_RESERVED_BT_NULL * R23BE_RESERVED_PAGE,
        0xc8, peer, false);
    locations[0] = R23BE_RESERVED_PROBE;
    locations[1] = R23BE_RESERVED_PSPOLL;
    locations[2] = R23BE_RESERVED_NULL;
    locations[3] = R23BE_RESERVED_QOS_NULL;
    locations[4] = R23BE_RESERVED_BT_NULL;
    return 0;
}

static void
r23be_reserved_release(void *arg, struct mbuf *m, bool completed)
{
    struct ieee80211_node *ni = arg;

    /* Reserved-page DMA is not an on-air station packet or an air ACK. */
    (void)completed;
    if (m != NULL)
        m_freem(m);
    ieee80211_free_node(ni);
}

int
rtwn8723be_reserved_native_prepare(struct rtwn8723be_reserved_native *rsvd,
    struct rtwn8723be_softc *sc, struct rtwn8723be_datapath *dp)
{
    if (rsvd == NULL || sc == NULL || dp == NULL || !dp->prepared || dp->sc != sc)
        return EINVAL;
    if (rsvd->initialized)
        return EALREADY;
    memset(rsvd, 0, sizeof(*rsvd));
    rsvd->sc = sc;
    rsvd->dp = dp;
    rsvd->initialized = true;
    return 0;
}

static int
r23be_reserved_reclaim(struct rtwn8723be_reserved_native *rsvd, bool *pending)
{
    size_t reclaimed;
    int error;

    mutex_enter(&rsvd->dp->tx_lock);
    error = rtwn8723be_tx_native_reclaim_reserved(rsvd->sc, &reclaimed);
    *pending = rsvd->sc->sc_tx_ring[RTWN8723BE_BEACON_QUEUE].slot != NULL &&
        rsvd->sc->sc_tx_ring[RTWN8723BE_BEACON_QUEUE].slot[0].m != NULL;
    mutex_exit(&rsvd->dp->tx_lock);
    return error;
}

int
rtwn8723be_reserved_native_download(struct rtwn8723be_reserved_native *rsvd,
    struct ieee80211_node *ni)
{
    struct rtwn8723be_softc *sc;
    struct ieee80211com *ic;
    struct rtwn8723be_reserved_peer peer;
    struct rtwn8723be_tx_params p;
    struct mbuf *m;
    uint8_t locations[5], cr, txq, bcn, valid = 0;
    unsigned int attempt, poll;
    bool pending;
    uint16_t aid_register;
    int error;

    if (rsvd == NULL || !rsvd->initialized || ni == NULL || rsvd->sc == NULL ||
        rsvd->downloading)
        return EINVAL;
    if (cpu_intr_p() || cpu_softintr_p())
        return EWOULDBLOCK;
    sc = rsvd->sc;
    ic = &sc->sc_ic;
    rsvd->valid = false;
    if (!sc->sc_mapped || !sc->sc_linux.started || !sc->sc_linux.fw_ready ||
        !rsvd->dp->prepared || !rsvd->dp->tx_enabled || ni->ni_ic != ic ||
        ic->ic_opmode != IEEE80211_M_STA || ni->ni_chan == NULL ||
        !sc->sc_h2c.initialized || sc->sc_h2c.firmware_generation == 0)
        return EAGAIN;
    memset(&peer, 0, sizeof(peer));
    memcpy(peer.mac, ic->ic_myaddr, 6);
    memcpy(peer.bssid, ni->ni_bssid, 6);
    peer.aid = IEEE80211_AID(ni->ni_associd);
    peer.beacon_interval = ni->ni_intval;
    peer.capability = ni->ni_capinfo;
    peer.channel = (uint8_t)ieee80211_chan2ieee(ic, ni->ni_chan);
    peer.erp = ni->ni_erp;
    peer.dtim_period = ni->ni_dtim_period;
    peer.ssid = ni->ni_essid;
    peer.ssid_length = ni->ni_esslen;
    peer.rates = ni->ni_rates.rs_rates;
    peer.rate_count = ni->ni_rates.rs_nrates;
    peer.wpa_ie = ni->ni_wpa_ie;
    peer.wpa_ie_length = peer.wpa_ie != NULL ? (size_t)peer.wpa_ie[1] + 2 : 0;

    m = m_gethdr(M_DONTWAIT, MT_DATA);
    if (m == NULL)
        return ENOBUFS;
    MEXTMALLOC(m, RTWN8723BE_RESERVED_SIZE, M_DONTWAIT);
    if ((m->m_flags & M_EXT) == 0) {
        m_freem(m);
        return ENOBUFS;
    }
    m->m_len = m->m_pkthdr.len = RTWN8723BE_RESERVED_SIZE;
    error = rtwn8723be_reserved_build(&peer, mtod(m, uint8_t *),
        RTWN8723BE_RESERVED_SIZE, locations);
    if (error != 0) {
        m_freem(m);
        return error;
    }
    error = r23be_reserved_reclaim(rsvd, &pending);
    if (error != 0 || pending) {
        m_freem(m);
        return error != 0 ? error : EBUSY;
    }
    rsvd->downloading = true;
    /* Frozen HW_VAR_H2C_FW_JOINBSSRPT first programs HW_VAR_AID. */
    aid_register = rtwn8723be_read_2(sc, R23BE_REG_BCN_PSR_RPT) & 0xc000U;
    rtwn8723be_write_2(sc, R23BE_REG_BCN_PSR_RPT, aid_register | peer.aid);
    cr = rtwn8723be_read_1(sc, R23BE_REG_CR + 1);
    txq = rtwn8723be_read_1(sc, R23BE_REG_FWHW_TXQ_CTRL + 2);
    bcn = rtwn8723be_read_1(sc, R23BE_REG_BCN_CTRL);
    rtwn8723be_write_1(sc, R23BE_REG_CR + 1, cr | 1U);
    sc->sc_bcn_ctrl_val = (bcn & ~8U) | 16U;
    rtwn8723be_write_1(sc, R23BE_REG_BCN_CTRL, sc->sc_bcn_ctrl_val);
    rtwn8723be_write_1(sc, R23BE_REG_FWHW_TXQ_CTRL + 2, txq & ~64U);
    memset(&p, 0, sizeof(p));
    p.packet_len = p.buffer_len = RTWN8723BE_RESERVED_SIZE;
    p.fw_queue = RTWN8723BE_TX_FW_BEACON;
    error = ETIMEDOUT;
    for (attempt = 0; attempt < 5; attempt++) {
        struct ieee80211_node *owned_ni;

        valid = rtwn8723be_read_1(sc, R23BE_REG_TDECTRL + 2);
        rtwn8723be_write_1(sc, R23BE_REG_TDECTRL + 2, valid | 1U);
        owned_ni = ieee80211_ref_node(ni);
        mutex_enter(&rsvd->dp->tx_lock);
        if (!rsvd->dp->tx_enabled)
            error = EAGAIN;
        else
            error = rtwn8723be_tx_native_enqueue_reserved(sc, m, &p,
                owned_ni, r23be_reserved_release);
        mutex_exit(&rsvd->dp->tx_lock);
        if (error != 0) {
            ieee80211_free_node(owned_ni);
            break;
        }
        m = NULL; /* Successful ring publication owns buffer and node. */
        rsvd->attempts++;
        for (poll = 0; poll <= 20; poll++) {
            valid = rtwn8723be_read_1(sc, R23BE_REG_TDECTRL + 2);
            if (valid & 1U)
                break;
            if (poll != 20)
                delay(10);
        }
        error = r23be_reserved_reclaim(rsvd, &pending);
        if (error != 0)
            break;
        if (valid & 1U) {
            error = rtwn8723be_h2c_native_send(sc, 0, locations, sizeof(locations));
            break;
        }
        error = ETIMEDOUT;
        /* Never repeat Linux's freeing of a still-device-owned DMA buffer. */
        if (pending || attempt == 4)
            break;
        m = m_gethdr(M_DONTWAIT, MT_DATA);
        if (m == NULL) {
            error = ENOBUFS;
            break;
        }
        MEXTMALLOC(m, RTWN8723BE_RESERVED_SIZE, M_DONTWAIT);
        if ((m->m_flags & M_EXT) == 0) {
            error = ENOBUFS;
            break;
        }
        m->m_len = m->m_pkthdr.len = RTWN8723BE_RESERVED_SIZE;
        error = rtwn8723be_reserved_build(&peer, mtod(m, uint8_t *),
            RTWN8723BE_RESERVED_SIZE, locations);
        if (error != 0)
            break;
    }
    if (valid & 1U)
        rtwn8723be_write_1(sc, R23BE_REG_TDECTRL + 2, 1U);
    /* Restore the actual entry state on every success/failure path. */
    rtwn8723be_write_1(sc, R23BE_REG_BCN_CTRL, bcn);
    sc->sc_bcn_ctrl_val = bcn;
    rtwn8723be_write_1(sc, R23BE_REG_FWHW_TXQ_CTRL + 2, txq);
    rtwn8723be_write_1(sc, R23BE_REG_CR + 1, cr);
    rsvd->downloading = false;
    rsvd->last_error = error;
    if (m != NULL)
        m_freem(m);
    if (error == 0) {
        rsvd->valid = true;
        rsvd->firmware_generation = sc->sc_h2c.firmware_generation;
        memcpy(rsvd->bssid, peer.bssid, 6);
        rsvd->aid = peer.aid;
    }
    return error;
}

bool
rtwn8723be_reserved_native_ready(const struct rtwn8723be_reserved_native *rsvd,
    const struct ieee80211_node *ni)
{
    return rsvd != NULL && rsvd->initialized && rsvd->valid && ni != NULL &&
        rsvd->sc != NULL && ni->ni_ic == &rsvd->sc->sc_ic &&
        rsvd->sc->sc_linux.started && rsvd->sc->sc_linux.fw_ready &&
        rsvd->dp != NULL && rsvd->dp->prepared && rsvd->dp->tx_enabled &&
        rsvd->firmware_generation == rsvd->sc->sc_h2c.firmware_generation &&
        rsvd->aid == IEEE80211_AID(ni->ni_associd) &&
        memcmp(rsvd->bssid, ni->ni_bssid, 6) == 0;
}

int
rtwn8723be_reserved_native_invalidate(struct rtwn8723be_reserved_native *rsvd)
{
    if (rsvd == NULL || !rsvd->initialized)
        return EINVAL;
    if (rsvd->downloading)
        return EBUSY;
    rsvd->valid = false;
    return 0;
}

int
rtwn8723be_reserved_native_fini(struct rtwn8723be_reserved_native *rsvd)
{
    int error = rtwn8723be_reserved_native_invalidate(rsvd);

    if (error == 0)
        memset(rsvd, 0, sizeof(*rsvd));
    return error;
}
