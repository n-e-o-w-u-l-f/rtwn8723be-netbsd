#!/usr/bin/env python3
"""Real native provider/BTC/controller C with explicit pthread/MMIO boundaries.

The fixture executes production admission, pins, provider scope, context/policy,
both frozen BTC algorithms, native broker and portable DM. Its kernel, MMIO,
H2C and configured OS action implementations are instrumented test boundaries,
not NetBSD ABI, Bluetooth firmware or physical WLAN acceptance.
"""
from pathlib import Path
import hashlib
import json
import os
import platform
import re
import resource
import socket
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WORK = Path(os.environ["RTWN8723BE_HP_WORKDIR"]).resolve(strict=True)
LINUX = Path(os.environ["RTWN8723BE_LINUX_TREE"]).resolve(strict=True)
PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
    raise SystemExit("REFUSED: only HP/NetBSD compilation is authorized")
if WORK.name != "fixture-tmp" or WORK.parent.parent != ROOT.parent / "audit":
    raise SystemExit("REFUSED: declare the project audit fixture workspace")
if Path.cwd().resolve() != WORK or Path(os.environ["TMPDIR"]).resolve() != WORK:
    raise SystemExit("REFUSED: cwd/TMPDIR must equal the fixture workspace")
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

def function(source, name):
    m = re.search(r"(?m)^(?:static\s+)?(?:int|void|bool|uint32_t|struct\s+\w+\s*\*)\s*\n" +
                  re.escape(name) + r"\([^;{}]*\)\n\{", source)
    assert m, name
    return source[m.start():source.index("\n}\n", m.end()) + 3]

def structure(source, name):
    m = re.search(r"(?m)^struct " + re.escape(name) + r"\s*\{", source)
    assert m, name
    return source[m.start():source.index("\n};", m.end()) + 3]

def without_includes(source):
    return re.sub(r"(?m)^(?:#include[^\n]*|__KERNEL_RCSID[^\n]*)\n", "", source)

def replace_once(source, before, after):
    assert source.count(before) == 1, (before, source.count(before))
    return source.replace(before, after, 1)

# Explicit boundary scaffolding from the existing admitted runtime fixture.
# It is kept as fixture data here so concurrent legacy-fixture API migration
# cannot silently change this integration model. Production bodies are read
# fresh below and compiled without replacing their logic.

