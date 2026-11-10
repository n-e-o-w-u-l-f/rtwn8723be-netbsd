#!/usr/bin/env python3
"""Run real native queue, key-epoch, completion and STOP code with API mocks.

This checks ownership and deterministic interleavings, not a NetBSD ABI,
SMP/PCI timing, native descriptor-DMA integration or physical WPA2 test.
"""
from net80211_tx_fixture import run_fixture

HARNESS = r'''
static struct mbuf *queue_data(struct rtwn8723be_softc *sc, bool pae)
{
    struct mbuf *m = fixture_ether(pae);
    fixture_queue(&sc->sc_ec.ec_if.if_snd, m);
    return m;
}
static void start(struct rtwn8723be_softc *sc)
{ rtwn8723be_net80211_tx_start(sc, &sc->sc_ec.ec_if); }
static struct mbuf *make_pending(struct rtwn8723be_softc *sc)
{
    queue_data(sc, false);
    busy_budget = 1;
    start(sc);
    struct mbuf *pending = sc->sc_net80211.tx_pending_m;
    assert(pending && pending->alive && peers[0].refs == 2);
    assert(sc->sc_net80211.tx_pending_ni == &peers[0]);
    assert(sc->sc_ec.ec_if.if_flags & IFF_OACTIVE);
    assert(dma_count == 0 && crypto_calls == 1 && encap_calls == 1);
    return pending;
}
int main(void)
{
    struct rtwn8723be_softc sc;
    struct rtwn8723be_net80211 *n;
    struct mbuf *m, *pending;

    fixture_setup(&sc); n = &sc.sc_net80211;
    assert(rtwn8723be_net80211_tx_owner(NULL) == NULL);
    assert(rtwn8723be_net80211_tx_owner(&sc) == n);
    mock_tx_lock = true;
    assert(rtwn8723be_net80211_tx_owner(&sc) == n); /* Pure under TX lock. */
    mock_tx_lock = false;
    n->registered = false;
    assert(rtwn8723be_net80211_tx_owner(&sc) == NULL);
    n->registered = true;
    fixture_assert_balanced();

    /* Management is already an MPDU with one queued node reference.
     * Normal data must acquire exactly one node and use stack encap. */
    fixture_setup(&sc); n = &sc.sc_net80211;
    m = fixture_frame(false, false);
    mtod(m, struct ieee80211_frame *)->i_fc[0] = IEEE80211_FC0_TYPE_MGT;
    m->m_pkthdr.ctx = &peers[0]; peers[0].refs++;
    fixture_queue(&sc.sc_ic.ic_mgtq, m);
    queue_data(&sc, false);
    start(&sc);
    assert(dma_count == 2 && handoff_types[0] == 0 && handoff_types[1] == 8);
    assert(!m->alive && find_calls == 1 && encap_calls == 1 && crypto_calls == 1);
    assert(sc.sc_ec.ec_if.if_opackets == 2 && peers[0].refs == 3);
    fixture_dma_complete(); fixture_assert_balanced();

    /* Management can drain before RUN, data remains queued. */
    fixture_setup(&sc); n = &sc.sc_net80211;
    sc.sc_ic.ic_state = 1;
    m = fixture_frame(false, false);
    mtod(m, struct ieee80211_frame *)->i_fc[0] = IEEE80211_FC0_TYPE_MGT;
    m->m_pkthdr.ctx = &peers[0]; peers[0].refs++;
    fixture_queue(&sc.sc_ic.ic_mgtq, m);
    struct mbuf *data = queue_data(&sc, false);
    start(&sc);
    assert(dma_count == 1 && data->alive && find_calls == 0);
    dequeue(&sc.sc_ec.ec_if.if_snd, &data); fixture_release_packet(data);
    fixture_dma_complete(); fixture_assert_balanced();

    /* Missing management context and copy-allocation failures release once. */
    for (int which = 0; which < 3; which++) {
        fixture_setup(&sc); n = &sc.sc_net80211;
        m = fixture_frame(false, false);
        mtod(m, struct ieee80211_frame *)->i_fc[0] = 0;
        if (which != 0) { m->m_pkthdr.ctx = &peers[0]; peers[0].refs++; }
        fixture_queue(&sc.sc_ic.ic_mgtq, m);
        if (which == 1) fail_alloc = alloc_calls + 1;
        if (which == 2) fail_ext = ext_calls + 1;
        start(&sc);
        assert(dma_count == 0 && sc.sc_ec.ec_if.if_oerrors == 1);
        fixture_assert_balanced();
    }

    /* Input pullup, node acquisition and encap can consume their input. */
    for (int which = 0; which < 4; which++) {
        fixture_setup(&sc); n = &sc.sc_net80211;
        m = queue_data(&sc, false);
        if (which == 0) { fixture_split_frame(m, 8); fail_pullup = 1; }
        if (which == 1) fail_find = 1;
        if (which == 2) fail_encap = 1;
        if (which == 3) fragment_encap = 1;
        start(&sc);
        assert(dma_count == 0 && sc.sc_ec.ec_if.if_oerrors == 1);
        fixture_assert_balanced();
    }
    fixture_setup(&sc);
    m = queue_data(&sc, false); fixture_split_frame(m, 8);
    start(&sc);
    assert(pullup_calls == 1 && !m->alive && dma_count == 1);
    fixture_dma_complete(); fixture_assert_balanced();

    /* Clear EAPOL before key setup is valid; normal privacy data is not. */
    fixture_setup(&sc); peers[0].ni_ucastkey = no_key;
    queue_data(&sc, true); start(&sc);
    assert(dma_count == 1 && crypto_calls == 0);
    fixture_dma_complete(); fixture_assert_balanced();
    fixture_setup(&sc); peers[0].ni_ucastkey = no_key;
    queue_data(&sc, false); start(&sc);
    assert(dma_count == 0 && sc.sc_ec.ec_if.if_oerrors == 1);
    fixture_assert_balanced();

    /* Policy enabled reentrantly during node acquisition may not leak clear data. */
    fixture_setup(&sc); sc.sc_ic.ic_flags &= ~IEEE80211_F_PRIVACY;
    privacy_in_find = force_clear_encap = 1;
    queue_data(&sc, false); start(&sc);
    assert(dma_count == 0 && crypto_calls == 0);
    fixture_assert_balanced();

    /* Reentrant rekey during stack encapsulation invalidates first submission. */
    fixture_setup(&sc); rekey_in_encap = 1;
    queue_data(&sc, false); start(&sc);
    assert(dma_count == 0 && sc.sc_ec.ec_if.if_oerrors == 1);
    fixture_assert_balanced();

    fixture_setup(&sc); n = &sc.sc_net80211; pending = make_pending(&sc);
    rtwn8723be_net80211_tx_complete(n, 1, 0);
    rtwn8723be_net80211_tx_complete(n, RTWN8723BE_TX_QUEUE_COUNT, 1);
    assert(n->tx_pending_m == pending && start_kicks == 0);
    rtwn8723be_net80211_tx_complete(n, 1, 1);
    assert(n->tx_pending_m == NULL && dma_count == 1 && dma_m[0] == pending);
    assert(crypto_calls == 1 && encap_calls == 1 && peers[0].ni_ucastkey.wk_keytsc == 1);
    assert(start_kicks == 1);
    fixture_dma_complete(); fixture_assert_balanced();

    /* Two separate frames each see completion before OACTIVE publication. */
    fixture_setup(&sc); queue_data(&sc, false); queue_data(&sc, false);
    busy_call_mask = completion_call_mask = (1U << 0) | (1U << 2);
    start(&sc);
    assert(enqueue_calls == 4 && dma_count == 2);
    assert(sc.sc_net80211.tx_pending_m == NULL &&
           (sc.sc_ec.ec_if.if_flags & IFF_OACTIVE) == 0);
    assert(crypto_calls == 2 && encap_calls == 2);
    fixture_dma_complete(); fixture_assert_balanced();

    /* Same-address key replacement/deletion and association/channel policy
     * changes invalidate the prepared pair; no retry may consume another PN. */
    for (int which = 0; which < 10; which++) {
        fixture_setup(&sc); n = &sc.sc_net80211; pending = make_pending(&sc);
        uint64_t pn = peers[0].ni_ucastkey.wk_keytsc;
        if (which <= 1) {
            sc.sc_ic.ic_crypto.cs_key_update_begin(&sc.sc_ic);
            peers[0].ni_ucastkey = which == 0 ? valid_key : no_key;
            sc.sc_ic.ic_crypto.cs_key_update_end(&sc.sc_ic);
        } else if (which == 2) sc.sc_ic.ic_curchan = &channels[1];
        else if (which == 3) channels[0].ic_freq++;
        else if (which == 4) channels[0].ic_flags ^= 0x20;
        else if (which == 5) peers[0].ni_bssid[5]++;
        else if (which == 6) sc.sc_ic.ic_state = 1;
        else if (which == 7) sc.sc_ic.ic_def_txkey = 1;
        else if (which == 8) sc.sc_ic.ic_flags ^= IEEE80211_F_PRIVACY;
        else sc.sc_ic.ic_curmode = IEEE80211_MODE_11B;
        rtwn8723be_net80211_tx_complete(n, 1, 1);
        assert(!pending->alive && n->tx_pending_m == NULL && dma_count == 0);
        assert(crypto_calls == 1 && encap_calls == 1);
        if (which > 1) assert(peers[0].ni_ucastkey.wk_keytsc == pn);
        fixture_assert_balanced();
    }

    /* The real datapath completion must wake the native consumer even if
     * there is NO optional external completion callback. */
    fixture_setup(&sc); n = &sc.sc_net80211;
    queue_data(&sc, false); queue_data(&sc, false);
    busy_call_mask = 1U << 1;
    start(&sc);
    assert(dma_count == 1 && n->tx_pending_m != NULL);
    expect_callback_lease = true;
    rtwn8723be_dp_tx_done(&fixture_dp, 1);
    assert(reclaim_calls == 1 && start_kicks == 1 && dma_count == 1);
    assert(n->tx_pending_m == NULL && fixture_dp.tx_callback_active == 0);
    fixture_dma_complete(); fixture_assert_balanced();

    /* Optional notification shares the same outside-lock lifetime lease. */
    fixture_setup(&sc); queue_data(&sc, false); start(&sc);
    fixture_dp.tx_complete = fixture_notify; fixture_dp.tx_complete_arg = &fixture_dp;
    expect_callback_lease = true; rtwn8723be_dp_tx_done(&fixture_dp, 1);
    assert(notify_calls == 1 && fixture_dp.tx_callback_active == 0);
    fixture_assert_balanced();

    /* Last-node key update under DMA reclaim may change only the epoch. */
    fixture_setup(&sc); n = &sc.sc_net80211;
    queue_data(&sc, false); queue_data(&sc, false); busy_call_mask = 1U << 1;
    start(&sc); key_delete_in_reclaim = true;
    rtwn8723be_dp_tx_done(&fixture_dp, 1);
    assert(dma_count == 0 && n->tx_pending_m == NULL);
    assert(saved_begin_calls == 1 && saved_end_calls == 1);
    fixture_assert_balanced();

    /* Failed STOP and false success retain ownership; actual quiescence purges. */
    for (int which = 0; which < 4; which++) {
        fixture_setup(&sc); n = &sc.sc_net80211; pending = make_pending(&sc);
        if (which == 0) hw_stop_result = EBUSY;
        else if (which == 1) hw_stop_false_success = 1;
        else if (which == 2) n->tx_busy = true;
        else n->tx_key_update_depth = 1;
        assert(rtwn8723be_n80211_ifstop(n) != 0);
        assert(pending->alive && n->tx_pending_m == pending && peers[0].refs == 2);
        assert((sc.sc_ec.ec_if.if_flags & IFF_RUNNING) == 0);
        hw_stop_result = hw_stop_false_success = 0;
        n->tx_busy = false; n->tx_key_update_depth = 0;
        assert(rtwn8723be_n80211_ifstop(n) == 0);
        assert(!pending->alive && n->tx_pending_m == NULL);
        fixture_remove_keys(&sc); fixture_assert_balanced();
    }
    fixture_setup(&sc); n = &sc.sc_net80211; pending = make_pending(&sc);
    sc.sc_linux.started = sc.sc_linux.fw_ready = false;
    assert(rtwn8723be_n80211_ifstop(n) == 0 && !pending->alive);
    assert(hw_stop_calls == 0); fixture_remove_keys(&sc); fixture_assert_balanced();


    /* Unsupported native frame formats are rejected and cleaned up. */
    for (int which = 1; which <= 3; which++) {
        fixture_setup(&sc); encap_format = which;
        queue_data(&sc, false); start(&sc);
        assert(dma_count == 0 && sc.sc_ec.ec_if.if_oerrors == 1);
        fixture_assert_balanced();
    }

    /* The exact RTS boundary includes the on-air FCS, then ERP policy
     * may choose CTS-to-self from genuine negotiated BASIC CCK rates. */
    fixture_setup(&sc);
    m = fixture_frame(false, false);
    struct rtwn8723be_tx_params rate;
    sc.sc_ic.ic_rtsthreshold = (uint16_t)(m->m_pkthdr.len + 4);
    assert(r23be_n80211_tx_rate(&sc, &peers[0], m, &rate) == 0);
    assert(!rate.rts_enable && !rate.cts2self);
    sc.sc_ic.ic_rtsthreshold--;
    assert(r23be_n80211_tx_rate(&sc, &peers[0], m, &rate) == 0);
    assert(rate.rts_enable && !rate.cts2self && rate.rts_rate == 8);
    sc.sc_ic.ic_rtsthreshold = 2347;
    sc.sc_ic.ic_flags |= IEEE80211_F_USEPROT;
    sc.sc_ic.ic_protmode = IEEE80211_PROT_CTSONLY;
    assert(r23be_n80211_tx_rate(&sc, &peers[0], m, &rate) == 0);
    assert(rate.rts_enable && rate.cts2self && rate.rts_rate == 3);
    sc.sc_ic.ic_rtsthreshold = 1;
    assert(r23be_n80211_tx_rate(&sc, &peers[0], m, &rate) == 0);
    assert(rate.rts_enable && !rate.cts2self && rate.rts_rate == 3);
    for (unsigned j = 0; j < peers[0].ni_rates.rs_nrates; j++)
        peers[0].ni_rates.rs_rates[j] &= IEEE80211_RATE_VAL;
    assert(r23be_n80211_tx_rate(&sc, &peers[0], m, &rate) == EOPNOTSUPP);
    fixture_release_packet(m); fixture_assert_balanced();

    /* Fixed-rate index selects supported rates, then negotiated membership. */
    fixture_setup(&sc); m = fixture_frame(false, false);
    sc.sc_ic.ic_fixed_rate = 0;
    assert(r23be_n80211_tx_rate(&sc, &peers[0], m, &rate) == 0 && rate.hw_rate == 0);
    peers[0].ni_rates.rs_rates[0] = 4;
    assert(r23be_n80211_tx_rate(&sc, &peers[0], m, &rate) == EINVAL);
    fixture_release_packet(m); fixture_assert_balanced();

    /* Native descriptor parameters must reflect BPF callbacks that change
     * rate or protection policy; context changes must prevent submission. */
    for (int which = 1; which <= 5; which++) {
        fixture_setup(&sc); raw_bpf_hook = which;
        queue_data(&sc, false); start(&sc);
        if (which <= 3) {
            assert(dma_count == 1);
            if (which == 1) assert(last_rate.hw_rate == 0);
            if (which == 2) assert(last_rate.rts_enable && last_rate.cts2self &&
                                   last_rate.rts_rate == 3);
            if (which == 3) assert(last_rate.rts_enable && !last_rate.cts2self);
            fixture_dma_complete();
        } else assert(dma_count == 0);
        fixture_assert_balanced();
    }

    puts("RTL_NET80211_TX_CONSUMER_PRODUCTION_C11_UBSAN_OK");
    return 0;
}
'''

