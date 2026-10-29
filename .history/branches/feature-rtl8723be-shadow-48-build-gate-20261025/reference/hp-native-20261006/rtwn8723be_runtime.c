/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Actual RTL8723BE NetBSD RF/DM/net80211 lifetime.
 * Frozen Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab:
 * pci.c/core.c/base.c/ps.c, rtl8723be/{hw,fw,dm,phy}.c and halbtcoutsrc.c.
 * Frozen NetBSD 03d918f6d0e81fa05b8f1160eca0628ad39988a6: if_rtwn.c.
 *
 * The lifecycle mutex serializes thread transitions. The adaptive I/O
 * mutex excludes RF/channel/DM/calibration/BTC/H2C and precedes the BTC
 * engine mutex. RX only copies statistics/events under IPL_SOFTNET locks;
 * it never waits for that I/O mutex. Stop closes/drains copied jobs and
 * BTC/MP calls BEFORE power or DMA lifetime is released. No spin lock is
 * held across the source delays or firmware waits.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/kernel.h>
#include <sys/kmem.h>
#include <sys/cpu.h>
#include <sys/intr.h>
#include <sys/proc.h>
#include <sys/endian.h>
#include <sys/errno.h>
#include <net/if.h>
#include "rtwn8723be_runtime.h"
#include <net80211/ieee80211_proto.h>
#include <net80211/ieee80211_node.h>
#include "rtwn8723be_c2h_native.h"
#include "rtwn8723be_rf_serial.h"

static void runtime_worker(struct work *, void *);
static void runtime_watchdog_timer(void *);
static void runtime_scan_timer(void *);
static int runtime_newstate(struct ieee80211com *, enum ieee80211_state, int);
static int runtime_state(struct rtwn8723be_softc *, enum ieee80211_state, int);
static int runtime_watchdog(struct rtwn8723be_softc *);
static int runtime_queue(struct rtwn8723be_softc *,
    enum rtwn8723be_runtime_job_kind, enum ieee80211_state, int);

static bool
runtime_thread(void)
{
    return !cpu_intr_p() && !cpu_softintr_p();
}

int
rtwn8723be_runtime_io_enter(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r;
    if (sc == NULL || (r = sc->sc_runtime) == NULL || !r->initialized)
        return ENXIO;
    if (!runtime_thread()) return EWOULDBLOCK;
    if (mutex_owned(&r->io_lock)) {
        if (r->io_depth == UINT_MAX) return EOVERFLOW;
        r->io_depth++;
        return 0;
    }
    mutex_enter(&r->io_lock);
    r->io_depth = 1;
    if (!sc->sc_mapped || sc->sc_mapsize < 0x1000U) {
        r->io_depth = 0;
        mutex_exit(&r->io_lock);
        return ENXIO;
    }
    return 0;
}

void
rtwn8723be_runtime_io_exit(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    KASSERT(r != NULL && mutex_owned(&r->io_lock) && r->io_depth != 0);
    if (--r->io_depth == 0) mutex_exit(&r->io_lock);
}

bool
rtwn8723be_runtime_io_ready(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc == NULL ? NULL : sc->sc_runtime;
    bool ready;
    if (r == NULL || !r->initialized || !mutex_owned(&r->io_lock) ||
        r->io_depth == 0 || !sc->sc_mapped || sc->sc_mapsize < 0x1000U)
        return false;
    mutex_enter(&r->queue_lock);
    ready = !r->faulted || r->shutdown_active;
    mutex_exit(&r->queue_lock);
    return ready;
}

static void
runtime_fault(struct rtwn8723be_softc *sc, int error)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    unsigned int tail;
    bool first;
    if (error == 0 || r == NULL) return;
    mutex_enter(&r->queue_lock);
    first = !r->faulted;
    r->faulted = true;
    if (r->first_error == 0) r->first_error = error;
    r->jobs_enabled = false;
    /* A quarantined provider requests real thread teardown, never a
     * fabricated successful notification or more algorithm I/O. */
    if (first && !r->closing && r->workqueue != NULL) {
        if (r->count == R23BE_RUNTIME_QUEUE) {
            r->head = 0;
            r->count = 0; /* obsolete scalar jobs; state stays uncommitted */
        }
        tail = (r->head + r->count) % R23BE_RUNTIME_QUEUE;
        memset(&r->jobs[tail], 0, sizeof(r->jobs[tail]));
        r->jobs[tail].kind = R23BE_RUNTIME_QUIESCE;
        r->jobs[tail].generation = r->generation;
        r->count++;
        if (!r->scheduled) {
            r->scheduled = true;
            workqueue_enqueue(r->workqueue, &r->work, NULL);
        }
    }
    mutex_exit(&r->queue_lock);
}

static int
btc_owner_acquire(void *arg, struct rtwn8723be_softc *sc)
{
    if (arg != sc->sc_runtime) return ENXIO;
    return rtwn8723be_runtime_io_enter(sc);
}
static bool
btc_owner_ready(void *arg, struct rtwn8723be_softc *sc)
{
    return arg == sc->sc_runtime && rtwn8723be_runtime_io_ready(sc);
}
static void
btc_owner_release(void *arg, struct rtwn8723be_softc *sc, int error)
{
    KASSERT(arg == sc->sc_runtime);
    if (error != 0 && !sc->sc_runtime->shutdown_active)
        runtime_fault(sc, error);
    rtwn8723be_runtime_io_exit(sc);
}
static const struct rtwn8723be_btc_native_owner runtime_btc_owner = {
    btc_owner_acquire, btc_owner_ready, btc_owner_release
};

static bool
runtime_rf_ready(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    return rtwn8723be_runtime_io_ready(sc) && r->rf_state_valid && r->rf_on &&
        sc->sc_bb_valid && sc->sc_rf_path_count_valid &&
        sc->sc_rf_path_count == 1U && sc->sc_rf_chnlval_valid;
}
static int
runtime_reg(struct rtwn8723be_softc *sc, uint32_t reg, unsigned int width)
{
    if (!rtwn8723be_runtime_io_ready(sc)) return ENXIO;
    if ((reg & (width - 1U)) != 0 || reg > sc->sc_mapsize ||
        width > sc->sc_mapsize - reg) return EINVAL;
    return 0;
}
static int runtime_read8(void *arg, uint32_t reg, uint8_t *out)
{
    struct rtwn8723be_softc *sc = arg;
    int error = runtime_reg(sc, reg, 1);
    if (out == NULL) return EINVAL;
    if (error == 0) *out = rtwn8723be_read_1(sc, reg);
    return error;
}
static int runtime_read16(void *arg, uint32_t reg, uint16_t *out)
{
    struct rtwn8723be_softc *sc = arg;
    int error = runtime_reg(sc, reg, 2);
    if (out == NULL) return EINVAL;
    if (error == 0) *out = rtwn8723be_read_2(sc, reg);
    return error;
}
static int runtime_read32(void *arg, uint32_t reg, uint32_t *out)
{
    struct rtwn8723be_softc *sc = arg;
    int error = runtime_reg(sc, reg, 4);
    if (out == NULL) return EINVAL;
    if (error == 0) *out = rtwn8723be_read_4(sc, reg);
    return error;
}
static int runtime_write8(void *arg, uint32_t reg, uint8_t value)
{
    struct rtwn8723be_softc *sc = arg;
    int error = runtime_reg(sc, reg, 1);
    if (error == 0) {
        rtwn8723be_write_1(sc, reg, value);
        /* hw.c's BCN_CTRL cache belongs to the actual register writer. */
        if (reg == 0x550U) sc->sc_bcn_ctrl_val = value;
    }
    return error;
}
static int runtime_write16(void *arg, uint32_t reg, uint16_t value)
{
    struct rtwn8723be_softc *sc = arg;
    int error = runtime_reg(sc, reg, 2);
    if (error == 0) rtwn8723be_write_2(sc, reg, value);
    return error;
}
static int runtime_write32(void *arg, uint32_t reg, uint32_t value)
{
    struct rtwn8723be_softc *sc = arg;
    int error = runtime_reg(sc, reg, 4);
    if (error == 0) {
        rtwn8723be_write_4(sc, reg, value);
        if (reg == 0x608U) sc->sc_receive_config = value;
    }
    return error;
}
static void runtime_rf_delay(void *arg, unsigned int usec)
{
    KASSERT(runtime_rf_ready(arg));
    delay(usec);
}
static const struct rtwn8723be_rf_serial_io runtime_rf_io = {
    runtime_rf_ready, runtime_read32, runtime_write32, runtime_rf_delay
};

int
rtwn8723be_runtime_read_rf(struct rtwn8723be_softc *sc, unsigned int path,
    uint32_t reg, uint32_t mask, uint32_t *out)
{
    const struct rtwn8723be_rf_serial_ctx ctx = { &runtime_rf_io, sc };
    uint32_t value;
    unsigned int shift;
    int error;
    if (out == NULL || mask == 0 || (mask & ~RTWN8723BE_RF_FULL_MASK) != 0)
        return EINVAL;
    error = rtwn8723be_rf_serial_read(&ctx, path, reg, &value);
    if (error != 0) return error;
    for (shift = 0; (mask & (1U << shift)) == 0; shift++) ;
    *out = (value & mask) >> shift;
    return 0;
}
int
rtwn8723be_runtime_write_rf(struct rtwn8723be_softc *sc, unsigned int path,
    uint32_t reg, uint32_t mask, uint32_t value)
{
    const struct rtwn8723be_rf_serial_ctx ctx = { &runtime_rf_io, sc };
    if (mask == 0 || (mask & ~RTWN8723BE_RF_FULL_MASK) != 0) return EINVAL;
    return rtwn8723be_rf_masked_write(&ctx, path, reg, mask, value);
}