BASE = {
  "PRELUDE": "\n#include <assert.h>\n#include <stdbool.h>\n#include <stdint.h>\n#include <stddef.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <errno.h>\n#include \"rtwn8723be_linux_state.h\"\n#include \"rtwn8723be_net80211_state.h\"\n#include \"rtwn8723be_irq_pending.h\"\n#define CHECK(x) do { if (!(x)) { fprintf(stderr, \"FIXTURE_ASSERT:%s:%d:%s\\n\", __FILE__, __LINE__, #x); exit(97); } } while (0)\n/* Release-style project assertions: conditions are typechecked, not evaluated. */\n#define KASSERT(x) ((void)sizeof(x))\n#define MUTEX_DEFAULT 0\n/* Actual target x86 intrdefs.h values; IPL_NET is the compatibility IPL_VM. */\n#define IPL_NONE 0\n#define IPL_SOFTCLOCK 2\n#define IPL_SOFTBIO 3\n#define IPL_SOFTNET 4\n#define IPL_SOFTSERIAL 5\n#define IPL_NET 6\n#define SOFTINT_NET 3\n#define KM_NOSLEEP 0\n#define IFF_RUNNING 0x40\n#define IFF_OACTIVE 0x400\nstruct lwp { int identity; };\nstatic struct lwp first_lwp = {1}, second_lwp = {2};\nstatic _Thread_local struct lwp *curlwp = &first_lwp;\ntypedef struct { bool initialized, held; int ipl; struct lwp *holder; } kmutex_t;\ntypedef unsigned int pci_intr_handle_t;\nstruct ifnet { unsigned int if_flags; int if_timer; };\nstruct mbuf;\nstruct ieee80211_node;\nstruct ieee80211com;\nstruct rtwn8723be_softc;\nstruct rtwn8723be_rx_packet;\nstruct rtwn8723be_c2h_event;\nstruct rtwn8723be_calibration_inputs;\nstruct rtwn8723be_calibration_state;\nstruct rtwn8723be_calibration_context;\nstruct rtwn8723be_hw_disable_inputs;\nstruct rtwn8723be_hw_disable_state;\nstatic _Thread_local bool in_hard, in_soft, in_pserialize;\nstatic bool fail_allocation;\nstatic _Thread_local int giant_count;\nstatic int giant_unlocks, giant_restores, barriers;\nstatic unsigned int allocated, freed, destroyed, hardware_calls, pci_effects;\nstatic unsigned int event_count;\nstatic int events[512], fail_module, fail_compensator, fail_hardware;\nstatic int false_prepare_kind;\nstatic bool partial_prepare, false_compensator, radio_on = true, fail_dp_start;\nstatic int radio_error, barrier_injection;\nstatic void (*boundary_hook)(struct rtwn8723be_softc *);\nstatic void (*barrier_hook)(struct rtwn8723be_softc *);\nstatic struct rtwn8723be_softc *active_sc;\nstatic uint32_t hisr_value, hisre_value, ack_value;\nstatic uint8_t hsisr_value;\nstatic unsigned int mmio_reads, mmio_writes, soft_schedules;\nstatic bool hardware_off;\nstatic void (*read_hook)(struct rtwn8723be_softc *);\nstatic void (*read1_hook)(struct rtwn8723be_softc *);\nstatic void (*poweroff_hook)(struct rtwn8723be_softc *);\nstatic bool false_hal_stop;\nstatic void mutex_init(kmutex_t *m, int type, int ipl) {\n    (void)type; CHECK(!m->initialized); m->initialized=true; m->held=false; m->holder=NULL; m->ipl=ipl;\n}\nstatic bool mutex_owned(kmutex_t *m) { return m->initialized && m->held && m->holder == curlwp; }\nstatic int mutex_tryenter(kmutex_t *m) {\n    CHECK(m->initialized); if (m->held) return 0;\n    m->held=true; m->holder=curlwp; return 1;\n}\nstatic void mutex_enter(kmutex_t *m) { CHECK(mutex_tryenter(m)); }\nstatic void mutex_exit(kmutex_t *m) { CHECK(mutex_owned(m)); m->held=false; m->holder=NULL; }\nstatic void mutex_destroy(kmutex_t *m) { CHECK(m->initialized && !m->held); m->initialized=false; destroyed++; }\nstatic bool cpu_intr_p(void) { return in_hard; }\nstatic bool cpu_softintr_p(void) { return in_soft; }\nstatic bool pserialize_not_in_read_section(void) { return !in_pserialize; }\nstatic void *kmem_zalloc(size_t, int);\nstatic void kmem_free(void *, size_t);\nstatic bool kernel_locked_p(void) { return giant_count != 0; }\nstatic void kernel_unlock_all(int *n) { CHECK(n != NULL); *n=giant_count; giant_count=0; giant_unlocks++; }\nstatic void kernel_lock(int n) { CHECK(n>=0); if (n!=0) { giant_count+=n; giant_restores++; } }\n#define KERNEL_LOCKED_P() kernel_locked_p()\n#define KERNEL_UNLOCK_ALL(l,p) do { (void)(l); kernel_unlock_all(p); } while (0)\n#define KERNEL_LOCK(n,l) do { (void)(l); kernel_lock(n); } while (0)\n/* Exact allowable target xc_encode_ipl mapping; hardware IPL_NET is invalid. */\nstatic unsigned int xc_encode_ipl(int ipl) {\n    switch (ipl) {\n    case IPL_SOFTSERIAL:return 0;\n    case IPL_SOFTNET:return 0x100;\n    case IPL_SOFTBIO:return 0x200;\n    case IPL_SOFTCLOCK:return 0x300;\n    default:CHECK(false);return 0;\n    }\n}\n#define XC_HIGHPRI_IPL(ipl) (1U | xc_encode_ipl(ipl))\nstatic void xc_barrier(unsigned int);\nstatic void rtwn8723be_write_4(struct rtwn8723be_softc *, uint32_t, uint32_t);\nstatic void __attribute__((unused)) rtwn8723be_write_1(struct rtwn8723be_softc *, uint32_t, uint8_t);\nstatic uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *, uint32_t);\nstatic uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *, uint32_t);\nstatic void softint_schedule(void *);\n",
  "TYPES": "\nstruct rtwn8723be_net80211 {\n    struct rtwn8723be_softc *sc;\n    struct rtwn8723be_net80211_methods methods;\n    bool registered, tx_busy;\n    unsigned int tx_key_update_depth;\n    struct mbuf *tx_pending_m;\n    struct ieee80211_node *tx_pending_ni;\n    void (*tx_key_begin_saved)(struct ieee80211com *);\n    void (*tx_key_end_saved)(struct ieee80211com *);\n};\nstruct rtwn8723be_irq_dispatch {\n    void (*rx)(void *);\n    void (*tx_done)(void *, unsigned int);\n    void (*power_event)(void *);\n};\nstruct rtwn8723be_softc {\n    struct rtwn8723be_linux_state sc_linux;\n    struct rtwn8723be_runtime_owner sc_runtime_owner;\n    struct rtwn8723be_net80211 sc_net80211;\n    struct rtwn8723be_datapath *sc_datapath;\n    struct rtwn8723be_rx_binding *sc_rx_binding;\n    struct { bool initialized, active, work_queued; void *wq; } sc_rfkill_native;\n    struct { bool initialized; struct rtwn8723be_softc *sc; struct { bool firmware_ready; } state; } sc_h2c;\n    struct { bool initialized, scheduled; void *workqueue, *owner, *owner_arg, *worker; unsigned int calls, count; } sc_btc;\n    struct { bool initialized, active, busy, pending; } sc_btc_mp;\n    const struct rtwn8723be_calibration_owner *sc_calibration_owner;\n    void *sc_calibration_owner_arg;\n    const struct rtwn8723be_hw_disable_owner *sc_hw_disable_owner;\n    void *sc_hw_disable_owner_arg;\n    kmutex_t sc_irq_lock, sc_rf_ps_lock;\n    bool sc_irq_lock_initialized, sc_rf_ps_lock_initialized;\n    bool sc_irq_requested, sc_irq_enabled, sc_irq_dispatch_ready;\n    struct rtwn8723be_irq_dispatch sc_irq_dispatch;\n    void *sc_irq_arg, *sc_ih, *sc_soft_ih;\n    pci_intr_handle_t *sc_pihp;\n    uint32_t sc_irq_pending[2], sc_irq_epoch, sc_irq_mask[2], sc_sys_irq_mask;\n    bool sc_rfchange_inprogress, sc_initial_pci_saved, sc_mapped;\n    bool sc_core_initialized, sc_rings_allocated, sc_dmat_owned, sc_dma_32bit, sc_hal_started;\n    void *sc_dmat;\n    struct { struct ifnet ec_if; } sc_ec;\n};\nextern const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops;\nint rtwn8723be_net80211_register(struct rtwn8723be_net80211 *, struct rtwn8723be_softc *, const struct rtwn8723be_net80211_methods *);\nint rtwn8723be_net80211_unregister(struct rtwn8723be_net80211 *);\nvoid rtwn8723be_net80211_tx_start(struct rtwn8723be_softc *, struct ifnet *);\nint rtwn8723be_rx_binding_init(struct rtwn8723be_rx_binding *, struct rtwn8723be_net80211 *, const struct rtwn8723be_c2h_handlers *);\nint rtwn8723be_rx_binding_fini(struct rtwn8723be_rx_binding *);\nint rtwn8723be_datapath_prepare(struct rtwn8723be_datapath *, struct rtwn8723be_softc *, const struct rtwn8723be_rx_dispatch *, void (*)(void *, unsigned int, size_t), void *);\nint rtwn8723be_datapath_unprepare(struct rtwn8723be_datapath *);\nint rtwn8723be_datapath_start(struct rtwn8723be_datapath *);\nbool rtwn8723be_datapath_running_ready(struct rtwn8723be_datapath *);\nint rtwn8723be_datapath_begin_stop(struct rtwn8723be_datapath *, struct rtwn8723be_linux_state *);\nint rtwn8723be_netbsd_disable_interrupt(void *);\nint rtwn8723be_netbsd_enable_interrupt(void *);\nint rtwn8723be_rfkill_native_radio_on(struct rtwn8723be_softc *, bool *);\n",
  "BOUNDARIES": "\nenum { EV_REGISTER=1, EV_RX_INIT, EV_DP_PREPARE, EV_DP_FINI, EV_RX_FINI, EV_UNREGISTER,\n       EV_RESET=10, EV_BT, EV_DISABLE_ASPM, EV_INIT_MAC, EV_FW, EV_HWCONFIG,\n       EV_IRQ_ENABLE, EV_MARK_START, EV_BEGIN_STOP=30, EV_BT_HALT, EV_MARK_STOP,\n       EV_MASK, EV_BARRIER, EV_RF_WAIT, EV_HW_DISABLE, EV_ASPM };\nstatic void record(int event) { CHECK(event_count<512); events[event_count++]=event; }\nstatic void boundary(struct rtwn8723be_softc *sc) {\n    CHECK(!mutex_owned(&sc->sc_runtime_owner.lifecycle_lock));\n    CHECK(!mutex_owned(&sc->sc_runtime_owner.io_lock));\n    if (boundary_hook != NULL) boundary_hook(sc);\n}\nstatic void *kmem_zalloc(size_t n, int flags) {\n    CHECK(flags==KM_NOSLEEP); CHECK(active_sc != NULL); boundary(active_sc);\n    if (fail_allocation) return NULL;\n    void *p=calloc(1,n); CHECK(p!=NULL); allocated++; return p;\n}\nstatic void kmem_free(void *p, size_t n) {\n    (void)n; CHECK(p!=NULL); CHECK(active_sc!=NULL); boundary(active_sc);\n    CHECK(active_sc->sc_runtime_owner.context==NULL); freed++; free(p);\n}\nstatic int fake_rx(void *arg, const uint8_t *data, size_t n, const struct rtwn8723be_rx_packet *pkt) {\n    (void)arg;(void)data;(void)n;(void)pkt;return 0;\n}\nstatic void fake_irq_rx(void *arg) { (void)arg; }\nstatic void fake_irq_tx(void *arg, unsigned int q) { (void)arg;(void)q; }\nstatic void __attribute__((unused)) fake_irq_power(void *arg) { (void)arg; }\nint rtwn8723be_net80211_register(struct rtwn8723be_net80211 *n, struct rtwn8723be_softc *sc, const struct rtwn8723be_net80211_methods *m) {\n    boundary(sc);record(EV_REGISTER); CHECK(n==&sc->sc_net80211);\n    if (fail_module==1) return EIO;\n    n->sc=sc;n->methods=*m;n->registered=true; return 0;\n}\nint rtwn8723be_net80211_unregister(struct rtwn8723be_net80211 *n) {\n    struct rtwn8723be_softc *sc=n->sc; CHECK(sc!=NULL);boundary(sc);record(EV_UNREGISTER);\n    CHECK(sc->sc_datapath==NULL && sc->sc_rx_binding==NULL);\n    if (fail_compensator==3) return EBUSY;\n    if (!false_compensator) memset(n,0,sizeof(*n));\n    return 0;\n}\nvoid rtwn8723be_net80211_tx_start(struct rtwn8723be_softc *sc, struct ifnet *ifp) { (void)sc;(void)ifp; }\nint rtwn8723be_rx_binding_init(struct rtwn8723be_rx_binding *rx, struct rtwn8723be_net80211 *n, const struct rtwn8723be_c2h_handlers *h) {\n    boundary(n->sc);record(EV_RX_INIT);\n    if (fail_module==2) return EIO;\n    rx->net=n;rx->firmware=*h;rx->dispatch.arg=rx;rx->dispatch.frame=fake_rx;rx->dispatch.c2h=fake_rx;\n    n->sc->sc_rx_binding=rx;return 0;\n}\nint rtwn8723be_rx_binding_fini(struct rtwn8723be_rx_binding *rx) {\n    struct rtwn8723be_softc *sc=rx->net->sc;boundary(sc);record(EV_RX_FINI);\n    CHECK(sc->sc_datapath==NULL); if (fail_compensator==2) return EBUSY;\n    if (!false_compensator) { sc->sc_rx_binding=NULL;memset(rx,0,sizeof(*rx)); } return 0;\n}\nint rtwn8723be_datapath_prepare(struct rtwn8723be_datapath *dp, struct rtwn8723be_softc *sc, const struct rtwn8723be_rx_dispatch *rx, void (*done)(void *,unsigned int,size_t), void *arg) {\n    boundary(sc);record(EV_DP_PREPARE);\n    if (fail_module==3 && !partial_prepare) return EIO;\n    if (false_prepare_kind==1) return 0;\n    dp->sc=sc;dp->rx=*rx;dp->prepared=true;dp->tx_complete=done;dp->tx_complete_arg=arg;\n    mutex_init(&dp->tx_lock,MUTEX_DEFAULT,IPL_NET);\n    sc->sc_datapath=dp;sc->sc_irq_arg=dp;sc->sc_irq_dispatch_ready=true;\n    sc->sc_irq_dispatch.rx=fake_irq_rx;sc->sc_irq_dispatch.tx_done=fake_irq_tx;\n    if(false_prepare_kind==2)dp->rx.arg=sc;\n    if(false_prepare_kind==3)dp->tx_enabled=true;\n    return fail_module==3 ? EIO : 0;\n}\nint rtwn8723be_datapath_unprepare(struct rtwn8723be_datapath *dp) {\n    struct rtwn8723be_softc *sc=dp->sc;boundary(sc);record(EV_DP_FINI);\n    if (fail_compensator==1) return EBUSY;\n    if (!false_compensator) {\n        if(dp->tx_enabled || dp->stop_pending || dp->rx_callback_active!=0 || dp->tx_callback_active!=0 || dp->tx_start_active!=0)return EBUSY;\n        sc->sc_datapath=NULL;sc->sc_irq_arg=NULL;sc->sc_irq_dispatch_ready=false;\n        memset(&sc->sc_irq_dispatch,0,sizeof(sc->sc_irq_dispatch));\n        mutex_destroy(&dp->tx_lock);memset(dp,0,sizeof(*dp));\n    } return 0;\n}\nint rtwn8723be_rfkill_native_radio_on(struct rtwn8723be_softc *sc, bool *on) {\n    boundary(sc);*on=radio_on;return radio_error;\n}\nstatic int hardware(struct rtwn8723be_softc *sc, int event) {\n    boundary(sc); hardware_calls++; record(event); return fail_hardware==event ? EIO:0;\n}\nstatic int step(void *p) { return hardware(p,90); }\nstatic int reset_rings(void *p) { hardware_off=false;return hardware(p,EV_RESET); }\nstatic int __attribute__((unused)) bt_prepare(void *p) { return hardware(p,EV_BT); }\nstatic int disable_aspm(void *p) { return hardware(p,EV_DISABLE_ASPM); }\nstatic int init_mac(void *p) { return hardware(p,EV_INIT_MAC); }\nstatic int firmware(void *p) { return hardware(p,EV_FW); }\nstatic int hw_config(void *p) { return hardware(p,EV_HWCONFIG); }\nstatic int read_cr(void *p,uint8_t *v) { boundary(p);*v=0;return 0; }\nstatic int dma_hang(void *p,bool *v) { boundary(p);*v=false;return 0; }\nstatic int dma_reset(void *p,bool v) { (void)v;return step(p); }\nstatic int irq_enable(void *p) { int e=hardware(p,EV_IRQ_ENABLE);return e ? e:rtwn8723be_netbsd_enable_interrupt(p); }\nstatic int mark_start(void *p) { struct rtwn8723be_softc *sc=p;int e=hardware(sc,EV_MARK_START);if (!e)sc->sc_hal_started=true;return e; }\nstatic int begin_stop(void *p,struct rtwn8723be_linux_state *s) {\n    struct rtwn8723be_softc *sc=p;int e=hardware(sc,EV_BEGIN_STOP);return e ? e:rtwn8723be_datapath_begin_stop(sc->sc_datapath,s);\n}\nstatic int bt_halt(void *p) { return hardware(p,EV_BT_HALT); }\nstatic int mark_stop(void *p) { struct rtwn8723be_softc *sc=p;int e=hardware(sc,EV_MARK_STOP);if (!e && !false_hal_stop)sc->sc_hal_started=false;return e; }\nstatic int rf_wait(void *p) { return hardware(p,EV_RF_WAIT); }\nstatic int __attribute__((unused)) hw_disable(void *p) {\n    struct rtwn8723be_softc *sc=p;\n    CHECK(sc->sc_runtime_owner.context->irq_drained);\n    CHECK(!sc->sc_irq_requested && !sc->sc_irq_enabled && barriers>0);\n    if(poweroff_hook!=NULL)poweroff_hook(sc);\n    int e=hardware(sc,EV_HW_DISABLE);if(e==0)hardware_off=true;return e;\n}\nstatic int aspm(void *p) { return hardware(p,EV_ASPM); }\n#ifndef MISSING_OP\n#define MISSING_OP 0\n#endif\nconst struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops = {\n .pci_enable=step,.dma_configure=step,.pci_set_master=step,.alloc_softc=step,\n .map_bar=step,.pci_prepare_d0=step,.find_adapter=step,.init_io=step,\n .read_eeprom_info=step,.init_sw_vars=step,.init_leds=step,.init_aspm=step,.init_core=step,.init_pci_rings=step,\n .register_ieee80211=rtwn8723be_netbsd_register_ieee80211,.init_rfkill=step,.establish_irq=step,\n .reset_trx_ring=reset_rings,\n#if MISSING_OP != 1\n .bt_prepare=bt_prepare,\n#endif\n .disable_aspm=disable_aspm,.read_cr=read_cr,.check_pcie_dma_hang=dma_hang,.reset_pcie_interface_dma=dma_reset,\n .poweroff_adapter=step,.init_mac=init_mac,.sys_cfg_clear_bit7=step,.download_firmware=firmware,\n .phy_mac_config=step,.rcr_postprocess=step,.phy_bb_config=step,.phy_rf_config=step,.rf_channel_state_init=step,\n .hw_configure=hw_config,.cam_reset_all=step,.enable_hw_security=step,.set_mac_address=step,\n .enable_aspm_backdoor=step,.enable_aspm=aspm,.bt_hw_init=step,.rf_calibration=step,.set_nav_upper_235=step,\n .release_rx_dma=step,.release_pcie_dma=step,\n#if MISSING_OP != 2\n .dm_init=step,\n#endif\n .set_retry_limit=step,.enable_interrupt=irq_enable,.init_rx_config=step,.mark_hal_start=mark_start,\n .begin_stop=begin_stop,.bt_halt_deinit=bt_halt,.mark_hal_stop=mark_stop,\n .disable_interrupt=rtwn8723be_netbsd_disable_interrupt,.wait_rf_change_idle=rf_wait,\n#if MISSING_OP != 3\n .hw_disable=hw_disable,\n#endif\n};\nstatic int cal_acquire(void *a,struct rtwn8723be_softc *s,struct rtwn8723be_calibration_inputs *i) { (void)a;(void)s;(void)i;CHECK(false);return EIO; }\nstatic bool provider_ready(void *a,struct rtwn8723be_softc *s) { (void)a;(void)s;CHECK(false);return false; }\nstatic int scan_active(void *a,struct rtwn8723be_softc *s,bool *v) { (void)a;(void)s;(void)v;CHECK(false);return EIO; }\nstatic void cal_release(void *a,struct rtwn8723be_softc *s,const struct rtwn8723be_calibration_state *i,int e) { (void)a;(void)s;(void)i;(void)e;CHECK(false); }\nstatic int off_acquire(void *a,struct rtwn8723be_softc *s,struct rtwn8723be_hw_disable_inputs *i,struct rtwn8723be_hw_disable_state *t) { (void)a;(void)s;(void)i;(void)t;CHECK(false);return EIO; }\nstatic void off_release(void *a,struct rtwn8723be_softc *s,const struct rtwn8723be_hw_disable_state *i,int e) { (void)a;(void)s;(void)i;(void)e;CHECK(false); }\nstatic const struct rtwn8723be_calibration_owner calibration = {.acquire=cal_acquire,.ready=provider_ready,.scan_active=scan_active,.release=cal_release};\nstatic const struct rtwn8723be_hw_disable_owner disable_owner = {.acquire=off_acquire,.ready=provider_ready,.release=off_release};\nstatic int c2h(void *p,const struct rtwn8723be_c2h_event *event) { (void)p;(void)event;return 0; }\nstatic void fresh(struct rtwn8723be_softc *sc) {\n    memset(sc,0,sizeof(*sc));active_sc=sc;event_count=0;hardware_calls=0;pci_effects=0;\n    false_hal_stop=false;hardware_off=false;read_hook=NULL;read1_hook=NULL;poweroff_hook=NULL;\n    mmio_reads=0;mmio_writes=0;soft_schedules=0;hisr_value=0;hisre_value=0;hsisr_value=0;ack_value=0;\n    false_prepare_kind=0;fail_module=0;fail_compensator=0;fail_hardware=0;partial_prepare=false;false_compensator=false;\n    radio_on=true;radio_error=0;barrier_injection=0;boundary_hook=NULL;barrier_hook=NULL;barriers=0;\n    fail_allocation=false;fail_dp_start=false;in_hard=false;in_soft=false;in_pserialize=false;\n    giant_count=0;giant_unlocks=0;giant_restores=0;curlwp=&first_lwp;\n    rtwn8723be_runtime_owner_init(sc);\n    mutex_init(&sc->sc_irq_lock,MUTEX_DEFAULT,IPL_NET);sc->sc_irq_lock_initialized=true;\n    mutex_init(&sc->sc_rf_ps_lock,MUTEX_DEFAULT,IPL_NET);sc->sc_rf_ps_lock_initialized=true;\n}\nstatic struct rtwn8723be_c2h_handlers handlers(struct rtwn8723be_softc *sc) {\n    struct rtwn8723be_c2h_handlers h={sc,c2h,c2h,c2h,c2h};return h;\n}\nstatic void bind_providers(struct rtwn8723be_softc *sc) {\n    sc->sc_calibration_owner=&calibration;sc->sc_calibration_owner_arg=sc;\n    sc->sc_hw_disable_owner=&disable_owner;sc->sc_hw_disable_owner_arg=sc;\n}\nstatic void configure(struct rtwn8723be_softc *sc) {\n    struct rtwn8723be_c2h_handlers h=handlers(sc);\n    CHECK(rtwn8723be_runtime_owner_configure(sc,&h)==0);bind_providers(sc);\n}\nstatic void __attribute__((unused)) registered(struct rtwn8723be_softc *sc) {\n    configure(sc);sc->sc_linux.stage=R23BE_STAGE_IEEE80211_REGISTER;\n    CHECK(rtwn8723be_netbsd_register_ieee80211(sc)==0);\n}\nstatic void __attribute__((unused)) probed(struct rtwn8723be_softc *sc) {\n    registered(sc);sc->sc_linux.stage=R23BE_STAGE_PROBED;\n    sc->sc_ih=sc;sc->sc_soft_ih=&sc->sc_irq_lock;sc->sc_pihp=(pci_intr_handle_t *)&sc->sc_irq_epoch;\n    sc->sc_mapped=true;sc->sc_core_initialized=true;sc->sc_rings_allocated=true;sc->sc_dma_32bit=true;sc->sc_dmat=sc;\n    sc->sc_h2c.initialized=true;sc->sc_h2c.sc=sc;\n    sc->sc_rfkill_native.initialized=true;sc->sc_rfkill_native.active=true;sc->sc_rfkill_native.wq=sc;\n    sc->sc_irq_mask[0]=0xffffffffU;sc->sc_irq_mask[1]=0xffffffffU;\n}\nstatic void clear_external(struct rtwn8723be_softc *sc) {\n    sc->sc_ih=NULL;sc->sc_soft_ih=NULL;sc->sc_pihp=NULL;sc->sc_irq_requested=false;sc->sc_irq_enabled=false;\n    sc->sc_irq_pending[0]=0;sc->sc_irq_pending[1]=0;\n    sc->sc_linux.stage=R23BE_STAGE_IEEE80211_REGISTER;sc->sc_linux.started=false;sc->sc_linux.fw_ready=false;sc->sc_linux.mac_func_enable=false;\n    sc->sc_hal_started=false;\n    fail_compensator=0;false_compensator=false;\n    if(sc->sc_datapath!=NULL) { sc->sc_datapath->tx_enabled=false;sc->sc_datapath->stop_pending=false;sc->sc_datapath->rx_callback_active=0;sc->sc_datapath->tx_callback_active=0;sc->sc_datapath->tx_start_active=0;CHECK(rtwn8723be_datapath_unprepare(sc->sc_datapath)==0); }\n    if(sc->sc_rx_binding!=NULL)CHECK(rtwn8723be_rx_binding_fini(sc->sc_rx_binding)==0);\n    if(sc->sc_net80211.registered)CHECK(rtwn8723be_net80211_unregister(&sc->sc_net80211)==0);\n    memset(&sc->sc_rfkill_native,0,sizeof(sc->sc_rfkill_native));\n    memset(&sc->sc_h2c,0,sizeof(sc->sc_h2c));\n    sc->sc_mapped=false;sc->sc_core_initialized=false;sc->sc_rings_allocated=false;sc->sc_dma_32bit=false;sc->sc_dmat=NULL;\n    sc->sc_calibration_owner=NULL;sc->sc_calibration_owner_arg=NULL;sc->sc_hw_disable_owner=NULL;sc->sc_hw_disable_owner_arg=NULL;\n    sc->sc_linux.stage=R23BE_STAGE_IDLE;\n}\nstatic void retire(struct rtwn8723be_softc *sc) {\n    clear_external(sc);CHECK(rtwn8723be_runtime_owner_fini(sc)==0);\n    CHECK(!sc->sc_runtime_owner.initialized && sc->sc_runtime_owner.context==NULL);\n    mutex_destroy(&sc->sc_irq_lock);mutex_destroy(&sc->sc_rf_ps_lock);\n}\n",
  "IO": "\n\nstatic void rtwn8723be_write_4(struct rtwn8723be_softc *sc,uint32_t reg,uint32_t value) {\n    CHECK(sc->sc_mapped && !hardware_off);mmio_writes++;\n    if(reg==R23BE_REG_HIMR && value==0)record(EV_MASK);\n    if(reg==R23BE_REG_HISR || reg==R23BE_REG_HISRE)ack_value=value;\n}\nstatic void __attribute__((unused)) rtwn8723be_write_1(struct rtwn8723be_softc *sc,uint32_t reg,uint8_t value) {\n    CHECK(sc->sc_mapped && !hardware_off);CHECK(reg==R23BE_REG_HSISR);mmio_writes++;hsisr_value=value;\n}\nstatic uint32_t __attribute__((unused)) rtwn8723be_read_4(struct rtwn8723be_softc *sc,uint32_t reg) {\n    CHECK(sc->sc_mapped && !hardware_off);mmio_reads++;\n    if(read_hook!=NULL)read_hook(sc);\n    return reg==R23BE_REG_HISR ? hisr_value:hisre_value;\n}\nstatic uint8_t __attribute__((unused)) rtwn8723be_read_1(struct rtwn8723be_softc *sc,uint32_t reg) {\n    if(read1_hook!=NULL)read1_hook(sc);\n    CHECK(sc->sc_mapped && !hardware_off);CHECK(reg==R23BE_REG_HSISR);mmio_reads++;return hsisr_value;\n}\nstatic void __attribute__((unused)) softint_schedule(void *handle) { CHECK(handle!=NULL);soft_schedules++; }\nstatic void xc_barrier(unsigned int flags) {\n    struct rtwn8723be_softc *sc=active_sc;CHECK(sc!=NULL);\n    CHECK(flags==XC_HIGHPRI_IPL(IPL_SOFTNET));\n    CHECK(!in_hard && !in_soft && !in_pserialize && giant_count==0);\n    CHECK(!mutex_owned(&sc->sc_runtime_owner.lifecycle_lock));\n    CHECK(!mutex_owned(&sc->sc_runtime_owner.io_lock));\n    CHECK(!mutex_owned(&sc->sc_irq_lock));\n    CHECK(!mutex_owned(&sc->sc_datapath->tx_lock));\n    CHECK(!sc->sc_irq_requested && !sc->sc_irq_enabled);\n    barriers++;record(EV_BARRIER);\n    if(barrier_hook!=NULL)barrier_hook(sc);\n    switch(barrier_injection) {\n    case 1:sc->sc_irq_epoch++;break;\n    case 2:sc->sc_irq_requested=true;break;\n    case 3:sc->sc_irq_enabled=true;break;\n    case 4:sc->sc_irq_pending[0]=1;break;\n    case 5:sc->sc_ih=&first_lwp;break;\n    case 6:sc->sc_soft_ih=&first_lwp;break;\n    case 7:sc->sc_pihp=(pci_intr_handle_t *)&first_lwp;break;\n    default:break;\n    }\n}\n"
}

