#!/usr/bin/env python3
"""Execute the production TX preparation/key hooks with NetBSD API mocks.

The fixture proves safe mbuf ownership and real stack-crypto API usage.
Cipher bytes are a test double: this is not an AES known-answer test,
NetBSD ABI validation, native kernel run, or WPA2 hardware acceptance.
"""
from net80211_tx_fixture import run_fixture

HARNESS = r'''
static void failed_unchanged(struct rtwn8723be_softc *sc,
    struct ieee80211_node *ni, struct mbuf *m, bool require_protected)
{
    struct mbuf *original = m;
    int refs = ni == NULL ? 0 : ni->refs;
    assert(r23be_n80211_tx_prepare(sc, ni, &m, require_protected) != 0);
    assert(m == original && original->alive);
    assert(ni == NULL || ni->refs == refs);
    fixture_release_packet(m);
    fixture_assert_balanced();
}
int main(void)
{
    struct rtwn8723be_softc sc;
    struct ieee80211_node *ni;
    struct mbuf *m, *original;
    struct ieee80211_key *k;
    unsigned int flags;
    const uint64_t pn_max = UINT64_C(0xffffffffffff);

    /* Execute the ACTUAL installed pointer-by-value crypto API unsafely
     * once: missing headroom relocates/frees the passed head. This proves
     * why the production preparation step must preallocate it. */
    fixture_setup(&sc); ni = &peers[0];
    m = fixture_frame(false, true); original = m;
    assert(ieee80211_crypto_encap(&sc.sc_ic, ni, m) != NULL);
    assert(!original->alive && last_crypto_m != original);
    assert(prepend_allocations == 1 && pullup_calls == 1);
    fixture_release_packet(last_crypto_m); fixture_assert_balanced();

    fixture_setup(&sc); ni = &peers[0];
    m = fixture_frame(false, false); original = m;
    assert(r23be_n80211_tx_prepare(&sc, ni, &m, false) == 0);
    assert(m != original && !original->alive && m->alive);
    assert(m->m_next == NULL && m->m_len == m->m_pkthdr.len);
    assert(crypto_calls == 0);
    fixture_release_packet(m); fixture_assert_balanced();

    /* Protected input is copied from a read-only chain with zero headroom.
     * Only the exclusive replacement may be prepended/encrypted/appended. */
    fixture_setup(&sc); ni = &peers[0]; k = &ni->ni_ucastkey;
    m = fixture_frame(false, true); original = m;
    fixture_split_frame(m, 10);
    m->readonly = true;
    assert(r23be_n80211_tx_prepare(&sc, ni, &m, true) == 0);
    assert(m != original && !original->alive && m->alive);
    assert(m->m_next == NULL && m->m_len == 50);
    assert(crypto_calls == 1 && k->wk_keytsc == 1);
    assert(prepend_allocations == 0 && pullup_calls == 0 && append_allocations == 0);
    assert(mtod(m, uint8_t *)[24] == 1); /* PN, not plaintext. */
    assert(M_TRAILINGSPACE(m) >= 0);
    fixture_release_packet(m); fixture_assert_balanced();

    /* Allocation failure consumes only a failed private clone. */
    for (int which = 1; which <= 2; which++) {
        fixture_setup(&sc); ni = &peers[0];
        m = fixture_frame(false, true);
        if (which == 1) fail_alloc = alloc_calls + 1;
        else fail_ext = ext_calls + 1;
        failed_unchanged(&sc, ni, m, true);
        assert(crypto_calls == 0 && ni->ni_ucastkey.wk_keytsc == 0);
    }

    /* Normal privacy data cannot silently fall back to plaintext. */
    fixture_setup(&sc); ni = &peers[0]; m = fixture_frame(false, false);
    failed_unchanged(&sc, ni, m, true);
    assert(crypto_calls == 0);

    /* Actual key-selection semantics: unicast uses PTK; group RA uses GTK. */
    fixture_setup(&sc); ni = &peers[0];
    m = fixture_frame(true, true); sc.sc_ic.ic_def_txkey = 2;
    sc.sc_ic.ic_nw_keys[2] = valid_key;
    assert(r23be_n80211_tx_prepare(&sc, ni, &m, true) == 0);
    assert(last_crypto_key == &sc.sc_ic.ic_nw_keys[2]);
    assert(ni->ni_ucastkey.wk_keytsc == 0);
    fixture_release_packet(m); fixture_assert_balanced();

    fixture_setup(&sc); ni = &peers[0]; ni->ni_ucastkey = no_key;
    sc.sc_ic.ic_def_txkey = 1; sc.sc_ic.ic_nw_keys[1] = valid_key;
    m = fixture_frame(false, true);
    assert(r23be_n80211_tx_prepare(&sc, ni, &m, true) == 0);
    assert(last_crypto_key == &sc.sc_ic.ic_nw_keys[1]);
    fixture_release_packet(m); fixture_assert_balanced();

    /* Missing/default out-of-range/unsupported and incomplete key states. */
    for (int which = 0; which < 11; which++) {
        fixture_setup(&sc); ni = &peers[0]; k = &ni->ni_ucastkey;
        m = fixture_frame(false, true);
        switch (which) {
        case 0: *k = no_key; break;
        case 1: *k = no_key; sc.sc_ic.ic_def_txkey = 4; break;
        case 2: k->wk_cipher = NULL; break;
        case 3: bad_cipher = ccmp_cipher; bad_cipher.ic_cipher = 1;
                k->wk_cipher = &bad_cipher; break;
        case 4: k->wk_flags &= ~IEEE80211_KEY_SWCRYPT; break;
        case 5: k->wk_flags &= ~IEEE80211_KEY_XMIT; break;
        case 6: k->wk_keylen = 15; break;
        case 7: k->wk_private = NULL; break;
        case 8: bad_cipher = ccmp_cipher; bad_cipher.ic_header = 9;
                k->wk_cipher = &bad_cipher; break;
        case 9: bad_cipher = ccmp_cipher; bad_cipher.ic_trailer = 7;
                k->wk_cipher = &bad_cipher; break;
        default: bad_cipher = ccmp_cipher; bad_cipher.ic_miclen = 8;
                 k->wk_cipher = &bad_cipher; break;
        }
        failed_unchanged(&sc, ni, m, true);
        assert(crypto_calls == 0);
    }
    fixture_setup(&sc); ni = &peers[0]; ni->ni_ucastkey.wk_keytsc = pn_max;
    m = fixture_frame(false, true);
    failed_unchanged(&sc, ni, m, true);
    assert(crypto_calls == 0);

    fixture_setup(&sc); ni = &peers[0]; ni->ni_ucastkey.wk_keytsc = pn_max - 1;
    m = fixture_frame(false, true);
    assert(r23be_n80211_tx_prepare(&sc, ni, &m, true) == 0);
    assert(ni->ni_ucastkey.wk_keytsc == pn_max);
    fixture_release_packet(m); fixture_assert_balanced();

    /* A cipher failure consumes a PN but must never free the original. */
    fixture_setup(&sc); ni = &peers[0]; m = fixture_frame(false, true);
    fail_crypto = true;
    failed_unchanged(&sc, ni, m, true);
    assert(crypto_calls == 1 && ni->ni_ucastkey.wk_keytsc == 1);

    /* Bad packet lengths/fragment lists cannot reach stack crypto. */
    fixture_setup(&sc); ni = &peers[0]; m = fixture_frame(false, true);
    m->m_pkthdr.len++;
    failed_unchanged(&sc, ni, m, true);
    assert(crypto_calls == 0);

    /* Same key-slot reuse is observable through the real begin/end hooks.
     * Calling them while a DMA lock is held must not dequeue/kick/purge. */
    fixture_setup(&sc);
    fixture_install_keys(&sc);
    uint64_t epoch = sc.sc_net80211.tx_key_epoch;
    mock_tx_lock = true;
    sc.sc_ic.ic_crypto.cs_key_update_begin(&sc.sc_ic);
    assert(sc.sc_net80211.tx_key_update_depth == 1);
    assert(sc.sc_net80211.tx_key_epoch != epoch);
    flags = (unsigned int)start_kicks;
    sc.sc_ic.ic_crypto.cs_key_update_end(&sc.sc_ic);
    assert(sc.sc_net80211.tx_key_update_depth == 0);
    assert((unsigned int)start_kicks == flags && enqueue_calls == 0);
    mock_tx_lock = false;
    fixture_remove_keys(&sc);
    assert(saved_begin_calls == 1 && saved_end_calls == 1);
    fixture_assert_balanced();
    puts("RTL_NET80211_TX_CRYPTO_PRODUCTION_C11_UBSAN_OK");
    return 0;
}
'''

# Behavioral mutants are added once the final production spellings are read.
MUTATIONS = [
  [
    "key->wk_keylen != 16",
    "false"
  ],
  [
    "cipher->ic_cipher != IEEE80211_CIPHER_AES_CCM",
    "false"
  ],
  [
    "key->wk_private == NULL",
    "false"
  ],
  [
    "key->wk_keytsc >= 0x0000ffffffffffffULL",
    "false"
  ],
  [
    "copy->m_data += headroom;",
    "(void)0;"
  ],
  [
    "bytes = total + headroom + trailer;",
    "bytes = total + headroom;"
  ],
  [
    "m_freem(original);",
    "(void)0;"
  ],
  [
    "used != key",
    "false"
  ],
  [
    "n->tx_key_epoch++;",
    "(void)0;"
  ],
  [
    "n->tx_key_update_depth--;",
    "(void)0;"
  ],
  [
    "n->tx_key_begin_saved(ic);",
    "(void)0;"
  ]
]
run_fixture("crypto", HARNESS, MUTATIONS)