static int runtime_writebb(void *arg, uint32_t reg, uint32_t mask, uint32_t value)
{
    struct rtwn8723be_softc *sc = arg;
    int error = runtime_reg(sc, reg, 4);
    if (mask == 0) return EINVAL;
    if (error == 0) rtwn8723be_netbsd_set_bbreg(sc, reg, mask, value);
    return error;
}
static int runtime_readbb(void *arg, uint32_t reg, uint32_t mask, uint32_t *out)
{
    struct rtwn8723be_softc *sc = arg;
    int error = runtime_reg(sc, reg, 4);
    if (mask == 0 || out == NULL) return EINVAL;
    if (error == 0) *out = rtwn8723be_netbsd_get_bbreg(sc, reg, mask);
    return error;
}
static int runtime_write_rf_cb(void *arg, unsigned int path, uint32_t reg,
    uint32_t mask, uint32_t value)
{
    return rtwn8723be_runtime_write_rf(arg, path, reg, mask, value);
}
static int runtime_read_rf_cb(void *arg, unsigned int path, uint32_t reg,
    uint32_t mask, uint32_t *out)
{
    return rtwn8723be_runtime_read_rf(arg, path, reg, mask, out);
}
static int runtime_delay_us(void *arg, unsigned int usec)
{
    if (!rtwn8723be_runtime_io_ready(arg)) return ENXIO;
    delay(usec);
    return rtwn8723be_runtime_io_ready(arg) ? 0 : ENXIO;
}
static int runtime_delay_ms(void *arg, unsigned int ms)
{
    int error = 0;
    while (ms-- != 0 && error == 0) error = runtime_delay_us(arg, 1000);
    return error;
}
static int runtime_scan_active(void *arg, bool *out)
{
    struct rtwn8723be_softc *sc = arg;
    if (out == NULL || !rtwn8723be_runtime_io_ready(sc)) return ENXIO;
    mutex_enter(&sc->sc_runtime->stats_lock);
    *out = sc->sc_runtime->wifi.scanning;
    mutex_exit(&sc->sc_runtime->stats_lock);
    return 0;
}
static int runtime_readmac(void *arg, uint32_t reg, unsigned int width,
    uint32_t *out)
{
    uint8_t v8;
    uint16_t v16;
    int error;
    if (out == NULL) return EINVAL;
    switch (width) {
    case 1: error = runtime_read8(arg, reg, &v8); if (!error) *out = v8; break;
    case 2: error = runtime_read16(arg, reg, &v16); if (!error) *out = v16; break;
    case 4: error = runtime_read32(arg, reg, out); break;
    default: error = EINVAL; break;
    }
    return error;
}
static int runtime_writemac(void *arg, uint32_t reg, unsigned int width,
    uint32_t value)
{
    switch (width) {
    case 1: return runtime_write8(arg, reg, (uint8_t)value);
    case 2: return runtime_write16(arg, reg, (uint16_t)value);
    case 4: return runtime_write32(arg, reg, value);
    default: return EINVAL;
    }
}
static const struct rtwn8723be_calibration_io runtime_cal_io = {
    runtime_rf_ready, runtime_readbb, runtime_writebb,
    runtime_read_rf_cb, runtime_write_rf_cb, runtime_readmac, runtime_writemac,
    runtime_delay_us, runtime_scan_active, NULL
};

static int
cal_owner_acquire(void *arg, struct rtwn8723be_softc *sc,
    struct rtwn8723be_calibration_inputs *in)
{
    struct rtwn8723be_runtime *r = arg;
    int error;
    if (r != sc->sc_runtime || in == NULL) return EINVAL;
    error = rtwn8723be_runtime_io_enter(sc);
    if (error != 0) return error;
    memset(in, 0, sizeof(*in));
    in->rf_state_valid = r->rf_state_valid;
    in->rf_on = r->rf_on;
    in->btc_bound = sc->sc_btc.initialized && sc->sc_btc.engine.btc.binded;
    in->btc_initialized = sc->sc_btc.initialized && sc->sc_btc.engine.btc.initialized;
    in->btc_ant_num = sc->sc_btdm_ant_num;
    in->dm_state_valid = r->dm.software_initialized;
    in->txpower_tracking = r->dm.thermal.txpower_tracking;
    in->tm_trigger = r->dm.thermal.tm_trigger != 0;
    in->current_channel = r->wifi.channel;
    return 0;
}
static bool cal_owner_ready(void *arg, struct rtwn8723be_softc *sc)
{
    return arg == sc->sc_runtime && runtime_rf_ready(sc);
}
static int cal_owner_scan(void *arg, struct rtwn8723be_softc *sc, bool *out)
{
    if (arg != sc->sc_runtime) return ENXIO;
    return runtime_scan_active(sc, out);
}
static int cal_owner_thermal(void *arg, struct rtwn8723be_softc *sc,
    const struct rtwn8723be_calibration_context *ctx,
    struct rtwn8723be_calibration_state *state)
{
    struct rtwn8723be_runtime *r = arg;
    if (r != sc->sc_runtime || !runtime_rf_ready(sc)) return ENXIO;
    r->thermal.current_channel = r->wifi.channel;
    return rtwn8723be_thermal_callback(ctx, state, &r->dm.thermal, &r->thermal);
}
static void cal_owner_release(void *arg, struct rtwn8723be_softc *sc,
    const struct rtwn8723be_calibration_state *state, int error)
{
    struct rtwn8723be_runtime *r = arg;
    KASSERT(r == sc->sc_runtime && state != NULL);
    if (state->tracking_changed) r->dm.thermal.tm_trigger = state->tm_trigger;
    if (error != 0) runtime_fault(sc, error);
    rtwn8723be_runtime_io_exit(sc);
}
static const struct rtwn8723be_calibration_owner runtime_cal_owner = {
    cal_owner_acquire, cal_owner_ready, cal_owner_scan, cal_owner_thermal,
    cal_owner_release
};

static int
disable_owner_acquire(void *arg, struct rtwn8723be_softc *sc,
    struct rtwn8723be_hw_disable_inputs *in,
    struct rtwn8723be_hw_disable_state *state)
{
    struct rtwn8723be_runtime *r = arg;
    int error;
    if (r != sc->sc_runtime || in == NULL || state == NULL) return EINVAL;
    if (!r->shutdown_active || sc->sc_ih != NULL || sc->sc_soft_ih != NULL ||
        sc->sc_irq_enabled || sc->sc_btc_mp.active || sc->sc_btc_mp.busy)
        return EBUSY;
    error = rtwn8723be_runtime_io_enter(sc);
    if (error != 0) return error;
    memset(in, 0, sizeof(*in));
    in->state_valid = r->rf_state_valid && sc->sc_core_initialized;
    in->rf_idle = !r->channel.inprogress && !sc->sc_calibration.lck_inprogress;
    in->driver_is_goingto_unload = r->unloading;
    in->rfoff_reason = sc->sc_rfoff_reason;
    in->led_opendrain = sc->sc_led_opendrain;
    in->led_pin = sc->sc_sw_led0;
    return 0;
}
static bool disable_owner_ready(void *arg, struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = arg;
    return r == sc->sc_runtime && r->shutdown_active &&
        rtwn8723be_runtime_io_ready(sc) && sc->sc_ih == NULL &&
        sc->sc_soft_ih == NULL && !sc->sc_irq_enabled &&
        !sc->sc_btc_mp.active && !sc->sc_btc_mp.busy &&
        (!sc->sc_btc.initialized || sc->sc_btc.closing);
}
static void disable_owner_release(void *arg, struct rtwn8723be_softc *sc,
    const struct rtwn8723be_hw_disable_state *state, int error)
{
    KASSERT(arg == sc->sc_runtime);
    rtwn8723be_runtime_poweroff(sc, state->powered_off ? 0 :
        (state->poweroff_error != 0 ? state->poweroff_error : error));
    rtwn8723be_runtime_io_exit(sc);
}
static const struct rtwn8723be_hw_disable_owner runtime_disable_owner = {
    disable_owner_acquire, disable_owner_ready, disable_owner_release
};

