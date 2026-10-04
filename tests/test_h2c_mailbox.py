#!/usr/bin/env python3
"""Exercise the actual H2C protocol C with source-pinned registers and UBSan.
Standalone hardware-mock regression, NOT an integrated NetBSD/HP WLAN test.
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
header = (ROOT / "src/rtwn8723be_f16_1.h").read_text()
for symbol, value in (("R23BE_REG_HMETFR", "0x01cc"),
                      ("R23BE_REG_HMEBOX_0", "0x01d0"),
                      ("R23BE_REG_HMEBOX_EXT_0", "0x01f0"),
                      ("R23BE_REG_HMEBOX_3", "0x01dc"),
                      ("R23BE_REG_HMEBOX_EXT_3", "0x01fc")):
    assert re.search(rf"^#define\s+{symbol}\s+{value}\b", header, re.M), symbol

C = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_h2c.h"

struct event { uint16_t reg; uint8_t data; };
struct mock {
    int locked, acquired, released, reads, writes, waits;
    int lock_error, read_error_at, write_error_at, busy_reads;
    struct event records[12];
};
static int lock_fn(void *ctx) {
    struct mock *m=ctx;
    m->acquired++;
    if (m->lock_error) return m->lock_error;
    assert(!m->locked);
    m->locked=1;
    return 0;
}
static void unlock_fn(void *ctx) {
    struct mock *m=ctx;
    assert(m->locked);
    m->locked=0;
    m->released++;
}
static int read_fn(void *ctx, uint16_t reg, uint8_t *out) {
    struct mock *m=ctx;
    assert(m->locked);
    assert(reg==0x01cc);
    m->reads++;
    if (m->reads==m->read_error_at) return ENXIO;
    *out=(m->reads <= m->busy_reads) ? 0x0f : 0;
    return 0;
}
static int write_fn(void *ctx, uint16_t reg, uint8_t data) {
    struct mock *m=ctx;
    assert(m->locked);
    m->writes++;
    if (m->writes==m->write_error_at) return EIO;
    assert(m->writes<=12);
    m->records[m->writes-1]=(struct event){reg,data};
    return 0;
}
static void wait_fn(void *ctx,unsigned int us) {
    struct mock *m=ctx;
    assert(m->locked && us==10);
    m->waits++;
}
static struct rtwn8723be_h2c_ops ops(struct mock *m) {
    return (struct rtwn8723be_h2c_ops){
        m,lock_fn,unlock_fn,read_fn,write_fn,wait_fn};
}
static void reset_ready(struct rtwn8723be_h2c_state *s) {
    rtwn8723be_h2c_reset(s);
    assert(!s->firmware_ready && !s->faulted && s->next_box==0);
    s->firmware_ready=true; /* test-only simulated verified firmware */
}
int main(void) {
    struct rtwn8723be_h2c_state state={0};
    struct mock m={0};
    struct rtwn8723be_h2c_ops io=ops(&m);
    const uint8_t p[]={0x11,0x22,0x33,0x44,0x55,0x66,0x77};
    unsigned box,len,i;
    /* Firmware readiness and invalid packet never write MMIO. */
    assert(rtwn8723be_h2c_send(&state,&io,0x81,p,1)==EAGAIN);
    assert(m.writes==0 && m.reads==0 && m.acquired==m.released);
    assert(rtwn8723be_h2c_send(&state,&io,0x81,p,0)==EINVAL);
    assert(rtwn8723be_h2c_send(&state,&io,0x81,p,8)==EINVAL);
    assert(rtwn8723be_h2c_send(&state,&io,0x81,NULL,1)==EINVAL);
    assert(rtwn8723be_h2c_send(NULL,&io,0x81,p,1)==EINVAL);
    assert(rtwn8723be_h2c_send(&state,NULL,0x81,p,1)==EINVAL);
    reset_ready(&state);

    /* Every length 1..7 in each of four rotating PCIe mailboxes. */
    for (len=1;len<=7;len++) for (box=0;box<4;box++) {
        unsigned ext=(len>3)?4:0;
        memset(&m,0,sizeof(m));
        assert(state.next_box==box);
        assert(rtwn8723be_h2c_send(&state,&io,0x81,p,len)==0);
        assert(m.locked==0 && m.acquired==1 && m.released==1);
        assert(m.reads==1 && m.waits==0 && m.writes==(int)(4+ext));
        for(i=0;i<ext;i++) {
            assert(m.records[i].reg==0x01f0+4*box+i);
            assert(m.records[i].data==((3+i<len)?p[3+i]:0));
        }
        for(i=0;i<4;i++) {
            assert(m.records[ext+i].reg==0x01d0+4*box+i);
            assert(m.records[ext+i].data==
                ((i==0)?0x81:((i<=len)?p[i-1]:0)));
        }
        assert(state.next_box==(box+1)%4 && !state.faulted);
    }
    reset_ready(&state);
    memset(&m,0,sizeof(m));m.busy_reads=3;
    assert(rtwn8723be_h2c_send(&state,&io,4,p,4)==0);
    assert(m.reads==4 && m.waits==3);
    reset_ready(&state);
    memset(&m,0,sizeof(m));m.busy_reads=100;
    assert(rtwn8723be_h2c_send(&state,&io,4,p,4)==ETIMEDOUT);
    assert(m.reads==100 && m.waits==99 && m.writes==0);
    assert(state.next_box==0 && !state.faulted && m.acquired==m.released);
    reset_ready(&state);
    memset(&m,0,sizeof(m));m.read_error_at=1;
    assert(rtwn8723be_h2c_send(&state,&io,4,p,4)==ENXIO);
    assert(m.writes==0 && state.next_box==0 && !state.faulted);
    reset_ready(&state);
    memset(&m,0,sizeof(m));m.lock_error=EBUSY;
    assert(rtwn8723be_h2c_send(&state,&io,4,p,4)==EBUSY);
    assert(m.acquired==1 && m.released==0 && m.reads==0);
    /* Each of 8 write positions fails closed without box advancement. */
    for(i=1;i<=8;i++){
        reset_ready(&state);
        memset(&m,0,sizeof(m));m.write_error_at=(int)i;
        assert(rtwn8723be_h2c_send(&state,&io,4,p,7)==EIO);
        assert(m.acquired==1 && m.released==1 && !m.locked);
        assert(state.faulted && state.next_box==0 && m.writes==(int)i);
        assert(rtwn8723be_h2c_send(&state,&io,4,p,7)==EIO);
        assert(m.reads==1 && m.writes==(int)i);
    }
    reset_ready(&state);
    state.next_box=4;
    memset(&m,0,sizeof(m));
    assert(rtwn8723be_h2c_send(&state,&io,4,p,7)==EIO);
    assert(state.faulted && m.reads==0 && m.writes==0);
    reset_ready(&state);
    memset(&m,0,sizeof(m));
    assert(rtwn8723be_h2c_media_status(&state,&io,true)==0);
    assert(m.writes==4 && m.records[0].reg==0x01d0 &&
        m.records[0].data==1 && m.records[1].data==1 &&
        m.records[2].data==0 && m.records[3].data==0);
    memset(&m,0,sizeof(m));
    assert(rtwn8723be_h2c_media_status(&state,&io,false)==0);
    assert(m.writes==4 && m.records[0].reg==0x01d4 &&
        m.records[0].data==1 && m.records[1].data==0 &&
        m.records[2].data==0 && m.records[3].data==0);
    puts("RTL_H2C_MAILBOX_C11_UBSAN_OK lengths=7 boxes=4 "
         "busy_timeout=100 write_failure_points=8");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-h2c-") as d:
    p = Path(d) / "main.c"
    exe = Path(d) / "main"
    p.write_text(C)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all", "-I", str(ROOT / "src"),
                    str(ROOT / "src/rtwn8723be_h2c.c"), str(p),
                    "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
