#!/usr/bin/env python3
"""Shared strict-C execution support for the real native TX consumer.

The boundary mocks model inspected NetBSD 11 APIs. They prove ownership and
control-flow contracts; they do not emulate NetBSD ABI/SMP/PCI or AES/CCMP.
"""
from pathlib import Path
import os
import hashlib
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MARKER = "/* Native TX queue consumer and software-CCMP ownership. */"


def production_core():
    source = (ROOT / "src/rtwn8723be_net80211.c").read_text()
    assert source.count(MARKER) == 1, "missing or ambiguous production TX core"
    return source.split(MARKER, 1)[1]


def production_function(source, name, result):
    anchor = "\n" + name + "("
    assert source.count(anchor) == 1, name
    tail = name + "(" + source.split(anchor, 1)[1]
    depth = 0
    for offset in range(tail.index("{"), len(tail)):
        if tail[offset] == "{":
            depth += 1
        elif tail[offset] == "}":
            depth -= 1
            if depth == 0:
                return result + "\n" + tail[:offset + 1]
    raise AssertionError(name)


def run_fixture(label, harness, mutations=(), extra=""):
    """Every mutant must compile and then fail a behavioral assertion."""
    original = production_core()
    net = (ROOT / "src/rtwn8723be_net80211.c").read_text()
    dp = (ROOT / "src/rtwn8723be_datapath.c").read_text()
    original += "\n" + production_function(net, "rtwn8723be_n80211_ifstop", "static int")
    original += "\n" + production_function(dp, "rtwn8723be_dp_tx_done", "static void")
    sdk = Path(os.environ.get("RTWN_NETBSD_SRC", "/usr/src"))
    crypto_path = sdk / "sys/net80211/ieee80211_crypto.c"
    assert crypto_path.is_file(), "This fixture requires inspected NetBSD target sources"
    crypto_api = production_function(crypto_path.read_text(),
                                    "ieee80211_crypto_encap",
                                    "static struct ieee80211_key *")
    # The unmodified target OS routine has a native signed/unsigned length
    # comparison. Keep that imported-code diagnostic local; our production
    # core and all boundary mocks remain compiled with every strict warning.
    crypto_api = ('#pragma GCC diagnostic push\n'
                  '#pragma GCC diagnostic ignored "-Wsign-compare"\n' +
                  crypto_api + '\n#pragma GCC diagnostic pop\n')
    print("RTL_TX_PRODUCTION_SNAPSHOT_SHA256=" +
          hashlib.sha256(original.encode()).hexdigest(), flush=True)
    print("RTL_TX_TARGET_CRYPTO_SHA256=" +
          hashlib.sha256(crypto_path.read_bytes()).hexdigest(), flush=True)
    base = Path(os.environ.get("TMPDIR", ROOT.parent /
                              "audit/net80211-tx-20261110/fixture-tmp"))
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rtl-tx-" + label + "-", dir=base) as td:
        folder = Path(td)
        def execute(core, tag, expected_pass):
            source, output = folder / (tag + ".c"), folder / tag
            source.write_text(PREAMBLE + "\n" + crypto_api + "\n" + core + "\n" + SUPPORT +
                              "\n" + extra + "\n" + harness)
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                "-I", str(ROOT / "src"), str(source), "-o", str(output),
            ], check=True)
            def no_core():
                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            try:
                result = subprocess.run([str(output)], capture_output=True,
                                        text=True, timeout=8, cwd=folder,
                                        preexec_fn=no_core)
            except subprocess.TimeoutExpired:
                if expected_pass:
                    raise
                return
            if expected_pass:
                assert result.returncode == 0, result.stdout + result.stderr
                print(result.stdout.strip())
            else:
                assert result.returncode != 0, "unsafe mutant accepted: " + tag
        execute(original, "baseline", True)
        for index, (before, after) in enumerate(mutations, 1):
            assert before in original and before != after, (index, before)
            mutant = original.replace(before, after, 1)
            assert mutant != original
            execute(mutant, "mutation" + str(index), False)
    print("RTL_NET80211_TX_" + label.upper() +
          "_PRODUCTION_MUTATIONS_OK negatives=" + str(len(mutations)))