static int runtime_edca_reset(void *arg, unsigned int ac)
{
    struct rtwn8723be_softc *sc = arg;
    if (ac >= 4 || !runtime_rf_ready(sc)) return ENXIO;
    /* Exact rtl8723_dm_init_edca_turbo(), against this device's real DM. */
    sc->sc_runtime->dm.current_turbo_edca = false;
    sc->sc_runtime->dm.is_any_nonbepkts = false;
    sc->sc_runtime->dm.is_cur_rdlstate = false;
    return 0;
}
static int runtime_led(void *arg, unsigned int action)
{
    if (!runtime_rf_ready(arg)) return ENXIO;
    return rtwn8723be_netbsd_led_control(arg, action);
}
static int runtime_irq_disable(void *arg, bool *was)
{
    struct rtwn8723be_softc *sc = arg;
    if (was == NULL || !runtime_rf_ready(sc)) return ENXIO;
    mutex_enter(&sc->sc_irq_lock);
    *was = sc->sc_irq_wanted;
    mutex_exit(&sc->sc_irq_lock);
    return rtwn8723be_netbsd_disable_interrupt(sc);
}
static int runtime_irq_restore(void *arg, bool was)
{
    struct rtwn8723be_softc *sc = arg;
    /* Mandatory unwind even if the transaction revoked RF validity. */
    if (!was) return 0;
    if (!sc->sc_mapped || sc->sc_runtime->shutdown_active) return ENXIO;
    return rtwn8723be_netbsd_enable_interrupt(sc);
}
static const struct rtwn8723be_media_io runtime_media_io = {
    runtime_rf_ready, runtime_read8, runtime_read16, runtime_read32,
    runtime_write8, runtime_write16, runtime_write32, runtime_edca_reset,
    runtime_led, runtime_irq_disable, runtime_irq_restore
};
static int runtime_channel_access(void *arg, bool ht)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    return rtwn8723be_media_channel_access(&runtime_media_io, sc, &r->media,
        (sc->sc_ic.ic_flags & IEEE80211_F_SHSLOT) != 0 ? 9U : 20U,
        2U, false, ht); /* pci.c: EACMWAY2_SW; legacy has no WME ACM */
}
static const struct rtwn8723be_channel_io runtime_channel_io = {
    runtime_rf_ready, runtime_read8, runtime_write8, runtime_writebb,
    runtime_write_rf_cb, runtime_delay_ms, runtime_channel_access
};
static void runtime_media_commit(struct rtwn8723be_softc *sc)
{
    sc->sc_bcn_ctrl_val = sc->sc_runtime->media.bcn_ctrl;
    sc->sc_receive_config = sc->sc_runtime->media.receive_config;
}
static void runtime_media_import(struct rtwn8723be_softc *sc)
{
    /* DM rate-mask and reserved-page operations are real BCN_CTRL
     * producers outside the media helper. Import their final cache, never
     * overwrite it with an older helper snapshot or reset quarantine. */
    sc->sc_runtime->media.bcn_ctrl = sc->sc_bcn_ctrl_val;
    sc->sc_runtime->media.receive_config = sc->sc_receive_config;
}
static int runtime_channel(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    unsigned int ch = ieee80211_chan2ieee(&sc->sc_ic, sc->sc_ic.ic_curchan);
    int error;
    if (ch < 1 || ch > 14) return EINVAL;
    error = rtwn8723be_channel_apply(&runtime_channel_io, sc, &r->channel,
        &r->txpower, &sc->sc_txpwr_pg, ch, R23BE_CHANNEL_BW20,
        R23BE_CHANNEL_SC_NONE, false);
    if (error != 0) {
        rtwn8723be_channel_state_invalidate(&r->channel);
        rtwn8723be_media_state_invalidate(&r->media);
        sc->sc_rf_chnlval_valid = false;
        return error;
    }
    memcpy(sc->sc_rf_chnlval, r->channel.rf_chnlval, sizeof(sc->sc_rf_chnlval));
    runtime_media_commit(sc);
    mutex_enter(&r->stats_lock);
    r->wifi.channel = r->channel.current_channel;
    r->wifi.bandwidth = BTC_WIFI_BW_LEGACY;
    r->wifi.under_b = sc->sc_ic.ic_curmode == IEEE80211_MODE_11B;
    mutex_exit(&r->stats_lock);
    r->thermal.current_channel = r->channel.current_channel;
    return 0;
}

int
rtwn8723be_runtime_btc_event(struct rtwn8723be_softc *sc,
    enum rtwn8723be_btc_event_kind kind, uint8_t value)
{
    struct rtwn8723be_btc_event event;
    memset(&event, 0, sizeof(event));
    event.kind = kind;
    event.value = value;
    return rtwn8723be_btc_native_execute(sc, &event);
}

int
rtwn8723be_runtime_btc_snapshot(struct rtwn8723be_softc *sc,
    struct rtwn8723be_btc_wifi_state *out)
{
    struct rtwn8723be_runtime *r;
    if (out == NULL || !rtwn8723be_runtime_io_ready(sc)) return ENXIO;
    r = sc->sc_runtime;
    mutex_enter(&r->stats_lock);
    *out = r->wifi;
    out->rssi = (int32_t)r->rx.undec_sm_pwdb;
    mutex_exit(&r->stats_lock);
    return 0;
}

int
rtwn8723be_runtime_aggregate(struct rtwn8723be_softc *sc, struct btc_bt_info *b)
{
    struct rtwn8723be_runtime *r;
    uint64_t now = (uint32_t)getticks();
    if (b == NULL || !rtwn8723be_runtime_io_ready(sc)) return ENXIO;
    r = sc->sc_runtime;
    if ((uint32_t)(now - r->aggregate_tick) <= (uint32_t)(8U * hz)) return 0;
    r->aggregate_tick = now;
    if (b->reject_agg_pkt) b->pre_reject_agg_pkt = true;
    else {
        b->pre_reject_agg_pkt = false;
        b->pre_bt_ctrl_agg_buf_size = b->bt_ctrl_agg_buf_size;
        if (b->bt_ctrl_agg_buf_size) b->pre_agg_buf_size = b->agg_buf_size;
    }
    /* IEEE80211_NO_HT has no BA sessions to delete or establish. Preserve
     * the source throttle/history; full HT ABI remains a declared gap. */
    return 0;
}

static int
runtime_lps_notify(struct rtwn8723be_softc *sc, bool enter)
{
    struct rtwn8723be_btc_native *n = &sc->sc_btc;
    struct rtwn8723be_btc_event e;
    if (!n->initialized) return ENXIO;
    if (!mutex_owned(&n->engine_lock))
        return rtwn8723be_runtime_btc_event(sc, R23BE_BTC_LPS,
            enter ? BTC_LPS_ENABLE : BTC_LPS_DISABLE);
    /* Frozen LPS notification only updates under_lps; recursive source
     * actions occur while the same native engine/IO mutexes are held. */
    memset(&e, 0, sizeof(e));
    e.kind = R23BE_BTC_LPS;
    e.value = enter ? BTC_LPS_ENABLE : BTC_LPS_DISABLE;
    n->engine.btc.statistics.cnt_lps_notify++;
    if (n->engine.btc.manual_control) return 0;
    return rtwn8723be_btc_engine_execute(&n->engine, &e);
}

static bool
runtime_reserved_current(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    bool tx;
    KASSERT(mutex_owned(&r->io_lock));
    /* The BTC worker owns IO, not a framework BSS reference. Compare the
     * true downloaded peer with committed hardware media state; never
     * dereference an ic_bss that net80211 can replace or release. */
    mutex_enter(&r->datapath.tx_lock);
    tx = r->datapath.prepared && r->datapath.sc == sc &&
        r->datapath.tx_enabled;
    mutex_exit(&r->datapath.tx_lock);
    return tx && sc->sc_linux.started && sc->sc_linux.fw_ready &&
        r->reserved.initialized && r->reserved.valid &&
        r->reserved.firmware_generation == sc->sc_h2c.firmware_generation &&
        r->media.cache_valid && r->media.linked &&
        r->reserved.aid == r->media.aid &&
        memcmp(r->reserved.bssid, r->media.bssid, 6) == 0;
}

int
rtwn8723be_runtime_lps(struct rtwn8723be_softc *sc, bool enter)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    struct btc_coexist *b = &sc->sc_btc.engine.btc;
    uint8_t payload[7] = {0}, old;
    bool controlled;
    int error;
    if (!runtime_rf_ready(sc)) return ENXIO;
    /* ps.c: STA linked, actual reserved pages/JOINBSSRPT, ten seconds
     * linked, no busy traffic or special packet for two seconds. */
    if (!r->wifi.connected || r->wifi.ap) return 0;
    if (enter && (!r->report_linked || !runtime_reserved_current(sc)))
        return 0;
    if (!sc->sc_linux.started) return EAGAIN;
    if (enter && (r->linked_periods < 5 || r->wifi.busy ||
        (uint32_t)((uint32_t)getticks() - r->last_special_tick) < 2U * hz))
        return 0;
    if (!enter && !r->in_lps) return 0;
    controlled = b->bt_info.bt_ctrl_lps;
    if (controlled) enter = b->bt_info.bt_lps_on;
    /* fw.c seven-byte SETPWRMODE, sw.c MAX mode/32k disabled defaults. */
    payload[0] = enter ? 1U : 0U;
    payload[1] = enter ? (controlled ? 0U : 0x21U) : 2U;
    payload[2] = enter ? 2U : 4U;
    payload[4] = enter ? (controlled ? b->bt_info.rpwm_val : 0U) : 0x0cU;
    payload[5] = enter && controlled ? b->bt_info.lps_val : 0x40U;
    if (enter) {
        error = runtime_lps_notify(sc, true);
        if (error != 0) return error;
        r->fw_in_ps = true; /* source publishes before H2C */
        error = rtwn8723be_h2c_native_send(sc, 0x20U, payload, sizeof(payload));
        if (error != 0) return error;
    }
    error = runtime_read8(sc, 0x361U, &old);
    if (error != 0) return error;
    delay(1);
    error = runtime_write8(sc, 0x361U, (old & 0x80U) != 0 ? 0U : 0x80U);
    if (error != 0) return error;
    if (!enter) {
        error = rtwn8723be_h2c_native_send(sc, 0x20U, payload, sizeof(payload));
        if (error != 0) return error;
        r->fw_in_ps = false;
        error = runtime_lps_notify(sc, false);
        if (error != 0) return error;
    }
    r->in_lps = enter;
    memcpy(b->pwr_mode_val, payload, sizeof(payload));
    return 0;
}

