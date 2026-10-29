/* SPDX-License-Identifier: GPL-2.0 */
/* Actual native broker/dispatch; only kernel primitives and algorithm bodies
 * are modeled here. Full algorithm differential proof is a separate test. */
#include "rtwn8723be_netbsd.h"
#include "btc_algorithm_model.h"
#include <time.h>
#include <sched.h>
#include <stdatomic.h>

_Thread_local struct lwp btc_test_lwp;
static _Thread_local bool hard_irq,soft_irq;
static _Thread_local kmutex_t *held[16];
static _Thread_local unsigned int held_count;
static unsigned int scenarios,queues_created,queues_destroyed;
static atomic_uint checks;
static bool fail_create;
#define CHECK(x) do {++checks;assert(x);}while(0)
bool cpu_intr_p(void){return hard_irq;}
bool cpu_softintr_p(void){return soft_irq;}
bool mutex_owned(kmutex_t *m){unsigned int i;for(i=0;i<held_count;++i)if(held[i]==m)return true;return false;}
void mutex_init(kmutex_t *m,int type,int ipl){CHECK(type==MUTEX_DEFAULT&&(ipl==IPL_NONE||ipl==IPL_SOFTNET));CHECK(!pthread_mutex_init(&m->p,NULL));}
void mutex_destroy(kmutex_t *m){CHECK(!pthread_mutex_destroy(&m->p));}
void mutex_enter(kmutex_t *m){assert(held_count<16&&!mutex_owned(m));assert(!pthread_mutex_lock(&m->p));held[held_count++]=m;}
void mutex_exit(kmutex_t *m){unsigned int i;assert(mutex_owned(m));for(i=0;i<held_count;++i)if(held[i]==m){held[i]=held[--held_count];break;}assert(!pthread_mutex_unlock(&m->p));}
void cv_init(kcondvar_t *c,const char *name){(void)name;CHECK(!pthread_cond_init(&c->p,NULL));}
void cv_destroy(kcondvar_t *c){CHECK(!pthread_cond_destroy(&c->p));}
void cv_wait(kcondvar_t *c,kmutex_t *m){assert(mutex_owned(m));assert(!pthread_cond_wait(&c->p,&m->p));}
void cv_broadcast(kcondvar_t *c){assert(!pthread_cond_broadcast(&c->p));}

