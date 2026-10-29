#!/usr/bin/env python3
"""C11/UBSan execution: real 802.11 frame classifier and native TX bridge.

No full NetBSD PCI DMA, net80211 queue consumer, WPA key setup or hardware
TX is claimed. Caller retains mbuf/node on error; DMA slot owns both
only on successful lower-layer handoff.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
DP=(ROOT/"src/rtwn8723be_datapath.c").read_text()
FRAME=(ROOT/"src/rtwn8723be_tx_frame.h").read_text()
HDR=(ROOT/"src/rtwn8723be_datapath.h").read_text()

def body(src,name):
    key="\n"+name+"("
    assert src.count(key)==1, name
    rest=name+"("+src.split(key,1)[1]
    depth=0
    for i in range(rest.index("{"),len(rest)):
        if rest[i]=="{":depth+=1
        elif rest[i]=="}":
            depth-=1
            if depth==0:return rest[:i+1]
    raise AssertionError(name)

WRAP=body(DP,"rtwn8723be_datapath_enqueue_80211")
assert "rtwn8723be_datapath_enqueue_80211(" in HDR
required=(
    "m == NULL || ni == NULL || rate == NULL",
    "!dp->sc->sc_sw_crypto || !dp->sc->sc_security_policy_valid",
    "rate->security != 0", "m->m_next != NULL",
    "m->m_len != m->m_pkthdr.len",
    "rtwn8723be_tx_frame_plan(",
    "params.packet_len = (uint16_t)m->m_pkthdr.len;",
    "params.fw_queue = plan.fw_queue;",
    "params.seq = plan.seq;",
    "params.qos_data = plan.qos_data;",
    "params.multicast = plan.multicast;",
    "params.security = 0;",
    "params.first_segment = true;",
    "params.last_segment = true;",
    "params.ampdu = false;",
    "params.rdg = false;",
    "rtwn8723be_datapath_enqueue(dp, qid, m, ni, &params, false);",
)
for token in required:
    assert token in WRAP, token
assert WRAP.index("rtwn8723be_tx_frame_plan(") < WRAP.index(
    "rtwn8723be_datapath_enqueue(dp, qid,")
assert "ieee80211_free_node(" not in WRAP and "m_freem(" not in WRAP
assert '#include "rtwn8723be_tx_frame.h"' in DP
assert FRAME.count("tid == 1 || tid == 2")==1
assert FRAME.count("tid == 4 || tid == 5")==1
assert FRAME.count("tid == 6 || tid == 7")==1

mutants=(
    WRAP.replace("rate->security != 0","false",1),
    WRAP.replace("m->m_next != NULL","false",1),
    WRAP.replace("params.seq = plan.seq;","",1),
    WRAP.replace("params.fw_queue = plan.fw_queue;","",1),
    WRAP.replace("params.security = 0;","",1),
    WRAP.replace("params.ampdu = false;","",1),
    WRAP.replace("params.first_segment = true;","",1),
    WRAP.replace("params.multicast = plan.multicast;","",1),
)
for i,mutant in enumerate(mutants,1):
    assert mutant!=WRAP,i
    try:
        for token in required: assert token in mutant
    except AssertionError:continue
    raise AssertionError(f"unsafe net80211 TX submission mutation {i} accepted")

prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
#include "rtwn8723be_tx_frame.h"
#define M_PKTHDR 1
#define RTWN8723BE_BK_QUEUE 0
#define RTWN8723BE_BE_QUEUE 1
#define RTWN8723BE_VI_QUEUE 2
#define RTWN8723BE_VO_QUEUE 3
#define RTWN8723BE_MGNT_QUEUE 6
#define mtod(m,t) ((t)((m)->bytes))
struct ieee80211_node { int alive; };
struct mbuf {
    int m_flags, m_len;
    struct mbuf *m_next;
    struct { int len; } m_pkthdr;
    uint8_t bytes[128];
};
struct rtwn8723be_softc {
    bool sc_sw_crypto, sc_security_policy_valid;
};
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    bool prepared;
};
static int called, result, last_qid;
static struct rtwn8723be_tx_params last;
static struct mbuf *last_m;
static struct ieee80211_node *last_ni;
static int rtwn8723be_datapath_enqueue(struct rtwn8723be_datapath *dp,
    unsigned int qid,struct mbuf *m,struct ieee80211_node *ni,
    const struct rtwn8723be_tx_params *p,bool command)
{
    assert(dp && dp->prepared && m && ni && ni->alive && p && !command);
    called++;
    last_qid=(int)qid;last=*p;last_m=m;last_ni=ni;
    return result;
}
'''
tail=r'''
static void setup(struct rtwn8723be_softc *sc,
    struct rtwn8723be_datapath *dp,struct mbuf *m,
    struct rtwn8723be_tx_params *p)
{
    *sc=(struct rtwn8723be_softc){.sc_sw_crypto=true,
        .sc_security_policy_valid=true};
    *dp=(struct rtwn8723be_datapath){.sc=sc,.prepared=true};
    *m=(struct mbuf){.m_flags=M_PKTHDR,.m_len=38,.m_pkthdr.len=38};
    m->bytes[0]=0x08; /* Unicast non-QoS data */
    m->bytes[22]=0x30;m->bytes[23]=0x12;
    *p=(struct rtwn8723be_tx_params){.hw_rate=11,
        .rateid=3,.macid=0,.security=0};
    called=0;result=0;last_qid=-1;
    last_m=NULL;last_ni=NULL;
}
static void eq(unsigned int q,unsigned int fw, unsigned seq,bool qos)
{
    assert(called==1 && last_qid==(int)q && last.fw_queue==fw);
    assert(last.seq==seq && last.qos_data==qos);
    assert(last.first_segment && last.last_segment);
    assert(last.security==0 && !last.ampdu && !last.rdg);
    assert(last.buffer_len==38 && last.packet_len==38);
}
int main(void)
{
    struct rtwn8723be_softc sc;
    struct rtwn8723be_datapath dp;
    struct mbuf m;
    struct ieee80211_node ni={.alive=1};
    struct rtwn8723be_tx_params p;
    setup(&sc,&dp,&m,&p);
    assert(rtwn8723be_datapath_enqueue_80211(&dp,&m,&ni,false,&p)==0);
    eq(1,0,0x123,false);
    assert(last.hw_rate==11 && last_m==&m && last_ni==&ni);

    setup(&sc,&dp,&m,&p);
    m.bytes[0]=0x00; /* Management over MGNT queue, forced CCK1. */
    assert(rtwn8723be_datapath_enqueue_80211(&dp,&m,&ni,false,&p)==0);
    eq(6,18,0x123,false);
    assert(last.hw_rate==0 && last.use_driver_rate &&
        last.disable_rate_fallback);

    setup(&sc,&dp,&m,&p);
    m.bytes[4]=1; /* Multicast data forced CCK1, BE queue. */
    assert(rtwn8723be_datapath_enqueue_80211(&dp,&m,&ni,false,&p)==0);
    eq(1,0,0x123,false);
    assert(last.multicast && last.hw_rate==0 && last.use_driver_rate);

    const unsigned tid[]={0,1,2,3,4,5,6,7};
    const int qid[]={1,0,0,1,2,2,3,3};
    const int fw[]={0,2,2,0,5,5,7,7};
    for (unsigned i=0;i<8;i++) {
        setup(&sc,&dp,&m,&p);
        m.bytes[0]=0x88; /* QoS data, 3-address */
        m.bytes[24]=(uint8_t)tid[i];
        assert(rtwn8723be_datapath_enqueue_80211(
            &dp,&m,&ni,false,&p)==0);
        eq((unsigned)qid[i],(unsigned)fw[i],0x123,true);
    }

    setup(&sc,&dp,&m,&p);
    m.bytes[1]=0x40; /* WPA protected frame, not encrypted yet. */
    assert(rtwn8723be_datapath_enqueue_80211(
        &dp,&m,&ni,false,&p)==EACCES);
    assert(called==0 && ni.alive);
    assert(rtwn8723be_datapath_enqueue_80211(
        &dp,&m,&ni,true,&p)==0 && last.security==0);

    setup(&sc,&dp,&m,&p);
    p.security=3; /* Driver HW CAM offload deliberately forbidden. */
    assert(rtwn8723be_datapath_enqueue_80211(
        &dp,&m,&ni,true,&p)==EACCES && called==0);
    p.security=0;
    sc.sc_security_policy_valid=false;
    assert(rtwn8723be_datapath_enqueue_80211(
        &dp,&m,&ni,true,&p)==EACCES && called==0);

    setup(&sc,&dp,&m,&p);
    m.m_next=&m; /* Not one contiguous DMA segment. */
    assert(rtwn8723be_datapath_enqueue_80211(
        &dp,&m,&ni,false,&p)==EFBIG && called==0);
    m.m_next=NULL;
    m.bytes[0]=0x04; /* Control frame. */
    assert(rtwn8723be_datapath_enqueue_80211(
        &dp,&m,&ni,false,&p)==EOPNOTSUPP && called==0);

    setup(&sc,&dp,&m,&p);
    m.bytes[0]=0x88;m.m_len=m.m_pkthdr.len=25;
    assert(rtwn8723be_datapath_enqueue_80211(
        &dp,&m,&ni,false,&p)==EINVAL && called==0);
    m.m_len=m.m_pkthdr.len=38;
    m.bytes[24]=9; /* Invalid QoS TID. */
    assert(rtwn8723be_datapath_enqueue_80211(
        &dp,&m,&ni,false,&p)==EOPNOTSUPP && called==0);

    setup(&sc,&dp,&m,&p);
    m.bytes[1]=0x03; /* WDS four address. */
    assert(rtwn8723be_datapath_enqueue_80211(
        &dp,&m,&ni,false,&p)==EOPNOTSUPP && called==0);
    m.bytes[1]=0;
    m.bytes[22]=0x31; /* Fragmented sequence not yet supported. */
    assert(rtwn8723be_datapath_enqueue_80211(
        &dp,&m,&ni,false,&p)==EOPNOTSUPP && called==0);

    setup(&sc,&dp,&m,&p);
    result=EBUSY;
    assert(rtwn8723be_datapath_enqueue_80211(
        &dp,&m,&ni,false,&p)==EBUSY);
    assert(called==1 && ni.alive && m.m_len==38);
    puts("RTL_NET80211_TX_PLAN_AND_BRIDGE_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="rtl-net80211-txframe-") as td:
    source=Path(td)/"test.c"
    exe=Path(td)/"test"
    source.write_text(prefix+"\nint\n"+WRAP+"\n"+tail)
    subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror",
                    "-pedantic","-fsanitize=undefined",
                    "-fno-sanitize-recover=all",
                    "-I",str(ROOT/"src"),str(source),"-o",str(exe)],
                   check=True)
    subprocess.run([str(exe)],check=True)
print("RTL_NET80211_TX_FRAME_MUTATIONS_OK negatives=8")