static bool
runtime_rx_current(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    return r != NULL && r->initialized && r->rx_generation != 0 &&
        r->rx_generation == sc->sc_h2c.firmware_generation &&
        sc->sc_linux.fw_ready;
}
static int runtime_ra_report(void *arg, const struct rtwn8723be_c2h_event *e)
{
    (void)arg; (void)e;
    /* base.c dispatches RA only if c2h_ra_report_handler exists; the
     * frozen rtl8723be_hal_ops supplies no such handler. */
    return 0;
}
static int runtime_bt_info(void *arg, const struct rtwn8723be_c2h_event *e)
{
    struct rtwn8723be_softc *sc = arg;
    if (!runtime_rx_current(sc)) return EAGAIN;
    return rtwn8723be_btc_native_c2h_info(sc, e);
}
static int runtime_bt_mp(void *arg, const struct rtwn8723be_c2h_event *e)
{
    struct rtwn8723be_softc *sc = arg;
    if (!runtime_rx_current(sc)) return EAGAIN;
    return rtwn8723be_btc_mp_native_receive(sc, e);
}
static int runtime_tx_report(void *arg, const struct rtwn8723be_c2h_event *e)
{
    struct rtwn8723be_softc *sc = arg;
    if (!runtime_rx_current(sc)) return EAGAIN;
    return rtwn8723be_net80211_tx_report(&sc->sc_runtime->tx, e);
}
static int runtime_c2h(void *arg, const uint8_t *data, size_t len,
    const struct rtwn8723be_rx_packet *packet)
{
    const struct rtwn8723be_c2h_handlers handlers = {
        arg, runtime_tx_report, runtime_ra_report, runtime_bt_info, runtime_bt_mp
    };
    return rtwn8723be_c2h_native_receive(&handlers, data, len, packet);
}

static bool runtime_frame_unicast(const uint8_t *frame, size_t len)
{
    return len >= 10 && (frame[4] & 1U) == 0;
}
static void
runtime_scan_collect(struct rtwn8723be_runtime *r, const uint8_t *frame,
    size_t len)
{
    struct rtwn8723be_runtime_scan_entry *entry;
    KASSERT(mutex_owned(&r->stats_lock));
    /* base.c rtl_collect_scan_list: only real scan beacon/probe-response
     * addr3, unique BSSID, refreshed monotonic age. RX never owns a node. */
    if (!r->wifi.scanning || len < 24 ||
        ((frame[0] & 0xfcU) != 0x80U && (frame[0] & 0xfcU) != 0x50U))
        return;
    for (entry = r->scan_entries; entry != NULL; entry = entry->next)
        if (memcmp(entry->bssid, frame + 16, 6) == 0) break;
    if (entry == NULL) {
        if (r->scan_count == UINT32_MAX) return;
        entry = kmem_intr_zalloc(sizeof(*entry), KM_NOSLEEP);
        if (entry == NULL) return; /* same source atomic-allocation failure */
        memcpy(entry->bssid, frame + 16, 6);
        entry->next = r->scan_entries;
        r->scan_entries = entry;
        r->scan_count++;
    }
    entry->age = (uint32_t)getticks();
}
static void
runtime_scan_expire(struct rtwn8723be_runtime *r)
{
    struct rtwn8723be_runtime_scan_entry **link, *entry;
    uint32_t now = (uint32_t)getticks();
    KASSERT(mutex_owned(&r->stats_lock));
    for (link = &r->scan_entries; (entry = *link) != NULL;) {
        if ((uint32_t)(now - entry->age) < 180U * hz) {
            link = &entry->next;
            continue;
        }
        *link = entry->next;
        KASSERT(r->scan_count != 0);
        r->scan_count--;
        kmem_intr_free(entry, sizeof(*entry));
    }
    /* Frozen BTC ap_num is u8; retain its actual narrowing semantics. */
    r->wifi.ap_count = (uint8_t)r->scan_count;
}
static int runtime_rx_frame(void *arg, const uint8_t *frame, size_t len,
    const struct rtwn8723be_rx_packet *packet)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    struct rtwn8723be_dm_rx_inputs in;
    struct rtwn8723be_dm_rx_observation obs;
    const uint8_t *data;
    int error;
    if (!runtime_rx_current(sc) || packet == NULL || frame == NULL)
        return EAGAIN;
    memset(&in, 0, sizeof(in));
    in.frame = frame; in.frame_length = len;
    data = frame - packet->packet_offset; /* borrowed validated ring buffer */
    in.phy = data + packet->phy_offset; in.phy_length = packet->phy_length;
    in.phy_present = packet->phy_present;
    in.crc_error = packet->crc_error; in.icv_error = packet->icv_error;
    in.rate = packet->rate; in.rf_path_count = sc->sc_rf_path_count;
    memcpy(in.macaddr, sc->sc_macaddr, sizeof(in.macaddr));
    if (sc->sc_ic.ic_bss != NULL)
        memcpy(in.bssid, sc->sc_ic.ic_bss->ni_bssid, sizeof(in.bssid));
    error = rtwn8723be_dm_native_rx_parse(&in, &obs);
    if (error != 0 && error != ENODATA) return error;
    mutex_enter(&r->stats_lock);
    runtime_scan_collect(r, frame, len);
    if (error == 0) (void)rtwn8723be_dm_native_rx_accumulate(&r->rx, &obs);
    if (len >= 24 && (frame[0] & 0x0cU) == 0x08U &&
        runtime_frame_unicast(frame, len)) {
        r->rx_period++;
        r->rx_bytes += len;
        /* Actual plaintext LLC EAPOL marks the source four-way window. */
        if ((frame[1] & 0x40U) == 0 && len >= 32 &&
            frame[24] == 0xaa && frame[25] == 0xaa && frame[26] == 3 &&
            frame[30] == 0x88 && frame[31] == 0x8e) {
            r->wifi.in_4way = true;
            r->in_4way_tick = (uint32_t)getticks();
        }
    }
    mutex_exit(&r->stats_lock);
    return rtwn8723be_net80211_rx_frame(&r->net, frame, len, packet);
}

void
rtwn8723be_runtime_tx_produce(struct rtwn8723be_softc *sc,
    const uint8_t *frame, size_t len, uint8_t special)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    struct rtwn8723be_btc_event event;
    if (r == NULL || frame == NULL) return;
    mutex_enter(&r->stats_lock);
    if (len >= 24 && (frame[0] & 0x0cU) == 0x08U &&
        runtime_frame_unicast(frame, len)) {
        r->tx_period++;
        r->tx_bytes += len;
    }
    if (special != 0) r->last_special_tick = (uint32_t)getticks();
    if (special == BTC_PACKET_EAPOL) {
        r->wifi.in_4way = true;
        r->in_4way_tick = (uint32_t)getticks();
    }
    mutex_exit(&r->stats_lock);
    if (special != 0) {
        memset(&event, 0, sizeof(event));
        event.kind = R23BE_BTC_SPECIAL_PACKET;
        event.value = special;
        (void)rtwn8723be_btc_native_enqueue(sc, &event);
    }
}

static void runtime_tx_start(struct rtwn8723be_softc *sc, struct ifnet *ifp)
{
    rtwn8723be_net80211_tx_start(&sc->sc_runtime->tx, ifp);
}

int
rtwn8723be_runtime_register(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    const struct rtwn8723be_net80211_methods methods = {
        rtwn8723be_runtime_start, rtwn8723be_runtime_stop, runtime_tx_start
    };
    const struct rtwn8723be_rx_dispatch rx = { sc, runtime_rx_frame, runtime_c2h };
    int error;
    if (r == NULL || !r->initialized || !sc->sc_rings_allocated) return ENXIO;
    error = rtwn8723be_datapath_prepare(&r->datapath, sc, &rx,
        rtwn8723be_net80211_tx_complete, &r->tx);
    if (error != 0) return error;
    error = rtwn8723be_net80211_tx_prepare(&r->tx, sc, &r->datapath);
    if (error != 0) goto fail_dp;
    rtwn8723be_net80211_tx_set_accepted(&r->tx, rtwn8723be_runtime_tx_produce);
    error = rtwn8723be_reserved_native_prepare(&r->reserved, sc, &r->datapath);
    if (error != 0) goto fail_tx;
    error = rtwn8723be_net80211_register(&r->net, sc, &methods);
    if (error != 0) goto fail_reserved;
    r->newstate = sc->sc_ic.ic_newstate;
    sc->sc_ic.ic_newstate = runtime_newstate;
    return 0;
fail_reserved:
    (void)rtwn8723be_reserved_native_fini(&r->reserved);
fail_tx:
    (void)rtwn8723be_net80211_tx_fini(&r->tx);
fail_dp:
    (void)rtwn8723be_datapath_unprepare(&r->datapath);
    return error;
}

