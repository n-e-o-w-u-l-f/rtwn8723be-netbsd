/* Actual native production C, with explicit pthread kernel/MMIO models. */
#include "rtwn8723be_netbsd.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>

enum mode { EARLY, ASYNC, BLOCK_SEND, TIMEOUT, EDGE, SEND_ERROR,
    MISMATCH, CV_ERROR };
struct test_env {
    pthread_mutex_t gate;
    pthread_cond_t change;
    enum mode mode;
    bool entered, release, wait_entered, drain_entered, stop_done;
    unsigned sends, waits;
    uint64_t budgets[8];
    uint16_t value;
    uint8_t submitted[7];
    size_t length;
};
_Thread_local struct test_env *current_env;
_Thread_local bool hard_context, soft_context;
static _Thread_local kmutex_t *held[8];
static _Thread_local unsigned nheld;
static atomic_uint destroyed;
static unsigned checks, scenarios;
#define CHECK(x) do { assert(x); checks++; } while (0)

bool cpu_intr_p(void) { return hard_context; }
bool cpu_softintr_p(void) { return soft_context; }
bool mutex_owned(kmutex_t *m) {
    for (unsigned i=0; i<nheld; i++) if (held[i]==m) return true;
    return false;
}
static void track(kmutex_t *m) { assert(nheld<8); held[nheld++]=m; }
static void untrack(kmutex_t *m) {
    unsigned i=0;
    while (i<nheld && held[i]!=m) i++;
    assert(i<nheld); held[i]=held[--nheld];
}
void mutex_init(kmutex_t *m, int kind, int ipl) {
    assert(kind==MUTEX_DEFAULT && (ipl==IPL_SOFTNET || ipl==IPL_NONE));
    assert(pthread_mutex_init(&m->p,NULL)==0);
}
void mutex_destroy(kmutex_t *m) {
    assert(!mutex_owned(m)); assert(pthread_mutex_destroy(&m->p)==0);
    atomic_fetch_add(&destroyed,1);
}
void mutex_enter(kmutex_t *m) {
    assert(!hard_context && !mutex_owned(m));
    assert(pthread_mutex_lock(&m->p)==0); track(m);
}
void mutex_exit(kmutex_t *m) {
    untrack(m); assert(pthread_mutex_unlock(&m->p)==0);
}
void cv_init(kcondvar_t *c, const char *name) {
    assert(pthread_cond_init(&c->p,NULL)==0); c->name=name;
}
void cv_destroy(kcondvar_t *c) {
    assert(pthread_cond_destroy(&c->p)==0); atomic_fetch_add(&destroyed,1);
}
void cv_signal(kcondvar_t *c) { assert(pthread_cond_signal(&c->p)==0); }
void cv_broadcast(kcondvar_t *c) { assert(pthread_cond_broadcast(&c->p)==0); }
static void notify_wait(bool drain) {
    struct test_env *e=current_env;
    if (e==NULL) return;
    pthread_mutex_lock(&e->gate);
    if (drain) e->drain_entered=true; else e->wait_entered=true;
    pthread_cond_broadcast(&e->change); pthread_mutex_unlock(&e->gate);
}
void cv_wait(kcondvar_t *c, kmutex_t *m) {
    assert(!hard_context && !soft_context && mutex_owned(m));
    notify_wait(true); untrack(m);
    assert(pthread_cond_wait(&c->p,&m->p)==0); track(m);
}
static void emit(struct rtwn8723be_softc *sc, uint8_t seq, uint8_t ext,
    size_t length, uint16_t value) {
    uint8_t bytes[7]={ext,0,(uint8_t)(seq<<4),(uint8_t)value,
        (uint8_t)(value>>8),0x56,0x78};
    struct rtwn8723be_c2h_event event={.id=R23BE_C2H_BT_MP,
        .payload=bytes,.payload_length=length,.recognized=true,.fast=true};
    bool old=soft_context; soft_context=true;
    int rc=rtwn8723be_btc_mp_native_receive(sc,&event);
    soft_context=old;
    assert(rc==(length<4 || (seq==14 && length<6) ? EMSGSIZE : 0));
    memset(bytes,0,sizeof(bytes)); /* Borrowed RX storage is reused. */
}
static _Thread_local struct rtwn8723be_softc *request_sc;
int cv_timedwaitbt(kcondvar_t *c, kmutex_t *m, struct bintime *bt,
    const struct bintime *epsilon) {
    struct test_env *e=current_env;
    struct timespec start,end,until,span;
    struct bintime elapsed;
    assert(!hard_context && !soft_context && mutex_owned(m));
    (void)epsilon;
    assert(e!=NULL && bt->sec==0 && e->waits<8);
    e->budgets[e->waits++]=bt->frac; notify_wait(false);
    if (e->mode==TIMEOUT || e->mode==MISMATCH) {
        mutex_exit(m); sched_yield(); mutex_enter(m);
        if (e->waits==1) { bt->frac/=2; return 0; }
        if (e->waits==2) { bt->frac=0; return 0; }
        assert(bt->frac==0); return EWOULDBLOCK;
    }
    if (e->mode==CV_ERROR) return EINTR;
    if (e->mode==EDGE) {
        mutex_exit(m); emit(request_sc,14,1,6,e->value); mutex_enter(m);
        bt->frac=0; return EWOULDBLOCK;
    }
    assert(clock_gettime(CLOCK_REALTIME,&start)==0);
    bintime2timespec(bt,&span);
    until=start; until.tv_sec+=span.tv_sec; until.tv_nsec+=span.tv_nsec;
    if (until.tv_nsec>=1000000000L) { until.tv_sec++; until.tv_nsec-=1000000000L; }
    untrack(m);
    int rc=pthread_cond_timedwait(&c->p,&m->p,&until); track(m);
    assert(rc==0 || rc==ETIMEDOUT);
    assert(clock_gettime(CLOCK_REALTIME,&end)==0);
    timespecsub(&end,&start,&span); timespec2bintime(&span,&elapsed);
    if (bintimecmp(&elapsed,bt,>=)) { bt->sec=0; bt->frac=0; }
    else bintime_sub(bt,&elapsed);
    return rc==ETIMEDOUT ? EWOULDBLOCK : 0;
}
int rtwn8723be_h2c_native_send(struct rtwn8723be_softc *sc,
    uint8_t id, const uint8_t *bytes, size_t length) {
    struct test_env *e=sc->env;
    assert(!mutex_owned(&sc->sc_btc_mp.lock));
    assert(!hard_context && !soft_context && id==0x67 && length<=7);
    memcpy(e->submitted,bytes,length); e->length=length; e->sends++;
    pthread_mutex_lock(&e->gate); e->entered=true;
    pthread_cond_broadcast(&e->change);
    while (e->mode==BLOCK_SEND && !e->release)
        pthread_cond_wait(&e->change,&e->gate);
    pthread_mutex_unlock(&e->gate);
    if (e->mode==EARLY) emit(sc,bytes[0]>>4,1,6,e->value);
    if (e->mode==MISMATCH) {
        emit(sc,7,1,5,e->value); emit(sc,14,0,6,e->value);
        emit(sc,14,1,3,e->value);
    }
    return e->mode==SEND_ERROR ? EIO : 0;
}
static void setup(struct rtwn8723be_softc *sc, struct test_env *e,
    enum mode mode) {
    memset(sc,0,sizeof(*sc)); memset(e,0,sizeof(*e));
    pthread_mutex_init(&e->gate,NULL); pthread_cond_init(&e->change,NULL);
    e->mode=mode; e->value=0x1234; sc->env=e;
    sc->sc_h2c.initialized=true; sc->sc_h2c.firmware_generation=1;
    sc->sc_h2c.state.firmware_ready=true;
    mutex_init(&sc->sc_h2c.lock,MUTEX_DEFAULT,IPL_NONE);
    sc->sc_mapped=true; sc->sc_linux.being_init_adapter=true;
    sc->sc_linux.fw_ready=true;
    current_env=e; request_sc=sc;
    CHECK(rtwn8723be_btc_mp_native_init(sc)==0);
}
static void finish(struct rtwn8723be_softc *sc) {
    CHECK(rtwn8723be_btc_mp_native_fini(sc)==0);
    CHECK(!sc->sc_btc_mp.initialized);
    mutex_destroy(&sc->sc_h2c.lock);
    pthread_cond_destroy(&sc->env->change); pthread_mutex_destroy(&sc->env->gate);
    current_env=NULL; request_sc=NULL;
}
static int request(struct rtwn8723be_softc *sc,
    struct rtwn8723be_btc_mp_reply *out, bool wait) {
    const uint8_t bytes[4]={0,0,0xaa,0xbb};
    current_env=sc->env; request_sc=sc;
    return rtwn8723be_btc_mp_native_request(sc,R23BE_BT_OP_VERSION,
        bytes,sizeof(bytes),wait,out);
}
static void early(void) {
    struct rtwn8723be_softc sc; struct test_env e;
    struct rtwn8723be_btc_mp_reply out;
    setup(&sc,&e,EARLY); CHECK(rtwn8723be_btc_mp_native_activate(&sc)==0);
    CHECK(request(&sc,&out,true)==0);
    CHECK(out.sequence==14 && out.value==0x1234 && out.firmware_subversion==0x56);
    CHECK(out.field==R23BE_BT_MP_VERSION && e.waits==0);
    CHECK(e.length==4 && e.submitted[0]==0xe0 && e.submitted[1]==0);
    CHECK(e.submitted[2]==0xaa && e.submitted[3]==0xbb);
    CHECK(request(&sc,&out,true)==0); CHECK(e.sends==2);
    finish(&sc); scenarios++;
}
static void mismatch(void) {
    struct rtwn8723be_softc sc; struct test_env e;
    struct rtwn8723be_btc_mp_reply out,before;
    setup(&sc,&e,MISMATCH); CHECK(rtwn8723be_btc_mp_native_activate(&sc)==0);
    memset(&out,0x5a,sizeof(out)); before=out;
    CHECK(request(&sc,&out,true)==ETIMEDOUT);
    CHECK(memcmp(&out,&before,sizeof(out))==0);
    CHECK(e.waits==3 && e.budgets[0]==ms2bintime(200).frac);
    CHECK(e.budgets[1]==e.budgets[0]/2 && e.budgets[2]==0);
    emit(&sc,14,1,6,e.value);
    CHECK(request(&sc,&out,true)==EAGAIN); CHECK(e.sends==1);
    CHECK(rtwn8723be_btc_mp_native_activate(&sc)==EAGAIN);
    finish(&sc); scenarios++;
}
struct thread_arg { struct rtwn8723be_softc *sc;
    struct rtwn8723be_btc_mp_reply out; int rc; };