# Filled below from the agreed production interface; no driver logic is mocked.
PREAMBLE = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <arpa/inet.h>
#include "rtwn8723be_tx_frame.h"
#define KASSERT assert
#define M_EXT 0x00000001
#define M_PKTHDR 0x00000002
#define M_EXT_RW 0x08000000
#define M_NOWAIT 1
#define MT_DATA 1
#define IFF_RUNNING 0x0040
#define IFF_OACTIVE 0x0400
#define IEEE80211_M_STA 1
#define IEEE80211_S_RUN 4
#define IEEE80211_MODE_11B 2
#define IEEE80211_MODE_11G 3
#define IEEE80211_RATE_VAL 0x7f
#define IEEE80211_RATE_BASIC 0x80
#define IEEE80211_F_USEPROT 0x00100000
#define IEEE80211_PROT_NONE 0
#define IEEE80211_PROT_CTSONLY 1
#define IEEE80211_PROT_RTSCTS 2
#define IEEE80211_CRC_LEN 4
#define IEEE80211_F_PRIVACY 0x00000010
#define IEEE80211_F_WPA2 0x01000000
#define IEEE80211_F_WPA1 0x00800000
#define IEEE80211_F_WPA (IEEE80211_F_WPA1 | IEEE80211_F_WPA2)
#define IEEE80211_F_DATAPAD 0x00080000
#define IEEE80211_FC0_TYPE_MASK 0x0c
#define IEEE80211_FC0_TYPE_MGT 0
#define IEEE80211_FC0_TYPE_DATA 8
#define IEEE80211_FC0_VERSION_MASK 3
#define IEEE80211_FC0_VERSION_0 0
#define IEEE80211_FC1_MORE_FRAG 4
#define IEEE80211_FC1_WEP 0x40
#define IEEE80211_SEQ_FRAG_MASK 0x0f
#define IEEE80211_ADDR_LEN 6
#define IEEE80211_KEY_XMIT 1
#define IEEE80211_KEY_SWCRYPT 0x10
#define IEEE80211_CIPHER_AES_CCM 3
#define IEEE80211_WEP_NKID 4
#define IEEE80211_KEYIX_NONE 0xffff
#define ETHERTYPE_PAE 0x888e
#define BPF_D_OUT 1
#define R23BE_STAGE_RUNNING 43
#define R23BE_STAGE_STOPPED 45
#define RTWN8723BE_RX_BUFFER_SIZE 9100
#define RTWN8723BE_TX_QUEUE_COUNT 9
#define IEEE80211_ADDR_COPY(a,b) memcpy((a),(b),6)
#define IEEE80211_ADDR_EQ(a,b) (memcmp((a),(b),6) == 0)
#define IEEE80211_IS_MULTICAST(a) (((a)[0] & 1) != 0)
struct ieee80211_channel { uint16_t ic_freq; uint16_t ic_flags; };
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel *)(uintptr_t)0xffff)
#define IEEE80211_IS_CHAN_2GHZ(c) (((c)->ic_flags & 0x80) != 0)
struct ieee80211_frame {
    uint8_t i_fc[2], i_dur[2], i_addr1[6], i_addr2[6], i_addr3[6], i_seq[2];
};
struct ether_header { uint8_t ether_dhost[6], ether_shost[6]; uint16_t ether_type; };
struct ieee80211_key;
struct mbuf;
struct ieee80211_cipher {
    unsigned ic_cipher, ic_header, ic_trailer, ic_miclen;
    int (*ic_encap)(struct ieee80211_key *, struct mbuf *, uint8_t);
};
struct ieee80211_key {
    uint8_t wk_keylen;
    unsigned wk_flags;
    uint64_t wk_keytsc;
    const struct ieee80211_cipher *wk_cipher;
    void *wk_private;
};
struct ieee80211_rateset { uint8_t rs_nrates, rs_rates[15]; };
struct ieee80211_node {
    int refs;
    uint8_t ni_bssid[6];
    int ni_txrate;
    struct ieee80211_rateset ni_rates;
    struct ieee80211_key ni_ucastkey;
};
struct mbuf {
    int m_flags, m_len;
    struct { int len; void *ctx; } m_pkthdr;
    struct mbuf *m_next, *m_nextpkt;
    char *m_data;
    struct { char *ext_buf; size_t ext_size; } m_ext;
    bool alive, readonly;
    unsigned id;
    char storage[9400];
};
struct ifqueue { struct mbuf *head, *tail; };
struct ifnet {
    void *if_softc;
    unsigned if_flags;
    int if_timer;
    unsigned if_oerrors, if_opackets;
    void (*if_start)(struct ifnet *);
    struct ifqueue if_snd;
};
struct ethercom { struct ifnet ec_if; };
struct ieee80211com;
struct ieee80211_crypto_state {
    void (*cs_key_update_begin)(struct ieee80211com *);
    void (*cs_key_update_end)(struct ieee80211com *);
};
struct ieee80211com {
    struct ifnet *ic_ifp;
    int ic_opmode, ic_state, ic_curmode, ic_fixed_rate;
    unsigned ic_flags;
    uint16_t ic_rtsthreshold;
    int ic_protmode;
    struct ieee80211_channel *ic_curchan;
    struct ieee80211_rateset ic_sup_rates[8];
    struct ieee80211_node *ic_bss;
    uint16_t ic_def_txkey;
    struct ieee80211_key ic_nw_keys[4];
    struct ieee80211_crypto_state ic_crypto;
    struct { unsigned is_tx_nodefkey; } ic_stats;
    struct ifqueue ic_mgtq;
    void *ic_rawbpf;
};
#include "rtwn8723be_net80211.h"
struct rtwn8723be_linux_state {
    int stage;
    bool started, fw_ready, mac_func_enable, being_init_adapter;
};
typedef struct { bool held; } kmutex_t;
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    bool ready, prepared, tx_enabled;
    kmutex_t tx_lock;
    unsigned tx_callback_active;
    int tx_error;
    size_t tx_reclaimed;
    void (*tx_complete)(void *, unsigned int, size_t);
    void *tx_complete_arg;
};
struct rtwn8723be_softc {
    struct ethercom sc_ec;
    struct ieee80211com sc_ic;
    struct rtwn8723be_net80211 sc_net80211;
    struct rtwn8723be_datapath *sc_datapath;
    struct rtwn8723be_linux_state sc_linux;
    bool sc_sw_crypto, sc_use_sw_sec, sc_security_policy_valid;
    bool sc_hw_security_enabled;
    void *sc_irq_arg;
};
static struct mbuf pool[96], *dma_m[32];
static struct ieee80211_node peers[4], *dma_ni[32];
static struct rtwn8723be_datapath fixture_dp;
static struct ieee80211_channel channels[2];
static int mock_ccmp_encap(struct ieee80211_key *, struct mbuf *, uint8_t);
static const struct ieee80211_cipher ieee80211_cipher_none = {.ic_cipher=6};
static struct ieee80211_cipher ccmp_cipher = {3,8,8,0,mock_ccmp_encap}, bad_cipher;
static struct ieee80211_key valid_key, no_key;
static struct ieee80211_key *last_crypto_key;
static struct mbuf *last_crypto_m;
static int prepend_allocations, append_allocations;
static unsigned pool_used, dma_count;
static int alloc_calls, ext_calls, fail_alloc, fail_ext, crypto_calls;
static int enqueue_calls, find_calls, encap_calls, pullup_calls, raw_taps;
static int start_kicks, saved_begin_calls, saved_end_calls, net_depth;
static int fail_find, fail_encap, fail_pullup, enqueue_result;
static int completion_in_enqueue, rekey_in_encap, fragment_encap;
static int force_clear_encap, privacy_in_find, raw_bpf_hook, encap_format;
static unsigned busy_call_mask, completion_call_mask;
static int busy_budget, hw_stop_result, hw_stop_false_success, hw_stop_calls;
static bool fail_crypto, mock_tx_lock;
static int reclaim_calls, reclaim_error, reclaim_count, notify_calls;
static bool key_delete_in_reclaim, expect_callback_lease;
static struct rtwn8723be_tx_params last_rate;
static char handoff_types[32];
static void rtwn8723be_dp_tx_done(void *, unsigned int);
static int rtwn8723be_n80211_ifstop(struct rtwn8723be_net80211 *);
static void fixture_setup(struct rtwn8723be_softc *);
static void fixture_install_keys(struct rtwn8723be_softc *);
static void fixture_remove_keys(struct rtwn8723be_softc *);
static void fixture_assert_balanced(void);
static void fixture_release_packet(struct mbuf *);
static struct mbuf *fixture_frame(bool, bool);
static void fixture_split_frame(struct mbuf *, int);
static void fixture_dma_complete(void);
static void fixture_queue(struct ifqueue *, struct mbuf *);
static struct mbuf *fixture_ether(bool);
static void *checked_data(struct mbuf *m)
{ assert(m != NULL && m->alive); return m->m_data; }
#define mtod(m,t) ((t)checked_data(m))
#define M_READONLY(m) ((m)->readonly)
#define M_LEADINGSPACE(m) ((m)->m_data - (m)->m_ext.ext_buf)
#define M_TRAILINGSPACE(m) ((int)((m)->m_ext.ext_buf + (m)->m_ext.ext_size - \
                                  ((m)->m_data + (m)->m_len)))