int
rtwn8723be_runtime_rfkill_init(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    if (r == NULL || !r->initialized || !r->net.registered) return ENXIO;
    /* Linux starts wiphy RF-kill polling at probe; GPIO reads are gated
     * by RTL_STATUS_INTERFACE_START. NetBSD has no wiphy, so the actual
     * two-second native watchdog supplies the same GPIO producer. */
    r->rfkill_polling = true;
    r->rfkill_valid = false; /* not inferred from an EEPROM or default */
    return 0;
}

int
rtwn8723be_runtime_bt_prepare(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    struct btc_coexist context;
    int error;
    if (!rtwn8723be_runtime_io_ready(sc) || !r->mcu_rx_drained ||
        sc->sc_irq_enabled || sc->sc_soft_ih != NULL || sc->sc_ih != NULL)
        return EBUSY;
    if (sc->sc_btc.initialized) return EALREADY;
    mutex_enter(&r->stats_lock);
    r->wifi.ap_count = 36; /* frozen rtl_pci_start software default */
    mutex_exit(&r->stats_lock);
    error = rtwn8723be_btc_provider_native_context(sc, &context);
    if (error != 0) return error;
    return rtwn8723be_btc_native_init(sc, &context, &runtime_btc_owner, r);
}

int
rtwn8723be_runtime_bt_hw_init(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    int error;
    if (!rtwn8723be_runtime_io_ready(sc) || !sc->sc_linux.fw_ready ||
        !sc->sc_linux.mac_func_enable || !sc->sc_bb_valid ||
        !sc->sc_rf_chnlval_valid || !sc->sc_btc.initialized)
        return ENXIO;
    /* hw.c publishes ERFON after the completed MAC/BB/RF configuration. */
    r->rf_on = true;
    r->rf_state_valid = true;
    r->poweroff_verified = false;
    mutex_enter(&r->stats_lock);
    r->wifi.firmware_version = ((uint32_t)sc->sc_fw_info.version << 16) |
        sc->sc_fw_info.subversion;
    mutex_exit(&r->stats_lock);
    error = rtwn8723be_channel_state_seed(&r->channel, sc->sc_rf_chnlval,
        sc->sc_rf_path_count);
    if (error == 0) error = rtwn8723be_media_state_seed(&r->media,
        sc->sc_bcn_ctrl_val, sc->sc_receive_config);
    if (error == 0) error = rtwn8723be_btc_mp_native_activate(sc);
    if (error == 0) {
        r->rx_generation = sc->sc_h2c.firmware_generation;
        error = rtwn8723be_runtime_btc_event(sc, R23BE_BTC_INIT_HW, 0);
    }
    if (error == 0) error = rtwn8723be_runtime_btc_event(sc, R23BE_BTC_INIT_DM, 0);
    return error;
}

int
rtwn8723be_runtime_dm_init(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    struct rtwn8723be_dm_init_inputs in;
    int error;
    memset(&in, 0, sizeof(in));
    in.hardware_ready = runtime_rf_ready(sc);
    in.rf_identity_valid = sc->sc_phy_identity_valid;
    in.crystal_cap_valid = sc->sc_xtal_valid;
    in.rf_path_count = sc->sc_rf_path_count;
    in.crystal_cap = sc->sc_xtal_cap;
    in.current_channel = r->wifi.channel;
    error = rtwn8723be_dm_native_init(sc, &r->dm, &in);
    if (error == 0) error = rtwn8723be_btc_native_enable_events(sc);
    return error;
}

int
rtwn8723be_runtime_bt_halt(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    if (sc->sc_runtime == NULL) return ENXIO;
    if (mutex_owned(&sc->sc_runtime->io_lock)) return EDEADLK;
    return rtwn8723be_btc_native_stop(sc);
}

int
rtwn8723be_runtime_wait_rf(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    int error;
    if (r == NULL || !r->shutdown_active) return EBUSY;
    /* Receive stays live through terminal HALT/MP requests, then is
     * physically disestablished before H2C/firmware/ring reset. */
    error = rtwn8723be_btc_mp_native_stop(sc);
    rtwn8723be_netbsd_disestablish_irq(sc);
    if (error != 0) return error;
    error = rtwn8723be_runtime_io_enter(sc);
    if (error != 0) return error;
    if (r->channel.inprogress || sc->sc_calibration.lck_inprogress)
        error = EBUSY;
    rtwn8723be_runtime_io_exit(sc);
    return error;
}

void
rtwn8723be_runtime_poweroff(struct rtwn8723be_softc *sc, int error)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    if (r == NULL) return;
    KASSERT(mutex_owned(&r->io_lock));
    r->poweroff_verified = error == 0;
    if (error == 0) {
        r->rf_on = false;
        r->rf_state_valid = true;
        r->fw_in_ps = false;
        r->in_lps = false;
        r->report_linked = false;
        mutex_enter(&r->stats_lock);
        r->wifi.connected = false;
        r->wifi.scanning = false;
        r->wifi.linking = false;
        r->wifi.busy = false;
        r->wifi.link_status = 0;
        mutex_exit(&r->stats_lock);
        if (r->reserved.initialized)
            (void)rtwn8723be_reserved_native_invalidate(&r->reserved);
        r->rx_generation = 0;
        rtwn8723be_channel_state_invalidate(&r->channel);
        rtwn8723be_media_state_invalidate(&r->media);
        sc->sc_rf_chnlval_valid = false;
        sc->sc_bb_valid = false;
    }
}
bool rtwn8723be_runtime_mcu_prepared(struct rtwn8723be_softc *sc)
{
    return sc != NULL && sc->sc_runtime != NULL &&
        sc->sc_runtime->initialized && sc->sc_runtime->mcu_rx_drained;
}
bool rtwn8723be_runtime_poweroff_verified(struct rtwn8723be_softc *sc)
{
    return rtwn8723be_runtime_mcu_prepared(sc) &&
        sc->sc_runtime->poweroff_verified;
}

/* Drop the old net80211 big lock while waiting for this worker, whose
 * framework calls acquire it before lifecycle_lock. No ABBA with ifioctl. */
static void
runtime_jobs_drain(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    int locks = 0;
    bool self;
    mutex_enter(&r->queue_lock);
    r->jobs_enabled = false;
    self = r->worker == curlwp;
    mutex_exit(&r->queue_lock);
    callout_halt(&r->watchdog, NULL);
    callout_halt(&r->scan, NULL);
    if (self) return;
    if (KERNEL_LOCKED_P()) KERNEL_UNLOCK_ALL(NULL, &locks);
    workqueue_wait(r->workqueue, &r->work);
    KERNEL_LOCK(locks, NULL);
}

static int
runtime_shutdown(struct rtwn8723be_softc *sc, bool normal)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    int first = 0, error, wait_error;
    r->shutdown_active = true;
    r->report_linked = false;
    if (r->reserved.initialized)
        (void)rtwn8723be_reserved_native_invalidate(&r->reserved);
    rtwn8723be_net80211_tx_stop(&r->tx);
    rtwn8723be_datapath_stop(&r->datapath);
    sc->sc_ec.ec_if.if_flags &= ~(IFF_RUNNING | IFF_OACTIVE);
    if (normal) {
        /* Preserve the frozen normal order, including HALT before IRQ.
         * On a failure, finish real safety rundown rather than leaking
         * an accepted call or freeing live DMA underneath the device. */
        error = rtwn8723be_linux_adapter_stop(sc, &sc->sc_linux,
            &rtwn8723be_netbsd_ops);
        if (error != 0) first = error;
    } else {
        error = rtwn8723be_runtime_bt_halt(sc);
        if (error != 0) first = error;
    }
    if (!r->poweroff_verified) {
        (void)rtwn8723be_netbsd_mark_hal_stop(sc);
        (void)rtwn8723be_netbsd_disable_interrupt(sc);
        wait_error = rtwn8723be_runtime_wait_rf(sc);
        if (first == 0 && wait_error != 0) first = wait_error;
        if (wait_error == 0) {
            if (normal && sc->sc_linux.started && r->rf_state_valid) {
                sc->sc_linux.stage = R23BE_STAGE_STOPPING;
                error = rtwn8723be_netbsd_hw_disable(sc);
            } else {
                error = rtwn8723be_runtime_io_enter(sc);
                if (error == 0) {
                    error = rtwn8723be_netbsd_poweroff_adapter(sc);
                    rtwn8723be_runtime_poweroff(sc, error);
                    rtwn8723be_runtime_io_exit(sc);
                }
            }
            if (first == 0 && error != 0) first = error;
        }
    }
    if (r->poweroff_verified) {
        (void)rtwn8723be_netbsd_disable_interrupt(sc);
        rtwn8723be_netbsd_disestablish_irq(sc);
        sc->sc_linux.started = false;
        sc->sc_linux.fw_ready = false;
        sc->sc_linux.mac_func_enable = false;
        sc->sc_linux.being_init_adapter = false;
        sc->sc_linux.stage = R23BE_STAGE_STOPPED;
        /* Actual stopped DMA + IRQ/softint rundown establish reset safety. */
        error = rtwn8723be_netbsd_reset_trx_ring(sc);
        if (first == 0 && error != 0) first = error;
        r->mcu_rx_drained = error == 0;
        error = rtwn8723be_btc_native_retire(sc);
        if (first == 0 && error != 0) first = error;
        error = rtwn8723be_netbsd_enable_aspm(sc);
        if (first == 0 && error != 0) first = error;
    }
    r->shutdown_error = first;
    r->shutdown_active = false;
    return first != 0 ? first : (r->poweroff_verified ? 0 : EBUSY);
}