PTHREAD = r"""
typedef struct { pthread_cond_t p; } kcondvar_t;
struct work { unsigned token; };
struct workqueue {
    pthread_mutex_t lock;
    pthread_cond_t cv;
    pthread_t thread;
    struct work *queued,*running;
    void (*fn)(struct work *,void *);
    void *arg;
    bool paused,quit;
};
#define PRI_NONE -1
#define WQ_MPSAFE 1
static _Thread_local kmutex_t *held_locks[32];
static _Thread_local unsigned held_count;
static _Thread_local struct lwp actor_lwp;
static void before_block(kmutex_t *);
static void mutex_init(kmutex_t *m,int type,int ipl) {
    CHECK(type==MUTEX_DEFAULT && !m->initialized);
    CHECK(pthread_mutex_init(&m->p,NULL)==0);m->initialized=true;m->ipl=ipl;
}
static bool mutex_owned(kmutex_t *m) {
    for(unsigned i=0;i<held_count;i++)if(held_locks[i]==m)return true;
    return false;
}
static int mutex_tryenter(kmutex_t *m) {
    CHECK(m->initialized && !mutex_owned(m));
    int e=pthread_mutex_trylock(&m->p);
    if(e==EBUSY)return 0;
    CHECK(e==0 && held_count<32);held_locks[held_count++]=m;return 1;
}
static void mutex_enter(kmutex_t *m) {
    CHECK(m->initialized && !mutex_owned(m));
    before_block(m);
    CHECK(pthread_mutex_lock(&m->p)==0 && held_count<32);
    held_locks[held_count++]=m;
}
static void mutex_exit(kmutex_t *m) {
    CHECK(mutex_owned(m));
    for(unsigned i=0;i<held_count;i++)if(held_locks[i]==m) {
        held_locks[i]=held_locks[--held_count];break;
    }
    CHECK(pthread_mutex_unlock(&m->p)==0);
}
static void mutex_destroy(kmutex_t *m) {
    CHECK(m->initialized && !mutex_owned(m));
    CHECK(pthread_mutex_destroy(&m->p)==0);m->initialized=false;destroyed++;
}
static void cv_init(kcondvar_t *c,const char *name) {
    (void)name;CHECK(pthread_cond_init(&c->p,NULL)==0);
}
static void cv_destroy(kcondvar_t *c) {CHECK(pthread_cond_destroy(&c->p)==0);}
static void cv_wait(kcondvar_t *c,kmutex_t *m) {
    CHECK(mutex_owned(m));
    for(unsigned i=0;i<held_count;i++)if(held_locks[i]==m) {
        held_locks[i]=held_locks[--held_count];break;
    }
    CHECK(pthread_cond_wait(&c->p,&m->p)==0);
    CHECK(held_count<32);held_locks[held_count++]=m;
}
static void cv_broadcast(kcondvar_t *c) {CHECK(pthread_cond_broadcast(&c->p)==0);}
static void *work_main(void *arg) {
    struct workqueue *q=arg;curlwp=&actor_lwp;
    CHECK(pthread_mutex_lock(&q->lock)==0);
    for(;;) {
        while((q->queued==NULL || q->paused) && !q->quit)
            CHECK(pthread_cond_wait(&q->cv,&q->lock)==0);
        if(q->quit)break;
        struct work *w=q->queued;q->queued=NULL;q->running=w;
        CHECK(pthread_mutex_unlock(&q->lock)==0);
        q->fn(w,q->arg);
        CHECK(pthread_mutex_lock(&q->lock)==0);
        q->running=NULL;CHECK(pthread_cond_broadcast(&q->cv)==0);
    }
    CHECK(q->queued==NULL && q->running==NULL);
    CHECK(pthread_mutex_unlock(&q->lock)==0);return NULL;
}
static int workqueue_create(struct workqueue **out,const char *name,
    void (*fn)(struct work *,void *),void *arg,int pri,int ipl,int flags) {
    (void)name;CHECK(pri==PRI_NONE && ipl==IPL_SOFTNET && flags==WQ_MPSAFE);
    struct workqueue *q=calloc(1,sizeof(*q));CHECK(q!=NULL);
    q->fn=fn;q->arg=arg;q->paused=true;
    CHECK(pthread_mutex_init(&q->lock,NULL)==0);
    CHECK(pthread_cond_init(&q->cv,NULL)==0);
    CHECK(pthread_create(&q->thread,NULL,work_main,q)==0);*out=q;return 0;
}
static void workqueue_enqueue(struct workqueue *q,struct work *w,void *cpu) {
    CHECK(cpu==NULL && pthread_mutex_lock(&q->lock)==0);
    CHECK(!q->quit && q->queued==NULL);q->queued=w;
    CHECK(pthread_cond_broadcast(&q->cv)==0);
    CHECK(pthread_mutex_unlock(&q->lock)==0);
}
static void workqueue_release(struct workqueue *q) {
    CHECK(pthread_mutex_lock(&q->lock)==0);q->paused=false;
    CHECK(pthread_cond_broadcast(&q->cv)==0);
    CHECK(pthread_mutex_unlock(&q->lock)==0);
}
static void workqueue_wait(struct workqueue *q,struct work *w) {
    CHECK(giant_count==0);
    CHECK(!pthread_equal(pthread_self(),q->thread));
    CHECK(pthread_mutex_lock(&q->lock)==0);
    while(q->queued==w || q->running==w)
        CHECK(pthread_cond_wait(&q->cv,&q->lock)==0);
    CHECK(pthread_mutex_unlock(&q->lock)==0);
}
static void workqueue_destroy(struct workqueue *q) {
    CHECK(pthread_mutex_lock(&q->lock)==0);
    CHECK(q->queued==NULL && q->running==NULL);q->quit=true;
    CHECK(pthread_cond_broadcast(&q->cv)==0);
    CHECK(pthread_mutex_unlock(&q->lock)==0);
    CHECK(pthread_join(q->thread,NULL)==0);
    CHECK(pthread_cond_destroy(&q->cv)==0 && pthread_mutex_destroy(&q->lock)==0);
    free(q);
}
static void delay(unsigned int);
static uint16_t rtwn8723be_read_2(struct rtwn8723be_softc *,uint32_t);
static void rtwn8723be_write_2(struct rtwn8723be_softc *,uint32_t,uint16_t);
static uint32_t rtwn8723be_netbsd_get_bbreg(struct rtwn8723be_softc *,uint32_t,uint32_t);
int rtwn8723be_btc_mp_native_stop(struct rtwn8723be_softc *);
int rtwn8723be_h2c_native_send(struct rtwn8723be_softc *,uint8_t,const uint8_t *,size_t);
int rtwn8723be_btc_mp_native_request(struct rtwn8723be_softc *,uint8_t,const uint8_t *,size_t,bool,struct rtwn8723be_btc_mp_reply *);
"""

