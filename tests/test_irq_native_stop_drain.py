#!/usr/bin/env python3
"""Run actual native IRQ bodies and STOP drain orchestration under C11/UBSan.

The cross-CPU barrier is an instrumented boundary: one POSIX worker executes
the complete production softint, paused at its MMIO read. The barrier must
release and join that worker before hardware shutdown. This demonstrates
required ordering; it is not a NetBSD scheduler, IRQ or real SMP proof.
"""
from runtime_owner_fixture import inputs, program, execute, function, replace_once

TEST = r'''
#include <pthread.h>
static pthread_mutex_t pause_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t pause_condition=PTHREAD_COND_INITIALIZER;
static pthread_t soft_worker;
static bool soft_paused, soft_continue, soft_finished;
static void pause_hsisr(struct rtwn8723be_softc *sc) {
    (void)sc;
    CHECK(pthread_mutex_lock(&pause_mutex)==0);
    soft_paused=true;CHECK(pthread_cond_broadcast(&pause_condition)==0);
    while(!soft_continue)CHECK(pthread_cond_wait(&pause_condition,&pause_mutex)==0);
    CHECK(pthread_mutex_unlock(&pause_mutex)==0);
}
static void *run_softint(void *p) {
    curlwp=&second_lwp;in_soft=true;
    rtwn8723be_netbsd_softintr(p);
    in_soft=false;
    CHECK(pthread_mutex_lock(&pause_mutex)==0);soft_finished=true;
    CHECK(pthread_cond_broadcast(&pause_condition)==0);
    CHECK(pthread_mutex_unlock(&pause_mutex)==0);return NULL;
}
static void drain_worker(struct rtwn8723be_softc *sc) {
    (void)sc;
    CHECK(pthread_mutex_lock(&pause_mutex)==0);
    CHECK(soft_paused && !soft_finished);soft_continue=true;
    CHECK(pthread_cond_broadcast(&pause_condition)==0);
    CHECK(pthread_mutex_unlock(&pause_mutex)==0);
    CHECK(pthread_join(soft_worker,NULL)==0);
    CHECK(pthread_mutex_lock(&pause_mutex)==0);CHECK(soft_finished);
    CHECK(pthread_mutex_unlock(&pause_mutex)==0);
}
static void power_requires_soft_completion(struct rtwn8723be_softc *sc) {
    (void)sc;
    CHECK(pthread_mutex_lock(&pause_mutex)==0);CHECK(soft_finished);
    CHECK(pthread_mutex_unlock(&pause_mutex)==0);
}
static bool saw_event(int event) {
    for(unsigned int i=0;i<event_count;i++)if(events[i]==event)return true;
    return false;
}
static unsigned int first_event(int event) {
    for(unsigned int i=0;i<event_count;i++)if(events[i]==event)return i;
    CHECK(false);return 0;
}
static void test_giant_and_drain(void) {
    struct rtwn8723be_softc sc;
    for(int n=0;n<=3;n++) {
        fresh(&sc);probed(&sc);CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
        giant_count=n;event_count=0;
        CHECK(rtwn8723be_runtime_hw_stop(&sc)==0);
        CHECK(giant_count==n && barriers==1);
        CHECK(giant_unlocks==(n ? 1:0) && giant_restores==(n ? 1:0));
        CHECK(first_event(EV_MASK)<first_event(EV_BARRIER));
        CHECK(first_event(EV_BARRIER)<first_event(EV_RF_WAIT));
        CHECK(first_event(EV_RF_WAIT)<first_event(EV_HW_DISABLE));
        CHECK(sc.sc_ih!=NULL && sc.sc_soft_ih!=NULL && sc.sc_pihp!=NULL);
        CHECK(sc.sc_runtime_owner.context->irq_drained);
        CHECK(sc.sc_runtime_owner.context->drained_epoch==sc.sc_irq_epoch);
        giant_count=0;retire(&sc);
    }
}
static void test_barrier_validation(void) {
    struct rtwn8723be_softc sc;
    for(int injection=1;injection<=7;injection++) {
        fresh(&sc);probed(&sc);CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
        barrier_injection=injection;giant_count=3;event_count=0;
        CHECK(rtwn8723be_runtime_hw_stop(&sc)==EBUSY);
        CHECK(giant_count==3 && giant_unlocks==1 && giant_restores==1);
        CHECK(sc.sc_linux.stage==R23BE_STAGE_STOPPING && sc.sc_linux.started);
        CHECK(sc.sc_runtime_owner.context->faulted && !sc.sc_runtime_owner.context->irq_drained);
        CHECK(!saw_event(EV_HW_DISABLE));
        giant_count=0;retire(&sc);
    }
    fresh(&sc);probed(&sc);CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
    false_hal_stop=true;event_count=0;
    CHECK(rtwn8723be_runtime_hw_stop(&sc)==EBUSY);
    CHECK(sc.sc_hal_started && barriers==0 && !saw_event(EV_HW_DISABLE));
    retire(&sc);
}
static void retire_during_hard_read(struct rtwn8723be_softc *sc) {
    read_hook=NULL;CHECK(rtwn8723be_netbsd_disable_interrupt(sc)==0);
}

static void replace_generation_during_hard_read(struct rtwn8723be_softc *sc) {
    read_hook=NULL;
    CHECK(rtwn8723be_netbsd_disable_interrupt(sc)==0);
    CHECK(rtwn8723be_netbsd_enable_interrupt(sc)==0);
}

static void test_actual_irq(void) {
    struct rtwn8723be_softc sc;fresh(&sc);probed(&sc);
    CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
    sc.sc_sys_irq_mask=5;hsisr_value=0x20;
    hisr_value=R23BE_IMR_ROK|R23BE_IMR_BEDOK|R23BE_IMR_HSISR_IND_ON_INT;
    hisre_value=R23BE_IMR_RXFOVW;
    in_hard=true;CHECK(rtwn8723be_netbsd_intr(&sc)==1);in_hard=false;
    CHECK(soft_schedules==1 && sc.sc_irq_pending[0]==hisr_value && sc.sc_irq_pending[1]==hisre_value);
    CHECK(!sc.sc_irq_enabled && sc.sc_irq_requested);
    in_soft=true;rtwn8723be_netbsd_softintr(&sc);in_soft=false;
    CHECK(sc.sc_irq_pending[0]==0 && sc.sc_irq_pending[1]==0);
    CHECK(hsisr_value==0x25 && sc.sc_irq_requested && sc.sc_irq_enabled);
    CHECK(rtwn8723be_runtime_hw_stop(&sc)==0);retire(&sc);

    fresh(&sc);probed(&sc);CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
    hisr_value=R23BE_IMR_ROK;hisre_value=0;read_hook=retire_during_hard_read;
    unsigned int epoch=sc.sc_irq_epoch;ack_value=0;
    in_hard=true;CHECK(rtwn8723be_netbsd_intr(&sc)==0);in_hard=false;
    CHECK(sc.sc_irq_epoch==epoch+1 && ack_value==0 && soft_schedules==0);
    CHECK(!sc.sc_irq_requested && !sc.sc_irq_enabled && sc.sc_irq_pending[0]==0);
    CHECK(rtwn8723be_runtime_hw_stop(&sc)==0);retire(&sc);

    fresh(&sc);probed(&sc);CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
    hisr_value=R23BE_IMR_ROK;read_hook=replace_generation_during_hard_read;
    epoch=sc.sc_irq_epoch;ack_value=0;
    in_hard=true;CHECK(rtwn8723be_netbsd_intr(&sc)==0);in_hard=false;
    CHECK(sc.sc_irq_epoch==epoch+2 && ack_value==0 && soft_schedules==0);
    CHECK(sc.sc_irq_requested && sc.sc_irq_enabled && sc.sc_irq_pending[0]==0);
    CHECK(rtwn8723be_runtime_hw_stop(&sc)==0);retire(&sc);
}
static void test_queued_old_softint(void) {
    struct rtwn8723be_softc sc;fresh(&sc);probed(&sc);
    CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
    sc.sc_irq_pending[0]=R23BE_IMR_HSISR_IND_ON_INT;
    CHECK(rtwn8723be_netbsd_disable_interrupt(&sc)==0);
    unsigned int reads=mmio_reads,writes=mmio_writes;
    in_soft=true;rtwn8723be_netbsd_softintr(&sc);in_soft=false;
    CHECK(mmio_reads==reads && mmio_writes==writes && !sc.sc_irq_enabled);
    CHECK(rtwn8723be_runtime_hw_stop(&sc)==0);retire(&sc);
}
static void test_inflight_hsisr_before_poweroff(void) {
    struct rtwn8723be_softc sc;fresh(&sc);probed(&sc);
    CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
    soft_paused=false;soft_continue=false;soft_finished=false;
    sc.sc_irq_pending[0]=R23BE_IMR_HSISR_IND_ON_INT;hsisr_value=0x10;sc.sc_sys_irq_mask=3;
    read1_hook=pause_hsisr;barrier_hook=drain_worker;poweroff_hook=power_requires_soft_completion;
    CHECK(pthread_create(&soft_worker,NULL,run_softint,&sc)==0);
    CHECK(pthread_mutex_lock(&pause_mutex)==0);
    while(!soft_paused)CHECK(pthread_cond_wait(&pause_condition,&pause_mutex)==0);
    CHECK(!soft_finished);CHECK(pthread_mutex_unlock(&pause_mutex)==0);
    CHECK(sc.sc_irq_pending[0]==0); /* Complete real softint already took work. */
    event_count=0;giant_count=3;
    CHECK(rtwn8723be_runtime_hw_stop(&sc)==0);
    CHECK(soft_finished && hsisr_value==0x13 && hardware_off && giant_count==3);
    CHECK(first_event(EV_BARRIER)<first_event(EV_HW_DISABLE));
    giant_count=0;read1_hook=NULL;barrier_hook=NULL;poweroff_hook=NULL;retire(&sc);
}
static void test_drain_entry_context(void) {
    struct rtwn8723be_softc sc;fresh(&sc);probed(&sc);
    CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
    unsigned int writes=mmio_writes;
    CHECK(runtime_disable_interrupt_drain(&sc)==EBUSY);
    CHECK(mmio_writes==writes && barriers==0);
    for(int kind=1;kind<=3;kind++) {
        in_hard=kind==1;in_soft=kind==2;in_pserialize=kind==3;
        CHECK(runtime_disable_interrupt_drain(&sc)==EWOULDBLOCK);
        CHECK(rtwn8723be_runtime_hw_stop(&sc)==EWOULDBLOCK);
    }
    in_hard=false;in_soft=false;in_pserialize=false;
    CHECK(mmio_writes==writes && barriers==0);
    CHECK(rtwn8723be_runtime_hw_stop(&sc)==0);retire(&sc);
}
int main(void) {
    test_giant_and_drain();test_barrier_validation();test_actual_irq();
    test_queued_old_softint();test_inflight_hsisr_before_poweroff();test_drain_entry_context();
    CHECK(allocated==freed);puts("RTL_NATIVE_IRQ_STOP_DRAIN_MATRIX_OK");return 0;
}
'''