#define M_GETCTX(m,t) ((t)(m)->m_pkthdr.ctx)
#define M_CLEARCTX(m) ((m)->m_pkthdr.ctx = NULL)
#define if_statinc(ifp,which) ((ifp)->which++)
static struct mbuf *m_gethdr(int how, int type)
{
    assert(how == M_NOWAIT && type == MT_DATA && !mock_tx_lock);
    alloc_calls++;
    if (alloc_calls == fail_alloc) return NULL;
    assert(pool_used < 96);
    struct mbuf *m = &pool[pool_used++];
    memset(m, 0, sizeof(*m));
    m->alive = true; m->id = pool_used; m->m_flags = M_PKTHDR;
    m->m_data = m->storage; m->m_ext.ext_buf = m->storage;
    m->m_ext.ext_size = sizeof(m->storage);
    return m;
}
static void mock_extmalloc(struct mbuf *m, size_t bytes, int how)
{
    assert(m->alive && how == M_NOWAIT && bytes <= sizeof(m->storage));
    ext_calls++;
    if (ext_calls == fail_ext) return;
    m->m_flags |= M_EXT | M_EXT_RW;
    m->m_data = m->storage; m->m_ext.ext_buf = m->storage;
    m->m_ext.ext_size = bytes;
}
#define MEXTMALLOC(m,bytes,how) mock_extmalloc((m),(bytes),(how))
static void m_freem(struct mbuf *m)
{
    while (m != NULL) {
        assert(m->alive);
        /* A management context must be detached before normal owner release. */
        assert(m->m_pkthdr.ctx == NULL);
        struct mbuf *next = m->m_next;
        m->alive = false; m->m_data = NULL; m->m_next = NULL;
        m = next;
    }
}
static void m_copydata(struct mbuf *m, int offset, int len, void *out)
{
    assert(offset >= 0 && len >= 0);
    char *dst = out;
    while (m != NULL && offset >= m->m_len) {
        assert(m->alive); offset -= m->m_len; m = m->m_next;
    }
    while (len != 0) {
        assert(m != NULL && m->alive && offset <= m->m_len);
        int n = m->m_len - offset;
        if (n > len) n = len;
        memcpy(dst, m->m_data + offset, (size_t)n);
        dst += n; len -= n; offset = 0; m = m->m_next;
    }
}
static void ieee80211_free_node(struct ieee80211_node *ni)
{ assert(ni != NULL && ni->refs > 1); ni->refs--; }
static void dequeue(struct ifqueue *q, struct mbuf **mp)
{
    *mp = q->head;
    if (*mp != NULL) {
        assert((*mp)->alive);
        q->head = (*mp)->m_nextpkt;
        (*mp)->m_nextpkt = NULL;
        if (q->head == NULL) q->tail = NULL;
    }
}
#define IF_DEQUEUE(q,m) dequeue((q),&(m))
#define IFQ_DEQUEUE(q,m) dequeue((q),&(m))
static int splnet(void)
{ assert(!mock_tx_lock); return net_depth++; }
static void splx(int previous)
{ assert(net_depth == previous + 1); net_depth--; }
static bool rtwn8723be_datapath_running_ready(struct rtwn8723be_datapath *dp)
{ assert(!mock_tx_lock); return dp != NULL && dp->ready; }
static int ieee80211_chan2ieee(struct ieee80211com *ic,
    struct ieee80211_channel *c)
{ (void)ic; return c->ic_freq == 2484 ? 14 : 1; }
static int ieee80211_hdrspace(struct ieee80211com *ic, const void *v)
{
    (void)ic;
    const struct ieee80211_frame *wh = v;
    return (wh->i_fc[0] & 0x80) != 0 ? 26 : 24;
}