BACKEND = r"""
static void before_block(kmutex_t *m) {
    if(active_sc!=NULL && m==&active_sc->sc_runtime_owner.io_lock) {
        CHECK(giant_count==0);
        for(unsigned i=0;i<held_count;i++)CHECK(held_locks[i]->ipl==IPL_NONE);
    }
}
static uint8_t mmio[0x2000];
static unsigned h2c_calls,delay_calls;
static int h2c_error,mp_stop_error;
static bool saw_lowlevel_failure;
static unsigned actions_at_lowlevel_failure;
static unsigned action_total(struct rtwn8723be_softc *);
static void check_mmio(struct rtwn8723be_softc *sc,uint32_t reg,size_t width) {
    CHECK(sc->sc_mapped && !hardware_off && reg<=sizeof(mmio) && width<=sizeof(mmio)-reg);
    bool irq=width==4 && (reg==R23BE_REG_HIMR || reg==R23BE_REG_HIMRE || reg==R23BE_REG_HSIMR) && mutex_owned(&sc->sc_irq_lock);
    if(!irq) {
        CHECK(giant_count==0);
        bool btc=runtime_io_ready(sc,R23BE_IO_BTC),dm=runtime_io_ready(sc,R23BE_IO_DM);
        CHECK(btc || dm);
        if(btc)CHECK(mutex_owned(&sc->sc_btc.engine_lock));
    }
}
static void rtwn8723be_write_4(struct rtwn8723be_softc *sc,uint32_t reg,uint32_t v) {
    check_mmio(sc,reg,4);mmio_writes++;
    if(reg==R23BE_REG_HIMR && v==0)record(EV_MASK);
    for(unsigned i=0;i<4;i++)mmio[reg+i]=(uint8_t)(v>>(8*i));
}
static void rtwn8723be_write_2(struct rtwn8723be_softc *sc,uint32_t reg,uint16_t v) {
    check_mmio(sc,reg,2);mmio_writes++;
    mmio[reg]=(uint8_t)v;mmio[reg+1]=(uint8_t)(v>>8);
}
static void rtwn8723be_write_1(struct rtwn8723be_softc *sc,uint32_t reg,uint8_t v) {
    check_mmio(sc,reg,1);mmio_writes++;mmio[reg]=v;
}
static uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *sc,uint32_t reg) {
    check_mmio(sc,reg,4);mmio_reads++;
    uint32_t value=0;for(unsigned i=0;i<4;i++)value|=(uint32_t)mmio[reg+i]<<(8*i);
    return value;
}
static uint16_t rtwn8723be_read_2(struct rtwn8723be_softc *sc,uint32_t reg) {
    check_mmio(sc,reg,2);mmio_reads++;
    return (uint16_t)((uint16_t)mmio[reg]|(uint16_t)mmio[reg+1]<<8);
}
static uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *sc,uint32_t reg) {
    check_mmio(sc,reg,1);mmio_reads++;return mmio[reg];
}
static uint32_t rtwn8723be_netbsd_get_bbreg(struct rtwn8723be_softc *sc,uint32_t reg,uint32_t mask) {
    CHECK(mask!=0);uint32_t value=rtwn8723be_read_4(sc,reg);
    unsigned shift=0;while((mask&1U)==0){mask>>=1;shift++;}
    return (value>>shift)&mask;
}
static void delay(unsigned int usec) {
    CHECK(usec>0 && giant_count==0 && active_sc!=NULL);
    CHECK(!mutex_owned(&active_sc->sc_runtime_owner.lifecycle_lock));
    CHECK(!mutex_owned(&active_sc->sc_rf_ps_lock));delay_calls++;
}
int rtwn8723be_h2c_native_send(struct rtwn8723be_softc *sc,uint8_t id,
    const uint8_t *data,size_t length) {
    CHECK(sc->sc_h2c.initialized && sc->sc_h2c.state.firmware_ready && sc->sc_linux.fw_ready && data!=NULL);
    CHECK(length<=7 && id!=0 && giant_count==0);
    CHECK(runtime_io_ready(sc,R23BE_IO_BTC));h2c_calls++;
    if(h2c_error!=0 && !saw_lowlevel_failure) {
        actions_at_lowlevel_failure=action_total(sc);saw_lowlevel_failure=true;
    }
    return h2c_error;
}
int rtwn8723be_btc_mp_native_request(struct rtwn8723be_softc *sc,uint8_t opcode,
    const uint8_t *data,size_t length,bool wait,struct rtwn8723be_btc_mp_reply *reply) {
    (void)sc;(void)opcode;(void)data;(void)length;(void)wait;(void)reply;
    /* MP activation remains OPEN: no success is invented for this boundary. */
    return ENOSYS;
}
int rtwn8723be_btc_mp_native_stop(struct rtwn8723be_softc *sc) {
    CHECK(!sc->sc_btc_mp.active);
    return sc->sc_btc_mp.busy ? EBUSY:mp_stop_error;
}
static void __attribute__((unused)) softint_schedule(void *handle) {CHECK(handle!=NULL);soft_schedules++;}
static void xc_barrier(unsigned int flags) {
    struct rtwn8723be_softc *sc=active_sc;
    CHECK(flags==XC_HIGHPRI_IPL(IPL_SOFTNET) && giant_count==0);
    CHECK(!in_hard && !in_soft && !in_pserialize);
    CHECK(!mutex_owned(&sc->sc_runtime_owner.io_lock));
    CHECK(!mutex_owned(&sc->sc_runtime_owner.lifecycle_lock));
    CHECK(!sc->sc_irq_requested && !sc->sc_irq_enabled);
    barriers++;record(EV_BARRIER);
}
struct env {
    pthread_mutex_t gate;
    pthread_cond_t cv;
    bool pause,entered,release,lps,busy;
    unsigned snapshots,enters,leaves,aggregates,queries,faults,calibrations,clocks;
    bool calibration_tracking;
    uint8_t calibration_history;
    uint64_t now;
    int error;
};
static struct env *environment(struct rtwn8723be_softc *sc) {return sc->fixture_env;}
static unsigned action_total(struct rtwn8723be_softc *sc) {
    struct env *e=environment(sc);
    return e->snapshots+e->clocks+e->enters+e->leaves+e->aggregates+e->queries;
}
static void action_scope(struct rtwn8723be_softc *sc) {
    CHECK(giant_count==0 && runtime_io_ready(sc,R23BE_IO_BTC));
    CHECK(sc->sc_btc.first_error==0);
    CHECK(mutex_owned(&sc->sc_btc.engine_lock));
    CHECK(!mutex_owned(&sc->sc_runtime_owner.lifecycle_lock));
    CHECK(!mutex_owned(&sc->sc_rf_ps_lock));
}
static int port_snapshot(void *arg,struct rtwn8723be_btc_wifi_snapshot *out) {
    struct rtwn8723be_softc *sc=arg;struct env *e=environment(sc);action_scope(sc);
    CHECK(out!=NULL);e->snapshots++;
    CHECK(pthread_mutex_lock(&e->gate)==0);
    if(e->pause){e->entered=true;CHECK(pthread_cond_broadcast(&e->cv)==0);
        while(!e->release)CHECK(pthread_cond_wait(&e->cv,&e->gate)==0);}
    CHECK(pthread_mutex_unlock(&e->gate)==0);
    if(e->error)return e->error;
    memset(out,0,sizeof(*out));out->station_linked=true;out->busy=e->busy;
    out->encryption_enabled=true;out->rssi=-39;out->dot11_channel=6;
    out->firmware_version=0x1234;return 0;
}
static int port_clock(void *arg,uint64_t *out) {
    struct rtwn8723be_softc *sc=arg;action_scope(sc);
    CHECK(out!=NULL);environment(sc)->clocks++;
    *out=environment(sc)->now;return environment(sc)->error;
}
static int port_aggregate(void *arg,const struct btc_bt_info *info) {
    struct rtwn8723be_softc *sc=arg;action_scope(sc);CHECK(info!=NULL);
    environment(sc)->aggregates++;return environment(sc)->error;
}
static int port_enter(void *arg) {
    struct rtwn8723be_softc *sc=arg;action_scope(sc);struct env *e=environment(sc);
    e->enters++;if(e->error)return e->error;e->lps=true;return 0;
}
static int port_leave(void *arg) {
    struct rtwn8723be_softc *sc=arg;action_scope(sc);struct env *e=environment(sc);
    e->leaves++;if(e->error)return e->error;e->lps=false;return 0;
}
static int port_query(void *arg,struct btc_coexist *btc,
    enum rtwn8723be_btc_policy_bt_query which,uint32_t *out) {
    struct rtwn8723be_softc *sc=arg;action_scope(sc);
    CHECK(btc==&sc->sc_btc.engine.btc && out!=NULL);
    CHECK(which>=R23BE_BTC_POLICY_BT_PATCH_VERSION && which<=R23BE_BTC_POLICY_BT_FORBIDDEN_SLOT);
    environment(sc)->queries++;return ENOSYS;
}
static void port_fault(void *arg,int error) {
    struct rtwn8723be_softc *sc=arg;CHECK(error!=0 && giant_count==0);
    CHECK(mutex_owned(&sc->sc_runtime_owner.io_lock));
    CHECK(mutex_owned(&sc->sc_btc.engine_lock));
    environment(sc)->faults++;
}
static const struct rtwn8723be_btc_policy_ops configured_ports={
    port_snapshot,port_clock,port_aggregate,port_enter,port_leave,port_query,port_fault
};
static int calibration_step(void *arg) {
    struct rtwn8723be_softc *sc=arg;
    CHECK(sc->sc_linux.stage==R23BE_STAGE_RF_CALIBRATION);
    CHECK(sc->sc_runtime_owner.context->btc_prepared);
    struct env *e=environment(sc);e->calibrations++;
    e->calibration_tracking=sc->sc_runtime_owner.context->dm.thermal.txpower_tracking;
    e->calibration_history=sc->sc_runtime_owner.context->dm.thermal.thermalvalue_avg[0];
    /* The production controller reaches calibration before DM_INIT.
     * Its calibration provider remains an explicit module boundary here. */
    return hardware(sc,91);
}
"""

def source_inputs():
    names = (
        "rtwn8723be_runtime_owner.c", "rtwn8723be_runtime_owner.h",
        "rtwn8723be_btc_native.c", "rtwn8723be_btc_native.h",
        "rtwn8723be_btc_providers_native.c", "rtwn8723be_netbsd.c",
        "rtwn8723be_c2h.h", "rtwn8723be_rx_native.h", "rtwn8723be_rx_binding.h",
        "rtwn8723be_net80211.h", "rtwn8723be_datapath.c", "rtwn8723be_datapath.h",
        "rtwn8723be_calibration_native.h", "rtwn8723be_hw_disable_native.h",
        "rtwn8723be_f16_1.h")
    return {name:(SRC/name).read_text() for name in names}