static void *request_thread(void *arg) {
    struct thread_arg *a=arg; memset(&a->out,0x5a,sizeof(a->out));
    a->rc=request(a->sc,&a->out,true); return NULL;
}
static void *stop_thread(void *arg) {
    struct thread_arg *a=arg; struct test_env *e=a->sc->env; current_env=e;
    a->rc=rtwn8723be_btc_mp_native_stop(a->sc);
    pthread_mutex_lock(&e->gate); e->stop_done=true;
    pthread_cond_broadcast(&e->change); pthread_mutex_unlock(&e->gate);
    return NULL;
}
static void wait_flag(struct test_env *e, bool *flag) {
    pthread_mutex_lock(&e->gate);
    while (!*flag) pthread_cond_wait(&e->change,&e->gate);
    pthread_mutex_unlock(&e->gate);
}
static void race(enum mode mode) {
    struct rtwn8723be_softc sc; struct test_env e;
    struct thread_arg a={.sc=&sc},s={.sc=&sc}; pthread_t worker,stopper;
    setup(&sc,&e,mode); CHECK(rtwn8723be_btc_mp_native_activate(&sc)==0);
    CHECK(pthread_create(&worker,NULL,request_thread,&a)==0);
    wait_flag(&e,&e.entered);
    struct rtwn8723be_btc_mp_reply out;
    CHECK(request(&sc,&out,true)==EBUSY); CHECK(e.sends==1);
    if (mode==ASYNC) {
        wait_flag(&e,&e.wait_entered); emit(&sc,7,1,5,e.value);
        mutex_enter(&sc.sc_btc_mp.lock); CHECK(!sc.sc_btc_mp.done);
        mutex_exit(&sc.sc_btc_mp.lock);
        emit(&sc,14,1,6,e.value);
        CHECK(pthread_join(worker,NULL)==0); CHECK(a.rc==0);
        CHECK(a.out.value==e.value);
    } else {
        unsigned old_destroyed=atomic_load(&destroyed);
        CHECK(pthread_create(&stopper,NULL,stop_thread,&s)==0);
        wait_flag(&e,&e.drain_entered);
        pthread_mutex_lock(&e.gate); CHECK(!e.stop_done);
        pthread_mutex_unlock(&e.gate);
        CHECK(atomic_load(&destroyed)==old_destroyed);
        emit(&sc,14,1,6,e.value);
        pthread_mutex_lock(&e.gate); e.release=true;
        pthread_cond_broadcast(&e.change); pthread_mutex_unlock(&e.gate);
        CHECK(pthread_join(worker,NULL)==0); CHECK(pthread_join(stopper,NULL)==0);
        CHECK(a.rc==ECANCELED && s.rc==0);
        struct rtwn8723be_btc_mp_reply sentinel; memset(&sentinel,0x5a,sizeof(sentinel));
        CHECK(memcmp(&a.out,&sentinel,sizeof(sentinel))==0);
        CHECK(request(&sc,&out,true)==EAGAIN);
    }
    finish(&sc); scenarios++;
}
static void stop_waiter(void) {
    struct rtwn8723be_softc sc; struct test_env e;
    struct thread_arg a={.sc=&sc}; pthread_t worker;
    setup(&sc,&e,ASYNC); CHECK(rtwn8723be_btc_mp_native_activate(&sc)==0);
    CHECK(pthread_create(&worker,NULL,request_thread,&a)==0);
    wait_flag(&e,&e.wait_entered);
    CHECK(rtwn8723be_btc_mp_native_stop(&sc)==0);
    CHECK(pthread_join(worker,NULL)==0); CHECK(a.rc==ECANCELED);
    finish(&sc); scenarios++;
}
static void separate_devices(void) {
    struct rtwn8723be_softc sa,sb; struct test_env ea,eb;
    struct thread_arg a={.sc=&sa},b={.sc=&sb}; pthread_t ta,tb;
    setup(&sa,&ea,ASYNC); setup(&sb,&eb,ASYNC); eb.value=0x9876;
    CHECK(rtwn8723be_btc_mp_native_activate(&sa)==0);
    CHECK(rtwn8723be_btc_mp_native_activate(&sb)==0);
    CHECK(pthread_create(&ta,NULL,request_thread,&a)==0);
    CHECK(pthread_create(&tb,NULL,request_thread,&b)==0);
    wait_flag(&ea,&ea.wait_entered); wait_flag(&eb,&eb.wait_entered);
    emit(&sb,14,1,6,eb.value);
    CHECK(pthread_join(tb,NULL)==0); CHECK(b.rc==0 && b.out.value==0x9876);
    mutex_enter(&sa.sc_btc_mp.lock); CHECK(!sa.sc_btc_mp.done);
    mutex_exit(&sa.sc_btc_mp.lock); emit(&sa,14,1,6,ea.value);
    CHECK(pthread_join(ta,NULL)==0); CHECK(a.rc==0 && a.out.value==0x1234);
    finish(&sa); finish(&sb); scenarios++;
}
static void guards(void) {
    struct rtwn8723be_softc sc; struct test_env e;
    struct rtwn8723be_btc_mp_reply out,before;
    uint8_t cmd[8]={0}; struct rtwn8723be_c2h_event ev={.id=3};
    setup(&sc,&e,EARLY); memset(&out,0x5a,sizeof(out)); before=out;
    CHECK(request(&sc,&out,true)==EAGAIN);
    CHECK(rtwn8723be_btc_mp_native_init(&sc)==EALREADY);
    sc.sc_irq_enabled=true; CHECK(rtwn8723be_btc_mp_native_activate(&sc)==EAGAIN);
    sc.sc_irq_enabled=false; sc.sc_irq_pending[0]=1;
    CHECK(rtwn8723be_btc_mp_native_activate(&sc)==EAGAIN); sc.sc_irq_pending[0]=0;
    sc.sc_irq_pending[1]=1; CHECK(rtwn8723be_btc_mp_native_activate(&sc)==EAGAIN);
    sc.sc_irq_pending[1]=0; sc.sc_linux.started=true;
    CHECK(rtwn8723be_btc_mp_native_activate(&sc)==EAGAIN); sc.sc_linux.started=false;
    sc.sc_h2c.state.faulted=true;
    CHECK(rtwn8723be_btc_mp_native_activate(&sc)==EAGAIN); sc.sc_h2c.state.faulted=false;
    CHECK(rtwn8723be_btc_mp_native_activate(&sc)==0);
    CHECK(rtwn8723be_btc_mp_native_activate(&sc)==EBUSY);
    CHECK(rtwn8723be_btc_mp_native_request(&sc,0,NULL,4,true,&out)==EINVAL);
    CHECK(rtwn8723be_btc_mp_native_request(&sc,0,cmd,1,true,&out)==EINVAL);
    CHECK(rtwn8723be_btc_mp_native_request(&sc,0,cmd,8,true,&out)==EINVAL);
    CHECK(rtwn8723be_btc_mp_native_request(&sc,0,cmd,4,true,NULL)==EINVAL);
    CHECK(rtwn8723be_btc_mp_native_receive(&sc,&ev)==EINVAL);
    for (unsigned i=0;i<2;i++) {
        hard_context=i==0; soft_context=i==1;
        CHECK(request(&sc,&out,true)==EWOULDBLOCK);
        CHECK(rtwn8723be_btc_mp_native_init(&sc)==EWOULDBLOCK);
        CHECK(rtwn8723be_btc_mp_native_activate(&sc)==EWOULDBLOCK);
        CHECK(rtwn8723be_btc_mp_native_stop(&sc)==EWOULDBLOCK);
        CHECK(rtwn8723be_btc_mp_native_fini(&sc)==EWOULDBLOCK);
        if (hard_context) CHECK(rtwn8723be_btc_mp_native_receive(&sc,&ev)==EWOULDBLOCK);
        hard_context=false; soft_context=false;
    }
    CHECK(e.sends==0 && memcmp(&out,&before,sizeof(out))==0);
    CHECK(rtwn8723be_btc_mp_native_stop(&sc)==0);
    CHECK(rtwn8723be_btc_mp_native_activate(&sc)==EAGAIN);
    sc.sc_h2c.firmware_generation++;
    CHECK(rtwn8723be_btc_mp_native_activate(&sc)==0);
    CHECK(request(&sc,&out,true)==0);
    finish(&sc); scenarios++;
}
static void failures(enum mode mode, bool wait) {
    struct rtwn8723be_softc sc; struct test_env e;
    struct rtwn8723be_btc_mp_reply out,before;
    setup(&sc,&e,mode); CHECK(rtwn8723be_btc_mp_native_activate(&sc)==0);
    memset(&out,0x5a,sizeof(out)); before=out;
    int expected=mode==SEND_ERROR ? EIO : mode==CV_ERROR ? EINTR :
        mode==TIMEOUT ? ETIMEDOUT : 0;
    CHECK(request(&sc,&out,wait)==expected);
    if (mode==EDGE) CHECK(out.value==e.value && e.waits==1);
    else {
        CHECK(memcmp(&out,&before,sizeof(out))==0);
        CHECK(sc.sc_btc_mp.faulted && !sc.sc_btc_mp.active);
        emit(&sc,14,1,6,e.value);
        CHECK(request(&sc,&out,true)==EAGAIN);
        CHECK(rtwn8723be_btc_mp_native_activate(&sc)==EAGAIN);
    }
    finish(&sc); scenarios++;
}
int main(int argc, char **argv) {
    if (argc==2) {
        if (!strcmp(argv[1],"--negative-match")) mismatch();
        else if (!strcmp(argv[1],"--negative-arm")) early();
        else return 2;
        return 0;
    }
    early(); mismatch(); guards(); failures(TIMEOUT,true);
    failures(EDGE,true); failures(SEND_ERROR,true); failures(CV_ERROR,true);
    failures(EARLY,false); stop_waiter(); separate_devices();
    for (unsigned i=0;i<16;i++) { race(ASYNC); race(BLOCK_SEND); }
    CHECK(nheld==0);
    printf("BTC_MP_NATIVE_SCENARIOS=%u CHECKS=%u\n",scenarios,checks);
    puts("BTC_MP_NATIVE_ACTUAL_C_PASS: pthread kernel/CV/MMIO models; physical acceptance OPEN");
    return 0;
}