def main():
    data=inputs()
    execute("irq-stop-drain-matrix",program(data,TEST,irq=True),definitions=("-pthread",))

    original=data["rtwn8723be_runtime_owner.c"]
    mutations=(
        ("barrier-omitted","xc_barrier(XC_HIGHPRI_IPL(IPL_SOFTNET));","if (false) xc_barrier(XC_HIGHPRI_IPL(IPL_SOFTNET));"),
        ("invalid-hardware-ipl","xc_barrier(XC_HIGHPRI_IPL(IPL_SOFTNET));","xc_barrier(XC_HIGHPRI_IPL(IPL_NET));"),
        ("giant-not-dropped","KERNEL_UNLOCK_ALL(NULL, &giant_count);","if (false) KERNEL_UNLOCK_ALL(NULL, &giant_count);"),
        ("giant-depth-lost","KERNEL_LOCK(giant_count, NULL);","KERNEL_LOCK(giant_count != 0 ? 1 : 0, NULL);"),
        ("new-epoch-accepted","sc->sc_irq_epoch == epoch","sc->sc_irq_epoch >= epoch"),
        ("rearmed-owner-accepted","valid = sc->sc_irq_epoch == epoch && !sc->sc_irq_requested &&","valid = sc->sc_irq_epoch == epoch &&"),
        ("enabled-owner-accepted","!sc->sc_irq_enabled && sc->sc_irq_pending[0] == 0 &&","(sc->sc_irq_enabled || !sc->sc_irq_enabled) && sc->sc_irq_pending[0] == 0 &&"),
        ("pending-work-accepted","!sc->sc_irq_enabled && sc->sc_irq_pending[0] == 0 &&","!sc->sc_irq_enabled && (sc->sc_irq_pending[0] == 0 || sc->sc_irq_pending[0] != 0) &&"),
        ("replacement-handle-accepted","sc->sc_ih == ih","(sc->sc_ih != NULL && ih != NULL)"),
        ("false-hal-stop-accepted","sc->sc_hal_started ||","(false && sc->sc_hal_started) ||"),
    )
    for label,old,new in mutations:
        body=function(original,"runtime_disable_interrupt_drain")
        altered=replace_once(original,body,replace_once(body,old,new))
        execute("irq-mutant-"+label,program(data,TEST,irq=True,owner=altered),
                definitions=("-pthread",),expect_failure=True,target="runtime_disable_interrupt_drain")
    native=data["rtwn8723be_netbsd.c"]
    changes=(
        ("permanent-mask-revocation-lost","rtwn8723be_netbsd_disable_interrupt","sc->sc_irq_requested = false;","sc->sc_irq_requested = true;"),
        ("old-hard-epoch-acknowledged","rtwn8723be_netbsd_intr","irq_epoch != sc->sc_irq_epoch","(false && irq_epoch != sc->sc_irq_epoch)"),
        ("actual-hsisr-write-lost","rtwn8723be_netbsd_softintr","rtwn8723be_write_1(sc, R23BE_REG_HSISR,","if (false) rtwn8723be_write_1(sc, R23BE_REG_HSISR,"),
    )
    for label,name,old,new in changes:
        body=function(native,name)
        altered=replace_once(native,body,replace_once(body,old,new))
        execute("irq-mutant-"+label,program(data,TEST,irq=True,native=altered),
                definitions=("-pthread",),expect_failure=True,target=name)
    print("RTL_NATIVE_IRQ_EXECUTED_MUTANTS=13")

    print("RTL_NATIVE_IRQ_STOP_DRAIN_C11_UBSAN_OK")
if __name__=="__main__":
    main()