def build(data, test, owner=None, native_btc=None):
    owner = data["rtwn8723be_runtime_owner.c"] if owner is None else owner
    native_btc = data["rtwn8723be_btc_native.c"] if native_btc is None else native_btc
    prelude=BASE["PRELUDE"]
    prelude=prelude.replace("#include <errno.h>", "#include <errno.h>\n#include <pthread.h>\n#include <stdatomic.h>\n#include <sched.h>\n#include <time.h>\n#include \"rtwn8723be_btc_engine.h\"\n#include \"rtwn8723be_btc_policy.h\"\n#include \"rtwn8723be_btc_context.h\"\n#include \"rtwn8723be_btc_providers_native.h\"\n#include \"rtwn8723be_btc_mp.h\"\n#include \"rtwn8723be_h2c.h\"\n#include \"rtwn8723be_c2h.h\"\n#include \"rtwn8723be_dm.h\"\n#include \"rtwn8723be_rf_serial.h\"")
    prelude=replace_once(prelude,
        "typedef struct { bool initialized, held; int ipl; struct lwp *holder; } kmutex_t;",
        "typedef struct { pthread_mutex_t p; bool initialized; int ipl; } kmutex_t;")
    first=prelude.index("static void mutex_init(")
    end=prelude.index("static bool cpu_intr_p",first)
    prelude=prelude[:first]+PTHREAD+prelude[end:]
    prelude=prelude.replace("static int giant_unlocks, giant_restores, barriers;",
                            "static _Atomic int giant_unlocks, giant_restores, barriers;")
    types=BASE["TYPES"]
    types=replace_once(types,
        "struct { bool initialized, scheduled; void *workqueue, *owner, *owner_arg, *worker; unsigned int calls, count; } sc_btc;",
        "struct rtwn8723be_btc_native sc_btc;")
    types=replace_once(types,"    void *sc_dmat;\n", """    void *sc_dmat;
    size_t sc_mapsize;
    bool sc_bb_valid,sc_bt_ant_valid,sc_btcoexist,sc_package_valid;
    bool sc_rf_chnlval_valid,sc_phy_identity_valid,sc_rf_path_count_valid,sc_xtal_valid;
    struct { bool pci_interface; } sc_phy_identity;
    uint8_t sc_btdm_ant_num,sc_single_ant_path,sc_package_type,sc_rf_path_count,sc_xtal_cap;
    void *fixture_env;
""")
    boundaries=BASE["BOUNDARIES"]
    boundaries=replace_once(boundaries,
        "static int firmware(void *p) { return hardware(p,EV_FW); }",
        "static int firmware(void *p) { struct rtwn8723be_softc *sc=p;int e=hardware(sc,EV_FW);if(!e)sc->sc_h2c.state.firmware_ready=true;return e; }")
    boundaries=replace_once(boundaries,
        "static int __attribute__((unused)) bt_prepare(void *p) { return hardware(p,EV_BT); }",
        "static int bt_prepare(void *p) { int e=hardware(p,EV_BT);return e?e:rtwn8723be_netbsd_bt_prepare(p); }")
    boundaries=replace_once(boundaries,
        "static int bt_halt(void *p) { return hardware(p,EV_BT_HALT); }",
        "static int bt_halt(void *p) { int e=hardware(p,EV_BT_HALT);return e?e:rtwn8723be_netbsd_bt_halt_deinit(p); }")
    boundaries=replace_once(boundaries,".bt_hw_init=step,.rf_calibration=step",
                            ".bt_hw_init=rtwn8723be_netbsd_bt_hw_init,.rf_calibration=calibration_step")
    boundaries=replace_once(boundaries," .dm_init=step,"," .dm_init=rtwn8723be_netbsd_dm_init,")
    boundaries=replace_once(boundaries,
        "CHECK(rtwn8723be_runtime_owner_configure(sc,&h)==0);bind_providers(sc);",
        "CHECK(rtwn8723be_runtime_owner_configure(sc,&h)==0);\n    CHECK(rtwn8723be_runtime_provider_configure(sc,&configured_ports,sc)==0);bind_providers(sc);")
    # The replacement calibration boundary is declared before the real ops
    # initializer; the definition follows hardware() and precedes execution.
    types += "\nstatic int calibration_step(void *);\n"
    pieces=[prelude,without_includes(data["rtwn8723be_runtime_owner.h"]),
            without_includes(data["rtwn8723be_btc_native.h"])]
    for file,name in (
        ("rtwn8723be_rx_native.h","rtwn8723be_rx_dispatch"),
        ("rtwn8723be_net80211.h","rtwn8723be_net80211_methods"),
        ("rtwn8723be_datapath.h","rtwn8723be_datapath"),
        ("rtwn8723be_rx_binding.h","rtwn8723be_rx_binding"),
        ("rtwn8723be_calibration_native.h","rtwn8723be_calibration_owner"),
        ("rtwn8723be_hw_disable_native.h","rtwn8723be_hw_disable_owner")):
        pieces.append(structure(data[file],name))
    pieces += [types]
    constants=data["rtwn8723be_f16_1.h"].split("/* Host interrupt block. */",1)[1].split(
        "/* Linux 8723BE default interrupt contract. */",1)[0]
    queues=re.findall(r"(?m)^#define RTWN8723BE_(?:BK|BE|VI|VO|MGNT|HIGH)_QUEUE[^\n]*",
                      data["rtwn8723be_f16_1.h"])
    pieces.insert(1,constants+"\n"+"\n".join(queues))
    for name in ("rtwn8723be_datapath_start","rtwn8723be_datapath_running_ready",
                 "rtwn8723be_datapath_begin_stop"):
        pieces.append(function(data["rtwn8723be_datapath.c"],name))
    pieces += [without_includes(owner),without_includes(native_btc),
               without_includes(data["rtwn8723be_btc_providers_native.c"])]
    for name in ("rtwn8723be_netbsd_irq_mask_locked","rtwn8723be_netbsd_irq_arm_locked",
                 "rtwn8723be_netbsd_enable_interrupt","rtwn8723be_netbsd_disable_interrupt",
                 "rtwn8723be_netbsd_context_fini"):
        pieces.append(function(data["rtwn8723be_netbsd.c"],name))
    # Backend actions are declared before configure() sees the immutable table.
    pieces.append("static const struct rtwn8723be_btc_policy_ops configured_ports;")
    pieces += [boundaries,BACKEND,test]
    return "\n\n".join(pieces)