int
rtwn8723be_runtime_start(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    int error, cleanup;
    if (r == NULL || !runtime_thread()) return EWOULDBLOCK;
    mutex_enter(&r->lifecycle_lock);
    if (r->closing || r->transition || r->radio_blocked || sc->sc_linux.started ||
        (sc->sc_linux.stage == R23BE_STAGE_STOPPED &&
         (!r->poweroff_verified || !r->mcu_rx_drained || sc->sc_btc.initialized)) ||
        (sc->sc_linux.stage != R23BE_STAGE_PROBED &&
         sc->sc_linux.stage != R23BE_STAGE_STOPPED)) {
        mutex_exit(&r->lifecycle_lock);
        return EBUSY;
    }
    if (r->generation == UINT64_MAX) {
        mutex_exit(&r->lifecycle_lock);
        return EOVERFLOW;
    }
    r->generation++;
    r->transition = true;
    mutex_enter(&r->queue_lock);
    r->faulted = false;
    mutex_exit(&r->queue_lock);
    r->first_error = 0;
    r->poweroff_verified = false;
    r->shutdown_error = 0;
    /* A new MCU generation is allowed only after actual old IRQ/RX drain. */
    rtwn8723be_netbsd_disestablish_irq(sc);
    error = rtwn8723be_btc_mp_native_stop(sc);
    if (error == 0) error = rtwn8723be_runtime_io_enter(sc);
    if (error != 0) goto fail;
    r->mcu_rx_drained = false;
    r->rx_generation = 0;
    /* Linux-order start's reset callback publishes proof only after the
     * actual old IRQ/softint drain and complete RX/TX ring reset. */
    error = rtwn8723be_linux_adapter_start(sc,
        &sc->sc_linux, &rtwn8723be_netbsd_ops);
    rtwn8723be_runtime_io_exit(sc);
    if (error != 0) goto fail;
    error = rtwn8723be_datapath_start(&r->datapath);
    if (error == 0) error = rtwn8723be_net80211_tx_run(&r->tx);
    if (error != 0) goto fail;
    mutex_enter(&r->queue_lock);
    r->jobs_enabled = true;
    mutex_exit(&r->queue_lock);
    r->linked_periods = 0;
    r->roam_periods = 0;
    callout_schedule(&r->watchdog, 2 * hz);
    error = ieee80211_new_state(&sc->sc_ic, IEEE80211_S_SCAN, -1);
    if (error != 0) goto fail;
    r->transition = false;
    mutex_exit(&r->lifecycle_lock);
    /* Framework state progression is asynchronous, with hardware state
     * committed in the worker before the saved net80211 method runs. */
    return 0;
fail:
    mutex_exit(&r->lifecycle_lock);
    runtime_jobs_drain(sc);
    mutex_enter(&r->lifecycle_lock);
    cleanup = runtime_shutdown(sc, sc->sc_linux.started);
    r->transition = false;
    mutex_exit(&r->lifecycle_lock);
    return error != 0 ? error : cleanup;
}

int
rtwn8723be_runtime_stop(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    int error;
    if (r == NULL || !runtime_thread()) return EWOULDBLOCK;
    mutex_enter(&r->lifecycle_lock);
    if (r->transition) {
        mutex_exit(&r->lifecycle_lock);
        return EBUSY;
    }
    r->transition = true;
    mutex_exit(&r->lifecycle_lock);
    runtime_jobs_drain(sc);
    mutex_enter(&r->lifecycle_lock);
    if (!sc->sc_linux.started &&
        (sc->sc_linux.stage <= R23BE_STAGE_PROBED ||
         (sc->sc_linux.stage == R23BE_STAGE_STOPPED && r->poweroff_verified &&
          r->mcu_rx_drained && !sc->sc_btc.initialized))) {
        rtwn8723be_netbsd_disestablish_irq(sc);
        r->transition = false;
        mutex_exit(&r->lifecycle_lock);
        return 0;
    }
    error = runtime_shutdown(sc, sc->sc_linux.started &&
        sc->sc_linux.stage == R23BE_STAGE_RUNNING);
    if (r->poweroff_verified && r->newstate != NULL && r->net.registered)
        (void)r->newstate(&sc->sc_ic, IEEE80211_S_INIT, -1);
    r->transition = false;
    mutex_exit(&r->lifecycle_lock);
    return error;
}

int
rtwn8723be_runtime_unregister(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    int error;
    if (r == NULL) return 0;
    mutex_enter(&r->lifecycle_lock);
    r->unloading = true;
    mutex_enter(&r->queue_lock);
    r->closing = true;
    r->jobs_enabled = false;
    mutex_exit(&r->queue_lock);
    mutex_exit(&r->lifecycle_lock);
    error = rtwn8723be_runtime_stop(sc);
    if (error != 0 && !r->poweroff_verified) return error;
    mutex_enter(&r->lifecycle_lock);
    mutex_enter(&r->queue_lock);
    r->closing = true;
    r->jobs_enabled = false;
    mutex_exit(&r->queue_lock);
    if (r->net.registered && r->newstate != NULL)
        sc->sc_ic.ic_newstate = r->newstate;
    error = rtwn8723be_net80211_unregister(&r->net);
    mutex_exit(&r->lifecycle_lock);
    return error;
}

static int
runtime_queue(struct rtwn8723be_softc *sc,
    enum rtwn8723be_runtime_job_kind kind, enum ieee80211_state state, int arg)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    unsigned int tail;
    int error = 0;
    if (r == NULL || !r->initialized || cpu_intr_p()) return EWOULDBLOCK;
    mutex_enter(&r->queue_lock);
    if (!r->jobs_enabled || r->closing || r->faulted) error = ECANCELED;
    else if (r->count == R23BE_RUNTIME_QUEUE) error = ENOBUFS;
    else {
        tail = (r->head + r->count) % R23BE_RUNTIME_QUEUE;
        r->jobs[tail].kind = kind;
        r->jobs[tail].state = state;
        r->jobs[tail].arg = arg;
        r->jobs[tail].generation = r->generation;
        r->count++;
        if (!r->scheduled) {
            r->scheduled = true;
            workqueue_enqueue(r->workqueue, &r->work, NULL);
        }
    }
    mutex_exit(&r->queue_lock);
    if (error == ENOBUFS) runtime_fault(sc, error);
    return error;
}
static int runtime_newstate(struct ieee80211com *ic,
    enum ieee80211_state state, int arg)
{
    struct rtwn8723be_net80211 *n = ic->ic_ifp->if_softc;
    if (n == NULL || n->sc == NULL) return ENXIO;
    return runtime_queue(n->sc, R23BE_RUNTIME_STATE, state, arg);
}
static void runtime_watchdog_timer(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    if (runtime_queue(sc, R23BE_RUNTIME_WATCHDOG, IEEE80211_S_INIT, 0) == 0)
        callout_schedule(&sc->sc_runtime->watchdog, 2 * hz);
}
static void runtime_scan_timer(void *arg)
{
    (void)runtime_queue(arg, R23BE_RUNTIME_SCAN, IEEE80211_S_SCAN, 0);
}