struct workqueue {
    pthread_mutex_t lock;pthread_cond_t cv;pthread_t thread;
    struct work *queued,*running;void (*fn)(struct work *,void *);void *arg;bool quit;
};
static void *work_main(void *arg)
{
    struct workqueue *q=arg;assert(!pthread_mutex_lock(&q->lock));
    for(;;){struct work *w;while(!q->queued&&!q->quit)assert(!pthread_cond_wait(&q->cv,&q->lock));
        if(q->quit){assert(!q->queued);break;}w=q->queued;q->queued=NULL;q->running=w;
        assert(!pthread_mutex_unlock(&q->lock));q->fn(w,q->arg);assert(!pthread_mutex_lock(&q->lock));
        q->running=NULL;assert(!pthread_cond_broadcast(&q->cv));}
    assert(!pthread_mutex_unlock(&q->lock));return NULL;
}
int workqueue_create(struct workqueue **out,const char *name,void (*fn)(struct work *,void *),void *arg,int pri,int ipl,int flags)
{
    struct workqueue *q;(void)name;CHECK(pri==PRI_NONE&&ipl==IPL_SOFTNET&&flags==WQ_MPSAFE);
    if(fail_create)return ENOMEM;
    q=calloc(1,sizeof(*q));assert(q);q->fn=fn;q->arg=arg;
    assert(!pthread_mutex_init(&q->lock,NULL));assert(!pthread_cond_init(&q->cv,NULL));
    assert(!pthread_create(&q->thread,NULL,work_main,q));*out=q;++queues_created;return 0;
}
void workqueue_enqueue(struct workqueue *q,struct work *w,void *cpu)
{
    assert(cpu==NULL);assert(!pthread_mutex_lock(&q->lock));assert(!q->quit&&!q->queued);
    q->queued=w;assert(!pthread_cond_broadcast(&q->cv));assert(!pthread_mutex_unlock(&q->lock));
}
void workqueue_wait(struct workqueue *q,struct work *w)
{
    /* Pinned NetBSD returns immediately for its own worker, so the native
     * caller must reject self-stop BEFORE depending on this API. */
    if(pthread_equal(pthread_self(),q->thread))return;
    assert(!pthread_mutex_lock(&q->lock));while(q->queued==w||q->running==w)assert(!pthread_cond_wait(&q->cv,&q->lock));assert(!pthread_mutex_unlock(&q->lock));
}
void workqueue_destroy(struct workqueue *q)
{
    assert(!pthread_mutex_lock(&q->lock));assert(!q->running&&!q->queued);q->quit=true;
    assert(!pthread_cond_broadcast(&q->cv));assert(!pthread_mutex_unlock(&q->lock));
    assert(!pthread_join(q->thread,NULL));assert(!pthread_cond_destroy(&q->cv));assert(!pthread_mutex_destroy(&q->lock));free(q);++queues_destroyed;
}
struct test_env {
    pthread_mutex_t resource,gate;pthread_cond_t cv;
    bool ready,pause_acquire,pause_engine,entered,release,self_acquire,self_engine;
    int acquire_error,io_error,self_result;
    unsigned int acquired,released,executed,halted,io;
    enum rtwn8723be_btc_event_kind last_kind;
    u8 info[10],length;
};
static void pause_at(struct test_env *e,bool enabled)
{
    assert(!pthread_mutex_lock(&e->gate));
    if(enabled){e->entered=true;assert(!pthread_cond_broadcast(&e->cv));while(!e->release)assert(!pthread_cond_wait(&e->cv,&e->gate));}
    assert(!pthread_mutex_unlock(&e->gate));
}
static int acquire(void *arg,struct rtwn8723be_softc *sc)
{
    struct test_env *e=arg;assert(btc_test_lwp.unused==0);assert(!hard_irq&&!soft_irq);
    if(e->acquire_error)return e->acquire_error;
    assert(!pthread_mutex_lock(&e->resource));++e->acquired;
    if(e->self_acquire)e->self_result=rtwn8723be_btc_native_stop(sc);
    pause_at(e,e->pause_acquire);return 0;
}
static bool ready(void *arg,struct rtwn8723be_softc *sc){(void)sc;return ((struct test_env *)arg)->ready;}
static void release_owner(void *arg,struct rtwn8723be_softc *sc,int error){struct test_env *e=arg;(void)sc;(void)error;++e->released;assert(!pthread_mutex_unlock(&e->resource));}
static const struct rtwn8723be_btc_native_owner owner={acquire,ready,release_owner};
static void observe(struct btc_coexist *b,enum rtwn8723be_btc_event_kind kind,const u8 *data,u8 len)
{
    struct rtwn8723be_softc *sc=b->adapter;struct test_env *e=sc->env;unsigned int i;
    assert(!hard_irq&&!soft_irq);assert(mutex_owned(&sc->sc_btc.engine_lock));
    pause_at(e,e->pause_engine);++e->executed;e->last_kind=kind;
    if(kind==R23BE_BTC_HALT)++e->halted;
    if(data){assert(len<=10);memcpy(e->info,data,len);e->length=len;}
    if(e->self_engine)e->self_result=rtwn8723be_btc_native_stop(sc);
    for(i=0;i<3;++i){if(i==0&&e->io_error)rtwn8723be_btc_native_provider_error(sc,e->io_error);if(rtwn8723be_btc_native_provider_ready(sc))++e->io;}
}
#define NOARG(n,suffix,kind) void ex_btc8723b##n##ant_##suffix(struct btc_coexist *b){observe(b,kind,NULL,0);}
#define VAL(n,suffix,kind) void ex_btc8723b##n##ant_##suffix(struct btc_coexist *b,u8 value){(void)value;observe(b,kind,NULL,0);}
#define COMMON(n) \
NOARG(n,power_on_setting,R23BE_BTC_POWER_ON) NOARG(n,init_coex_dm,R23BE_BTC_INIT_DM) \
NOARG(n,halt_notify,R23BE_BTC_HALT) NOARG(n,periodical,R23BE_BTC_PERIODIC) \
VAL(n,ips_notify,R23BE_BTC_IPS) VAL(n,lps_notify,R23BE_BTC_LPS) \
VAL(n,scan_notify,R23BE_BTC_SCAN) VAL(n,connect_notify,R23BE_BTC_CONNECT) \
VAL(n,media_status_notify,R23BE_BTC_MEDIA) VAL(n,special_packet_notify,R23BE_BTC_SPECIAL_PACKET) VAL(n,pnp_notify,R23BE_BTC_PNP) \
void ex_btc8723b##n##ant_bt_info_notify(struct btc_coexist *b,u8 *p,u8 len){observe(b,R23BE_BTC_INFO,p,len);} \
void ex_btc8723b##n##ant_display_coex_info(struct btc_coexist *b,struct seq_file *sink){(void)sink;observe(b,R23BE_BTC_DISPLAY,NULL,0);}
COMMON(1) COMMON(2)
void ex_btc8723b1ant_init_hwconfig(struct btc_coexist *b,bool wifi_only){(void)wifi_only;observe(b,R23BE_BTC_INIT_HW,NULL,0);}
NOARG(2,init_hwconfig,R23BE_BTC_INIT_HW)
NOARG(2,pre_load_firmware,R23BE_BTC_PRELOAD)
VAL(1,rf_status_notify,R23BE_BTC_RF_STATUS)