TEST = r"""
static void acceptance_cold_before_start(struct rtwn8723be_softc *);
static void acceptance_dm_identity_history(struct rtwn8723be_softc *);
static void init_environment(struct env *e) {
    memset(e,0,sizeof(*e));e->busy=true;e->lps=true;e->now=10000;
    CHECK(pthread_mutex_init(&e->gate,NULL)==0 && pthread_cond_init(&e->cv,NULL)==0);
}
static void setup(struct rtwn8723be_softc *sc,struct env *e,unsigned raw_ant,bool bt) {
    fresh(sc);init_environment(e);sc->fixture_env=e;h2c_error=mp_stop_error=0;
    h2c_calls=delay_calls=0;saw_lowlevel_failure=false;actions_at_lowlevel_failure=0;
    memset(mmio,0,sizeof(mmio));
    probed(sc);
    sc->sc_mapsize=sizeof(mmio);sc->sc_bb_valid=true;
    sc->sc_rf_chnlval_valid=true;sc->sc_phy_identity_valid=true;
    sc->sc_phy_identity.pci_interface=true;sc->sc_rf_path_count_valid=true;
    sc->sc_rf_path_count=1;sc->sc_bt_ant_valid=true;sc->sc_package_valid=true;
    sc->sc_btdm_ant_num=(uint8_t)raw_ant;sc->sc_single_ant_path=0;
    sc->sc_package_type=2;sc->sc_btcoexist=bt;sc->sc_xtal_valid=true;sc->sc_xtal_cap=0x20;
    mmio[R23BE_DM_AGC_REG]=37;mmio[R23BE_DM_ATC_REG+1]=8;
}
static void running(struct rtwn8723be_softc *sc) {
    giant_count=3;
    CHECK(rtwn8723be_runtime_hw_start(sc)==0);
    CHECK(giant_count==3 && sc->sc_linux.stage==R23BE_STAGE_RUNNING);
    CHECK(sc->sc_btc.initialized && sc->sc_btc.engine.btc.initialized);
    CHECK(sc->sc_runtime_owner.context->btc_prepared);
    CHECK(sc->sc_runtime_owner.io_depth==0);
    sc->sc_ec.ec_if.if_flags=IFF_RUNNING|IFF_OACTIVE;sc->sc_ec.ec_if.if_timer=9;
}
static void success_dispose(struct rtwn8723be_softc *sc,struct env *e) {
    if(sc->sc_linux.stage==R23BE_STAGE_RUNNING) {
        CHECK(rtwn8723be_runtime_hw_stop(sc)==0);
        CHECK(giant_count==3 && !sc->sc_btc.initialized);
        CHECK(!sc->sc_runtime_owner.context->btc_prepared);
    }
    giant_count=0;retire(sc);
    CHECK(pthread_cond_destroy(&e->cv)==0 && pthread_mutex_destroy(&e->gate)==0);
}
static void test_configuration(void) {
    struct rtwn8723be_softc sc;struct env e;
    fresh(&sc);init_environment(&e);sc.fixture_env=&e;
    struct rtwn8723be_btc_policy_ops p=configured_ports;
    CHECK(rtwn8723be_runtime_provider_configure(&sc,&p,&sc)==ENOSYS);
    struct rtwn8723be_c2h_handlers h=handlers(&sc);
    CHECK(rtwn8723be_runtime_owner_configure(&sc,&h)==0);
    struct rtwn8723be_runtime_context *c=sc.sc_runtime_owner.context;
    CHECK(rtwn8723be_runtime_provider_configure(&sc,&p,&first_lwp)==EINVAL);
#define MISSING(field) do {p=configured_ports;p.field=NULL;CHECK(rtwn8723be_runtime_provider_configure(&sc,&p,&sc)==ENOSYS);CHECK(!c->providers_configured && mmio_reads==0 && mmio_writes==0);} while(0)
    MISSING(snapshot);MISSING(clock_msec);MISSING(aggregate_apply);MISSING(lps_enter);
    MISSING(lps_leave);MISSING(bt_query);MISSING(fault);
#undef MISSING
    p=configured_ports;CHECK(rtwn8723be_runtime_provider_configure(&sc,&p,&sc)==0);
    CHECK(c->dm.dm_initialgain_enable && !c->dm.thermal.txpower_tracking);
    memset(&p,0,sizeof(p));
    CHECK(c->ports.snapshot==port_snapshot && c->ports.lps_leave==port_leave);
    CHECK(c->policy.ops==&runtime_policy_ops && c->policy.arg==&sc);
    c->policy.aggregate_last_msec=9999;c->dm.thermal.thermalvalue_avg[0]=44;
    p=configured_ports;
    CHECK(rtwn8723be_runtime_provider_configure(&sc,&p,&sc)==EALREADY);
    CHECK(c->policy.aggregate_last_msec==9999 && c->dm.thermal.thermalvalue_avg[0]==44);
    CHECK(rtwn8723be_runtime_probe_ready(&sc)==ENOSYS);
    bind_providers(&sc);CHECK(rtwn8723be_runtime_probe_ready(&sc)==0);
    CHECK(hardware_calls==0 && pci_effects==0 && event_count==0);
    retire(&sc);CHECK(pthread_cond_destroy(&e.cv)==0 && pthread_mutex_destroy(&e.gate)==0);
}
static void test_lifecycle(void) {
    for(unsigned raw=0;raw<2;raw++)for(unsigned present=0;present<2;present++) {
        struct rtwn8723be_softc sc;struct env e;setup(&sc,&e,raw,present!=0);
        acceptance_cold_before_start(&sc);running(&sc);
        CHECK(e.calibrations==1 && !e.calibration_tracking && e.calibration_history==0);
        CHECK(sc.sc_btc.engine.btc.board_info.btdm_ant_num==(raw==0?2:1));
        CHECK(sc.sc_btc.engine.btc.board_info.pg_ant_num==(raw==0?2:1));
        CHECK(sc.sc_runtime_owner.context->dm.dig.cur_igvalue==(mmio[R23BE_DM_AGC_REG]&0x7fU));
        CHECK(sc.sc_runtime_owner.context->dm.atc_status);
        acceptance_dm_identity_history(&sc);
        struct rtwn8723be_runtime_context *c=sc.sc_runtime_owner.context;
        c->policy.aggregate_last_msec=9000;
        c->dm.thermal.tm_trigger=true;c->dm.thermal.thermalvalue_avg[0]=41;
        unsigned leaves=e.leaves;
        CHECK(rtwn8723be_runtime_hw_stop(&sc)==0 && giant_count==3);
        CHECK(c->policy.aggregate_last_msec==9000);
        CHECK(c->dm.thermal.tm_trigger && c->dm.thermal.thermalvalue_avg[0]==41);
        CHECK(!sc.sc_btc.initialized && !c->btc_prepared);
        CHECK(rtwn8723be_btc_native_enable_events(&sc)==EAGAIN);
        CHECK(rtwn8723be_runtime_hw_start(&sc)==0 && giant_count==3);
        CHECK(c==sc.sc_runtime_owner.context && c->policy.aggregate_last_msec==9000);
        CHECK(e.calibrations==2 && e.calibration_tracking && e.calibration_history==41);
        CHECK(c->dm.thermal.tm_trigger && c->dm.thermal.thermalvalue_avg[0]==41);
        CHECK(e.leaves>=leaves);
        sc.sc_ec.ec_if.if_flags=IFF_RUNNING;sc.sc_ec.ec_if.if_timer=9;
        success_dispose(&sc,&e);
    }
}
static void check_stop_busy_unchanged(struct rtwn8723be_softc *sc) {
    unsigned flags=sc->sc_ec.ec_if.if_flags,ev=event_count;
    int timer=sc->sc_ec.ec_if.if_timer;
    bool hal=sc->sc_hal_started,irq=sc->sc_irq_enabled;
    CHECK(rtwn8723be_runtime_hw_stop(sc)==EBUSY);
    CHECK(sc->sc_ec.ec_if.if_flags==flags && sc->sc_ec.ec_if.if_timer==timer);
    CHECK(event_count==ev && sc->sc_hal_started==hal && sc->sc_irq_enabled==irq);
    CHECK(sc->sc_linux.started && sc->sc_linux.stage==R23BE_STAGE_RUNNING);
}
static void test_tokens(void) {
    struct rtwn8723be_softc sc;struct env e;setup(&sc,&e,1,true);running(&sc);
    struct rtwn8723be_runtime_context *c=sc.sc_runtime_owner.context;
    CHECK(rtwn8723be_btc_native_enable_events(&sc)==0 && c->pending_btc==0);
    struct rtwn8723be_btc_event event;memset(&event,0,sizeof(event));
    event.kind=R23BE_BTC_LPS;event.value=0;
    in_soft=true;CHECK(rtwn8723be_btc_native_enqueue(&sc,&event)==0);in_soft=false;
    CHECK(c->pending_btc==1 && sc.sc_btc.count==1);
    check_stop_busy_unchanged(&sc);CHECK(!c->faulted && giant_count==3);
    unsigned free_before=freed;
    CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY && freed==free_before);
    giant_count=0;workqueue_release(sc.sc_btc.workqueue);
    workqueue_wait(sc.sc_btc.workqueue,&sc.sc_btc.work);giant_count=3;
    mutex_enter(&sc.sc_runtime_owner.lifecycle_lock);
    CHECK(c->pending_btc==0 && sc.sc_runtime_owner.io_depth==0);
    mutex_exit(&sc.sc_runtime_owner.lifecycle_lock);
    CHECK(!sc.sc_btc.faulted);success_dispose(&sc,&e);
    /* Permanent admission must reject before touching a deliberately retired
     * child whose lock storage is no longer initialized. */
    sc.sc_btc.initialized=true;
    CHECK(rtwn8723be_btc_native_enable_events(&sc)==ENXIO);
    CHECK(rtwn8723be_btc_native_execute(&sc,&event)==ENXIO);
    CHECK(rtwn8723be_btc_native_enqueue(&sc,&event)==ENXIO);
}
static int policy_busy(struct rtwn8723be_softc *sc) {
    int error=rtwn8723be_runtime_btc_admit(sc);if(error)return error;
    error=runtime_io_acquire(sc,R23BE_IO_BTC);
    if(error){rtwn8723be_runtime_btc_drop(sc);return error;}
    mutex_enter(&sc->sc_btc.engine_lock);bool busy=false,handled=false;
    sc->sc_btc.first_error=0;
    error=rtwn8723be_btc_policy_get(&sc->sc_runtime_owner.context->policy,
        &sc->sc_btc.engine.btc,BTC_GET_BL_WIFI_BUSY,&busy,&handled);
    if(error==0)CHECK(handled && busy==environment(sc)->busy);
    mutex_exit(&sc->sc_btc.engine_lock);
    runtime_btc_release(sc,sc,error);rtwn8723be_runtime_btc_drop(sc);return error;
}
struct actor {struct rtwn8723be_softc *sc;int result,giant_after;bool second;};
static void *policy_actor(void *arg) {
    struct actor *a=arg;curlwp=&actor_lwp;giant_count=2;
    a->result=policy_busy(a->sc);a->giant_after=giant_count;return NULL;
}
static void test_parallel_io(void) {
    struct rtwn8723be_softc sc;struct env e;setup(&sc,&e,1,true);running(&sc);
    struct actor a={&sc,-1,-1,false},b={&sc,-1,-1,true};pthread_t ta,tb;
    CHECK(pthread_mutex_lock(&e.gate)==0);e.pause=true;
    CHECK(pthread_create(&ta,NULL,policy_actor,&a)==0);
    while(!e.entered)CHECK(pthread_cond_wait(&e.cv,&e.gate)==0);
    CHECK(pthread_mutex_unlock(&e.gate)==0);
    check_stop_busy_unchanged(&sc);
    CHECK(pthread_create(&tb,NULL,policy_actor,&b)==0);
    /* Taking the real lifecycle mutex makes this observation synchronized.
     * The bounded wait is only for a reservation, never an unprotected flag. */
    bool waiting=false;
    for(unsigned i=0;i<1000000;i++) {
        mutex_enter(&sc.sc_runtime_owner.lifecycle_lock);
        waiting=sc.sc_runtime_owner.io_depth==2;
        mutex_exit(&sc.sc_runtime_owner.lifecycle_lock);
        if(waiting)break;
        sched_yield();
    }
    CHECK(waiting);check_stop_busy_unchanged(&sc);
    CHECK(pthread_mutex_lock(&e.gate)==0);e.release=true;
    CHECK(pthread_cond_broadcast(&e.cv)==0 && pthread_mutex_unlock(&e.gate)==0);
    CHECK(pthread_join(ta,NULL)==0 && pthread_join(tb,NULL)==0);
    CHECK(a.result==0 && b.result==0 && a.giant_after==2 && b.giant_after==2);
    CHECK(sc.sc_runtime_owner.io_depth==0 && sc.sc_runtime_owner.context->pending_btc==0);
    CHECK(!sc.sc_rfchange_inprogress && !sc.sc_runtime_owner.context->faulted);
    success_dispose(&sc,&e);
}
static void test_admission(void) {
    struct rtwn8723be_softc sc;struct env e;setup(&sc,&e,1,false);running(&sc);
    struct rtwn8723be_runtime_context *c=sc.sc_runtime_owner.context;
    struct rtwn8723be_btc_event event;memset(&event,0,sizeof(event));
    event.kind=(enum rtwn8723be_btc_event_kind)999;
    CHECK(rtwn8723be_btc_native_execute(&sc,&event)==EINVAL);
    CHECK(!c->faulted && c->provider_error==0 && !sc.sc_btc.faulted && c->pending_btc==0);
    event.kind=R23BE_BTC_LPS;event.value=0;
    CHECK(rtwn8723be_btc_native_execute(&sc,&event)==0);
    in_pserialize=true;
    CHECK(rtwn8723be_btc_native_execute(&sc,&event)==EWOULDBLOCK);
    CHECK(rtwn8723be_btc_native_enable_events(&sc)==EWOULDBLOCK);
    CHECK(rtwn8723be_btc_native_stop(&sc)==EWOULDBLOCK);
    in_pserialize=false;CHECK(!sc.sc_btc.faulted && c->provider_error==0);
    c->pending_btc=UINT32_MAX;
    CHECK(rtwn8723be_btc_native_enable_events(&sc)==EOVERFLOW);
    CHECK(c->pending_btc==UINT32_MAX);c->pending_btc=0;
    unsigned reads=mmio_reads,writes=mmio_writes;
    CHECK(rtwn8723be_netbsd_bt_prepare(&sc)==EAGAIN);
    CHECK(rtwn8723be_netbsd_dm_init(&sc)==EAGAIN);
    CHECK(mmio_reads==reads && mmio_writes==writes && sc.sc_runtime_owner.io_depth==0);
    CHECK(rtwn8723be_runtime_btc_admit(&sc)==0);
    unsigned delayed=delay_calls;sc.sc_rfchange_inprogress=true;
    CHECK(runtime_io_acquire(&sc,R23BE_IO_BTC)==ETIMEDOUT);
    CHECK(delay_calls==delayed+100 && giant_count==3 && sc.sc_rfchange_inprogress);
    CHECK(sc.sc_runtime_owner.io_depth==0 && !c->rf_owned && c->provider_error==0);
    sc.sc_rfchange_inprogress=false; /* release the modeled external RF holder */
    CHECK(runtime_io_acquire(&sc,R23BE_IO_BTC)==0 && giant_count==0);
    curlwp=&second_lwp;CHECK(!runtime_io_ready(&sc,R23BE_IO_BTC));curlwp=&first_lwp;
    CHECK(runtime_io_acquire(&sc,R23BE_IO_BTC)==EBUSY);
    CHECK(rtwn8723be_runtime_btc_admit(&sc)==EDEADLK);
    runtime_io_release(&sc,0);rtwn8723be_runtime_btc_drop(&sc);
    CHECK(giant_count==3 && c->pending_btc==0 && sc.sc_runtime_owner.io_depth==0);
    success_dispose(&sc,&e);
}
static void test_provider_failure(void) {
    struct rtwn8723be_softc sc;struct env e;setup(&sc,&e,1,true);running(&sc);
    e.error=EIO;CHECK(policy_busy(&sc)==EIO);
    CHECK(sc.sc_runtime_owner.context->provider_error==EIO && e.faults==1);
    CHECK(sc.sc_runtime_owner.io_depth==0 && sc.sc_runtime_owner.context->pending_btc==0);
    CHECK(giant_count==3 && !sc.sc_rfchange_inprogress);
    CHECK(rtwn8723be_runtime_btc_admit(&sc)==EIO);
    CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY);
    /* Process isolation disposes this retained model. No successful production
     * recovery, STOP, HALT or owner finalization is asserted. */
}
static void test_start_failure(void) {
    struct rtwn8723be_softc sc;struct env e;setup(&sc,&e,1,true);
    h2c_error=EIO;giant_count=3;
    CHECK(rtwn8723be_runtime_hw_start(&sc)==EIO);
    CHECK(!sc.sc_linux.started && !sc.sc_hal_started && sc.sc_btc.initialized);
    CHECK(sc.sc_runtime_owner.context->btc_prepared && sc.sc_runtime_owner.context->faulted);
    CHECK(sc.sc_btc.faulted && sc.sc_runtime_owner.context->provider_error==EIO);
    CHECK(sc.sc_btc.first_error==EIO && sc.sc_btc.last_error==EIO);
    CHECK(saw_lowlevel_failure && action_total(&sc)==actions_at_lowlevel_failure && e.faults<=1);
    CHECK(sc.sc_runtime_owner.io_depth==0 && sc.sc_runtime_owner.context->pending_btc==0);
    CHECK(giant_count==3 && !sc.sc_rfchange_inprogress && !sc.sc_irq_enabled);
    CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY);
}
static void test_stop_failure(void) {
    struct rtwn8723be_softc sc;struct env e;setup(&sc,&e,1,true);running(&sc);
    struct rtwn8723be_runtime_context *c=sc.sc_runtime_owner.context;
    mp_stop_error=EIO;
    CHECK(rtwn8723be_runtime_hw_stop(&sc)==EIO);
    CHECK(c==sc.sc_runtime_owner.context && c->faulted && c->btc_prepared);
    CHECK(!sc.sc_btc.initialized && sc.sc_linux.stage==R23BE_STAGE_STOPPING);
    CHECK(sc.sc_linux.started && sc.sc_hal_started && sc.sc_irq_enabled);
    CHECK(c->pending_btc==0 && sc.sc_runtime_owner.io_depth==0 && giant_count==3);
    CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY);
}
static void test_halt_provider_failure(void) {
    struct rtwn8723be_softc sc;struct env e;setup(&sc,&e,1,true);running(&sc);
    struct rtwn8723be_runtime_context *c=sc.sc_runtime_owner.context;
    h2c_error=EIO;
    CHECK(rtwn8723be_runtime_hw_stop(&sc)==EIO);
    CHECK(saw_lowlevel_failure && action_total(&sc)==actions_at_lowlevel_failure);
    CHECK(e.faults<=1 && c->provider_error==EIO);
    CHECK(sc.sc_btc.first_error==EIO && sc.sc_btc.last_error==EIO && sc.sc_btc.faulted);
    CHECK(sc.sc_btc.initialized && c->btc_prepared && c->faulted);
    CHECK(sc.sc_linux.started && sc.sc_linux.stage==R23BE_STAGE_STOPPING);
    CHECK(sc.sc_hal_started && sc.sc_irq_enabled);
    CHECK(c->pending_btc==0 && sc.sc_runtime_owner.io_depth==0 && giant_count==3);
    CHECK(!sc.sc_rfchange_inprogress && rtwn8723be_runtime_owner_fini(&sc)==EBUSY);
}
static void test_fault_normalization(void) {
    struct rtwn8723be_softc sc;struct env e;setup(&sc,&e,1,true);running(&sc);
    struct rtwn8723be_runtime_context *c=sc.sc_runtime_owner.context;
    CHECK(rtwn8723be_runtime_btc_admit(&sc)==0);
    CHECK(runtime_io_acquire(&sc,R23BE_IO_BTC)==0);
    mutex_enter(&sc.sc_btc.engine_lock);
    rtwn8723be_btc_native_provider_error(&sc,EIO);
    runtime_policy_fault(&sc,ENXIO);
    CHECK(c->provider_error==EIO && sc.sc_btc.first_error==EIO && e.faults==1);
    runtime_policy_fault(&sc,EINVAL);runtime_policy_fault(&sc,EAGAIN);
    CHECK(c->provider_error==EIO && sc.sc_btc.first_error==EIO && e.faults==1);
    mutex_exit(&sc.sc_btc.engine_lock);
    runtime_btc_release(&sc,&sc,EIO);rtwn8723be_runtime_btc_drop(&sc);
    CHECK(c->pending_btc==0 && sc.sc_runtime_owner.io_depth==0 && giant_count==3);
    CHECK(!sc.sc_rfchange_inprogress && rtwn8723be_runtime_btc_admit(&sc)==EIO);
    CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY);
}
/* Deterministic release-snapshot interleaving.  The native btc_fault()
 * transition becomes visible after real validation/engine completion and
 * before the broker takes its queue-locked fault snapshot.  This does not
 * claim automatic mirroring of faults occurring after that snapshot.
 * Each accepted-fault scenario runs in a separate process and retains the
 * failed owners; no harness cleanup is counted as production recovery.
 */
static void test_release_attribution(bool success_case) {
    struct rtwn8723be_softc sc;
    struct env e;
    struct rtwn8723be_btc_native *n;
    struct rtwn8723be_runtime_context *c;
    struct rtwn8723be_btc_event event;
    int validation_error, callback_error;
    unsigned int freed_before, destroyed_before, hardware_before;

    setup(&sc,&e,1,true);running(&sc);
    n=&sc.sc_btc;c=sc.sc_runtime_owner.context;
    CHECK(c!=NULL && c->provider_error==0 && !c->faulted);
    CHECK(!n->faulted && n->last_error==0 && c->pending_btc==0);
    CHECK(rtwn8723be_runtime_btc_admit(&sc)==0);
    CHECK(c->pending_btc==1);
    CHECK(runtime_io_acquire(&sc,R23BE_IO_BTC)==0);
    CHECK(sc.sc_runtime_owner.io_depth==1 && giant_count==0);
    CHECK(sc.sc_rfchange_inprogress && c->rf_owned);
    mutex_enter(&n->engine_lock);
    n->first_error=0;
    memset(&event,0,sizeof(event));
    event.kind=success_case ? R23BE_BTC_LPS :
        (enum rtwn8723be_btc_event_kind)999;
    validation_error=rtwn8723be_btc_event_validate(&n->engine,&event);
    if(success_case) {
        CHECK(validation_error==0);
        callback_error=rtwn8723be_btc_engine_execute(&n->engine,&event);
        CHECK(callback_error==0 && n->first_error==0);
        CHECK(n->owner->ready(n->owner_arg,&sc));
    } else {
        CHECK(validation_error==EINVAL);
        callback_error=validation_error;
    }
    mutex_exit(&n->engine_lock);
    freed_before=freed;destroyed_before=destroyed;hardware_before=hardware_calls;
    /* Invoke the actual native queue-fault transition at the exact boundary. */
    btc_fault(n,ENOBUFS);
    CHECK(n->faulted && n->last_error==ENOBUFS);
    runtime_btc_release(&sc,&sc,callback_error);
    rtwn8723be_runtime_btc_drop(&sc);

    /* Establish balanced ownership before testing first-fault attribution. */
    CHECK(c->pending_btc==0 && sc.sc_runtime_owner.io_depth==0);
    CHECK(c->io_lwp==NULL && c->io_kind==R23BE_IO_NONE);
    CHECK(c->io_giant_count==0 && !c->rf_owned);
    CHECK(!mutex_owned(&sc.sc_runtime_owner.io_lock));
    CHECK(!mutex_owned(&n->engine_lock));
    CHECK(!sc.sc_rfchange_inprogress && giant_count==3);
    CHECK(freed==freed_before && destroyed==destroyed_before);
    CHECK(hardware_calls==hardware_before);
    CHECK(validation_error==(success_case ? 0 : EINVAL));
    CHECK(callback_error==(success_case ? 0 : EINVAL));
    CHECK(n->faulted && n->last_error==ENOBUFS);
    CHECK(c->provider_error==ENOBUFS);
    CHECK(rtwn8723be_runtime_btc_admit(&sc)==ENOBUFS);
    CHECK(c->pending_btc==0 && sc.sc_runtime_owner.io_depth==0);
    CHECK(c==sc.sc_runtime_owner.context && n->initialized && c->btc_prepared);
    CHECK(rtwn8723be_runtime_owner_fini(&sc)==EBUSY);
    CHECK(freed==freed_before && destroyed==destroyed_before);
}
int main(int argc,char **argv) {
    CHECK(argc==2);
    if(!strcmp(argv[1],"configuration"))test_configuration();
    else if(!strcmp(argv[1],"lifecycle"))test_lifecycle();
    else if(!strcmp(argv[1],"tokens"))test_tokens();
    else if(!strcmp(argv[1],"parallel-io"))test_parallel_io();
    else if(!strcmp(argv[1],"admission"))test_admission();
    else if(!strcmp(argv[1],"provider-failure"))test_provider_failure();
    else if(!strcmp(argv[1],"start-failure"))test_start_failure();
    else if(!strcmp(argv[1],"stop-failure"))test_stop_failure();
    else if(!strcmp(argv[1],"halt-provider-failure"))test_halt_provider_failure();
    else if(!strcmp(argv[1],"fault-normalization"))test_fault_normalization();
    else if(!strcmp(argv[1],"invalid-then-native-fault"))test_release_attribution(false);
    else if(!strcmp(argv[1],"success-then-native-fault"))test_release_attribution(true);
    else CHECK(false);
    printf("NATIVE_PROVIDER_CASE=%s PASS\n",argv[1]);return 0;
}
"""

