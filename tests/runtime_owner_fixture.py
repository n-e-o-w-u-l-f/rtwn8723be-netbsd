#!/usr/bin/env python3
"""Compile actual runtime orchestration with explicit NetBSD/module boundaries.

The real Linux lifecycle controller, runtime owner, datapath admission and IRQ
bodies are compiled. Mutexes, Giant, allocation, interface/RX publication and
hardware providers are instrumented boundaries, not an OS ABI or SMP emulator.
The new policy configuration, policy storage and portable DM objects are real.
BTC execution/board construction remain explicit instrumented boundaries in
this older registration/IRQ suite; the provider suite covers their real chain.
Generated files and child working directories stay in TMPDIR; cores are disabled.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FLAGS = ("-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=undefined", "-fno-sanitize-recover=all")

def function(source, name):
    expression = re.compile(
        r"(?m)^(?:static\s+)?(?:int|void|bool)\s*\n" +
        re.escape(name) + r"\([^;{}]*\)\n\{")
    matches = list(expression.finditer(source))
    assert len(matches) == 1, (name, len(matches))
    match = matches[0]
    return source[match.start():source.index("\n}\n", match.end()) + 3]

def structure(source, name):
    match = re.search(r"(?m)^struct " + re.escape(name) + r"\s*\{", source)
    assert match, name
    return source[match.start():source.index("\n};", match.end()) + 3]

def without_includes(source):
    return re.sub(r"(?m)^(?:#include[^\n]*|__KERNEL_RCSID[^\n]*)\n", "", source)

def replace_once(source, old, new):
    assert source.count(old) == 1, (old, source.count(old))
    changed = source.replace(old, new, 1)
    assert changed != source
    return changed

def inputs():
    paths = (
        "rtwn8723be_runtime_owner.c", "rtwn8723be_runtime_owner.h",
        "rtwn8723be_linux_state.c", "rtwn8723be_linux_state.h",
        "rtwn8723be_netbsd.c", "rtwn8723be_netbsd.h",
        "rtwn8723be_datapath.c", "rtwn8723be_datapath.h",
        "rtwn8723be_rx_binding.h", "rtwn8723be_rx_native.h",
        "rtwn8723be_c2h.h", "rtwn8723be_net80211.h",
        "rtwn8723be_calibration_native.h", "rtwn8723be_hw_disable_native.h",
        "rtwn8723be_f16_1.h",
        "rtwn8723be_net80211_state.h", "rtwn8723be_irq_pending.h",
        "rtwn8723be_btc_native.h", "rtwn8723be_btc_engine.h",
        "rtwn8723be_btc_context.h", "rtwn8723be_btc_policy.h",
        "rtwn8723be_dm.h", "rtwn8723be_thermal.h", "rtwn8723be_phy_exec.h",
    )
    return {p: (SRC / p).read_text() for p in paths}

PRELUDE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include "rtwn8723be_linux_state.h"
#include "rtwn8723be_net80211_state.h"
#include "rtwn8723be_irq_pending.h"
#include "rtwn8723be_btc_engine.h"
#include "rtwn8723be_btc_context.h"
#include "rtwn8723be_btc_policy.h"
#include "rtwn8723be_btc_providers_native.h"
#include "rtwn8723be_dm.h"
#include "rtwn8723be_phy_exec.h"
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FIXTURE_ASSERT:%s:%d:%s\n", __FILE__, __LINE__, #x); exit(97); } } while (0)
/* Release-style project assertions: conditions are typechecked, not evaluated. */
#define KASSERT(x) ((void)sizeof(x))
#define MUTEX_DEFAULT 0
/* Actual target x86 intrdefs.h values; IPL_NET is the compatibility IPL_VM. */
#define IPL_NONE 0
#define IPL_SOFTCLOCK 2
#define IPL_SOFTBIO 3
#define IPL_SOFTNET 4
#define IPL_SOFTSERIAL 5
#define IPL_NET 6
#define SOFTINT_NET 3
#define KM_NOSLEEP 0
#define IFF_RUNNING 0x40
#define IFF_OACTIVE 0x400
struct lwp { int identity; };
static struct lwp first_lwp = {1}, second_lwp = {2};
static _Thread_local struct lwp *curlwp = &first_lwp;
typedef struct { bool initialized, held; int ipl; struct lwp *holder; } kmutex_t;
typedef unsigned int pci_intr_handle_t;
typedef size_t bus_size_t;
typedef struct { int unused; } kcondvar_t;
struct work { int unused; };
struct workqueue { int unused; };
struct ifnet { unsigned int if_flags; int if_timer; };
struct mbuf;
struct ieee80211_node;
struct ieee80211com;
struct rtwn8723be_softc;
struct rtwn8723be_rx_packet;
struct rtwn8723be_c2h_event;
struct rtwn8723be_calibration_inputs;
struct rtwn8723be_calibration_state;
struct rtwn8723be_calibration_context;
struct rtwn8723be_hw_disable_inputs;
struct rtwn8723be_hw_disable_state;
static _Thread_local bool in_hard, in_soft, in_pserialize;
static bool fail_allocation;
static _Thread_local int giant_count;
static int giant_unlocks, giant_restores, barriers;
static unsigned int allocated, freed, destroyed, hardware_calls, pci_effects;
static unsigned int event_count;
static int events[512], fail_module, fail_compensator, fail_hardware;
static int false_prepare_kind;
static bool partial_prepare, false_compensator, radio_on = true, fail_dp_start;
static int radio_error, barrier_injection;
static void (*boundary_hook)(struct rtwn8723be_softc *);
static void (*barrier_hook)(struct rtwn8723be_softc *);
static struct rtwn8723be_softc *active_sc;
static uint32_t hisr_value, hisre_value, ack_value;
static uint8_t hsisr_value;
static unsigned int mmio_reads, mmio_writes, soft_schedules;
static bool hardware_off;
static void (*read_hook)(struct rtwn8723be_softc *);
static void (*read1_hook)(struct rtwn8723be_softc *);
static void (*poweroff_hook)(struct rtwn8723be_softc *);
static bool false_hal_stop;
static void mutex_init(kmutex_t *m, int type, int ipl) {
    (void)type; CHECK(!m->initialized); m->initialized=true; m->held=false; m->holder=NULL; m->ipl=ipl;
}
static bool mutex_owned(kmutex_t *m) { return m->initialized && m->held && m->holder == curlwp; }
static int mutex_tryenter(kmutex_t *m) {
    CHECK(m->initialized); if (m->held) return 0;
    m->held=true; m->holder=curlwp; return 1;
}
static void mutex_enter(kmutex_t *m) { CHECK(mutex_tryenter(m)); }
static void mutex_exit(kmutex_t *m) { CHECK(mutex_owned(m)); m->held=false; m->holder=NULL; }
static void mutex_destroy(kmutex_t *m) { CHECK(m->initialized && !m->held); m->initialized=false; destroyed++; }
static bool cpu_intr_p(void) { return in_hard; }
static bool cpu_softintr_p(void) { return in_soft; }
static bool pserialize_not_in_read_section(void) { return !in_pserialize; }
static void *kmem_zalloc(size_t, int);
static void kmem_free(void *, size_t);
static bool kernel_locked_p(void) { return giant_count != 0; }
static void kernel_unlock_all(int *n) { CHECK(n != NULL); *n=giant_count; giant_count=0; giant_unlocks++; }
static void kernel_lock(int n) { CHECK(n>=0); if (n!=0) { giant_count+=n; giant_restores++; } }
#define KERNEL_LOCKED_P() kernel_locked_p()
#define KERNEL_UNLOCK_ALL(l,p) do { (void)(l); kernel_unlock_all(p); } while (0)
#define KERNEL_LOCK(n,l) do { (void)(l); kernel_lock(n); } while (0)
/* Exact allowable target xc_encode_ipl mapping; hardware IPL_NET is invalid. */
static unsigned int xc_encode_ipl(int ipl) {
    switch (ipl) {
    case IPL_SOFTSERIAL:return 0;
    case IPL_SOFTNET:return 0x100;
    case IPL_SOFTBIO:return 0x200;
    case IPL_SOFTCLOCK:return 0x300;
    default:CHECK(false);return 0;
    }
}
#define XC_HIGHPRI_IPL(ipl) (1U | xc_encode_ipl(ipl))
static void xc_barrier(unsigned int);
static void delay(unsigned int);
uint32_t rtwn8723be_netbsd_get_bbreg(struct rtwn8723be_softc *, bus_size_t, uint32_t);
int rtwn8723be_btc_mp_native_stop(struct rtwn8723be_softc *);
static void rtwn8723be_write_4(struct rtwn8723be_softc *, uint32_t, uint32_t);
static void __attribute__((unused)) rtwn8723be_write_1(struct rtwn8723be_softc *, uint32_t, uint8_t);
static uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *, uint32_t);
static uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *, uint32_t);
static void softint_schedule(void *);
'''

TYPES = r'''
struct rtwn8723be_net80211 {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_net80211_methods methods;
    bool registered, tx_busy;
    unsigned int tx_key_update_depth;
    struct mbuf *tx_pending_m;
    struct ieee80211_node *tx_pending_ni;
    void (*tx_key_begin_saved)(struct ieee80211com *);
    void (*tx_key_end_saved)(struct ieee80211com *);
};
struct rtwn8723be_irq_dispatch {
    void (*rx)(void *);
    void (*tx_done)(void *, unsigned int);
    void (*power_event)(void *);
};
struct rtwn8723be_softc {
    struct rtwn8723be_linux_state sc_linux;
    struct rtwn8723be_runtime_owner sc_runtime_owner;
    struct rtwn8723be_net80211 sc_net80211;
    struct rtwn8723be_datapath *sc_datapath;
    struct rtwn8723be_rx_binding *sc_rx_binding;
    struct { bool initialized, active, work_queued; void *wq; } sc_rfkill_native;
    struct { bool initialized; struct rtwn8723be_softc *sc; struct { bool firmware_ready; } state; } sc_h2c;
    struct rtwn8723be_btc_native sc_btc;
    struct { bool initialized, active, busy, pending; } sc_btc_mp;
    const struct rtwn8723be_calibration_owner *sc_calibration_owner;
    void *sc_calibration_owner_arg;
    const struct rtwn8723be_hw_disable_owner *sc_hw_disable_owner;
    void *sc_hw_disable_owner_arg;
    kmutex_t sc_irq_lock, sc_rf_ps_lock;
    bool sc_irq_lock_initialized, sc_rf_ps_lock_initialized;
    bool sc_irq_requested, sc_irq_enabled, sc_irq_dispatch_ready;
    struct rtwn8723be_irq_dispatch sc_irq_dispatch;
    void *sc_irq_arg, *sc_ih, *sc_soft_ih;
    pci_intr_handle_t *sc_pihp;
    uint32_t sc_irq_pending[2], sc_irq_epoch, sc_irq_mask[2], sc_sys_irq_mask;
    bool sc_rfchange_inprogress, sc_initial_pci_saved, sc_mapped;
    bool sc_core_initialized, sc_rings_allocated, sc_dmat_owned, sc_dma_32bit, sc_hal_started;
    void *sc_dmat;
    size_t sc_mapsize;
    struct rtwn8723be_phy_identity sc_phy_identity;
    bool sc_bb_valid, sc_rf_chnlval_valid, sc_phy_identity_valid;
    bool sc_rf_path_count_valid, sc_xtal_valid, sc_bt_ant_valid, sc_package_valid;
    bool sc_btcoexist;
    uint8_t sc_rf_path_count, sc_xtal_cap, sc_btdm_ant_num;
    uint8_t sc_single_ant_path, sc_package_type;
    struct { struct ifnet ec_if; } sc_ec;
};
extern const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops;
int rtwn8723be_net80211_register(struct rtwn8723be_net80211 *, struct rtwn8723be_softc *, const struct rtwn8723be_net80211_methods *);
int rtwn8723be_net80211_unregister(struct rtwn8723be_net80211 *);
void rtwn8723be_net80211_tx_start(struct rtwn8723be_softc *, struct ifnet *);
int rtwn8723be_rx_binding_init(struct rtwn8723be_rx_binding *, struct rtwn8723be_net80211 *, const struct rtwn8723be_c2h_handlers *);
int rtwn8723be_rx_binding_fini(struct rtwn8723be_rx_binding *);
int rtwn8723be_datapath_prepare(struct rtwn8723be_datapath *, struct rtwn8723be_softc *, const struct rtwn8723be_rx_dispatch *, void (*)(void *, unsigned int, size_t), void *);
int rtwn8723be_datapath_unprepare(struct rtwn8723be_datapath *);
int rtwn8723be_datapath_start(struct rtwn8723be_datapath *);
bool rtwn8723be_datapath_running_ready(struct rtwn8723be_datapath *);
int rtwn8723be_datapath_begin_stop(struct rtwn8723be_datapath *, struct rtwn8723be_linux_state *);
int rtwn8723be_netbsd_disable_interrupt(void *);
int rtwn8723be_netbsd_enable_interrupt(void *);
int rtwn8723be_rfkill_native_radio_on(struct rtwn8723be_softc *, bool *);
'''

BOUNDARIES = r'''
enum { EV_REGISTER=1, EV_RX_INIT, EV_DP_PREPARE, EV_DP_FINI, EV_RX_FINI, EV_UNREGISTER,
       EV_RESET=10, EV_BT, EV_DISABLE_ASPM, EV_INIT_MAC, EV_FW, EV_HWCONFIG,
       EV_IRQ_ENABLE, EV_MARK_START, EV_BEGIN_STOP=30, EV_BT_HALT, EV_MARK_STOP,
       EV_MASK, EV_BARRIER, EV_RF_WAIT, EV_HW_DISABLE, EV_ASPM };
static void record(int event) { CHECK(event_count<512); events[event_count++]=event; }
static void boundary(struct rtwn8723be_softc *sc) {
    CHECK(!mutex_owned(&sc->sc_runtime_owner.lifecycle_lock));
    CHECK(!mutex_owned(&sc->sc_runtime_owner.io_lock));
    if (boundary_hook != NULL) boundary_hook(sc);
}
static void *kmem_zalloc(size_t n, int flags) {
    CHECK(flags==KM_NOSLEEP); CHECK(active_sc != NULL); boundary(active_sc);
    if (fail_allocation) return NULL;
    void *p=calloc(1,n); CHECK(p!=NULL); allocated++; return p;
}
static void kmem_free(void *p, size_t n) {
    (void)n; CHECK(p!=NULL); CHECK(active_sc!=NULL); boundary(active_sc);
    CHECK(active_sc->sc_runtime_owner.context==NULL); freed++; free(p);
}
static int fake_rx(void *arg, const uint8_t *data, size_t n, const struct rtwn8723be_rx_packet *pkt) {
    (void)arg;(void)data;(void)n;(void)pkt;return 0;
}
static void fake_irq_rx(void *arg) { (void)arg; }
static void fake_irq_tx(void *arg, unsigned int q) { (void)arg;(void)q; }
static void __attribute__((unused)) fake_irq_power(void *arg) { (void)arg; }
int rtwn8723be_net80211_register(struct rtwn8723be_net80211 *n, struct rtwn8723be_softc *sc, const struct rtwn8723be_net80211_methods *m) {
    boundary(sc);record(EV_REGISTER); CHECK(n==&sc->sc_net80211);
    if (fail_module==1) return EIO;
    n->sc=sc;n->methods=*m;n->registered=true; return 0;
}
int rtwn8723be_net80211_unregister(struct rtwn8723be_net80211 *n) {
    struct rtwn8723be_softc *sc=n->sc; CHECK(sc!=NULL);boundary(sc);record(EV_UNREGISTER);
    CHECK(sc->sc_datapath==NULL && sc->sc_rx_binding==NULL);
    if (fail_compensator==3) return EBUSY;
    if (!false_compensator) memset(n,0,sizeof(*n));
    return 0;
}
void rtwn8723be_net80211_tx_start(struct rtwn8723be_softc *sc, struct ifnet *ifp) { (void)sc;(void)ifp; }
int rtwn8723be_rx_binding_init(struct rtwn8723be_rx_binding *rx, struct rtwn8723be_net80211 *n, const struct rtwn8723be_c2h_handlers *h) {
    boundary(n->sc);record(EV_RX_INIT);
    if (fail_module==2) return EIO;
    rx->net=n;rx->firmware=*h;rx->dispatch.arg=rx;rx->dispatch.frame=fake_rx;rx->dispatch.c2h=fake_rx;
    n->sc->sc_rx_binding=rx;return 0;
}
int rtwn8723be_rx_binding_fini(struct rtwn8723be_rx_binding *rx) {
    struct rtwn8723be_softc *sc=rx->net->sc;boundary(sc);record(EV_RX_FINI);
    CHECK(sc->sc_datapath==NULL); if (fail_compensator==2) return EBUSY;
    if (!false_compensator) { sc->sc_rx_binding=NULL;memset(rx,0,sizeof(*rx)); } return 0;
}
int rtwn8723be_datapath_prepare(struct rtwn8723be_datapath *dp, struct rtwn8723be_softc *sc, const struct rtwn8723be_rx_dispatch *rx, void (*done)(void *,unsigned int,size_t), void *arg) {
    boundary(sc);record(EV_DP_PREPARE);
    if (fail_module==3 && !partial_prepare) return EIO;
    if (false_prepare_kind==1) return 0;
    dp->sc=sc;dp->rx=*rx;dp->prepared=true;dp->tx_complete=done;dp->tx_complete_arg=arg;
    mutex_init(&dp->tx_lock,MUTEX_DEFAULT,IPL_NET);
    sc->sc_datapath=dp;sc->sc_irq_arg=dp;sc->sc_irq_dispatch_ready=true;
    sc->sc_irq_dispatch.rx=fake_irq_rx;sc->sc_irq_dispatch.tx_done=fake_irq_tx;
    if(false_prepare_kind==2)dp->rx.arg=sc;
    if(false_prepare_kind==3)dp->tx_enabled=true;
    return fail_module==3 ? EIO : 0;
}
int rtwn8723be_datapath_unprepare(struct rtwn8723be_datapath *dp) {
    struct rtwn8723be_softc *sc=dp->sc;boundary(sc);record(EV_DP_FINI);
    if (fail_compensator==1) return EBUSY;
    if (!false_compensator) {
        if(dp->tx_enabled || dp->stop_pending || dp->rx_callback_active!=0 || dp->tx_callback_active!=0 || dp->tx_start_active!=0)return EBUSY;
        sc->sc_datapath=NULL;sc->sc_irq_arg=NULL;sc->sc_irq_dispatch_ready=false;
        memset(&sc->sc_irq_dispatch,0,sizeof(sc->sc_irq_dispatch));
        mutex_destroy(&dp->tx_lock);memset(dp,0,sizeof(*dp));
    } return 0;
}
int rtwn8723be_rfkill_native_radio_on(struct rtwn8723be_softc *sc, bool *on) {
    boundary(sc);*on=radio_on;return radio_error;
}
static int hardware(struct rtwn8723be_softc *sc, int event) {
    boundary(sc); hardware_calls++; record(event); return fail_hardware==event ? EIO:0;
}
static int step(void *p) { return hardware(p,90); }
static int reset_rings(void *p) { hardware_off=false;return hardware(p,EV_RESET); }
static int __attribute__((unused)) bt_prepare(void *p) { return hardware(p,EV_BT); }
static int disable_aspm(void *p) { return hardware(p,EV_DISABLE_ASPM); }
static int init_mac(void *p) { return hardware(p,EV_INIT_MAC); }
static int firmware(void *p) { return hardware(p,EV_FW); }
static int hw_config(void *p) { return hardware(p,EV_HWCONFIG); }
static int read_cr(void *p,uint8_t *v) { boundary(p);*v=0;return 0; }
static int dma_hang(void *p,bool *v) { boundary(p);*v=false;return 0; }
static int dma_reset(void *p,bool v) { (void)v;return step(p); }
static int irq_enable(void *p) { int e=hardware(p,EV_IRQ_ENABLE);return e ? e:rtwn8723be_netbsd_enable_interrupt(p); }
static int mark_start(void *p) { struct rtwn8723be_softc *sc=p;int e=hardware(sc,EV_MARK_START);if (!e)sc->sc_hal_started=true;return e; }
static int begin_stop(void *p,struct rtwn8723be_linux_state *s) {
    struct rtwn8723be_softc *sc=p;int e=hardware(sc,EV_BEGIN_STOP);return e ? e:rtwn8723be_datapath_begin_stop(sc->sc_datapath,s);
}
static int bt_halt(void *p) { return hardware(p,EV_BT_HALT); }
static int mark_stop(void *p) { struct rtwn8723be_softc *sc=p;int e=hardware(sc,EV_MARK_STOP);if (!e && !false_hal_stop)sc->sc_hal_started=false;return e; }
static int rf_wait(void *p) { return hardware(p,EV_RF_WAIT); }
static int __attribute__((unused)) hw_disable(void *p) {
    struct rtwn8723be_softc *sc=p;
    CHECK(sc->sc_runtime_owner.context->irq_drained);
    CHECK(!sc->sc_irq_requested && !sc->sc_irq_enabled && barriers>0);
    if(poweroff_hook!=NULL)poweroff_hook(sc);
    int e=hardware(sc,EV_HW_DISABLE);if(e==0)hardware_off=true;return e;
}
static int aspm(void *p) { return hardware(p,EV_ASPM); }
#ifndef MISSING_OP
#define MISSING_OP 0
#endif
const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops = {
 .pci_enable=step,.dma_configure=step,.pci_set_master=step,.alloc_softc=step,
 .map_bar=step,.pci_prepare_d0=step,.find_adapter=step,.init_io=step,
 .read_eeprom_info=step,.init_sw_vars=step,.init_leds=step,.init_aspm=step,.init_core=step,.init_pci_rings=step,
 .register_ieee80211=rtwn8723be_netbsd_register_ieee80211,.init_rfkill=step,.establish_irq=step,
 .reset_trx_ring=reset_rings,
#if MISSING_OP != 1
 .bt_prepare=bt_prepare,
#endif
 .disable_aspm=disable_aspm,.read_cr=read_cr,.check_pcie_dma_hang=dma_hang,.reset_pcie_interface_dma=dma_reset,
 .poweroff_adapter=step,.init_mac=init_mac,.sys_cfg_clear_bit7=step,.download_firmware=firmware,
 .phy_mac_config=step,.rcr_postprocess=step,.phy_bb_config=step,.phy_rf_config=step,.rf_channel_state_init=step,
 .hw_configure=hw_config,.cam_reset_all=step,.enable_hw_security=step,.set_mac_address=step,
 .enable_aspm_backdoor=step,.enable_aspm=aspm,.bt_hw_init=step,.rf_calibration=step,.set_nav_upper_235=step,
 .release_rx_dma=step,.release_pcie_dma=step,
#if MISSING_OP != 2
 .dm_init=step,
#endif
 .set_retry_limit=step,.enable_interrupt=irq_enable,.init_rx_config=step,.mark_hal_start=mark_start,
 .begin_stop=begin_stop,.bt_halt_deinit=bt_halt,.mark_hal_stop=mark_stop,
 .disable_interrupt=rtwn8723be_netbsd_disable_interrupt,.wait_rf_change_idle=rf_wait,
#if MISSING_OP != 3
 .hw_disable=hw_disable,
#endif
};
static int cal_acquire(void *a,struct rtwn8723be_softc *s,struct rtwn8723be_calibration_inputs *i) { (void)a;(void)s;(void)i;CHECK(false);return EIO; }
static bool provider_ready(void *a,struct rtwn8723be_softc *s) { (void)a;(void)s;CHECK(false);return false; }
static int scan_active(void *a,struct rtwn8723be_softc *s,bool *v) { (void)a;(void)s;(void)v;CHECK(false);return EIO; }
static void cal_release(void *a,struct rtwn8723be_softc *s,const struct rtwn8723be_calibration_state *i,int e) { (void)a;(void)s;(void)i;(void)e;CHECK(false); }
static int off_acquire(void *a,struct rtwn8723be_softc *s,struct rtwn8723be_hw_disable_inputs *i,struct rtwn8723be_hw_disable_state *t) { (void)a;(void)s;(void)i;(void)t;CHECK(false);return EIO; }
static void off_release(void *a,struct rtwn8723be_softc *s,const struct rtwn8723be_hw_disable_state *i,int e) { (void)a;(void)s;(void)i;(void)e;CHECK(false); }
static const struct rtwn8723be_calibration_owner calibration = {.acquire=cal_acquire,.ready=provider_ready,.scan_active=scan_active,.release=cal_release};
static const struct rtwn8723be_hw_disable_owner disable_owner = {.acquire=off_acquire,.ready=provider_ready,.release=off_release};
/* These old lifecycle tests never execute BTC algorithms or MMIO providers.
 * A call into an unmodelled boundary fails explicitly; no owner success is
 * fabricated to make the new readiness gate pass. Policy/DM init are linked
 * from the actual production modules below. */
static int fixture_snapshot(void *p,struct rtwn8723be_btc_wifi_snapshot *v) { (void)p;(void)v;CHECK(false);return EIO; }
static int fixture_clock(void *p,uint64_t *v) { (void)p;(void)v;CHECK(false);return EIO; }
static int fixture_aggregate(void *p,const struct btc_bt_info *v) { (void)p;(void)v;CHECK(false);return EIO; }
static int fixture_lps(void *p) { (void)p;CHECK(false);return EIO; }
static int fixture_query(void *p,struct btc_coexist *b,enum rtwn8723be_btc_policy_bt_query q,uint32_t *v) { (void)p;(void)b;(void)q;(void)v;CHECK(false);return EIO; }
static void fixture_fault(void *p,int e) { (void)p;(void)e;CHECK(false); }
static const struct rtwn8723be_btc_policy_ops fixture_ports={
 .snapshot=fixture_snapshot,.clock_msec=fixture_clock,
 .aggregate_apply=fixture_aggregate,.lps_enter=fixture_lps,.lps_leave=fixture_lps,
 .bt_query=fixture_query,.fault=fixture_fault
};
static void bind_policy_ports(struct rtwn8723be_softc *sc) {
    CHECK(rtwn8723be_runtime_provider_configure(sc,&fixture_ports,sc)==0);
}
int rtwn8723be_btc_native_seed_lowlevel(struct btc_coexist *b,struct rtwn8723be_softc *sc) { (void)b;(void)sc;CHECK(false);return EIO; }
int rtwn8723be_btc_context_build(struct btc_coexist *b,const struct rtwn8723be_btc_context_identity *i,const struct rtwn8723be_btc_context_binders *v) { (void)b;(void)i;(void)v;CHECK(false);return EIO; }
int rtwn8723be_btc_native_init(struct rtwn8723be_softc *sc,const struct btc_coexist *b,const struct rtwn8723be_btc_native_owner *o,void *a) { (void)sc;(void)b;(void)o;(void)a;CHECK(false);return EIO; }
void rtwn8723be_btc_native_provider_error(struct rtwn8723be_softc *sc,int e) { (void)sc;(void)e;CHECK(false); }
int rtwn8723be_btc_mp_native_stop(struct rtwn8723be_softc *sc) { (void)sc;CHECK(false);return EIO; }
uint32_t rtwn8723be_netbsd_get_bbreg(struct rtwn8723be_softc *sc,bus_size_t r,uint32_t m) { (void)sc;(void)r;(void)m;CHECK(false);return 0; }
static void delay(unsigned int n) { (void)n;CHECK(false); }
static int c2h(void *p,const struct rtwn8723be_c2h_event *event) { (void)p;(void)event;return 0; }
static void fresh(struct rtwn8723be_softc *sc) {
    memset(sc,0,sizeof(*sc));active_sc=sc;event_count=0;hardware_calls=0;pci_effects=0;
    false_hal_stop=false;hardware_off=false;read_hook=NULL;read1_hook=NULL;poweroff_hook=NULL;
    mmio_reads=0;mmio_writes=0;soft_schedules=0;hisr_value=0;hisre_value=0;hsisr_value=0;ack_value=0;
    false_prepare_kind=0;fail_module=0;fail_compensator=0;fail_hardware=0;partial_prepare=false;false_compensator=false;
    radio_on=true;radio_error=0;barrier_injection=0;boundary_hook=NULL;barrier_hook=NULL;barriers=0;
    fail_allocation=false;fail_dp_start=false;in_hard=false;in_soft=false;in_pserialize=false;
    giant_count=0;giant_unlocks=0;giant_restores=0;curlwp=&first_lwp;
    rtwn8723be_runtime_owner_init(sc);
    mutex_init(&sc->sc_irq_lock,MUTEX_DEFAULT,IPL_NET);sc->sc_irq_lock_initialized=true;
    mutex_init(&sc->sc_rf_ps_lock,MUTEX_DEFAULT,IPL_NET);sc->sc_rf_ps_lock_initialized=true;
}
static struct rtwn8723be_c2h_handlers handlers(struct rtwn8723be_softc *sc) {
    struct rtwn8723be_c2h_handlers h={sc,c2h,c2h,c2h,c2h};return h;
}
static void bind_providers(struct rtwn8723be_softc *sc) {
    sc->sc_calibration_owner=&calibration;sc->sc_calibration_owner_arg=sc;
    sc->sc_hw_disable_owner=&disable_owner;sc->sc_hw_disable_owner_arg=sc;
}
static void configure(struct rtwn8723be_softc *sc) {
    struct rtwn8723be_c2h_handlers h=handlers(sc);
    CHECK(rtwn8723be_runtime_owner_configure(sc,&h)==0);bind_policy_ports(sc);bind_providers(sc);
}
static void __attribute__((unused)) registered(struct rtwn8723be_softc *sc) {
    configure(sc);sc->sc_linux.stage=R23BE_STAGE_IEEE80211_REGISTER;
    CHECK(rtwn8723be_netbsd_register_ieee80211(sc)==0);
}
static void __attribute__((unused)) probed(struct rtwn8723be_softc *sc) {
    registered(sc);sc->sc_linux.stage=R23BE_STAGE_PROBED;
    sc->sc_ih=sc;sc->sc_soft_ih=&sc->sc_irq_lock;sc->sc_pihp=(pci_intr_handle_t *)&sc->sc_irq_epoch;
    sc->sc_mapped=true;sc->sc_core_initialized=true;sc->sc_rings_allocated=true;sc->sc_dma_32bit=true;sc->sc_dmat=sc;
    sc->sc_h2c.initialized=true;sc->sc_h2c.sc=sc;
    sc->sc_rfkill_native.initialized=true;sc->sc_rfkill_native.active=true;sc->sc_rfkill_native.wq=sc;
    sc->sc_irq_mask[0]=0xffffffffU;sc->sc_irq_mask[1]=0xffffffffU;
}
static void clear_external(struct rtwn8723be_softc *sc) {
    sc->sc_ih=NULL;sc->sc_soft_ih=NULL;sc->sc_pihp=NULL;sc->sc_irq_requested=false;sc->sc_irq_enabled=false;
    sc->sc_irq_pending[0]=0;sc->sc_irq_pending[1]=0;
    sc->sc_linux.stage=R23BE_STAGE_IEEE80211_REGISTER;sc->sc_linux.started=false;sc->sc_linux.fw_ready=false;sc->sc_linux.mac_func_enable=false;
    sc->sc_hal_started=false;
    fail_compensator=0;false_compensator=false;
    if(sc->sc_datapath!=NULL) { sc->sc_datapath->tx_enabled=false;sc->sc_datapath->stop_pending=false;sc->sc_datapath->rx_callback_active=0;sc->sc_datapath->tx_callback_active=0;sc->sc_datapath->tx_start_active=0;CHECK(rtwn8723be_datapath_unprepare(sc->sc_datapath)==0); }
    if(sc->sc_rx_binding!=NULL)CHECK(rtwn8723be_rx_binding_fini(sc->sc_rx_binding)==0);
    if(sc->sc_net80211.registered)CHECK(rtwn8723be_net80211_unregister(&sc->sc_net80211)==0);
    memset(&sc->sc_rfkill_native,0,sizeof(sc->sc_rfkill_native));
    memset(&sc->sc_h2c,0,sizeof(sc->sc_h2c));
    sc->sc_mapped=false;sc->sc_core_initialized=false;sc->sc_rings_allocated=false;sc->sc_dma_32bit=false;sc->sc_dmat=NULL;
    sc->sc_calibration_owner=NULL;sc->sc_calibration_owner_arg=NULL;sc->sc_hw_disable_owner=NULL;sc->sc_hw_disable_owner_arg=NULL;
    sc->sc_linux.stage=R23BE_STAGE_IDLE;
}
static void retire(struct rtwn8723be_softc *sc) {
    clear_external(sc);CHECK(rtwn8723be_runtime_owner_fini(sc)==0);
    CHECK(!sc->sc_runtime_owner.initialized && sc->sc_runtime_owner.context==NULL);
    mutex_destroy(&sc->sc_irq_lock);mutex_destroy(&sc->sc_rf_ps_lock);
}
'''

def program(data, test, irq=False, owner=None, native=None):
    owner = data["rtwn8723be_runtime_owner.c"] if owner is None else owner
    native = data["rtwn8723be_netbsd.c"] if native is None else native
    pieces = [PRELUDE,
        without_includes(data["rtwn8723be_runtime_owner.h"]),
        without_includes(data["rtwn8723be_btc_native.h"]),
        structure(data["rtwn8723be_c2h.h"], "rtwn8723be_c2h_handlers"),
        structure(data["rtwn8723be_rx_native.h"], "rtwn8723be_rx_dispatch"),
        structure(data["rtwn8723be_net80211.h"], "rtwn8723be_net80211_methods"),
        structure(data["rtwn8723be_datapath.h"], "rtwn8723be_datapath"),
        structure(data["rtwn8723be_rx_binding.h"], "rtwn8723be_rx_binding"),
        structure(data["rtwn8723be_calibration_native.h"], "rtwn8723be_calibration_owner"),
        structure(data["rtwn8723be_hw_disable_native.h"], "rtwn8723be_hw_disable_owner"),
        TYPES]
    dma = data["rtwn8723be_datapath.c"]
    for name in ("rtwn8723be_datapath_start", "rtwn8723be_datapath_running_ready", "rtwn8723be_datapath_begin_stop"):
        body = function(dma,name)
        if name=="rtwn8723be_datapath_start":
            body=body.replace("    int error", "    int error",1)
        pieces.append(body)
    constants = data["rtwn8723be_f16_1.h"].split("/* Host interrupt block. */",1)[1].split("/* Linux 8723BE default interrupt contract. */",1)[0]
    pieces.insert(1,constants)
    queues = re.findall(r"(?m)^#define RTWN8723BE_(?:BK|BE|VI|VO|MGNT|HIGH)_QUEUE[^\n]*",data["rtwn8723be_f16_1.h"])
    assert len(queues)==6
    pieces.insert(1,"\n".join(queues))
    pieces.append(without_includes(owner))
    for name in ("rtwn8723be_netbsd_irq_mask_locked","rtwn8723be_netbsd_irq_arm_locked",
                 "rtwn8723be_netbsd_enable_interrupt",
                 "rtwn8723be_netbsd_disable_interrupt"):
        pieces.append(function(native,name))
    if irq:
        for name in ("rtwn8723be_netbsd_irq_rearm_if_requested","rtwn8723be_netbsd_intr","rtwn8723be_netbsd_softintr"):
            pieces.append(function(native,name))
    pieces.append(function(native,"rtwn8723be_netbsd_context_fini"))
    pieces += [BOUNDARIES, IO, test]
    return "\n\n".join(pieces)

def execute(label, source, *, definitions=(), expect_failure=False, target=""):
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    with tempfile.TemporaryDirectory(prefix="rtl-runtime-", dir=os.environ.get("TMPDIR")) as directory:
        tmp=Path(directory)
        c=tmp/"fixture.c";exe=tmp/"fixture";c.write_text(source)
        command=["cc",*FLAGS,*definitions,"-I",str(SRC),str(c),
                 str(SRC/"rtwn8723be_linux_state.c"),
                 str(SRC/"rtwn8723be_btc_policy.c"),str(SRC/"rtwn8723be_dm.c"),
                 str(SRC/"rtwn8723be_thermal.c"),str(SRC/"rtwn8723be_calibration.c"),
                 "-o",str(exe)]
        built=subprocess.run(command,cwd=tmp,text=True,capture_output=True)
        if built.returncode:
            raise AssertionError(label+" COMPILE_FAILED\n"+built.stdout+built.stderr)
        result=subprocess.run([str(exe)],cwd=tmp,text=True,capture_output=True)
        if expect_failure:
            assert result.returncode==97 and "FIXTURE_ASSERT:" in result.stderr, (
                label,"mutation did not reach targeted runtime assertion",result.returncode,result.stdout,result.stderr)
        else:
            assert result.returncode==0, (label,result.returncode,result.stdout,result.stderr)
        print(json.dumps({"label":label,"compiled":True,"executed":True,
              "exit":result.returncode,"target":target,
              "source_sha256":hashlib.sha256(source.encode()).hexdigest(),
              "assertion":result.stderr.strip()[:400]},sort_keys=True))
        return result


IO = r'''

static void rtwn8723be_write_4(struct rtwn8723be_softc *sc,uint32_t reg,uint32_t value) {
    CHECK(sc->sc_mapped && !hardware_off);mmio_writes++;
    if(reg==R23BE_REG_HIMR && value==0)record(EV_MASK);
    if(reg==R23BE_REG_HISR || reg==R23BE_REG_HISRE)ack_value=value;
}
static void __attribute__((unused)) rtwn8723be_write_1(struct rtwn8723be_softc *sc,uint32_t reg,uint8_t value) {
    CHECK(sc->sc_mapped && !hardware_off);CHECK(reg==R23BE_REG_HSISR);mmio_writes++;hsisr_value=value;
}
static uint32_t __attribute__((unused)) rtwn8723be_read_4(struct rtwn8723be_softc *sc,uint32_t reg) {
    CHECK(sc->sc_mapped && !hardware_off);mmio_reads++;
    if(read_hook!=NULL)read_hook(sc);
    return reg==R23BE_REG_HISR ? hisr_value:hisre_value;
}
static uint8_t __attribute__((unused)) rtwn8723be_read_1(struct rtwn8723be_softc *sc,uint32_t reg) {
    if(read1_hook!=NULL)read1_hook(sc);
    CHECK(sc->sc_mapped && !hardware_off);CHECK(reg==R23BE_REG_HSISR);mmio_reads++;return hsisr_value;
}
static void __attribute__((unused)) softint_schedule(void *handle) { CHECK(handle!=NULL);soft_schedules++; }
static void xc_barrier(unsigned int flags) {
    struct rtwn8723be_softc *sc=active_sc;CHECK(sc!=NULL);
    CHECK(flags==XC_HIGHPRI_IPL(IPL_SOFTNET));
    CHECK(!in_hard && !in_soft && !in_pserialize && giant_count==0);
    CHECK(!mutex_owned(&sc->sc_runtime_owner.lifecycle_lock));
    CHECK(!mutex_owned(&sc->sc_runtime_owner.io_lock));
    CHECK(!mutex_owned(&sc->sc_irq_lock));
    CHECK(!mutex_owned(&sc->sc_datapath->tx_lock));
    CHECK(!sc->sc_irq_requested && !sc->sc_irq_enabled);
    barriers++;record(EV_BARRIER);
    if(barrier_hook!=NULL)barrier_hook(sc);
    switch(barrier_injection) {
    case 1:sc->sc_irq_epoch++;break;
    case 2:sc->sc_irq_requested=true;break;
    case 3:sc->sc_irq_enabled=true;break;
    case 4:sc->sc_irq_pending[0]=1;break;
    case 5:sc->sc_ih=&first_lwp;break;
    case 6:sc->sc_soft_ih=&first_lwp;break;
    case 7:sc->sc_pihp=(pci_intr_handle_t *)&first_lwp;break;
    default:break;
    }
}
'''