static void init_env(struct rtwn8723be_softc *sc,struct test_env *e)
{
    struct btc_model *m=calloc(1,sizeof(*m));struct btc_coexist context;assert(m);
    memset(sc,0,sizeof(*sc));memset(e,0,sizeof(*e));
    assert(!pthread_mutex_init(&e->resource,NULL));assert(!pthread_mutex_init(&e->gate,NULL));assert(!pthread_cond_init(&e->cv,NULL));e->ready=true;sc->env=e;
    btc_model_init(m,&context,1,0,1);context.adapter=sc;
    CHECK(!rtwn8723be_btc_native_init(sc,&context,&owner,e));free(m);
    sc->sc_linux.started=sc->sc_linux.fw_ready=sc->sc_irq_enabled=true;sc->sc_linux.stage=R23BE_STAGE_RUNNING;
    CHECK(!rtwn8723be_btc_native_enable_events(sc));
}
static void destroy_env(struct rtwn8723be_softc *sc,struct test_env *e,bool faulted)
{
    if(faulted){CHECK(rtwn8723be_btc_native_fini(sc)!=0);CHECK(sc->sc_btc.initialized);
        /* Test-fixture destruction only. Production recovery remains OPEN. */
        workqueue_wait(sc->sc_btc.workqueue,&sc->sc_btc.work);workqueue_destroy(sc->sc_btc.workqueue);
        cv_destroy(&sc->sc_btc.calls_cv);mutex_destroy(&sc->sc_btc.engine_lock);mutex_destroy(&sc->sc_btc.queue_lock);
    }else {CHECK(!rtwn8723be_btc_native_fini(sc));CHECK(!sc->sc_btc.initialized);CHECK(e->halted==1);}
    CHECK(e->acquired==e->released);assert(!pthread_cond_destroy(&e->cv));assert(!pthread_mutex_destroy(&e->gate));assert(!pthread_mutex_destroy(&e->resource));
}
static void wait_enter(struct test_env *e){assert(!pthread_mutex_lock(&e->gate));while(!e->entered)assert(!pthread_cond_wait(&e->cv,&e->gate));assert(!pthread_mutex_unlock(&e->gate));}
static void unpause(struct test_env *e){assert(!pthread_mutex_lock(&e->gate));e->release=true;assert(!pthread_cond_broadcast(&e->cv));assert(!pthread_mutex_unlock(&e->gate));}
static struct rtwn8723be_btc_event periodic(void){struct rtwn8723be_btc_event e;memset(&e,0,sizeof(e));e.kind=R23BE_BTC_PERIODIC;return e;}
struct call {struct rtwn8723be_softc *sc;int result;bool stop;};
static void *call_main(void *arg){struct call *c=arg;struct rtwn8723be_btc_event e=periodic();c->result=c->stop?rtwn8723be_btc_native_stop(c->sc):rtwn8723be_btc_native_execute(c->sc,&e);return NULL;}
static void wait_calls(struct rtwn8723be_softc *sc,unsigned int calls)
{
    unsigned int i;for(i=0;i<1000000;++i){bool done;mutex_enter(&sc->sc_btc.queue_lock);done=sc->sc_btc.calls==calls;mutex_exit(&sc->sc_btc.queue_lock);if(done)return;sched_yield();}assert(false);
}
static void copied_info(void)
{
    struct rtwn8723be_softc sc;struct test_env e;u8 data[10]={1,0x49,0x40,70,2,5,30,7,8,9},expected[10];
    struct rtwn8723be_c2h_event event;memset(&event,0,sizeof(event));memcpy(expected,data,10);
    init_env(&sc,&e);e.pause_acquire=true;event.id=R23BE_C2H_BT_INFO;event.payload=data;event.payload_length=10;
    soft_irq=true;CHECK(!rtwn8723be_btc_native_c2h_info(&sc,&event));soft_irq=false;wait_enter(&e);
    memset(data,0xee,10);unpause(&e);workqueue_wait(sc.sc_btc.workqueue,&sc.sc_btc.work);
    CHECK(e.last_kind==R23BE_BTC_INFO&&e.length==10&&!memcmp(e.info,expected,10));
    destroy_env(&sc,&e,false);++scenarios;
}
static void stop_race(void)
{
    struct rtwn8723be_softc sc;struct test_env e;struct rtwn8723be_btc_event event=periodic();
    struct call call={&sc,-1,false},stop={&sc,-1,true};pthread_t caller,stopper;
    init_env(&sc,&e);e.pause_engine=true;CHECK(!rtwn8723be_btc_native_enqueue(&sc,&event));wait_enter(&e);
    assert(!pthread_create(&caller,NULL,call_main,&call));wait_calls(&sc,1);
    assert(!pthread_create(&stopper,NULL,call_main,&stop));
    for(;;){bool closing;mutex_enter(&sc.sc_btc.queue_lock);closing=sc.sc_btc.closing;mutex_exit(&sc.sc_btc.queue_lock);if(closing)break;sched_yield();}
    CHECK(rtwn8723be_btc_native_enqueue(&sc,&event)==EAGAIN);unpause(&e);
    assert(!pthread_join(caller,NULL)&&!pthread_join(stopper,NULL));CHECK(!call.result&&!stop.result);
    CHECK(e.executed==3&&e.halted==1);CHECK(!rtwn8723be_btc_native_stop(&sc)&&e.halted==1);
    destroy_env(&sc,&e,false);++scenarios;
}
static void overflow(void)
{
    struct rtwn8723be_softc sc;struct test_env e;struct rtwn8723be_btc_event event=periodic();unsigned int i;
    init_env(&sc,&e);e.pause_acquire=true;CHECK(!rtwn8723be_btc_native_enqueue(&sc,&event));wait_enter(&e);
    for(i=0;i<R23BE_BTC_QUEUE_SIZE;++i)CHECK(!rtwn8723be_btc_native_enqueue(&sc,&event));
    CHECK(rtwn8723be_btc_native_enqueue(&sc,&event)==ENOBUFS);CHECK(rtwn8723be_btc_native_enqueue(&sc,&event)==EAGAIN);
    unpause(&e);CHECK(rtwn8723be_btc_native_stop(&sc)==ENOBUFS);CHECK(e.executed==0&&e.halted==0&&sc.sc_btc.count==0);
    destroy_env(&sc,&e,true);++scenarios;
}
static void provider_fault(void)
{
    struct rtwn8723be_softc sc;struct test_env e;struct call a={&sc,-1,false},b={&sc,-1,false};pthread_t t1,t2;
    init_env(&sc,&e);e.pause_engine=true;e.io_error=EIO;
    assert(!pthread_create(&t1,NULL,call_main,&a));wait_enter(&e);assert(!pthread_create(&t2,NULL,call_main,&b));wait_calls(&sc,2);
    unpause(&e);assert(!pthread_join(t1,NULL)&&!pthread_join(t2,NULL));CHECK(a.result==EIO&&b.result==EIO);
    CHECK(e.executed==1&&e.io==0);CHECK(rtwn8723be_btc_native_stop(&sc)==EIO);destroy_env(&sc,&e,true);++scenarios;
}
static void guards(void)
{
    struct rtwn8723be_softc sc;struct test_env e;struct rtwn8723be_btc_event event=periodic();unsigned int mode;
    init_env(&sc,&e);hard_irq=true;CHECK(rtwn8723be_btc_native_execute(&sc,&event)==EWOULDBLOCK);CHECK(rtwn8723be_btc_native_enqueue(&sc,&event)==EWOULDBLOCK);CHECK(rtwn8723be_btc_native_stop(&sc)==EWOULDBLOCK);hard_irq=false;
    soft_irq=true;CHECK(rtwn8723be_btc_native_execute(&sc,&event)==EWOULDBLOCK);CHECK(rtwn8723be_btc_native_stop(&sc)==EWOULDBLOCK);soft_irq=false;
    event.kind=R23BE_BTC_HALT;CHECK(rtwn8723be_btc_native_enqueue(&sc,&event)==EINVAL);event.kind=R23BE_BTC_DISPLAY;CHECK(rtwn8723be_btc_native_enqueue(&sc,&event)==EINVAL);
    event.kind=R23BE_BTC_INFO;event.length=11;CHECK(rtwn8723be_btc_native_enqueue(&sc,&event)==EINVAL);CHECK(e.executed==0);destroy_env(&sc,&e,false);++scenarios;
    for(mode=0;mode<2;++mode){init_env(&sc,&e);event=periodic();e.self_acquire=mode==0;e.self_engine=mode==1;
        CHECK(!rtwn8723be_btc_native_enqueue(&sc,&event));workqueue_wait(sc.sc_btc.workqueue,&sc.sc_btc.work);CHECK(e.self_result==EDEADLK);
        e.self_acquire=e.self_engine=false;destroy_env(&sc,&e,false);++scenarios;}
    init_env(&sc,&e);e.acquire_error=EBUSY;event=periodic();CHECK(!rtwn8723be_btc_native_enqueue(&sc,&event));workqueue_wait(sc.sc_btc.workqueue,&sc.sc_btc.work);
    CHECK(sc.sc_btc.faulted&&sc.sc_btc.last_error==EBUSY&&e.executed==0);destroy_env(&sc,&e,true);++scenarios;
    init_env(&sc,&e);e.ready=false;CHECK(rtwn8723be_btc_native_execute(&sc,&event)==ENXIO);CHECK(e.executed==0);destroy_env(&sc,&e,true);++scenarios;
}
static void unwind(void)
{
    struct rtwn8723be_softc sc;struct test_env e;struct btc_model *m=calloc(1,sizeof(*m));struct btc_coexist context;
    memset(&sc,0,sizeof(sc));memset(&e,0,sizeof(e));btc_model_init(m,&context,1,0,1);context.adapter=&sc;
    fail_create=true;CHECK(rtwn8723be_btc_native_init(&sc,&context,&owner,&e)==ENOMEM);CHECK(!sc.sc_btc.initialized&&!sc.sc_btc.engine.prepared&&!sc.sc_btc.workqueue);
    fail_create=false;free(m);++scenarios;
}
int main(int argc,char **argv)
{
    if(argc==2&&!strcmp(argv[1],"copy-only")){copied_info();return 0;}
    CHECK(argc==1);copied_info();stop_race();overflow();provider_fault();guards();unwind();
    CHECK(queues_created==queues_destroyed);printf("BTC_NATIVE_SCENARIOS=%u CHECKS=%u\n",scenarios,checks);return 0;
}
