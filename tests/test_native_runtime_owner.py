#!/usr/bin/env python3
"""Execute the real native runtime owner and full Linux controller.

Hardware, interface/RX publication and target kernel primitives are explicit
instrumented boundaries. This is C11/UBSan ownership evidence, not OS ABI,
real SMP, firmware, radio, BTC/DM provider or physical WLAN acceptance.
"""
from runtime_owner_fixture import inputs, program, execute, replace_once, function

TEST = r'''

#if MISSING_OP != 0
int main(void) {
    struct rtwn8723be_softc sc;fresh(&sc);configure(&sc);
    CHECK(rtwn8723be_runtime_probe_ready(&sc)==ENOSYS);
    sc.sc_linux.stage=R23BE_STAGE_IEEE80211_REGISTER;
    CHECK(rtwn8723be_netbsd_register_ieee80211(&sc)==ENOSYS && event_count==0);
    struct rtwn8723be_runtime_context *ctx=sc.sc_runtime_owner.context;
    const struct rtwn8723be_net80211_methods methods={rtwn8723be_runtime_hw_start,rtwn8723be_runtime_hw_stop,rtwn8723be_net80211_tx_start};
    CHECK(rtwn8723be_net80211_register(&sc.sc_net80211,&sc,&methods)==0);
    CHECK(rtwn8723be_rx_binding_init(&ctx->rx,&sc.sc_net80211,&ctx->firmware)==0);
    CHECK(rtwn8723be_datapath_prepare(&ctx->dp,&sc,&ctx->rx.dispatch,NULL,NULL)==0);
    sc.sc_linux.stage=R23BE_STAGE_PROBED;sc.sc_ih=&sc;sc.sc_soft_ih=&sc.sc_irq_lock;sc.sc_pihp=(pci_intr_handle_t *)&sc.sc_irq_epoch;
    sc.sc_mapped=true;sc.sc_core_initialized=true;sc.sc_rings_allocated=true;sc.sc_dma_32bit=true;sc.sc_dmat=&sc;
    sc.sc_h2c.initialized=true;sc.sc_h2c.sc=&sc;
    sc.sc_rfkill_native.initialized=true;sc.sc_rfkill_native.active=true;sc.sc_rfkill_native.wq=&sc;
    event_count=0;
    CHECK(rtwn8723be_runtime_hw_start(&sc)==ENOSYS);
    CHECK(hardware_calls==0 && event_count==0 && pci_effects==0 && !sc.sc_linux.started);
    retire(&sc);
    (void)hisr_value;(void)hisre_value;(void)hsisr_value;(void)ack_value;
    (void)mmio_reads;(void)mmio_writes;(void)soft_schedules;(void)read_hook;(void)second_lwp;
    puts("RTL_NATIVE_RUNTIME_MISSING_OPS_NO_EFFECTS_OK");return 0;
}
#else

static void test_baseline(void) {
    struct rtwn8723be_softc sc;fresh(&sc);probed(&sc);
    struct rtwn8723be_runtime_context *ctx=sc.sc_runtime_owner.context;
    CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
    CHECK(sc.sc_linux.stage==R23BE_STAGE_RUNNING && sc.sc_linux.started && sc.sc_hal_started);
    CHECK(sc.sc_datapath==&ctx->dp && ctx->dp.tx_enabled);
    sc.sc_ec.ec_if.if_flags=IFF_RUNNING|IFF_OACTIVE;sc.sc_ec.ec_if.if_timer=7;
    CHECK(rtwn8723be_runtime_hw_stop(&sc)==0);
    CHECK(sc.sc_linux.stage==R23BE_STAGE_STOPPED && !sc.sc_linux.started && !sc.sc_hal_started);
    CHECK(sc.sc_net80211.registered && sc.sc_datapath==&ctx->dp && sc.sc_rx_binding==&ctx->rx);
    CHECK(sc.sc_ih!=NULL && sc.sc_soft_ih!=NULL && sc.sc_pihp!=NULL);
    CHECK(sc.sc_ec.ec_if.if_flags==0 && sc.sc_ec.ec_if.if_timer==0);
    CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
    CHECK(sc.sc_runtime_owner.context==ctx && sc.sc_datapath==&ctx->dp);
    CHECK(rtwn8723be_runtime_hw_stop(&sc)==0);
    retire(&sc);CHECK(allocated==freed);
}

static void test_configuration(void) {
    struct rtwn8723be_softc sc;struct rtwn8723be_c2h_handlers h,bad;
    fresh(&sc);h=handlers(&sc);
    CHECK(rtwn8723be_runtime_owner_configure(NULL,&h)==EINVAL);
    CHECK(rtwn8723be_runtime_owner_configure(&sc,NULL)==EINVAL);
    bad=h;bad.arg=&first_lwp;CHECK(rtwn8723be_runtime_owner_configure(&sc,&bad)==EINVAL);
#define BAD_HANDLER(field) do { bad=h;bad.field=NULL;CHECK(rtwn8723be_runtime_owner_configure(&sc,&bad)==EINVAL);CHECK(sc.sc_runtime_owner.context==NULL); } while(0)
    BAD_HANDLER(tx_report);BAD_HANDLER(ra_report);BAD_HANDLER(bt_info);BAD_HANDLER(bt_mp);
#undef BAD_HANDLER
    fail_allocation=true;CHECK(rtwn8723be_runtime_owner_configure(&sc,&h)==ENOMEM);
    CHECK(sc.sc_runtime_owner.context==NULL);fail_allocation=false;
    CHECK(rtwn8723be_runtime_owner_configure(&sc,&h)==0);
    struct rtwn8723be_runtime_context *ctx=sc.sc_runtime_owner.context;
    memset(&h,0,sizeof(h));
    CHECK(ctx->firmware.arg==&sc && ctx->firmware.tx_report==c2h && ctx->firmware.bt_mp==c2h);
    h=handlers(&sc);CHECK(rtwn8723be_runtime_owner_configure(&sc,&h)==EALREADY);
    CHECK(sc.sc_runtime_owner.context==ctx);
    CHECK(rtwn8723be_runtime_probe_ready(&sc)==ENOSYS);
    bind_providers(&sc);CHECK(rtwn8723be_runtime_probe_ready(&sc)==0);
    CHECK(hardware_calls==0 && pci_effects==0 && event_count==0);
    struct rtwn8723be_calibration_owner cal=calibration;
    struct rtwn8723be_hw_disable_owner off=disable_owner;
#define BAD_CAL(field) do { cal=calibration;cal.field=NULL;sc.sc_calibration_owner=&cal;CHECK(rtwn8723be_runtime_probe_ready(&sc)==ENOSYS); } while(0)
    BAD_CAL(acquire);BAD_CAL(ready);BAD_CAL(scan_active);BAD_CAL(release);
#undef BAD_CAL
    sc.sc_calibration_owner=&calibration;
#define BAD_OFF(field) do { off=disable_owner;off.field=NULL;sc.sc_hw_disable_owner=&off;CHECK(rtwn8723be_runtime_probe_ready(&sc)==ENOSYS); } while(0)
    BAD_OFF(acquire);BAD_OFF(ready);BAD_OFF(release);
#undef BAD_OFF
    sc.sc_hw_disable_owner=&disable_owner;
    CHECK(rtwn8723be_runtime_probe_ready(&sc)==0 && hardware_calls==0);
    retire(&sc);
}
static void test_context_and_claim(void) {
    struct rtwn8723be_softc sc;struct rtwn8723be_c2h_handlers h;
    fresh(&sc);h=handlers(&sc);
    for(int mode=1;mode<=3;mode++) {
        in_hard=mode==1;in_soft=mode==2;in_pserialize=mode==3;
        CHECK(rtwn8723be_runtime_owner_configure(&sc,&h)==EWOULDBLOCK);
        CHECK(rtwn8723be_runtime_probe_ready(&sc)==EWOULDBLOCK);
        CHECK(rtwn8723be_runtime_hw_start(&sc)==EWOULDBLOCK);
        CHECK(rtwn8723be_runtime_hw_stop(&sc)==EWOULDBLOCK);
        CHECK(rtwn8723be_runtime_owner_fini(&sc)==EWOULDBLOCK);
    }
    in_hard=false;in_soft=false;in_pserialize=false;
    CHECK(sc.sc_runtime_owner.context==NULL && event_count==0);
    configure(&sc);
    struct rtwn8723be_runtime_owner *o=&sc.sc_runtime_owner;
#define CLAIM_BUSY() do { CHECK(rtwn8723be_runtime_probe_ready(&sc)==EBUSY);CHECK(rtwn8723be_runtime_hw_start(&sc)==EBUSY);CHECK(rtwn8723be_runtime_hw_stop(&sc)==EBUSY);CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY); } while(0)
    o->io_depth=1;CLAIM_BUSY();o->io_depth=0;
    o->operation=R23BE_RUNTIME_START;CLAIM_BUSY();o->operation=R23BE_RUNTIME_NONE;
    o->operation_lwp=&second_lwp;CLAIM_BUSY();o->operation_lwp=NULL;
    o->closing=true;CLAIM_BUSY();o->closing=false;
    mutex_enter(&o->io_lock);CLAIM_BUSY();mutex_exit(&o->io_lock);
    mutex_enter(&o->lifecycle_lock);CLAIM_BUSY();mutex_exit(&o->lifecycle_lock);
    o->lifecycle_lock.held=true;o->lifecycle_lock.holder=&second_lwp;CLAIM_BUSY();
    o->lifecycle_lock.held=false;o->lifecycle_lock.holder=NULL;
#undef CLAIM_BUSY
    CHECK(o->operation==R23BE_RUNTIME_NONE && o->operation_lwp==NULL);
    CHECK(event_count==0 && hardware_calls==0);retire(&sc);
}
static void test_publication_retention(void) {
    struct rtwn8723be_softc sc;fresh(&sc);
    struct rtwn8723be_c2h_handlers h=handlers(&sc);
    CHECK(rtwn8723be_runtime_owner_configure(&sc,&h)==0);
    struct rtwn8723be_runtime_context *ctx=sc.sc_runtime_owner.context;
    unsigned int prior_freed=freed,prior_destroyed=destroyed;
#define LIVE(field,value,zero) do { sc.field=(value);CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY);CHECK(sc.sc_runtime_owner.context==ctx && sc.sc_runtime_owner.initialized);CHECK(freed==prior_freed && destroyed==prior_destroyed);sc.field=(zero); } while(0)
    LIVE(sc_net80211.registered,true,false);LIVE(sc_net80211.sc,&sc,NULL);
    LIVE(sc_net80211.tx_busy,true,false);LIVE(sc_net80211.tx_key_update_depth,1,0);
    LIVE(sc_net80211.tx_pending_m,(struct mbuf *)&sc,NULL);
    LIVE(sc_net80211.tx_pending_ni,(struct ieee80211_node *)&sc,NULL);
    LIVE(sc_irq_dispatch_ready,true,false);LIVE(sc_irq_arg,&sc,NULL);
    LIVE(sc_irq_dispatch.rx,fake_irq_rx,NULL);LIVE(sc_irq_dispatch.tx_done,fake_irq_tx,NULL);
    LIVE(sc_irq_dispatch.power_event,fake_irq_power,NULL);
    LIVE(sc_ih,&sc,NULL);LIVE(sc_soft_ih,&sc,NULL);
    LIVE(sc_pihp,(pci_intr_handle_t *)&sc,NULL);
    LIVE(sc_irq_requested,true,false);LIVE(sc_irq_enabled,true,false);
    LIVE(sc_irq_pending[0],1,0);LIVE(sc_irq_pending[1],1,0);
    LIVE(sc_rfkill_native.initialized,true,false);LIVE(sc_rfkill_native.active,true,false);
    LIVE(sc_rfkill_native.wq,&sc,NULL);LIVE(sc_rfkill_native.work_queued,true,false);
    LIVE(sc_h2c.initialized,true,false);LIVE(sc_h2c.sc,&sc,NULL);
    LIVE(sc_h2c.state.firmware_ready,true,false);
    LIVE(sc_btc.initialized,true,false);LIVE(sc_btc.workqueue,&sc,NULL);
    LIVE(sc_btc.owner,&sc,NULL);LIVE(sc_btc.owner_arg,&sc,NULL);
    LIVE(sc_btc.worker,&sc,NULL);LIVE(sc_btc.calls,1,0);LIVE(sc_btc.count,1,0);LIVE(sc_btc.scheduled,true,false);
    LIVE(sc_btc_mp.initialized,true,false);LIVE(sc_btc_mp.active,true,false);
    LIVE(sc_btc_mp.busy,true,false);LIVE(sc_btc_mp.pending,true,false);
    LIVE(sc_rfchange_inprogress,true,false);LIVE(sc_initial_pci_saved,true,false);
    LIVE(sc_mapped,true,false);LIVE(sc_core_initialized,true,false);LIVE(sc_rings_allocated,true,false);
    LIVE(sc_dmat_owned,true,false);LIVE(sc_dma_32bit,true,false);LIVE(sc_hal_started,true,false);
    LIVE(sc_linux.stage,R23BE_STAGE_STOPPING,R23BE_STAGE_IDLE);
    LIVE(sc_linux.started,true,false);LIVE(sc_linux.fw_ready,true,false);
    LIVE(sc_linux.mac_func_enable,true,false);LIVE(sc_linux.being_init_adapter,true,false);
    LIVE(sc_calibration_owner,&calibration,NULL);LIVE(sc_calibration_owner_arg,&sc,NULL);
    LIVE(sc_hw_disable_owner,&disable_owner,NULL);LIVE(sc_hw_disable_owner_arg,&sc,NULL);
#undef LIVE
#define PRIVATE(field,value,zero) do { ctx->field=(value);CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY);CHECK(sc.sc_runtime_owner.context==ctx && freed==prior_freed && destroyed==prior_destroyed);ctx->field=(zero); } while(0)
    PRIVATE(dp.sc,&sc,NULL);PRIVATE(dp.rx.arg,ctx,NULL);PRIVATE(dp.rx.frame,fake_rx,NULL);
    PRIVATE(dp.rx.c2h,fake_rx,NULL);PRIVATE(dp.tx_enabled,true,false);PRIVATE(dp.stop_pending,true,false);
    PRIVATE(dp.rx_callback_active,1,0);PRIVATE(dp.tx_callback_active,1,0);PRIVATE(dp.tx_start_active,1,0);
    PRIVATE(rx.net,&sc.sc_net80211,NULL);PRIVATE(rx.dispatch.arg,ctx,NULL);
    PRIVATE(rx.dispatch.frame,fake_rx,NULL);PRIVATE(rx.dispatch.c2h,fake_rx,NULL);
    PRIVATE(rx.firmware.arg,ctx,NULL);PRIVATE(rx.firmware.tx_report,c2h,NULL);
    PRIVATE(rx.firmware.ra_report,c2h,NULL);PRIVATE(rx.firmware.bt_info,c2h,NULL);PRIVATE(rx.firmware.bt_mp,c2h,NULL);
#undef PRIVATE
    /* Inconsistent initialized=false must not dereference even a poison ctx. */
    sc.sc_runtime_owner.initialized=false;sc.sc_runtime_owner.context=(struct rtwn8723be_runtime_context *)(uintptr_t)1;
    CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY);
    CHECK(sc.sc_runtime_owner.context==(struct rtwn8723be_runtime_context *)(uintptr_t)1);
    sc.sc_runtime_owner.context=ctx;sc.sc_runtime_owner.initialized=true;
    CHECK(freed==prior_freed && destroyed==prior_destroyed);retire(&sc);
}
static void reenter(struct rtwn8723be_softc *sc) {
    boundary_hook=NULL;
    unsigned int n=event_count, f=freed,d=destroyed;
    CHECK(rtwn8723be_runtime_hw_start(sc)==EBUSY);
    CHECK(rtwn8723be_runtime_hw_stop(sc)==EBUSY);
    CHECK(rtwn8723be_runtime_probe_ready(sc)==EBUSY);
    CHECK(rtwn8723be_runtime_owner_fini(sc)==EBUSY);
    CHECK(event_count==n && freed==f && destroyed==d);
}
static void test_registration(void) {
    struct rtwn8723be_softc sc;
    for(int failure=1;failure<=3;failure++) {
        fresh(&sc);configure(&sc);sc.sc_linux.stage=R23BE_STAGE_IEEE80211_REGISTER;fail_module=failure;
        CHECK(rtwn8723be_netbsd_register_ieee80211(&sc)==EIO);
        CHECK(!sc.sc_net80211.registered && sc.sc_rx_binding==NULL && sc.sc_datapath==NULL);
        CHECK(!sc.sc_runtime_owner.context->faulted);
        CHECK(sc.sc_runtime_owner.context!=NULL);
        if(failure==1)CHECK(event_count==1 && events[0]==EV_REGISTER);
        if(failure==2)CHECK(event_count==3 && events[2]==EV_UNREGISTER);
        if(failure==3)CHECK(event_count==5 && events[3]==EV_RX_FINI && events[4]==EV_UNREGISTER);
        retire(&sc);
    }
    for(int fail=0;fail<=3;fail++) {
        fresh(&sc);configure(&sc);sc.sc_linux.stage=R23BE_STAGE_IEEE80211_REGISTER;
        fail_module=3;partial_prepare=true;fail_compensator=fail;
        CHECK(rtwn8723be_netbsd_register_ieee80211(&sc)==(fail ? EBUSY:EIO));
        if(fail==0) {
            CHECK(event_count==6 && events[3]==EV_DP_FINI && events[4]==EV_RX_FINI && events[5]==EV_UNREGISTER);
            CHECK(!sc.sc_runtime_owner.context->faulted);
        } else {
            CHECK(sc.sc_runtime_owner.context->faulted);
            CHECK(rtwn8723be_netbsd_register_ieee80211(&sc)==EIO);
            CHECK(sc.sc_net80211.registered);
            if(fail==1)CHECK(sc.sc_datapath!=NULL && sc.sc_rx_binding!=NULL && event_count==4);
            if(fail==2)CHECK(sc.sc_datapath==NULL && sc.sc_rx_binding!=NULL && event_count==5);
            if(fail==3)CHECK(sc.sc_datapath==NULL && sc.sc_rx_binding==NULL && event_count==6);
            unsigned int f=freed;CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY && freed==f);
        }
        retire(&sc);
    }
    fresh(&sc);configure(&sc);sc.sc_linux.stage=R23BE_STAGE_IEEE80211_REGISTER;
    fail_module=3;partial_prepare=true;false_compensator=true;
    CHECK(rtwn8723be_netbsd_register_ieee80211(&sc)==EIO);
    CHECK(sc.sc_runtime_owner.context->faulted && sc.sc_datapath!=NULL && event_count==4);
    retire(&sc);
    fresh(&sc);configure(&sc);sc.sc_linux.stage=R23BE_STAGE_IEEE80211_REGISTER;boundary_hook=reenter;
    CHECK(rtwn8723be_netbsd_register_ieee80211(&sc)==0);
    CHECK(sc.sc_runtime_owner.operation==R23BE_RUNTIME_NONE);retire(&sc);
}
static bool recorded(int event) {
    for(unsigned int i=0;i<event_count;i++)if(events[i]==event)return true;
    return false;
}
static void test_start_failures(void) {
    struct rtwn8723be_softc sc;
    const int failures[]={EV_RESET,EV_BT,EV_DISABLE_ASPM,EV_INIT_MAC,EV_FW,EV_HWCONFIG,EV_MARK_START};
    for(size_t i=0;i<sizeof(failures)/sizeof(failures[0]);i++) {
        fresh(&sc);probed(&sc);fail_hardware=failures[i];
        struct rtwn8723be_runtime_context *ctx=sc.sc_runtime_owner.context;
        CHECK(rtwn8723be_runtime_hw_start(&sc)==EIO);
        CHECK(ctx->faulted && sc.sc_runtime_owner.context==ctx && sc.sc_net80211.registered);
        CHECK(sc.sc_linux.stage!=R23BE_STAGE_STOPPED);
        CHECK(!recorded(EV_BEGIN_STOP) && !recorded(EV_HW_DISABLE));
        CHECK(rtwn8723be_runtime_hw_start(&sc)==EIO);
        CHECK(rtwn8723be_runtime_hw_stop(&sc)==EBUSY);
        CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY);
        retire(&sc);
    }
    fresh(&sc);probed(&sc);radio_on=false;
    CHECK(rtwn8723be_runtime_hw_start(&sc)==ENETDOWN);
    CHECK(hardware_calls==0 && !sc.sc_runtime_owner.context->faulted);retire(&sc);
    fresh(&sc);probed(&sc);radio_error=EAGAIN;
    CHECK(rtwn8723be_runtime_hw_start(&sc)==EAGAIN && hardware_calls==0);retire(&sc);
    fresh(&sc);probed(&sc);boundary_hook=reenter;
    CHECK(rtwn8723be_runtime_hw_start(&sc)==0);CHECK(rtwn8723be_runtime_hw_stop(&sc)==0);retire(&sc);
}
static void test_stop_ownership(void) {
    struct rtwn8723be_softc sc;
    for(int kind=0;kind<3;kind++) {
        fresh(&sc);probed(&sc);CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
        struct rtwn8723be_datapath *dp=sc.sc_datapath;
        if(kind==0)dp->rx_callback_active=1;else if(kind==1)dp->tx_callback_active=1;else dp->tx_start_active=1;
        event_count=0;
        CHECK(rtwn8723be_runtime_hw_stop(&sc)==EBUSY);
        CHECK(sc.sc_linux.stage==R23BE_STAGE_RUNNING && sc.sc_linux.started && dp->stop_pending && !dp->tx_enabled);
        CHECK(!recorded(EV_BT_HALT) && !recorded(EV_HW_DISABLE) && barriers==0);
        CHECK(!sc.sc_runtime_owner.context->faulted);
        dp->rx_callback_active=0;dp->tx_callback_active=0;dp->tx_start_active=0;
        CHECK(rtwn8723be_runtime_hw_stop(&sc)==0 && !dp->stop_pending);retire(&sc);
    }
    const int failures[]={EV_BT_HALT,EV_MARK_STOP,EV_RF_WAIT,EV_HW_DISABLE,EV_ASPM};
    for(size_t i=0;i<sizeof(failures)/sizeof(failures[0]);i++) {
        fresh(&sc);probed(&sc);CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
        fail_hardware=failures[i];
        CHECK(rtwn8723be_runtime_hw_stop(&sc)==EIO);
        CHECK(sc.sc_linux.stage==R23BE_STAGE_STOPPING && sc.sc_linux.started);
        CHECK(sc.sc_runtime_owner.context->faulted && sc.sc_net80211.registered && sc.sc_datapath!=NULL);
        CHECK(rtwn8723be_runtime_hw_start(&sc)==EIO);
        CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY);retire(&sc);
    }
}
static void test_outer_context(void) {
    struct rtwn8723be_softc sc;fresh(&sc);configure(&sc);
    unsigned int f=freed,d=destroyed;
    sc.sc_runtime_owner.io_depth=1;
    CHECK(rtwn8723be_netbsd_context_fini(&sc)==EBUSY && freed==f && destroyed==d);
    CHECK(sc.sc_irq_lock_initialized && sc.sc_rf_ps_lock_initialized);
    sc.sc_runtime_owner.io_depth=0;clear_external(&sc);
    CHECK(rtwn8723be_netbsd_context_fini(&sc)==0);
    CHECK(!sc.sc_runtime_owner.initialized && !sc.sc_irq_lock_initialized && !sc.sc_rf_ps_lock_initialized);
}


static void test_admission_with_valid_bridge(void) {
    struct rtwn8723be_softc sc;
    for(int running=0;running<=1;running++)for(int hold=0;hold<3;hold++) {
        fresh(&sc);probed(&sc);
        if(running)CHECK(rtwn8723be_runtime_hw_start(&sc)==0);
        struct rtwn8723be_runtime_owner *o=&sc.sc_runtime_owner;
        struct rtwn8723be_runtime_context *ctx=o->context;
        sc.sc_ec.ec_if.if_flags=running ? IFF_RUNNING|IFF_OACTIVE:0;
        sc.sc_ec.ec_if.if_timer=running ? 9:0;
        bool tx=ctx->dp.tx_enabled,hal=sc.sc_hal_started,requested=sc.sc_irq_requested,enabled=sc.sc_irq_enabled;
        unsigned int flags=sc.sc_ec.ec_if.if_flags,epoch=sc.sc_irq_epoch,h=hardware_calls,e=event_count,f=freed,d=destroyed;
        enum rtwn8723be_linux_stage stage=sc.sc_linux.stage;
        if(hold==0)o->io_depth=1;
        else if(hold==1)o->operation=R23BE_RUNTIME_START;
        else o->operation_lwp=&second_lwp;
        CHECK((running ? rtwn8723be_runtime_hw_stop(&sc):rtwn8723be_runtime_hw_start(&sc))==EBUSY);
        CHECK(o->context==ctx && sc.sc_linux.stage==stage);
        CHECK(ctx->dp.tx_enabled==tx && sc.sc_hal_started==hal);
        CHECK(sc.sc_irq_requested==requested && sc.sc_irq_enabled==enabled && sc.sc_irq_epoch==epoch);
        CHECK(sc.sc_ec.ec_if.if_flags==flags && sc.sc_ec.ec_if.if_timer==(running ? 9:0));
        CHECK(hardware_calls==h && event_count==e && freed==f && destroyed==d);
        o->io_depth=0;o->operation=R23BE_RUNTIME_NONE;o->operation_lwp=NULL;
        if(running)CHECK(rtwn8723be_runtime_hw_stop(&sc)==0);
        retire(&sc);
    }
}

static void test_held_outer_locks(void) {
    struct rtwn8723be_softc sc;
    for(int kind=0;kind<3;kind++) {
        fresh(&sc);probed(&sc);
        kmutex_t *lock=kind==0 ? &sc.sc_datapath->tx_lock:kind==1 ? &sc.sc_irq_lock:&sc.sc_rf_ps_lock;
        mutex_enter(lock);unsigned int h=hardware_calls,f=freed,d=destroyed;
        CHECK(rtwn8723be_runtime_hw_start(&sc)==EBUSY);
        CHECK(rtwn8723be_runtime_hw_stop(&sc)==EBUSY);
        CHECK(rtwn8723be_netbsd_context_fini(&sc)==EBUSY);
        CHECK(hardware_calls==h && freed==f && destroyed==d && mutex_owned(lock));
        mutex_exit(lock);retire(&sc);
    }
    for(int kind=0;kind<2;kind++) {
        fresh(&sc);configure(&sc);clear_external(&sc);
        kmutex_t *lock=kind ? &sc.sc_rf_ps_lock:&sc.sc_irq_lock;
        mutex_enter(lock);unsigned int f=freed,d=destroyed;
        CHECK(rtwn8723be_netbsd_context_fini(&sc)==EBUSY);
        CHECK(freed==f && destroyed==d && sc.sc_runtime_owner.context!=NULL);
        mutex_exit(lock);
        CHECK(rtwn8723be_netbsd_context_fini(&sc)==0);
    }
}
static void test_false_registration(void) {
    struct rtwn8723be_softc sc;
    for(int kind=1;kind<=3;kind++) {
        fresh(&sc);configure(&sc);sc.sc_linux.stage=R23BE_STAGE_IEEE80211_REGISTER;
        false_prepare_kind=kind;
        CHECK(rtwn8723be_netbsd_register_ieee80211(&sc)==(kind==3 ? EBUSY:EIO));
        CHECK(sc.sc_runtime_owner.context->faulted);
        if(kind==3)CHECK(sc.sc_net80211.registered && sc.sc_datapath!=NULL);
        else CHECK(!sc.sc_net80211.registered && sc.sc_datapath==NULL && sc.sc_rx_binding==NULL);
        retire(&sc);
    }
}
int main(void) {
    (void)second_lwp;(void)hisr_value;(void)hisre_value;(void)hsisr_value;(void)ack_value;
    (void)mmio_reads;(void)mmio_writes;(void)soft_schedules;(void)read_hook;
    test_configuration();test_context_and_claim();test_publication_retention();
    test_registration();test_false_registration();test_start_failures();
    test_stop_ownership();test_admission_with_valid_bridge();test_held_outer_locks();test_outer_context();test_baseline();
    CHECK(allocated==freed);puts("RTL_NATIVE_RUNTIME_OWNER_MATRIX_OK");return 0;
}

#endif
'''