static int
runtime_state(struct rtwn8723be_softc *sc, enum ieee80211_state state, int arg)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    struct ieee80211com *ic = &sc->sc_ic;
    struct ieee80211_node *ni = ic->ic_bss;
    enum ieee80211_state old = ic->ic_state;
    uint16_t bitmap;
    uint64_t tsf;
    int error = 0;
    if (!runtime_rf_ready(sc) || ic->ic_opmode != IEEE80211_M_STA)
        return EOPNOTSUPP;
    callout_stop(&r->scan);
    if (old == IEEE80211_S_RUN && state != old) {
        error = rtwn8723be_runtime_lps(sc, false);
        if (error == 0) error = rtwn8723be_h2c_native_media_status(sc, false);
        r->report_linked = false;
        if (error == 0)
            error = rtwn8723be_reserved_native_invalidate(&r->reserved);
        mutex_enter(&r->stats_lock);
        r->wifi.connected = false;
        r->wifi.link_status = 0;
        mutex_exit(&r->stats_lock);
        if (error == 0) error = rtwn8723be_media_set_network(&runtime_media_io,
            sc, &r->media, false);
        if (error == 0) error = rtwn8723be_runtime_btc_event(sc,
            R23BE_BTC_MEDIA, BTC_MEDIA_DISCONNECT);
    }
    if (error == 0 && old == IEEE80211_S_SCAN && state != old) {
        mutex_enter(&r->stats_lock);
        r->wifi.scanning = false;
        r->wifi.ap_count = (uint8_t)r->scan_count;
        mutex_exit(&r->stats_lock);
        error = rtwn8723be_runtime_btc_event(sc, R23BE_BTC_SCAN, BTC_SCAN_FINISH);
    }
    if (error != 0) goto fail;
    if (state != IEEE80211_S_INIT) {
        error = runtime_channel(sc);
        if (error != 0) goto fail;
    }
    switch (state) {
    case IEEE80211_S_INIT:
        error = rtwn8723be_media_set_network(&runtime_media_io, sc, &r->media, false);
        break;
    case IEEE80211_S_SCAN:
        if (old != state) {
            mutex_enter(&r->stats_lock);
            r->wifi.scanning = true;
            r->wifi.linking = false;
            mutex_exit(&r->stats_lock);
            error = rtwn8723be_media_set_check_bssid(&runtime_media_io,
                sc, &r->media, false);
            if (error == 0) error = rtwn8723be_runtime_btc_event(sc,
                R23BE_BTC_SCAN, BTC_SCAN_START);
        }
        if (error == 0) callout_schedule(&r->scan, mstohz(200));
        break;
    case IEEE80211_S_AUTH:
    case IEEE80211_S_ASSOC:
        mutex_enter(&r->stats_lock);
        r->wifi.linking = true;
        mutex_exit(&r->stats_lock);
        error = rtwn8723be_media_set_check_bssid(&runtime_media_io,
            sc, &r->media, false);
        if (error == 0 && old != IEEE80211_S_AUTH && old != IEEE80211_S_ASSOC)
            error = rtwn8723be_runtime_btc_event(sc, R23BE_BTC_CONNECT,
                BTC_ASSOCIATE_START);
        break;
    case IEEE80211_S_RUN:
        if (ni == NULL || ni->ni_intval == 0) { error = EINVAL; break; }
        error = rtwn8723be_media_set_bssid(&runtime_media_io, sc,
            &r->media, ni->ni_bssid);
        if (error == 0) error = rtwn8723be_media_basic_rate_bitmap(
            ni->ni_rates.rs_rates, ni->ni_rates.rs_nrates, &bitmap);
        if (error == 0) error = rtwn8723be_media_set_basic_rates(&runtime_media_io,
            sc, &r->media, bitmap);
        if (error == 0) error = rtwn8723be_media_set_aid(&runtime_media_io,
            sc, &r->media, IEEE80211_AID(ni->ni_associd));
        if (error == 0) error = rtwn8723be_media_set_beacon_interval(
            &runtime_media_io, sc, &r->media, ni->ni_intval);
        if (error == 0) error = rtwn8723be_media_set_preamble(&runtime_media_io,
            sc, &r->media, (ic->ic_flags & IEEE80211_F_SHPREAMBLE) != 0);
        if (error == 0) error = rtwn8723be_media_set_network(&runtime_media_io,
            sc, &r->media, true);
        memcpy(&tsf, ni->ni_tstamp.data, sizeof(tsf));
        tsf = le64toh(tsf);
        tsf = tsf - tsf % ((uint64_t)ni->ni_intval * 1024U) - 1024U;
        if (error == 0) error = rtwn8723be_media_set_tsf(&runtime_media_io,
            sc, &r->media, tsf);
        if (error == 0) {
            static const uint8_t values[12] = {2,4,11,22,12,18,24,36,48,72,96,108};
            unsigned int i, j;
            memset(&r->rates, 0, sizeof(r->rates));
            for (i = 0; i < ni->ni_rates.rs_nrates; i++)
                for (j = 0; j < __arraycount(values); j++)
                    if ((ni->ni_rates.rs_rates[i] & IEEE80211_RATE_VAL) == values[j])
                        r->rates.legacy_rates |= 1U << j;
            r->rates.wireless_mode = ic->ic_curmode == IEEE80211_MODE_11B ?
                RTWN8723BE_DM_MODE_B : RTWN8723BE_DM_MODE_G;
            r->rates.rf_path_count = sc->sc_rf_path_count;
            error = rtwn8723be_dm_native_update_rate(sc, &r->dm,
                &r->rates, RTWN8723BE_DM_RA_INIT);
            runtime_media_import(sc);
        }
        if (error == 0) {
            mutex_enter(&r->stats_lock);
            r->wifi.connected = true;
            r->wifi.linking = false;
            r->wifi.encrypted = (ic->ic_flags & IEEE80211_F_PRIVACY) != 0;
            r->wifi.link_status = (1U << 16) | 1U; /* one STA port */
            mutex_exit(&r->stats_lock);
            error = rtwn8723be_runtime_btc_event(sc, R23BE_BTC_CONNECT,
                BTC_ASSOCIATE_FINISH);
            if (error == 0) error = rtwn8723be_runtime_btc_event(sc,
                R23BE_BTC_MEDIA, BTC_MEDIA_CONNECT);
            if (error == 0) {
                struct ieee80211_node *held = ieee80211_ref_node(ni);
                /* Frozen HW_VAR_JOINBSSRPT: AID, real page download,
                 * then MEDIASTATUS. The ring separately owns its node. */
                error = rtwn8723be_reserved_native_download(&r->reserved, held);
                runtime_media_import(sc);
                if (error == 0 &&
                    !rtwn8723be_reserved_native_ready(&r->reserved, held))
                    error = EAGAIN;
                if (error == 0)
                    error = rtwn8723be_h2c_native_media_status(sc, true);
                if (error == 0) r->report_linked = true;
                ieee80211_free_node(held);
            }
        }
        break;
    default: error = EINVAL; break;
    }
    if (error != 0) goto fail;
    runtime_media_commit(sc);
    error = r->newstate(ic, state, arg);
    if (error == 0) return 0;
    goto fail;
fail:
    r->report_linked = false;
    if (r->reserved.initialized)
        (void)rtwn8723be_reserved_native_invalidate(&r->reserved);
    rtwn8723be_media_state_invalidate(&r->media);
    rtwn8723be_channel_state_invalidate(&r->channel);
    sc->sc_rf_chnlval_valid = false;
    return error;
}

static int
runtime_watchdog(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    struct rtwn8723be_dm_watchdog_inputs in;
    struct rtwn8723be_dm_rx_state rx;
    const struct rtwn8723be_calibration_context cal = { &runtime_cal_io, sc };
    uint32_t rp, tp, ra = 0, ta = 0;
    unsigned int i;
    uint8_t gpio;
    int error;
    if (!runtime_rf_ready(sc) || !sc->sc_hal_started) return ENXIO;
    memset(&in, 0, sizeof(in));
    mutex_enter(&r->stats_lock);
    runtime_scan_expire(r);
    rp = r->rx_period; tp = r->tx_period;
    r->rx_period = r->tx_period = 0;
    rx = r->rx;
    r->rx.num_beacons = 0;
    in.txbytesunicast = r->tx_bytes; in.rxbytesunicast = r->rx_bytes;
    if (r->wifi.connected) {
        if (r->linked_periods < 20) r->linked_periods++;
        for (i = 0; i < 3; i++) {
            r->rx_history[i] = r->rx_history[i+1];
            r->tx_history[i] = r->tx_history[i+1];
        }
        r->rx_history[3] = rp; r->tx_history[3] = tp;
        for (i = 0; i < 4; i++) { ra += r->rx_history[i]; ta += r->tx_history[i]; }
        r->wifi.busy = ra / 4 > 100 || ta / 4 > 100;
    } else { r->linked_periods = 0; r->wifi.busy = false; }
    /* Frozen base.c leaves tx_busy_traffic false in both branches. */
    r->wifi.direction = BTC_WIFI_TRAFFIC_RX;
    if (r->wifi.in_4way && (uint32_t)((uint32_t)getticks() -
        r->in_4way_tick) > 30U * hz) r->wifi.in_4way = false;
    in.linked = r->wifi.connected; in.scanning = r->wifi.scanning;
    mutex_exit(&r->stats_lock);
    in.hardware_ready = true; in.hal_started = sc->sc_hal_started;
    in.rf_on = r->rf_on; in.fw_in_ps = r->fw_in_ps;
    in.fw_awake = !r->fw_in_ps; in.station = sc->sc_ic.ic_opmode == IEEE80211_M_STA;
    in.btc_active = sc->sc_btc.initialized;
    in.bt_disabled = sc->sc_btc.engine.btc.bt_info.bt_disabled;
    in.wireless_mode = r->rates.wireless_mode;
    in.rates_valid = in.linked && r->rates.legacy_rates != 0;
    in.rates = r->rates; in.thermal = r->thermal; in.rx_snapshot = &rx;
    in.acm_method = 2;
    if (!sc->sc_btc.engine.btc.bt_info.bt_ctrl_lps) {
        error = rtwn8723be_runtime_lps(sc, rp + tp <= 8 && rp <= 2);
        if (error != 0) return error;
    }
    error = rtwn8723be_dm_native_watchdog(sc, &r->dm, &in, &cal, &sc->sc_calibration);
    runtime_media_import(sc);
    if (error != 0) return error;
    if (in.linked && rp + rx.num_beacons == 0) {
        if (++r->roam_periods >= 5) {
            r->roam_periods = 0;
            error = ieee80211_new_state(&sc->sc_ic, IEEE80211_S_SCAN, -1);
            if (error != 0) return error;
        }
    } else r->roam_periods = 0;
    error = rtwn8723be_runtime_btc_event(sc, R23BE_BTC_PERIODIC, 0);
    if (error != 0) return error;
    if (r->rfkill_polling && !sc->sc_linux.being_init_adapter) {
        error = runtime_read8(sc, 0x62U, &gpio);
        if (error == 0) error = runtime_write8(sc, 0x62U, gpio & ~2U);
        if (error == 0) error = runtime_read8(sc, 0x60U, &gpio);
        if (error != 0) return error;
        /* polarity_ctl stays zero in this frozen 8723BE source. */
        r->rfkill_valid = true;
        r->radio_blocked = (gpio & 2U) == 0;
        if (r->radio_blocked) {
            sc->sc_rfoff_reason |= 1U << 30;
            return runtime_queue(sc, R23BE_RUNTIME_QUIESCE, IEEE80211_S_INIT, 0);
        }
        sc->sc_rfoff_reason &= ~(1U << 30);
    }
    return 0;
}