#define IEEE80211_DPRINTF(...) ((void)0)
static struct mbuf *m_prepend(struct mbuf *m, int bytes, int how)
{
    prepend_allocations++;
    struct mbuf *head = m_gethdr(how, MT_DATA);
    if (head == NULL) { m_freem(m); return NULL; }
    head->m_len = bytes; head->m_pkthdr = m->m_pkthdr;
    m->m_pkthdr.ctx = NULL; m->m_flags &= ~M_PKTHDR;
    head->m_next = m;
    return head;
}
#define M_PREPEND(m,bytes,how) do { \
    if (M_LEADINGSPACE(m) >= (bytes)) { \
        (m)->m_data -= (bytes); (m)->m_len += (bytes); \
    } else (m) = m_prepend((m),(bytes),(how)); \
    if ((m) != NULL && ((m)->m_flags & M_PKTHDR)) \
        (m)->m_pkthdr.len += (bytes); \
} while (0)
static int m_append(struct mbuf *m, int bytes, const void *buf)
{
    if (fail_crypto) return 0;
    struct mbuf *last = m;
    while (last->m_next) last = last->m_next;
    if (M_TRAILINGSPACE(last) < bytes) {
        append_allocations++;
        struct mbuf *tail = m_gethdr(M_NOWAIT, MT_DATA);
        if (tail == NULL) return 0;
        tail->m_flags &= ~M_PKTHDR; last->m_next = tail; last = tail;
    }
    memcpy(last->m_data + last->m_len, buf, (size_t)bytes);
    last->m_len += bytes; m->m_pkthdr.len += bytes;
    return 1;
}
static int mock_ccmp_encap(struct ieee80211_key *k, struct mbuf *m, uint8_t keyid)
{
    (void)keyid;
    assert(k && m->alive && !M_READONLY(m) && m->m_next == NULL);
    assert(m->m_len == m->m_pkthdr.len);
    assert(k->wk_cipher->ic_cipher == IEEE80211_CIPHER_AES_CCM);
    assert(k->wk_flags & IEEE80211_KEY_SWCRYPT);
    crypto_calls++; last_crypto_key = k; last_crypto_m = m;
    k->wk_keytsc++;
    struct ieee80211_frame *wh = mtod(m, struct ieee80211_frame *);
    int hdrlen = (wh->i_fc[0] & 0x80) ? 26 : 24;
    m->m_data[hdrlen] = (char)k->wk_keytsc;
    const uint8_t mic[8] = {0xa5,0xa5,0xa5,0xa5,0xa5,0xa5,0xa5,0xa5};
    return m_append(m, 8, mic);
}
static struct ieee80211_node *ieee80211_find_txnode(
    struct ieee80211com *ic, const uint8_t *dest)
{
    (void)dest; find_calls++;
    if (fail_find) return NULL;
    if (privacy_in_find) ic->ic_flags |= IEEE80211_F_PRIVACY;
    assert(ic->ic_bss); ic->ic_bss->refs++;
    return ic->ic_bss;
}
static void bpf_mtap(struct ifnet *ifp, struct mbuf *m, int direction)
{ assert(ifp && m->alive && direction == BPF_D_OUT && !mock_tx_lock); }
static void bpf_mtap3(void *bpf, struct mbuf *m, int direction)
{
    assert(m->alive && direction == BPF_D_OUT && !mock_tx_lock); raw_taps++;
    struct rtwn8723be_softc *sc = bpf;
    if (raw_bpf_hook == 1) sc->sc_ic.ic_fixed_rate = 0;
    else if (raw_bpf_hook == 2) {
        sc->sc_ic.ic_flags |= IEEE80211_F_USEPROT;
        sc->sc_ic.ic_protmode = IEEE80211_PROT_CTSONLY;
    } else if (raw_bpf_hook == 3) sc->sc_ic.ic_rtsthreshold = (uint16_t)(m->m_pkthdr.len + 3);
    else if (raw_bpf_hook == 4) sc->sc_ic.ic_curchan = &channels[1];
    else if (raw_bpf_hook == 5) sc->sc_ic.ic_flags ^= IEEE80211_F_PRIVACY;
}
static struct mbuf *m_pullup(struct mbuf *m, int bytes)
{
    pullup_calls++; assert(m->alive && bytes >= 14);
    if (fail_pullup) { m_freem(m); return NULL; }
    struct mbuf *copy = m_gethdr(M_NOWAIT, MT_DATA);
    assert(copy != NULL);
    copy->m_len = copy->m_pkthdr.len = m->m_pkthdr.len;
    m_copydata(m, 0, m->m_pkthdr.len, copy->m_data);
    m_freem(m); return copy;
}
static struct mbuf *ieee80211_encap(
    struct ieee80211com *ic, struct mbuf *m, struct ieee80211_node *ni)
{
    encap_calls++;
    assert(m->alive && ni->refs > 1 && m->m_len >= 14 && !mock_tx_lock);
    struct ether_header eh;
    memcpy(&eh, m->m_data, sizeof(eh));
    m_freem(m);
    if (fail_encap) return NULL;
    bool key_present = ni->ni_ucastkey.wk_cipher != &ieee80211_cipher_none;
    bool protected_frame = (ic->ic_flags & IEEE80211_F_PRIVACY) != 0 &&
        (eh.ether_type != htons(ETHERTYPE_PAE) || key_present);
    if (force_clear_encap) protected_frame = false;
    struct mbuf *copy = fixture_frame(false, protected_frame);
    memcpy(mtod(copy, struct ieee80211_frame *)->i_addr1, ni->ni_bssid, 6);
    if (encap_format == 1) mtod(copy, struct ieee80211_frame *)->i_fc[0] = 0x48;
    else if (encap_format == 2) mtod(copy, struct ieee80211_frame *)->i_fc[1] |= 3;
    else if (encap_format == 3) mtod(copy, struct ieee80211_frame *)->i_fc[1] |= 4;
    if (fragment_encap) copy->m_nextpkt = fixture_frame(false, protected_frame);
    if (rekey_in_encap) {
        ic->ic_crypto.cs_key_update_begin(ic);
        ni->ni_ucastkey = valid_key;
        ic->ic_crypto.cs_key_update_end(ic);
    }
    return copy;
}
static void if_start_lock(struct ifnet *ifp)
{
    assert(!mock_tx_lock && ifp->if_start != NULL);
    if (expect_callback_lease) assert(fixture_dp.tx_callback_active == 1);
    start_kicks++; ifp->if_start(ifp);
}
static int rtwn8723be_datapath_enqueue_80211(
    struct rtwn8723be_datapath *dp, struct mbuf *m, struct ieee80211_node *ni,
    bool crypto_complete, const struct rtwn8723be_tx_params *p)
{
    assert(!mock_tx_lock && dp && dp->ready && m->alive && ni->refs > 1);
    assert(crypto_complete && p->security == 0 && m->m_next == NULL);
    struct rtwn8723be_tx_frame_plan plan;
    int plan_error = rtwn8723be_tx_frame_plan((const uint8_t *)m->m_data,
        (size_t)m->m_pkthdr.len, crypto_complete, &plan);
    if (plan_error != 0) return plan_error;
    enqueue_calls++; last_rate = *p;
    unsigned call_bit = enqueue_calls <= 32 ? 1U << (enqueue_calls - 1) : 0;
    if ((completion_call_mask & call_bit) != 0)
        rtwn8723be_net80211_tx_complete(&dp->sc->sc_net80211, 1, 1);
    if (completion_in_enqueue) {
        completion_in_enqueue--;
        rtwn8723be_net80211_tx_complete(&dp->sc->sc_net80211, 1, 1);
    }
    if ((busy_call_mask & call_bit) != 0) return EBUSY;
    if (busy_budget != 0) { busy_budget--; return EBUSY; }
    if (enqueue_result != 0) return enqueue_result;
    assert(dma_count < 32);
    handoff_types[dma_count] = (char)(mtod(m, struct ieee80211_frame *)->i_fc[0] & 12);
    dma_m[dma_count] = m; dma_ni[dma_count] = ni; dma_count++;
    return 0;
}
static bool rtwn8723be_net80211_unstarted_detach_allowed(
    const struct rtwn8723be_linux_state *state)
{ return !state->started && !state->fw_ready && !state->being_init_adapter; }
static int fixture_hw_stop(struct rtwn8723be_softc *sc)
{
    hw_stop_calls++;
    if (hw_stop_result != 0) return hw_stop_result;
    if (!hw_stop_false_success) {
        sc->sc_linux.stage = R23BE_STAGE_STOPPED;
        sc->sc_linux.started = false; sc->sc_linux.fw_ready = false;
        sc->sc_linux.mac_func_enable = false; sc->sc_linux.being_init_adapter = false;
        sc->sc_datapath->ready = false;
    }
    return 0;
}