PEER_DM = r"""
/* Audit-only peer acceptance block for the actual native provider fixture.
 * Included after complete production broker/native-BTC/provider bodies.
 * Caller owns the softc/test-thread lifetime and excludes queued/active work.
 * This exercises existing cold storage and genuine native DM; it does not
 * manufacture a DM-ready flag, resource lease, provider or physical device.
 */
static void
acceptance_cold_before_start(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_context *ctx = sc->sc_runtime_owner.context;
    struct rtwn8723be_dm_state expected;

    CHECK(ctx != NULL && ctx->providers_configured && ctx->policy.initialized);
    CHECK(sc->sc_net80211.registered && sc->sc_datapath == &ctx->dp);
    CHECK(sc->sc_linux.stage == R23BE_STAGE_PROBED);
    CHECK(!sc->sc_linux.started && !sc->sc_linux.being_init_adapter);
    CHECK(!sc->sc_hal_started && !ctx->btc_prepared);
    CHECK(sc->sc_runtime_owner.operation == R23BE_RUNTIME_NONE);
    CHECK(sc->sc_runtime_owner.operation_lwp == NULL);
    CHECK(sc->sc_runtime_owner.io_depth == 0 && ctx->pending_btc == 0);
    CHECK(!sc->sc_btc.initialized && !ctx->faulted);
    CHECK(ctx->provider_error == 0);
    /* Cold registration/configuration must itself have performed no MMIO. */
    CHECK(mmio_reads == 0 && mmio_writes == 0);
    memset(&expected, 0, sizeof(expected));
    expected.dm_initialgain_enable = true;
    CHECK(memcmp(&ctx->dm, &expected, sizeof(expected)) == 0);
    CHECK(!ctx->dm.thermal.txpower_tracking);
    CHECK(!ctx->dm.thermal.txpower_state_valid);
}

static void
acceptance_dm_identity_history(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_owner *o = &sc->sc_runtime_owner;
    struct rtwn8723be_runtime_context *ctx = o->context;
    struct rtwn8723be_btc_native *n = &sc->sc_btc;
    struct rtwn8723be_dm_state before;
    struct rtwn8723be_thermal_state expected_thermal;
    struct rtwn8723be_btc_native_owner foreign_owner;
    struct rtwn8723be_btc_policy foreign_policy;
    const struct rtwn8723be_btc_native_owner *saved_owner;
    void *saved_owner_arg, *saved_adapter, *saved_policy;
    enum rtwn8723be_linux_stage saved_stage;
    enum rtwn8723be_runtime_operation saved_operation;
    struct lwp *saved_lwp;
    bool saved_started, saved_hal, saved_being_init;
    bool saved_requested, saved_enabled, saved_rf;
    unsigned int saved_flags, saved_epoch;
    int saved_timer, saved_giant;
    uint64_t saved_policy_clock;

    CHECK(ctx != NULL && ctx->providers_configured && ctx->policy.initialized);
    CHECK(sc->sc_linux.stage == R23BE_STAGE_RUNNING);
    CHECK(sc->sc_linux.started && sc->sc_hal_started);
    CHECK(!sc->sc_linux.being_init_adapter);
    CHECK(o->operation == R23BE_RUNTIME_NONE && o->operation_lwp == NULL);
    CHECK(o->io_depth == 0 && ctx->pending_btc == 0);
    CHECK(!ctx->faulted && ctx->provider_error == 0);
    CHECK(ctx->btc_prepared && n->initialized && n->engine.btc.initialized);
    CHECK(n->owner == &runtime_btc_owner && n->owner_arg == sc);
    CHECK(n->engine.btc.adapter == sc);
    CHECK(n->engine.btc.r23be_policy == &ctx->policy);
    CHECK(n->calls == 0 && n->count == 0 && !n->scheduled);
    CHECK(!mutex_owned(&o->io_lock) && !mutex_owned(&o->lifecycle_lock));
    CHECK(!mutex_owned(&n->engine_lock));
    CHECK(!sc->sc_rfchange_inprogress);

    saved_owner = n->owner;
    saved_owner_arg = n->owner_arg;
    saved_adapter = n->engine.btc.adapter;
    saved_policy = n->engine.btc.r23be_policy;
    foreign_owner = *saved_owner; /* complete real callbacks, wrong identity */
    foreign_policy = ctx->policy; /* complete real policy, wrong lifetime */
    saved_stage = sc->sc_linux.stage;
    saved_started = sc->sc_linux.started;
    saved_hal = sc->sc_hal_started;
    saved_being_init = sc->sc_linux.being_init_adapter;
    saved_operation = o->operation;
    saved_lwp = o->operation_lwp;
    saved_flags = sc->sc_ec.ec_if.if_flags;
    saved_timer = sc->sc_ec.ec_if.if_timer;
    saved_requested = sc->sc_irq_requested;
    saved_enabled = sc->sc_irq_enabled;
    saved_epoch = sc->sc_irq_epoch;
    saved_rf = sc->sc_rfchange_inprogress;
    saved_giant = giant_count;
    saved_policy_clock = ctx->policy.aggregate_last_msec;

    /* These fields are genuine persistent history, unassigned by frozen
     * rtl8723be_dm_init_txpower_tracking().  Do not cold-construct here. */
    ctx->dm.thermal.tm_trigger = 1;
    ctx->dm.thermal.txpower_trackinginit = true;
    ctx->dm.thermal.done_txpower = true;
    ctx->dm.thermal.txpowercount = 11;
    ctx->dm.thermal.thermalvalue_lck = 37;
    ctx->dm.thermal.thermalvalue_iqk = 39;
    ctx->dm.thermal.thermalvalue_avg_index = 3;
    ctx->dm.thermal.last_error = EIO;
    ctx->dm.thermal.last_restore_error = EBUSY;
    for (unsigned int i = 0; i < 8; i++)
        ctx->dm.thermal.thermalvalue_avg[i] = (uint8_t)(31U + i);
    for (unsigned int i = 1; i < 4; i++) {
        ctx->dm.thermal.ofdm_index[i] = (int8_t)(27U + i);
        ctx->dm.thermal.delta_power_index[i] = (int8_t)(1U + i);
        ctx->dm.thermal.delta_power_index_last[i] = (int8_t)(2U + i);
        ctx->dm.thermal.power_index_offset[i] = (int8_t)(3U + i);
        ctx->dm.thermal.swing_idx_ofdm[i] = (uint8_t)(28U + i);
        ctx->dm.thermal.swing_idx_ofdm_base[i] = (uint8_t)(29U + i);
    }
    /* Similar names are distinct frozen wifi.h fields; these are history. */
    ctx->dm.dig.cursta_cstate = 17;
    ctx->dm.dig.pre_sta_cstate = 19;
    ctx->dm.dig.rssi_val = 53;
    ctx->dm.ra.last_ratr = UINT32_C(0x13579bdf);
    ctx->dm.ra.reserve = UINT16_C(0x5a5a);
    memcpy(&before, &ctx->dm, sizeof(before));

    /* The fixture deliberately presents the actual pre-DM START checkpoint.
     * Only lifecycle controls are temporarily changed; real configured
     * providers, parsed resources, BTC context and RF/MMIO lease stay real. */
    mutex_enter(&o->lifecycle_lock);
    o->operation = R23BE_RUNTIME_START;
    o->operation_lwp = curlwp;
    sc->sc_linux.stage = R23BE_STAGE_DM_INIT;
    sc->sc_linux.started = false;
    sc->sc_linux.being_init_adapter = true;
    sc->sc_hal_started = false;
    mutex_exit(&o->lifecycle_lock);

    for (unsigned int which = 0; which < 4; which++) {
        unsigned int reads = mmio_reads, writes = mmio_writes;
        int error;

        if (which == 0)
            n->owner = &foreign_owner;
        else if (which == 1)
            n->owner_arg = &foreign_owner;
        else if (which == 2)
            n->engine.btc.adapter = &foreign_policy;
        else
            n->engine.btc.r23be_policy = &foreign_policy;
        CHECK(ctx->btc_prepared && n->initialized && n->engine.btc.initialized);
        error = rtwn8723be_netbsd_dm_init(sc);
        CHECK(error == EAGAIN);
        CHECK(mmio_reads == reads && mmio_writes == writes);
        CHECK(memcmp(&ctx->dm, &before, sizeof(before)) == 0);
        CHECK(o->io_depth == 0 && ctx->pending_btc == 0);
        CHECK(ctx->io_lwp == NULL && ctx->io_kind == R23BE_IO_NONE);
        CHECK(ctx->io_giant_count == 0 && !ctx->rf_owned);
        CHECK(!mutex_owned(&o->io_lock) && !sc->sc_rfchange_inprogress);
        CHECK(giant_count == saved_giant && ctx->provider_error == 0);
        CHECK(!ctx->faulted);
        n->owner = saved_owner;
        n->owner_arg = saved_owner_arg;
        n->engine.btc.adapter = saved_adapter;
        n->engine.btc.r23be_policy = saved_policy;
    }

    {
        unsigned int reads = mmio_reads, writes = mmio_writes;
        CHECK(rtwn8723be_netbsd_dm_init(sc) == 0);
        CHECK(mmio_reads == reads + 2U && mmio_writes == writes);
    }
    CHECK(o->io_depth == 0 && ctx->pending_btc == 0);
    CHECK(ctx->io_lwp == NULL && ctx->io_kind == R23BE_IO_NONE);
    CHECK(ctx->io_giant_count == 0 && !ctx->rf_owned);
    CHECK(!mutex_owned(&o->io_lock) && !sc->sc_rfchange_inprogress);
    CHECK(giant_count == saved_giant && ctx->provider_error == 0);
    CHECK(ctx->policy.aggregate_last_msec == saved_policy_clock);
    CHECK(!ctx->faulted);

    /* Exact frozen tracking-init assignments; all remaining thermal bytes,
     * including the deliberately seeded warm history, must be retained.
     * The separate raw-Linux differential DM test validates these equations. */
    memcpy(&expected_thermal, &before.thermal, sizeof(expected_thermal));
    expected_thermal.txpower_tracking = true;
    expected_thermal.txpower_track_control = true;
    expected_thermal.thermalvalue = 0;
    expected_thermal.ofdm_index[0] = 30;
    expected_thermal.cck_index = 20;
    expected_thermal.swing_idx_cck_base = 20;
    expected_thermal.swing_idx_ofdm_base[0] = 30;
    expected_thermal.delta_power_index[0] = 0;
    expected_thermal.delta_power_index_last[0] = 0;
    expected_thermal.power_index_offset[0] = 0;
    expected_thermal.txpower_state_valid = true;
    CHECK(memcmp(&ctx->dm.thermal, &expected_thermal,
        sizeof(expected_thermal)) == 0);
    CHECK(ctx->dm.dig.cursta_cstate == before.dig.cursta_cstate);
    CHECK(ctx->dm.dig.pre_sta_cstate == before.dig.pre_sta_cstate);
    CHECK(ctx->dm.dig.rssi_val == before.dig.rssi_val);
    CHECK(ctx->dm.ra.last_ratr == before.ra.last_ratr);
    CHECK(ctx->dm.ra.reserve == before.ra.reserve);
    CHECK(ctx->dm.dm_type == 1 && ctx->dm.useramask);
    CHECK(ctx->dm.dig.rssi_lowthresh == 35);
    CHECK(ctx->dm.dig.rssi_highthresh == 40);
    CHECK(ctx->dm.ra.high_rssi_thresh_for_ra == 50);
    CHECK(ctx->dm.ra.low_rssi_thresh_for_ra40m == 20);
    CHECK(ctx->dm.crystal_cap == sc->sc_xtal_cap);
    CHECK(ctx->dm.cfo_threshold == 10);

    mutex_enter(&o->lifecycle_lock);
    o->operation = saved_operation;
    o->operation_lwp = saved_lwp;
    sc->sc_linux.stage = saved_stage;
    sc->sc_linux.started = saved_started;
    sc->sc_linux.being_init_adapter = saved_being_init;
    sc->sc_hal_started = saved_hal;
    mutex_exit(&o->lifecycle_lock);
    CHECK(sc->sc_ec.ec_if.if_flags == saved_flags);
    CHECK(sc->sc_ec.ec_if.if_timer == saved_timer);
    CHECK(sc->sc_irq_requested == saved_requested);
    CHECK(sc->sc_irq_enabled == saved_enabled && sc->sc_irq_epoch == saved_epoch);
    CHECK(sc->sc_rfchange_inprogress == saved_rf);
    CHECK(n->owner == saved_owner && n->owner_arg == saved_owner_arg);
    CHECK(n->engine.btc.adapter == saved_adapter);
    CHECK(n->engine.btc.r23be_policy == saved_policy);
}

/* Proposed mutation DATA, each scoped ONLY to runtime_io_phase():
 *
 * dm-foreign-owner-accepted:
 *   "sc->sc_btc.owner == &runtime_btc_owner &&" -> "true &&"
 * dm-foreign-owner-arg-accepted:
 *   "sc->sc_btc.owner_arg == sc &&" -> "true &&"
 * dm-foreign-adapter-accepted:
 *   "sc->sc_btc.engine.btc.adapter == sc &&" -> "true &&"
 * dm-foreign-policy-accepted:
 *   "sc->sc_btc.engine.btc.r23be_policy == &ctx->policy &&" -> "true &&"
 *
 * All four negative cases otherwise retain the complete initialized/prepared
 * context and valid START checkpoint; removing one guard must reach real BB
 * reads and return success, failing the exact EAGAIN/no-effect assertion.
 */

"""