def main():
    data=inputs()
    execute("runtime-matrix",program(data,TEST))
    for missing in (1,2,3):
        execute("runtime-missing-op-"+str(missing),program(data,TEST),
                definitions=("-DMISSING_OP="+str(missing),))

    mutants=(
        ("foreign-c2h-arg","runtime_handlers_ok","h->arg == sc","(sc != NULL && h->arg != NULL)"),
        ("missing-bt-c2h","runtime_handlers_ok","h->bt_mp != NULL","(h->bt_mp != NULL || h->bt_mp == NULL)"),
        ("missing-scan-provider","runtime_provider_ops_ready","cal->scan_active == NULL","false"),
        ("firmware-copy-lost","rtwn8723be_runtime_owner_configure","created->firmware = *firmware;","memset(&created->firmware,0,sizeof(created->firmware));"),
        ("immutable-config-overwritten","rtwn8723be_runtime_owner_configure","if (ctx != NULL) {","if (ctx != NULL && ctx->faulted) {"),
        ("io-lease-ignored","runtime_claim","owner->io_depth != 0","owner->io_depth == UINT32_MAX"),
        ("operation-ignored","runtime_claim","owner->operation != R23BE_RUNTIME_NONE","false"),
        ("softint-context-accepted","runtime_thread_ok","!cpu_softintr_p()","(!cpu_softintr_p() || cpu_softintr_p())"),
        ("borrowed-dp-lock-accepted","runtime_caller_locks_held","mutex_owned(&dp->tx_lock)","(false && mutex_owned(&dp->tx_lock))"),
        ("borrowed-irq-lock-accepted","runtime_caller_locks_held","mutex_owned(&sc->sc_irq_lock)","(false && mutex_owned(&sc->sc_irq_lock))"),
        ("pending-packet-owner-freed","runtime_publication_present","sc->sc_net80211.tx_pending_m != NULL","false"),
        ("private-callback-owner-freed","rtwn8723be_runtime_owner_fini","runtime_private_publication_present(owner->context)","(false && runtime_private_publication_present(owner->context))"),
        ("false-registration-accepted","rtwn8723be_netbsd_register_ieee80211","error == 0 && runtime_registration_owned(sc, ctx)","error == 0 || runtime_registration_owned(sc, ctx)"),
        ("failed-compensator-forgotten","rtwn8723be_netbsd_register_ieee80211","if (unwind_error != 0) {","if (false && unwind_error != 0) {"),
        ("partial-start-unquarantined","rtwn8723be_runtime_hw_start","if (error != 0) {\n        ctx->faulted = true;\n        goto out;\n    }","if (error != 0) {\n        ctx->faulted = false;\n        goto out;\n    }"),
        ("operation-never-released","runtime_release","owner->operation = R23BE_RUNTIME_NONE;","owner->operation = operation;"),
    )
    original=data["rtwn8723be_runtime_owner.c"]
    for label,name,old,new in mutants:
        body=function(original,name)
        changed=replace_once(body,old,new)
        owner=replace_once(original,body,changed)
        execute("runtime-mutant-"+label,program(data,TEST,owner=owner),
                expect_failure=True,target=name)
    # Complete start dependencies are insufficient if native STOP is missing.
    body=function(original,"runtime_provider_ops_ready")
    changed=replace_once(body,"if (error != 0)\n        return error;","if (false && error != 0)\n        return error;")
    owner=replace_once(original,body,changed)
    execute("runtime-mutant-missing-stop-preflight",program(data,TEST,owner=owner),
            definitions=("-DMISSING_OP=3",),expect_failure=True,target="runtime_provider_ops_ready")
    native=data["rtwn8723be_netbsd.c"]
    body=function(native,"rtwn8723be_netbsd_context_fini")
    changed=replace_once(body,"if (error != 0)\n        return error;","if (false && error != 0)\n        return error;")
    altered=replace_once(native,body,changed)
    execute("runtime-mutant-context-retention-bypassed",program(data,TEST,native=altered),
            expect_failure=True,target="rtwn8723be_netbsd_context_fini")
    print("RTL_NATIVE_RUNTIME_EXECUTED_MUTANTS=18")

    print("RTL_NATIVE_RUNTIME_OWNER_C11_UBSAN_OK")
if __name__=="__main__":
    main()