static void mutex_enter(kmutex_t *lock)
{ assert(!lock->held && !mock_tx_lock); lock->held = mock_tx_lock = true; }
static void mutex_exit(kmutex_t *lock)
{ assert(lock->held && mock_tx_lock); lock->held = mock_tx_lock = false; }
static int rtwn8723be_tx_native_reclaim(
    struct rtwn8723be_softc *sc, unsigned int qid, size_t *count)
{
    assert(mock_tx_lock && qid < RTWN8723BE_TX_QUEUE_COUNT);
    reclaim_calls++; *count = 0;
    if (reclaim_error) return reclaim_error;
    if (key_delete_in_reclaim) {
        sc->sc_ic.ic_crypto.cs_key_update_begin(&sc->sc_ic);
        sc->sc_ic.ic_crypto.cs_key_update_end(&sc->sc_ic);
    }
    if (reclaim_count && dma_count) {
        struct mbuf *m = dma_m[0];
        struct ieee80211_node *ni = dma_ni[0];
        m_freem(m); ieee80211_free_node(ni);
        for (unsigned j = 1; j < dma_count; j++) {
            dma_m[j-1] = dma_m[j]; dma_ni[j-1] = dma_ni[j];
        }
        dma_count--; *count = 1;
    }
    return 0;
}
"""
SUPPORT = r"""
static void saved_begin(struct ieee80211com *ic)
{ assert(ic != NULL); saved_begin_calls++; }
static void saved_end(struct ieee80211com *ic)
{ assert(ic != NULL); saved_end_calls++; }
static void fixture_if_start(struct ifnet *ifp)
{
    struct rtwn8723be_net80211 *n = ifp->if_softc;
    assert(n && n->sc);
    rtwn8723be_net80211_tx_start(n->sc, ifp);
}
static void fixture_notify(void *arg, unsigned int qid, size_t count)
{
    assert(arg == &fixture_dp && qid < RTWN8723BE_TX_QUEUE_COUNT && count != 0);
    assert(!mock_tx_lock && fixture_dp.tx_callback_active == 1);
    notify_calls++;
}
static void fixture_setup(struct rtwn8723be_softc *sc)
{
    for (unsigned i = 0; i < pool_used; i++) assert(!pool[i].alive);
    memset(pool, 0, sizeof(pool)); memset(peers, 0, sizeof(peers));
    memset(sc, 0, sizeof(*sc)); memset(&fixture_dp, 0, sizeof(fixture_dp));
    memset(dma_m, 0, sizeof(dma_m)); memset(dma_ni, 0, sizeof(dma_ni));
    pool_used = dma_count = 0;
    alloc_calls = ext_calls = fail_alloc = fail_ext = crypto_calls = 0;
    enqueue_calls = find_calls = encap_calls = pullup_calls = raw_taps = 0;
    start_kicks = saved_begin_calls = saved_end_calls = net_depth = 0;
    fail_find = fail_encap = fail_pullup = enqueue_result = 0;
    completion_in_enqueue = rekey_in_encap = fragment_encap = 0;
    force_clear_encap = privacy_in_find = raw_bpf_hook = encap_format = 0;
    busy_call_mask = completion_call_mask = 0;
    busy_budget = hw_stop_result = hw_stop_false_success = hw_stop_calls = 0;
    reclaim_calls = reclaim_error = notify_calls = 0; reclaim_count = 1;
    fail_crypto = mock_tx_lock = key_delete_in_reclaim = expect_callback_lease = false;
    last_crypto_key = NULL; last_crypto_m = NULL;
    prepend_allocations = append_allocations = 0;
    ccmp_cipher = (struct ieee80211_cipher){3,8,8,0,mock_ccmp_encap};
    bad_cipher = ccmp_cipher;
    valid_key = (struct ieee80211_key){
        .wk_keylen=16, .wk_flags=IEEE80211_KEY_XMIT|IEEE80211_KEY_SWCRYPT,
        .wk_cipher=&ccmp_cipher, .wk_private=&fixture_dp
    };
    no_key = (struct ieee80211_key){.wk_cipher=&ieee80211_cipher_none};
    channels[0] = (struct ieee80211_channel){2412,0x0480};
    channels[1] = (struct ieee80211_channel){2437,0x0480};
    const uint8_t rates[] = {0x82,0x84,0x8b,0x96,0x8c,18,0x98,36,0xb0,72,96,108};
    for (unsigned i = 0; i < 4; i++) {
        peers[i].refs = 1; peers[i].ni_bssid[0] = 2;
        peers[i].ni_bssid[5] = (uint8_t)(i+1);
        peers[i].ni_txrate = 11;
        peers[i].ni_rates.rs_nrates = 12;
        memcpy(peers[i].ni_rates.rs_rates, rates, sizeof(rates));
        peers[i].ni_ucastkey = valid_key;
        sc->sc_ic.ic_nw_keys[i] = no_key;
    }
    sc->sc_sw_crypto = sc->sc_use_sw_sec = sc->sc_security_policy_valid = true;
    sc->sc_linux = (struct rtwn8723be_linux_state){
        .stage=R23BE_STAGE_RUNNING, .started=true, .fw_ready=true
    };
    sc->sc_ic.ic_opmode = IEEE80211_M_STA;
    sc->sc_ic.ic_state = IEEE80211_S_RUN;
    sc->sc_ic.ic_curmode = IEEE80211_MODE_11G;
    sc->sc_ic.ic_fixed_rate = -1;
    sc->sc_ic.ic_rtsthreshold = 2347;
    sc->sc_ic.ic_flags = IEEE80211_F_PRIVACY | IEEE80211_F_WPA2;
    sc->sc_ic.ic_curchan = &channels[0]; sc->sc_ic.ic_bss = &peers[0];
    sc->sc_ic.ic_def_txkey = IEEE80211_KEYIX_NONE;
    sc->sc_ic.ic_ifp = &sc->sc_ec.ec_if;
    sc->sc_ic.ic_rawbpf = sc;
    sc->sc_ic.ic_sup_rates[IEEE80211_MODE_11G] = peers[0].ni_rates;
    sc->sc_ic.ic_sup_rates[IEEE80211_MODE_11B] = peers[0].ni_rates;
    sc->sc_ic.ic_crypto.cs_key_update_begin = saved_begin;
    sc->sc_ic.ic_crypto.cs_key_update_end = saved_end;
    sc->sc_ec.ec_if.if_flags = IFF_RUNNING;
    sc->sc_ec.ec_if.if_softc = &sc->sc_net80211;
    sc->sc_ec.ec_if.if_start = fixture_if_start;
    sc->sc_net80211.sc = sc; sc->sc_net80211.registered = true;
    sc->sc_net80211.methods.tx_start = rtwn8723be_net80211_tx_start;
    sc->sc_net80211.methods.hw_stop = fixture_hw_stop;
    fixture_dp.sc = sc; fixture_dp.ready = fixture_dp.prepared = true;
    fixture_dp.tx_enabled = true;
    sc->sc_datapath = &fixture_dp; sc->sc_irq_arg = &fixture_dp;
    rtwn8723be_n80211_tx_install(&sc->sc_net80211);
}
static void fixture_install_keys(struct rtwn8723be_softc *sc)
{
    if (sc->sc_ic.ic_crypto.cs_key_update_begin != r23be_n80211_tx_key_begin)
        rtwn8723be_n80211_tx_install(&sc->sc_net80211);
}
static void fixture_remove_keys(struct rtwn8723be_softc *sc)
{ assert(rtwn8723be_n80211_tx_remove(&sc->sc_net80211) == 0); }
static struct mbuf *fixture_frame(bool group, bool protected_frame)
{
    struct mbuf *m = m_gethdr(M_NOWAIT, MT_DATA);
    assert(m != NULL); m->m_len = m->m_pkthdr.len = 34;
    struct ieee80211_frame *wh = mtod(m, struct ieee80211_frame *);
    wh->i_fc[0] = IEEE80211_FC0_TYPE_DATA;
    wh->i_fc[1] = protected_frame ? IEEE80211_FC1_WEP : 0;
    memcpy(wh->i_addr1, peers[0].ni_bssid, 6);
    if (group) wh->i_addr1[0] |= 1;
    wh->i_seq[0] = 0x30; wh->i_seq[1] = 0x12;
    return m;
}
static void fixture_split_frame(struct mbuf *m, int cut)
{
    assert(cut > 0 && cut < m->m_len && m->m_next == NULL);
    struct mbuf *tail = m_gethdr(M_NOWAIT, MT_DATA);
    assert(tail);
    tail->m_flags = 0; tail->m_len = m->m_len-cut;
    memcpy(tail->m_data, m->m_data+cut, (size_t)tail->m_len);
    m->m_next = tail; m->m_len = cut;
}
static void fixture_release_packet(struct mbuf *m)
{ r23be_n80211_tx_free_frames(m); }
static void fixture_dma_complete(void)
{
    for (unsigned i = 0; i < dma_count; i++) {
        m_freem(dma_m[i]); ieee80211_free_node(dma_ni[i]);
    }
    dma_count = 0;
}
static void fixture_assert_balanced(void)
{
    assert(dma_count == 0 && !mock_tx_lock && net_depth == 0);
    for (unsigned i = 0; i < pool_used; i++) assert(!pool[i].alive);
    for (unsigned i = 0; i < 4; i++) assert(peers[i].refs == 1);
    /* Touch API helpers in both binaries; real behavior is covered below. */
    (void)fixture_install_keys; (void)fixture_remove_keys; (void)fixture_notify;
    (void)fixture_split_frame; (void)fixture_dma_complete;
    (void)fixture_queue; (void)fixture_ether;
    (void)rtwn8723be_dp_tx_done; (void)rtwn8723be_n80211_ifstop;
}
static void fixture_queue(struct ifqueue *q, struct mbuf *m)
{
    assert(m && m->alive && m->m_nextpkt == NULL);
    if (q->tail != NULL) q->tail->m_nextpkt = m; else q->head = m;
    q->tail = m;
}
static struct mbuf *fixture_ether(bool pae)
{
    struct mbuf *m = m_gethdr(M_NOWAIT, MT_DATA);
    assert(m); m->m_len = m->m_pkthdr.len = 24;
    struct ether_header *eh = mtod(m, struct ether_header *);
    memcpy(eh->ether_dhost, peers[0].ni_bssid, 6);
    eh->ether_type = htons(pae ? ETHERTYPE_PAE : 0x0800);
    return m;
}
"""