CASES = ("configuration","lifecycle","tokens","parallel-io","admission",
         "provider-failure","start-failure","stop-failure","halt-provider-failure","fault-normalization",
         "invalid-then-native-fault","success-then-native-fault")
UNITS = ("rtwn8723be_linux_state.c","rtwn8723be_btc_context.c",
         "rtwn8723be_btc_policy.c","rtwn8723be_btc_engine.c",
         "rtwn8723be_btc1.c","rtwn8723be_btc2.c","rtwn8723be_dm.c",
         "rtwn8723be_thermal.c","rtwn8723be_calibration.c","rtwn8723be_rf_serial.c")
FLAGS = ("-std=c11","-Wall","-Wextra","-Werror","-pedantic",
         "-Wno-unused-parameter","-fsanitize=undefined","-fno-sanitize-recover=all","-pthread")
MUTANTS = [
    ("missing-action","owner","runtime_ports_ok","p->lps_leave != NULL",
     "(p->lps_leave != NULL || p->lps_leave == NULL)","configuration"),
    ("ports-copy-lost","owner","rtwn8723be_runtime_provider_configure",
     "ctx->ports = *ports;","memset(&ctx->ports,0,sizeof(ctx->ports));","configuration"),
    ("configuration-overwritten","owner","rtwn8723be_runtime_provider_configure",
     "else if (ctx->providers_configured)","else if (false && ctx->providers_configured)","configuration"),
    ("queued-pin-ignored","owner","runtime_claim",
     "(owner->context != NULL && owner->context->pending_btc != 0)",
     "false","tokens"),
    ("admit-pin-lost","owner","rtwn8723be_runtime_btc_admit",
     "ctx->pending_btc++;","ctx->pending_btc += 0;","tokens"),
    ("copied-event-pin-leaked","native","btc_worker",
     "rtwn8723be_runtime_btc_drop(sc);",
     "(void)sc;","tokens"),
    ("Giant-held-before-io-lock","owner","runtime_io_acquire",
     "if (KERNEL_LOCKED_P())","if (false && KERNEL_LOCKED_P())","lifecycle"),
    ("validation-error-quarantined","owner","runtime_btc_release",
     "runtime_io_release(sc, fault_error);",
     "(void)fault_error;\n    runtime_io_release(sc, error);","admission"),
    ("observed-native-fault-replaced-by-callback","owner","runtime_btc_release",
     "fault_error = sc->sc_btc.faulted ? sc->sc_btc.last_error : 0;",
     "fault_error = sc->sc_btc.faulted ? error : 0;","invalid-then-native-fault"),
    ("events-admission-lost","native","rtwn8723be_btc_native_enable_events",
     "error = rtwn8723be_runtime_btc_admit(sc);","error = 0;","tokens"),
    ("pserialize-admission-lost","native","btc_thread",
     "pserialize_not_in_read_section()","(pserialize_not_in_read_section() || true)","admission"),
    ("dm-foreign-owner","owner","runtime_io_phase",
     "sc->sc_btc.owner == &runtime_btc_owner &&","true &&","lifecycle"),
    ("dm-foreign-owner-argument","owner","runtime_io_phase",
     "sc->sc_btc.owner_arg == sc &&","true &&","lifecycle"),
    ("dm-foreign-adapter","owner","runtime_io_phase",
     "sc->sc_btc.engine.btc.adapter == sc &&","true &&","lifecycle"),
    ("dm-foreign-policy","owner","runtime_io_phase",
     "sc->sc_btc.engine.btc.r23be_policy == &ctx->policy &&","true &&","lifecycle"),
    ("policy-history-reset","owner","rtwn8723be_netbsd_bt_prepare",
     "ctx->btc_prepared = true;",
     "ctx->btc_prepared = true;\n        ctx->policy.aggregate_last_msec = 0;","lifecycle"),
    ("warm-DM-cold-constructed","owner","rtwn8723be_netbsd_dm_init",
     "error = rtwn8723be_dm_init(&ctx->dm, &io, sc, sc->sc_xtal_cap);",
     "rtwn8723be_dm_construct(&ctx->dm);\n    error = rtwn8723be_dm_init(&ctx->dm, &io, sc, sc->sc_xtal_cap);","lifecycle"),
    ("policy-first-error-gate-lost","owner","runtime_policy_context",
     "sc->sc_btc.first_error == 0","(sc->sc_btc.first_error == 0 || true)","start-failure"),
    ("policy-first-error-normalizer-lost","owner","runtime_policy_fault",
     "error = sc->sc_btc.first_error;",
     "error = error == 0 ? sc->sc_btc.first_error : error;","fault-normalization"),
    ("fault-notified-repeatedly","owner","runtime_policy_fault",
     "if (notify)","if (notify || !notify)","fault-normalization"),
    ("RF-owner-stolen","owner","runtime_io_acquire",
     "if (!sc->sc_rfchange_inprogress)","if (true)","admission"),
    ("Giant-restore-lost","owner","runtime_io_release",
     "KERNEL_LOCK(giant_count, NULL);",
     "KERNEL_LOCK(giant_count - giant_count, NULL);","lifecycle"),
]
def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--baseline-only",action="store_true")
    args=parser.parse_args()
    attempt=os.environ["RTWN8723BE_FIXTURE_ATTEMPT"]
    assert re.fullmatch(r"[A-Za-z0-9_-]+",attempt)
    out=WORK/("native-provider-"+attempt)
    out.mkdir()
    receipt=out/"proof.json"
    data=source_inputs()
    paths={Path(__file__)}
    pending=[SRC/p for p in set(UNITS)|set(data)]
    while pending:
        path=pending.pop()
        if path in paths:continue
        paths.add(path)
        for dep in re.findall(r'^#\s*include\s*"([^"]+)"',path.read_text(),re.M):
            child=SRC/dep
            if child.is_file():pending.append(child)
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    assert subprocess.check_output(
        ["git","--no-optional-locks","-C",str(LINUX),"rev-parse","HEAD"],text=True).strip()==PIN
    frozen={}
    for name in ("pci.c","rtl8723be/hw.c"):
        path="drivers/net/wireless/realtek/rtlwifi/"+name
        raw=subprocess.check_output(["git","--no-optional-locks","-C",str(LINUX),"show",PIN+":"+path])
        assert raw==(LINUX/path).read_bytes()
        frozen[path]=hashlib.sha256(raw).hexdigest()
    proof={"result":"RUNNING","attempt":attempt,"pid":os.getpid(),"source_sha256":hashes,
           "frozen_sha256":frozen,"positive":[],"mutants":[],"physical":"NOT_RUN",
           "dialect_exception":{"rtwn8723be_btc_engine.c":"GNU11 for unchanged BOTH macro empty variadic dispatch; all other actual units and generated fixture remain strict C11/pedantic"},
           "scope":"Production runtime owner, BTC native/context/engine/policy/providers, both actual antenna algorithms, DM and Linux controller; pthread/kernel/MMIO/H2C/configured action boundaries are explicit models.",
           "limits":["No NetBSD ABI/SMP proof or physical firmware/WLAN/PM acceptance.",
                     "MP activation and genuine calibration/HW-disable supplier configuration remain OPEN.",
                     "Failure scenarios use separate process lifetimes; retained model storage is not production recovery."]}
    def save():
        receipt.write_text(json.dumps(proof,sort_keys=True,indent=2)+"\n")
    def compile_run(command,label):
        result=subprocess.run(command,cwd=out,text=True,stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,timeout=240)
        (out/(label+"-compile.log")).write_text(result.stdout)
        if result.returncode:
            proof.update(result="FAILED",failure={"phase":"compile","label":label,"exit":result.returncode})
            save()
            raise AssertionError((label,"COMPILE_FAILED",result.stdout))
    save()
    objects={}
    try:
        for mode,defs in (("normal",()),("ndebug",("-DNDEBUG",))):
            objects[mode]=[]
            for unit in UNITS:
                obj=out/(mode+"-"+Path(unit).stem+".o")
                # The frozen dispatcher has GNU ##__VA_ARGS__ empty calls.
                # Keep this existing dialect exception local to that real TU.
                unit_flags=FLAGS if unit!="rtwn8723be_btc_engine.c" else tuple(
                    flag for flag in FLAGS if flag not in ("-std=c11","-pedantic"))+("-std=gnu11",)
                compile_run(["/usr/bin/cc",*unit_flags,*defs,"-I",str(SRC),"-c",str(SRC/unit),"-o",str(obj)],
                            mode+"-"+Path(unit).stem)
                objects[mode].append(str(obj))
            model=build(data,PEER_DM+TEST)
            c=out/(mode+"-fixture.c");c.write_text(model)
            exe=out/(mode+"-fixture")
            compile_run(["/usr/bin/cc",*FLAGS,*defs,"-I",str(SRC),str(c),*objects[mode],"-o",str(exe)],mode)
            for case in CASES:
                run=subprocess.run([str(exe),case],cwd=out,text=True,stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,timeout=90)
                (out/(mode+"-"+case+"-run.log")).write_text(run.stdout)
                proof["positive"].append({"mode":mode,"case":case,"compile_exit":0,"run_exit":run.returncode})
                save()
                assert run.returncode==0,(mode,case,run.returncode,run.stdout)
        if not args.baseline_only:
            for label,kind,name,before,after,case in MUTANTS:
                key="rtwn8723be_runtime_owner.c" if kind=="owner" else "rtwn8723be_btc_native.c"
                original=data[key];body=function(original,name)
                changed=replace_once(body,before,after)
                unit=replace_once(original,body,changed)
                model=build(data,PEER_DM+TEST,
                            owner=unit if kind=="owner" else None,
                            native_btc=unit if kind=="native" else None)
                c=out/(label+".c");c.write_text(model);exe=out/label
                compile_run(["/usr/bin/cc",*FLAGS,"-DNDEBUG","-I",str(SRC),str(c),
                             *objects["ndebug"],"-o",str(exe)],label)
                run=subprocess.run([str(exe),case],cwd=out,text=True,
                                   stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
                (out/(label+"-run.log")).write_text(run.stdout)
                assert run.returncode==97 and "FIXTURE_ASSERT:" in run.stdout,(
                    label,"mutant did not hit a runtime assertion",run.returncode,run.stdout)
                proof["mutants"].append({"name":label,"case":case,"compile_exit":0,
                                         "run_exit":run.returncode,"assertion":run.stdout.strip()[-500:]})
                save()
        actual={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
        assert actual==hashes,"source input changed during fixture execution"
        proof.update(result="PASS",source_unchanged=True,mutants_executed=len(proof["mutants"]),
                     positive_executions=len(proof["positive"]),
                     baseline_only=args.baseline_only)
        save()
    except BaseException as exc:
        proof.update(result="FAILED",error=str(exc));save();raise
    print("NATIVE_PROVIDER_PASS positives="+str(len(proof["positive"]))+
          " mutants_executed="+str(len(proof["mutants"])),receipt)

if __name__=="__main__":
    main()