static void
runtime_worker(struct work *work, void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    struct rtwn8723be_runtime_job job;
    bool admitted;
    int error;
    (void)work;
    mutex_enter(&r->queue_lock);
    r->worker = curlwp;
    mutex_exit(&r->queue_lock);
    for (;;) {
        mutex_enter(&r->queue_lock);
        if (r->count == 0) {
            r->scheduled = false;
            r->worker = NULL;
            mutex_exit(&r->queue_lock);
            return;
        }
        job = r->jobs[r->head];
        r->head = (r->head + 1U) % R23BE_RUNTIME_QUEUE;
        r->count--;
        admitted = job.generation == r->generation && !r->closing &&
            (r->jobs_enabled || job.kind == R23BE_RUNTIME_QUIESCE);
        mutex_exit(&r->queue_lock);
        if (!admitted) continue;
        KERNEL_LOCK(1, NULL);
        if (job.kind == R23BE_RUNTIME_QUIESCE) {
            (void)rtwn8723be_runtime_stop(sc);
            KERNEL_UNLOCK_ONE(NULL);
            continue;
        }
        mutex_enter(&r->lifecycle_lock);
        mutex_enter(&r->queue_lock);
        admitted = job.generation == r->generation && r->jobs_enabled &&
            !r->closing && !r->faulted;
        mutex_exit(&r->queue_lock);
        if (!admitted) {
            mutex_exit(&r->lifecycle_lock);
            KERNEL_UNLOCK_ONE(NULL);
            continue;
        }
        error = rtwn8723be_runtime_io_enter(sc);
        if (error == 0) {
            if (job.kind == R23BE_RUNTIME_STATE)
                error = runtime_state(sc, job.state, job.arg);
            else if (job.kind == R23BE_RUNTIME_WATCHDOG)
                error = runtime_watchdog(sc);
            else if (job.kind == R23BE_RUNTIME_SCAN && sc->sc_ic.ic_state == IEEE80211_S_SCAN)
                ieee80211_next_scan(&sc->sc_ic);
            rtwn8723be_runtime_io_exit(sc);
        }
        if (error != 0) runtime_fault(sc, error);
        mutex_exit(&r->lifecycle_lock);
        KERNEL_UNLOCK_ONE(NULL);
    }
}

int
rtwn8723be_runtime_init(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r;
    bool meter_ignored;
    int error;
    if (sc == NULL || !runtime_thread()) return EWOULDBLOCK;
    if (sc->sc_runtime != NULL) return EALREADY;
    r = kmem_zalloc(sizeof(*r), KM_SLEEP);
    mutex_init(&r->lifecycle_lock, MUTEX_DEFAULT, IPL_NONE);
    mutex_init(&r->io_lock, MUTEX_DEFAULT, IPL_NONE);
    mutex_init(&r->queue_lock, MUTEX_DEFAULT, IPL_SOFTNET);
    mutex_init(&r->stats_lock, MUTEX_DEFAULT, IPL_SOFTNET);
    mutex_init(&sc->sc_irq_lock, MUTEX_DEFAULT, IPL_NET);
    sc->sc_irq_lock_initialized = true;
    callout_init(&r->watchdog, CALLOUT_MPSAFE);
    callout_init(&r->scan, CALLOUT_MPSAFE);
    callout_setfunc(&r->watchdog, runtime_watchdog_timer, sc);
    callout_setfunc(&r->scan, runtime_scan_timer, sc);
    error = rtwn8723be_eeprom_txpower_parse(&r->txpower, sc->sc_efuse_map,
        sizeof(sc->sc_efuse_map), !sc->sc_efuse_autoload_ok);
    if (error == 0) error = rtwn8723be_thermal_meter_parse(sc->sc_efuse_map,
        sizeof(sc->sc_efuse_map), sc->sc_efuse_autoload_ok,
        &r->thermal.eeprom_thermalmeter, &meter_ignored);
    if (error == 0) r->thermal.eeprom_meter_valid = !meter_ignored;
    if (error == 0) error = workqueue_create(&r->workqueue, "r23berun",
        runtime_worker, sc, PRI_NONE, IPL_SOFTNET, WQ_MPSAFE);
    if (error != 0) {
        callout_destroy(&r->scan); callout_destroy(&r->watchdog);
        mutex_destroy(&sc->sc_irq_lock); sc->sc_irq_lock_initialized = false;
        mutex_destroy(&r->stats_lock); mutex_destroy(&r->queue_lock);
        mutex_destroy(&r->io_lock); mutex_destroy(&r->lifecycle_lock);
        kmem_free(r, sizeof(*r));
        return error;
    }
    rtwn8723be_dm_native_preinit(&r->dm);
    rtwn8723be_dm_native_rx_init(&r->rx);
    /* Exact Linux software defaults, not EEPROM-inferred HW ownership. */
    r->wifi.channel = 1;
    r->wifi.ap_count = 36;
    r->wifi.bandwidth = BTC_WIFI_BW_LEGACY;
    r->wifi.direction = BTC_WIFI_TRAFFIC_RX;
    r->wifi.firmware_version = ((uint32_t)sc->sc_fw_info.version << 16) |
        sc->sc_fw_info.subversion;
    r->initialized = true;
    sc->sc_runtime = r;
    sc->sc_calibration_owner = &runtime_cal_owner;
    sc->sc_calibration_owner_arg = r;
    sc->sc_hw_disable_owner = &runtime_disable_owner;
    sc->sc_hw_disable_owner_arg = r;
    return 0;
}

int
rtwn8723be_runtime_fini(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    int error;
    if (r == NULL) return 0;
    if (!runtime_thread() || r->net.registered || sc->sc_linux.started ||
        sc->sc_ih != NULL || sc->sc_soft_ih != NULL) return EBUSY;
    runtime_jobs_drain(sc);
    if (sc->sc_btc.initialized) {
        error = rtwn8723be_btc_native_retire(sc);
        if (error != 0) return error;
    }
    if (r->reserved.initialized) {
        error = rtwn8723be_reserved_native_fini(&r->reserved);
        if (error != 0) return error;
    }
    if (r->tx.prepared) {
        error = rtwn8723be_net80211_tx_fini(&r->tx);
        if (error != 0) return error;
    }
    if (r->datapath.prepared) {
        error = rtwn8723be_datapath_unprepare(&r->datapath);
        if (error != 0) return error;
    }
    workqueue_destroy(r->workqueue);
    callout_destroy(&r->watchdog); callout_destroy(&r->scan);
    sc->sc_calibration_owner = NULL; sc->sc_calibration_owner_arg = NULL;
    sc->sc_hw_disable_owner = NULL; sc->sc_hw_disable_owner_arg = NULL;
    rtwn8723be_dm_native_fini(&r->dm);
    while (r->scan_entries != NULL) {
        struct rtwn8723be_runtime_scan_entry *entry = r->scan_entries;
        r->scan_entries = entry->next;
        kmem_intr_free(entry, sizeof(*entry));
    }
    r->scan_count = 0;
    r->initialized = false;
    sc->sc_runtime = NULL;
    mutex_destroy(&sc->sc_irq_lock); sc->sc_irq_lock_initialized = false;
    mutex_destroy(&r->stats_lock); mutex_destroy(&r->queue_lock);
    mutex_destroy(&r->io_lock); mutex_destroy(&r->lifecycle_lock);
    kmem_free(r, sizeof(*r));
    return 0;
}

int rtwn8723be_runtime_suspend(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    if (r == NULL || !r->net.registered) return ENXIO;
    r->resume_up = (sc->sc_ec.ec_if.if_flags & IFF_UP) != 0;
    return rtwn8723be_runtime_stop(sc);
}
int rtwn8723be_runtime_resume(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime *r = sc->sc_runtime;
    int error;
    if (r == NULL || !r->net.registered) return ENXIO;
    if (!r->resume_up) return 0;
    r->radio_blocked = false; /* validate actual GPIO during restarted service */
    error = rtwn8723be_runtime_start(sc);
    if (error == 0) sc->sc_ec.ec_if.if_flags |= IFF_RUNNING;
    return error;
}