MUTATIONS = [
  [
    "M_CLEARCTX(m);",
    "(void)0;"
  ],
  [
    "n->tx_pending_m = m;",
    "n->tx_pending_m = NULL;"
  ],
  [
    "n->tx_pending_ni = ni;",
    "n->tx_pending_ni = NULL;"
  ],
  [
    "goto submit; /* Already encrypted; never consume another PN. */",
    "if (r23be_n80211_tx_prepare(sc, ni, &m, false) != 0) goto drop;\n            goto submit;"
  ],
  [
    "context->key_epoch != n->tx_key_epoch",
    "false"
  ],
  [
    "context->channel_flags != context->channel->ic_flags",
    "false"
  ],
  [
    "context->channel_freq != context->channel->ic_freq",
    "false"
  ],
  [
    "context->default_key != ic->ic_def_txkey",
    "false"
  ],
  [
    "native = rtwn8723be_net80211_tx_owner(dp->sc);",
    "native = NULL;"
  ],
  [
    "dp->tx_callback_active++;",
    "dp->tx_callback_active += 0;"
  ],
  [
    "if_start_lock(ifp);",
    "(void)if_start_lock;"
  ],
  [
    "if (n->tx_again &&",
    "if (false &&"
  ],
  [
    "ieee80211_free_node(ni);",
    "(void)0;"
  ]
]
run_fixture("consumer", HARNESS, MUTATIONS)
