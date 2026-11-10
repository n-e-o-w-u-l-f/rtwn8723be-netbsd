/* SPDX-License-Identifier: GPL-2.0 */
/*
 * NetBSD 11 net80211 interface lifecycle modelled on pinned
 * NetBSD/src sys/dev/pci/if_rtwn.c; NOT the hardware-specific rtwn driver.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <sys/sockio.h>
#include <sys/mbuf.h>
#include <sys/intr.h>

#include <net/if.h>
#include <net/if_ether.h>
#include <net/if_media.h>
#include <net/bpf.h>
#include <net80211/ieee80211_var.h>
#include <net80211/ieee80211_proto.h>

#include "rtwn8723be_net80211.h"
#include "rtwn8723be_net80211_state.h"
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_datapath.h"

static int rtwn8723be_n80211_ifinit(struct ifnet *);
static int rtwn8723be_n80211_ioctl(struct ifnet *, u_long, void *);
static int rtwn8723be_n80211_media_change(struct ifnet *);
static void rtwn8723be_n80211_ifstart(struct ifnet *);
static int rtwn8723be_n80211_ifstop(struct rtwn8723be_net80211 *);
static void rtwn8723be_n80211_tx_purge(struct rtwn8723be_net80211 *);
static void rtwn8723be_n80211_tx_install(struct rtwn8723be_net80211 *);
static int rtwn8723be_n80211_tx_remove(struct rtwn8723be_net80211 *);


static int
rtwn8723be_n80211_ifinit(struct ifnet *ifp)
{
    struct rtwn8723be_net80211 *n = ifp->if_softc;
    struct rtwn8723be_softc *sc;
    bool radio_on;
    int error;

    if (n == NULL || !n->registered || n->sc == NULL)
        return ENXIO;
    sc = n->sc;
    if (n->methods.hw_start == NULL || n->methods.hw_stop == NULL ||
        n->methods.tx_start == NULL)
        return ENOSYS;
    /*
     * A failed/partial earlier hardware start owns the residual firmware,
     * MAC and DMA state until a specifically journalled recovery drains it.
     * Only a truly quiescent PROBED/STOPPED owner may start again.
     */
    if ((ifp->if_flags & IFF_RUNNING) != 0)
        return EBUSY;
    if (!rtwn8723be_net80211_start_checkpoint_ok(&sc->sc_linux) ||
        !sc->sc_irq_dispatch_ready || sc->sc_ih == NULL ||
        !sc->sc_rings_allocated || !sc->sc_mapped)
        return EAGAIN;

    /*
     * A live RFKill poller is a prerequisite to bringing up net80211.
     * A failing/busy last GPIO sample cannot authorize hardware start,
     * even if the last *older* successful sample reported radio-on.
     */
    error = rtwn8723be_rfkill_native_radio_on(sc, &radio_on);
    if (error != 0)
        return error;
    if (!radio_on)
        return ENETDOWN;

    /*
     * hw_start must complete Linux-order hw_init(), irq enable, RX config,
     * mark_hal_start and the datapath bridge's start + unwind on failure.
     * A partially initialized device must NEVER be marked IFF_RUNNING.
     */
    error = n->methods.hw_start(sc);
    if (error != 0)
        return error;
    if (!sc->sc_linux.started || !sc->sc_linux.fw_ready ||
        sc->sc_linux.stage != R23BE_STAGE_RUNNING ||
        !rtwn8723be_datapath_running_ready(sc->sc_datapath)) {
        /*
         * A false-success start is NOT a completed RUNNING adapter.
         * linux_adapter_stop() requires started + RUNNING and cannot
         * safely compensate an incomplete firmware/MAC transition.
         * Keep the actual failed stage for the separate pre-RUNNING
         * journal; never fabricate STOPPED or try generic hw_stop.
         */
        return EIO;
    }
    /*
     * The physical RF switch could have changed while hw_start was
     * sleeping. Do not publish IFF_RUNNING unless the post-start sample
     * still authorizes radio-on. A failed stop is propagated (and the
     * remaining hardware lifetime stays owned for explicit recovery).
     * Asynchronous switch-off after publication needs a separate,
     * fully serialized RFKill/net80211 notification owner.
     */
    error = rtwn8723be_rfkill_native_radio_on(sc, &radio_on);
    if (error != 0 || !radio_on) {
        int stop_error = n->methods.hw_stop(sc);
        if (stop_error != 0)
            return stop_error;
        /*
         * A false-success RFKill rollback must not hide a still-RUNNING
         * adapter behind ENETDOWN/EAGAIN. Retain all hardware owners
         * for explicit recovery; never claim STOPPED without proof.
         */
        if (sc->sc_linux.stage != R23BE_STAGE_STOPPED ||
            sc->sc_linux.started || sc->sc_linux.fw_ready ||
            sc->sc_linux.mac_func_enable ||
            sc->sc_linux.being_init_adapter)
            return EIO;
        return error != 0 ? error : ENETDOWN;
    }
    /*
     * RFKill sampling can run while STOP is pending or an owner is
     * revoked. Recheck the real TX/IRQ/RUNNING bridge immediately before
     * publishing IFF_RUNNING. Actual TX enqueue rechecks under tx_lock.
     */
    if (!rtwn8723be_datapath_running_ready(sc->sc_datapath))
        return EIO;
    ifp->if_flags |= IFF_RUNNING;
    ifp->if_flags &= ~IFF_OACTIVE;
    return 0;
}

static int
rtwn8723be_n80211_ifstop(struct rtwn8723be_net80211 *n)
{
    struct ifnet *ifp;
    int error;

    if (n == NULL || !n->registered || n->sc == NULL)
        return ENXIO;
    ifp = &n->sc->sc_ec.ec_if;
    /* Stop further net80211 dequeue BEFORE stopping hardware/interrupts. */
    ifp->if_flags &= ~(IFF_RUNNING | IFF_OACTIVE);
    ifp->if_timer = 0;
    /* An active consumer/key update still owns its CPU-side packet/node. */
    if (n->tx_busy || n->tx_key_update_depth != 0)
        return EBUSY;
    /* Detach may stop an interface that was registered but never started. */
    if (!n->sc->sc_linux.started) {
        if (rtwn8723be_net80211_unstarted_detach_allowed(
            &n->sc->sc_linux)) {
            rtwn8723be_n80211_tx_purge(n);
            return 0;
        }
        return EBUSY;
    }
    if (n->sc->sc_linux.stage != R23BE_STAGE_RUNNING)
        return EBUSY; /* An interrupted stop needs explicit recovery. */
    if (n->methods.hw_stop == NULL)
        return ENOSYS;
    error = n->methods.hw_stop(n->sc);
    if (error != 0)
        return error;
    /*
     * An allegedly successful hardware STOP must actually retire the
     * complete Linux RUNNING lifetime before net80211 is allowed to
     * report success, restart, unregister or release its resources.
     * A false-success callback retains the actual state for recovery.
     */
    if (n->sc->sc_linux.stage != R23BE_STAGE_STOPPED ||
        n->sc->sc_linux.started || n->sc->sc_linux.fw_ready ||
        n->sc->sc_linux.mac_func_enable ||
        n->sc->sc_linux.being_init_adapter)
        return EIO;
    rtwn8723be_n80211_tx_purge(n);
    return 0;
}

static void
rtwn8723be_n80211_ifstart(struct ifnet *ifp)
{
    struct rtwn8723be_net80211 *n = ifp->if_softc;
    struct rtwn8723be_datapath *dp;

    if (n == NULL || !n->registered || n->sc == NULL ||
        (ifp->if_flags & (IFF_RUNNING | IFF_OACTIVE)) != IFF_RUNNING ||
        !n->sc->sc_linux.started ||
        n->sc->sc_linux.stage != R23BE_STAGE_RUNNING ||
        n->methods.tx_start == NULL)
        return;
    dp = n->sc->sc_datapath;
    /*
     * A read-only readiness snapshot would race STOPPING before the
     * external net80211 queue consumer is called. Acquire a lifetime
     * reference atomically with RUNNING/TX/owner admission. The native
     * STOP entry refuses to shut down while this reference is held.
     */
    if (!rtwn8723be_datapath_tx_start_begin(dp))
        return;
    /* The external consumer must never run under dp->tx_lock (IPL_NET). */
    n->methods.tx_start(n->sc, ifp);
    rtwn8723be_datapath_tx_start_end(dp);
}

static int
rtwn8723be_n80211_ioctl(struct ifnet *ifp, u_long cmd, void *data)
{
    struct rtwn8723be_net80211 *n = ifp->if_softc;
    struct ieee80211com *ic;
    int error = 0, s;

    if (n == NULL || !n->registered || n->sc == NULL)
        return ENXIO;
    ic = &n->sc->sc_ic;
    s = splnet();
    switch (cmd) {
    case SIOCSIFFLAGS:
        error = ifioctl_common(ifp, cmd, data);
        if (error != 0)
            break;
        if ((ifp->if_flags & (IFF_UP | IFF_RUNNING)) == IFF_UP) {
            error = rtwn8723be_n80211_ifinit(ifp);
            if (error != 0)
                ifp->if_flags &= ~IFF_UP;
        } else if ((ifp->if_flags & (IFF_UP | IFF_RUNNING)) ==
            IFF_RUNNING) {
            error = rtwn8723be_n80211_ifstop(n);
        } else if ((ifp->if_flags & (IFF_UP | IFF_RUNNING)) == 0 &&
            (rtwn8723be_datapath_stop_retry_ready(
                n->sc->sc_datapath) ||
             rtwn8723be_net80211_running_hw_stop_needed(
                &n->sc->sc_linux))) {
            /*
             * IFF_RUNNING may already have been cleared by ifstop()
             * returning EBUSY, or by a failed/false-success hw_start
             * or RFKill rollback. A real Linux RUNNING MAC still owns
             * PCI/DMA even if no stop_pending lease was ever latched.
             * An explicit DOWN retries the real stop, never fabricates
             * IFF_RUNNING, and lets begin_stop revalidate under tx_lock.
             */
            error = rtwn8723be_n80211_ifstop(n);
        } else if ((ifp->if_flags & (IFF_UP | IFF_RUNNING)) == 0 &&
            rtwn8723be_net80211_hw_recovery_required(
                &n->sc->sc_linux)) {
            /*
             * STOPPING or a failed pre-RUNNING firmware init cannot be
             * resumed through the normal RUNNING hw_stop path. Keep
             * the interface logically DOWN, but report the unresolved
             * recovery obligation rather than falsely returning success.
             */
            error = EBUSY;
        }
        break;
    case SIOCADDMULTI:
    case SIOCDELMULTI:
        error = ether_ioctl(ifp, cmd, data);
        /* Multicast filter programming requires full hardware callbacks. */
        if (error == ENETRESET && (ifp->if_flags & IFF_RUNNING) == 0 &&
            !rtwn8723be_datapath_stop_retry_ready(
                n->sc->sc_datapath) &&
            !rtwn8723be_net80211_hw_recovery_required(
                &n->sc->sc_linux))
            error = 0;
        break;
    default:
        error = ieee80211_ioctl(ic, cmd, data);
        break;
    }
    if (error == ENETRESET) {
        error = 0;
        if ((ifp->if_flags & (IFF_UP | IFF_RUNNING)) ==
            (IFF_UP | IFF_RUNNING)) {
            error = rtwn8723be_n80211_ifstop(n);
            if (error == 0)
                error = rtwn8723be_n80211_ifinit(ifp);
        } else if (rtwn8723be_datapath_stop_retry_ready(
            n->sc->sc_datapath) ||
            rtwn8723be_net80211_hw_recovery_required(
                &n->sc->sc_linux)) {
            /*
             * A real hardware RUNNING owner may be orphaned behind
             * cleared ifnet flags even without a pending STOP lease.
             * Reconfiguration must not conceal that unsatisfied STOP.
             */
            error = EBUSY;
        }
    }
    splx(s);
    return error;
}

static int
rtwn8723be_n80211_media_change(struct ifnet *ifp)
{
    struct rtwn8723be_net80211 *n = ifp->if_softc;
    int error;

    if (n == NULL || !n->registered || n->sc == NULL)
        return ENXIO;
    error = ieee80211_media_change(ifp);
    if (error != ENETRESET)
        return error;
    if ((ifp->if_flags & (IFF_UP | IFF_RUNNING)) ==
        (IFF_UP | IFF_RUNNING)) {
        error = rtwn8723be_n80211_ifstop(n);
        if (error != 0)
            return error;
        return rtwn8723be_n80211_ifinit(ifp);
    }
    /*
     * A prior ifstop() may have already cleared IFF_RUNNING but left
     * a real RUNNING adapter behind when an RX/TX callback held a
     * lease. Explicit media change is not permission to discard that
     * pending hardware STOP or claim successful reconfiguration.
     */
    if (rtwn8723be_datapath_stop_retry_ready(n->sc->sc_datapath) ||
        rtwn8723be_net80211_hw_recovery_required(
            &n->sc->sc_linux))
        return EBUSY;
    return 0;
}

int
rtwn8723be_net80211_register(struct rtwn8723be_net80211 *n,
    struct rtwn8723be_softc *sc,
    const struct rtwn8723be_net80211_methods *methods)
{
    struct ieee80211com *ic;
    struct ifnet *ifp;
    int error;

    if (n == NULL || sc == NULL || methods == NULL)
        return EINVAL;
    if (n->registered)
        return EALREADY;
    if (methods->hw_start == NULL || methods->hw_stop == NULL)
        return ENOSYS;
    /*
     * if_initialize / ieee80211_ifattach / if_register create externally
     * visible NetBSD interface owners. They must not run before the
     * exact Linux probe stage, complete PCI/DMA/ring prerequisites and
     * unique sc_net80211 storage are verified. A live IRQ or RFKill
     * owner means registration was attempted out of Linux probe order.
     */
    if (n != &sc->sc_net80211 ||
        !rtwn8723be_net80211_registration_checkpoint_ok(
            &sc->sc_linux) ||
        !sc->sc_initial_pci_saved || !sc->sc_mapped ||
        !sc->sc_core_initialized || !sc->sc_rings_allocated ||
        !sc->sc_dma_32bit || sc->sc_dmat == NULL ||
        !sc->sc_irq_lock_initialized ||
        sc->sc_irq_requested || sc->sc_irq_enabled ||
        sc->sc_ih != NULL || sc->sc_soft_ih != NULL ||
        sc->sc_pihp != NULL || sc->sc_irq_dispatch_ready ||
        sc->sc_irq_arg != NULL || sc->sc_datapath != NULL ||
        sc->sc_rx_binding != NULL ||
        sc->sc_rfkill_native.initialized ||
        sc->sc_rfkill_native.active ||
        sc->sc_rfkill_native.wq != NULL)
        return EBUSY;
    if (!sc->sc_package_valid || !sc->sc_efuse_autoload_ok ||
        sc->sc_eeprom_id != R23BE_EEPROM_ID ||
        (sc->sc_macaddr[0] & 1U) != 0 ||
        (sc->sc_macaddr[0] == 0 && sc->sc_macaddr[1] == 0 &&
        sc->sc_macaddr[2] == 0 && sc->sc_macaddr[3] == 0 &&
        sc->sc_macaddr[4] == 0 && sc->sc_macaddr[5] == 0))
        return EINVAL;

    ic = &sc->sc_ic;
    ifp = &sc->sc_ec.ec_if;
    ic->ic_ifp = ifp;
    ic->ic_phytype = IEEE80211_T_OFDM;
    ic->ic_opmode = IEEE80211_M_STA;
    ic->ic_state = IEEE80211_S_INIT;
    /*
     * Station-mode 2.4-GHz software crypto: the frozen NetBSD if_rtwn
     * reference advertises WPA/RSN and ieee80211_ifattach initializes
     * the software crypto methods.  Restrict this bridge to WPA2/RSN;
     * legacy WPA1 and hardware CAM offload are not claimed here.
     * Successful key installation and actual TX/RX remain separate gates.
     */
    ic->ic_caps = IEEE80211_C_SHPREAMBLE | IEEE80211_C_SHSLOT |
        IEEE80211_C_WPA2;
    ic->ic_sup_rates[IEEE80211_MODE_11B] = ieee80211_std_rateset_11b;
    ic->ic_sup_rates[IEEE80211_MODE_11G] = ieee80211_std_rateset_11g;
    error = rtwn8723be_netbsd_apply_world_regdomain(sc);
    if (error != 0)
        return error;

    sc->sc_security_policy_valid = false;
    n->sc = sc;
    n->methods = *methods;
    if (n->methods.tx_start == NULL)
        n->methods.tx_start = rtwn8723be_net80211_tx_start;

    ifp->if_softc = n;
    ifp->if_flags = IFF_BROADCAST | IFF_SIMPLEX | IFF_MULTICAST;
    ifp->if_init = rtwn8723be_n80211_ifinit;
    ifp->if_start = rtwn8723be_n80211_ifstart;
    ifp->if_ioctl = rtwn8723be_n80211_ioctl;
    IFQ_SET_READY(&ifp->if_snd);
    strlcpy(ifp->if_xname, device_xname(sc->sc_dev), IFNAMSIZ);
    if_initialize(ifp);
    IEEE80211_ADDR_COPY(ic->ic_myaddr, sc->sc_macaddr);
    ieee80211_ifattach(ic);
    rtwn8723be_n80211_tx_install(n);
    /*
     * Frozen NetBSD if_percpuq_create() uses kmem_zalloc(KM_SLEEP)
     * and returns its allocated queue, not an ENOMEM status.
     * In particular, if_detach() may not be used to unwind an
     * interface that has not yet completed if_register(): doing so
     * removes a nonexistent ifnet_list entry.  Match if_rtwn.c order.
     * The driver owner must quiesce and detach after registration.
     */
    ifp->if_percpuq = if_percpuq_create(ifp);
    KASSERT(ifp->if_percpuq != NULL);
    if_register(ifp);
    ieee80211_media_init(ic, rtwn8723be_n80211_media_change,
        ieee80211_media_status);
    /* The current net80211 adapter uses the framework's software key methods.
     * Hardware CAM set/delete and cipher ownership remain a separate full-port
     * requirement. A future hardware-key adapter must explicitly select policy.
     */
    sc->sc_sw_crypto = true;
    sc->sc_use_sw_sec = true;
    sc->sc_use_defaultkey = false;
    sc->sc_security_policy_valid = true;
    n->registered = true;
    ieee80211_announce(ic);
    return 0;
}

int
rtwn8723be_net80211_unregister(struct rtwn8723be_net80211 *n)
{
    struct ifnet *ifp;
    int s, error;

    if (n == NULL)
        return EINVAL;
    if (!n->registered)
        return 0;
    if (n->sc == NULL)
        return EIO;
    s = splnet();
    ifp = &n->sc->sc_ec.ec_if;
    error = rtwn8723be_n80211_ifstop(n);
    if (error != 0) {
        splx(s);
        return error; /* Retain registered resources on failed hardware stop. */
    }
    /*
     * hw_stop() retires the Linux MAC lifetime but does not establish a
     * NetBSD IRQ/softint, datapath, RX binding or RFKill worker drain.
     * A public unregister may be called outside the ordered probe-unwind
     * broker. Never free net80211/ifnet storage while any asynchronous
     * producer could still dereference it. The existing native probe
     * journal drains IRQ -> datapath -> RX -> RFKill before reaching here.
     *
     * The caller owns exclusion against NEW entry points; splnet only
     * serializes the current network-side detach, not PCI DMA lifetime.
     */
    if (n->sc->sc_irq_requested || n->sc->sc_irq_enabled ||
        n->sc->sc_ih != NULL || n->sc->sc_soft_ih != NULL ||
        n->sc->sc_pihp != NULL ||
        n->sc->sc_irq_dispatch_ready ||
        n->sc->sc_irq_arg != NULL ||
        n->sc->sc_irq_dispatch.rx != NULL ||
        n->sc->sc_irq_dispatch.tx_done != NULL ||
        n->sc->sc_irq_dispatch.power_event != NULL ||
        n->sc->sc_datapath != NULL || n->sc->sc_rx_binding != NULL ||
        n->sc->sc_rfkill_native.initialized ||
        n->sc->sc_rfkill_native.active ||
        n->sc->sc_rfkill_native.wq != NULL) {
        splx(s);
        return EBUSY; /* Preserve registration and security policy. */
    }
    error = rtwn8723be_n80211_tx_remove(n);
    if (error != 0) {
        splx(s);
        return error;
    }
    n->sc->sc_security_policy_valid = false;
    n->sc->sc_security_configured = false;
    n->sc->sc_hw_security_enabled = false;
    ieee80211_ifdetach(&n->sc->sc_ic);
    if_detach(ifp);
    n->registered = false;
    n->sc = NULL;
    memset(&n->methods, 0, sizeof(n->methods));
    splx(s);
    return 0;
}

int
rtwn8723be_net80211_input(struct rtwn8723be_net80211 *n,
    const uint8_t *frame, size_t length, int rssi_dbm)
{
    struct ieee80211com *ic;
    struct ieee80211_node *ni;
    struct mbuf *m;
    int s;

    if (n == NULL || !n->registered || n->sc == NULL ||
        frame == NULL || length < sizeof(struct ieee80211_frame_min) ||
        length > RTWN8723BE_RX_BUFFER_SIZE ||
        rssi_dbm < -127 || rssi_dbm > 0)
        return EINVAL;
    if ((n->sc->sc_ec.ec_if.if_flags & IFF_RUNNING) == 0 ||
        !rtwn8723be_datapath_running_ready(n->sc->sc_datapath))
        return ENETDOWN;

    m = m_devget((char *)(uintptr_t)frame, (int)length, 0,
        &n->sc->sc_ec.ec_if);
    if (m == NULL)
        return ENOBUFS;
    /*
     * A hardware stop may clear IFF_RUNNING while m_devget copies a
     * borrowed DMA frame. Revalidate under the same splnet boundary
     * used by ifstop/unregister; never inject a late frame into
     * net80211 after STOP has revoked receive publication.
     *
     * PCI detach must separately quiesce all RX softints before freeing
     * softc: splnet is not a borrowed-callback lifetime reference.
     */
    s = splnet();
    if (!n->registered || n->sc == NULL ||
        (n->sc->sc_ec.ec_if.if_flags & IFF_RUNNING) == 0 ||
        !n->sc->sc_linux.started ||
        n->sc->sc_linux.stage != R23BE_STAGE_RUNNING ||
        !rtwn8723be_datapath_running_ready(n->sc->sc_datapath)) {
        splx(s);
        m_freem(m);
        return ENETDOWN;
    }
    ic = &n->sc->sc_ic;
    ni = ieee80211_find_rxnode(ic,
        mtod(m, struct ieee80211_frame_min *));
    if (ni == NULL) {
        splx(s);
        m_freem(m);
        return ENOENT;
    }
    /* ieee80211_input takes ownership of the COPIED mbuf. */
    ieee80211_input(ic, m, ni, rssi_dbm, 0);
    ieee80211_free_node(ni);
    splx(s);
    return 0;
}

int
rtwn8723be_net80211_rx_frame(void *arg, const uint8_t *frame,
    size_t length, const struct rtwn8723be_rx_packet *packet)
{
    struct rtwn8723be_net80211 *n = arg;

    if (n == NULL || packet == NULL || frame == NULL ||
        packet->kind != RTWN8723BE_RX_FRAME ||
        packet->packet_length != length ||
        packet->crc_error || packet->icv_error)
        return EINVAL;
    /*
     * Pinned NetBSD if_rtwn.c:rtwn_rx_frame() initializes rssi to zero,
     * then replaces it only when valid PHY status is present. Match that
     * existing NetBSD no-PHY fallback so management/control/data frames
     * are not discarded merely because hardware omitted PHYST.
     *
     * Zero here is the framework fallback, NOT a measured 0 dBm signal.
     * The measured/unmeasured distinction remains in packet->rssi_valid.
     */
    return rtwn8723be_net80211_input(n, frame, length,
        packet->rssi_valid ? packet->rssi_dbm : 0);
}

/* Native TX queue consumer and software-CCMP ownership. */
/* BEGIN NATIVE NET80211 TX QUEUE CONSUMER
 * All entry points run with the non-MPSAFE ifnet's kernel serialization.
 * The outer if_start owns a datapath TX-start lease. No OS callback or
 * crypto operation executes while the native descriptor mutex is held.
 */
static struct rtwn8723be_net80211 *
r23be_n80211_tx_key_owner(struct ieee80211com *ic)
{
    struct rtwn8723be_net80211 *n;

    if (ic == NULL || ic->ic_ifp == NULL)
        return NULL;
    n = ic->ic_ifp->if_softc;
    if (n == NULL || n->sc == NULL || ic != &n->sc->sc_ic)
        return NULL;
    return n;
}

static void
r23be_n80211_tx_key_begin(struct ieee80211com *ic)
{
    struct rtwn8723be_net80211 *n = r23be_n80211_tx_key_owner(ic);

    if (n == NULL)
        return;
    /* Saturation permanently denies TX rather than aliasing an old epoch. */
    if (n->tx_key_epoch != UINT64_MAX)
        n->tx_key_epoch++;
    if (n->tx_key_update_depth == (unsigned int)-1) {
        n->tx_key_epoch = UINT64_MAX;
        return;
    }
    n->tx_key_update_depth++;
    if (n->tx_key_begin_saved != NULL)
        n->tx_key_begin_saved(ic);
}

static void
r23be_n80211_tx_key_end(struct ieee80211com *ic)
{
    struct rtwn8723be_net80211 *n = r23be_n80211_tx_key_owner(ic);

    if (n == NULL)
        return;
    if (n->tx_key_update_depth == 0) {
        n->tx_key_epoch = UINT64_MAX;
        return;
    }
    if (n->tx_key_end_saved != NULL)
        n->tx_key_end_saved(ic);
    if (n->tx_key_update_depth == 0) {
        n->tx_key_epoch = UINT64_MAX;
        return;
    }
    n->tx_key_update_depth--;
}

static void
rtwn8723be_n80211_tx_install(struct rtwn8723be_net80211 *n)
{
    struct ieee80211_crypto_state *cs = &n->sc->sc_ic.ic_crypto;

    KASSERT(!n->tx_busy && n->tx_pending_m == NULL &&
        n->tx_pending_ni == NULL);
    n->tx_again = false;
    memset(&n->tx_pending_rate, 0, sizeof(n->tx_pending_rate));
    n->tx_pending_key_epoch = 0;
    n->tx_pending_channel = NULL;
    n->tx_pending_channel_flags = 0;
    n->tx_pending_channel_freq = 0;
    n->tx_pending_defkey = 0;
    n->tx_pending_state = 0;
    n->tx_pending_security_flags = 0;
    n->tx_pending_mode = 0;
    memset(n->tx_pending_bssid, 0, sizeof(n->tx_pending_bssid));
    n->tx_key_epoch = 0;
    n->tx_key_update_depth = 0;
    n->tx_key_begin_saved = cs->cs_key_update_begin;
    n->tx_key_end_saved = cs->cs_key_update_end;
    cs->cs_key_update_begin = r23be_n80211_tx_key_begin;
    cs->cs_key_update_end = r23be_n80211_tx_key_end;
}

static int
rtwn8723be_n80211_tx_remove(struct rtwn8723be_net80211 *n)
{
    struct ieee80211_crypto_state *cs;

    if (n == NULL || n->sc == NULL)
        return EINVAL;
    cs = &n->sc->sc_ic.ic_crypto;
    if (n->tx_busy || n->tx_key_update_depth != 0 ||
        n->tx_pending_m != NULL || n->tx_pending_ni != NULL ||
        cs->cs_key_update_begin != r23be_n80211_tx_key_begin ||
        cs->cs_key_update_end != r23be_n80211_tx_key_end)
        return EBUSY;
    cs->cs_key_update_begin = n->tx_key_begin_saved;
    cs->cs_key_update_end = n->tx_key_end_saved;
    n->tx_key_begin_saved = NULL;
    n->tx_key_end_saved = NULL;
    n->tx_key_epoch = 0;
    n->tx_again = false;
    return 0;
}

static void
r23be_n80211_tx_free_frames(struct mbuf *m)
{
    struct mbuf *next;

    while (m != NULL) {
        next = m->m_nextpkt;
        m->m_nextpkt = NULL;
        m_freem(m);
        m = next;
    }
}

static void
rtwn8723be_n80211_tx_purge(struct rtwn8723be_net80211 *n)
{
    struct mbuf *m;
    struct ieee80211_node *ni;

    if (n == NULL)
        return;
    /* ifstop has revoked RUNNING and proved the consumer idle first. */
    KASSERT(!n->tx_busy);
    m = n->tx_pending_m;
    ni = n->tx_pending_ni;
    n->tx_pending_m = NULL;
    n->tx_pending_ni = NULL;
    n->tx_again = false;
    n->tx_pending_key_epoch = 0;
    n->tx_pending_channel = NULL;
    n->tx_pending_channel_flags = 0;
    n->tx_pending_channel_freq = 0;
    n->tx_pending_defkey = 0;
    n->tx_pending_state = 0;
    n->tx_pending_security_flags = 0;
    n->tx_pending_mode = 0;
    memset(n->tx_pending_bssid, 0, sizeof(n->tx_pending_bssid));
    if (n->sc != NULL)
        n->sc->sc_ec.ec_if.if_flags &= ~IFF_OACTIVE;
    memset(&n->tx_pending_rate, 0, sizeof(n->tx_pending_rate));
    r23be_n80211_tx_free_frames(m);
    if (ni != NULL)
        ieee80211_free_node(ni);
}

static int
r23be_n80211_tx_rate(struct rtwn8723be_softc *sc,
    struct ieee80211_node *ni, struct mbuf *m,
    struct rtwn8723be_tx_params *p)
{
    static const uint8_t legacy[] =
        { 2, 4, 11, 22, 12, 18, 24, 36, 48, 72, 96, 108 };
    struct ieee80211com *ic;
    const struct ieee80211_rateset *rs, *supported;
    struct ieee80211_frame *wh;
    unsigned int i, j;
    uint8_t rate = 2, type, candidate, best = 0, best_hw = 0;
    bool basic, threshold_rts, erp, cck_only;

    if (sc == NULL || ni == NULL || m == NULL || p == NULL)
        return EINVAL;
    ic = &sc->sc_ic;
    rs = &ni->ni_rates;
    if ((m->m_flags & M_PKTHDR) == 0 ||
        m->m_len < (int)sizeof(*wh) ||
        m->m_pkthdr.len <= 0 ||
        ic->ic_opmode != IEEE80211_M_STA ||
        ic->ic_curchan == NULL || ic->ic_curchan == IEEE80211_CHAN_ANYC ||
        !IEEE80211_IS_CHAN_2GHZ(ic->ic_curchan))
        return EINVAL;
    wh = mtod(m, struct ieee80211_frame *);
    type = wh->i_fc[0] & IEEE80211_FC0_TYPE_MASK;
    basic = type == IEEE80211_FC0_TYPE_MGT ||
        IEEE80211_IS_MULTICAST(wh->i_addr1);
    memset(p, 0, sizeof(*p));
    p->macid = 0; /* Frozen Linux station peer MACID. */
    p->use_driver_rate = true;
    p->disable_rate_fallback = true;
    p->security = 0;
    cck_only = ic->ic_curmode == IEEE80211_MODE_11B ||
        ieee80211_chan2ieee(ic, ic->ic_curchan) == 14;
    if (basic) {
        p->hw_rate = 0; /* Mandatory 2.4-GHz CCK1, as native wrapper. */
        p->rateid = 7; /* RATR_INX_WIRELESS_MC in pinned wifi.h. */
    } else {
        if (type != IEEE80211_FC0_TYPE_DATA ||
            (ic->ic_curmode != IEEE80211_MODE_11B &&
            ic->ic_curmode != IEEE80211_MODE_11G) ||
            rs->rs_nrates == 0 ||
            rs->rs_nrates > sizeof(rs->rs_rates))
            return EINVAL;
        if (ic->ic_fixed_rate >= 0) {
            supported = &ic->ic_sup_rates[ic->ic_curmode];
            if (supported->rs_nrates > sizeof(supported->rs_rates) ||
                ic->ic_fixed_rate >= supported->rs_nrates)
                return EINVAL;
            rate = supported->rs_rates[ic->ic_fixed_rate] &
                IEEE80211_RATE_VAL;
            for (i = 0; i < rs->rs_nrates; i++)
                if ((rs->rs_rates[i] & IEEE80211_RATE_VAL) == rate)
                    break;
            if (i == rs->rs_nrates)
                return EINVAL;
        } else {
            if (ni->ni_txrate < 0 || ni->ni_txrate >= rs->rs_nrates)
                return EINVAL;
            rate = rs->rs_rates[ni->ni_txrate] & IEEE80211_RATE_VAL;
        }
        for (i = 0; i < sizeof(legacy); i++)
            if (legacy[i] == rate)
                break;
        if (i == sizeof(legacy) || (cck_only && i >= 4))
            return EOPNOTSUPP;
        p->hw_rate = (uint8_t)i;
        p->rateid = ic->ic_curmode == IEEE80211_MODE_11B ? 6 : 4;
    }

    /* Target if_iwn includes the on-air FCS and gives threshold priority. */
    if (IEEE80211_IS_MULTICAST(wh->i_addr1))
        return 0;
    threshold_rts = (size_t)m->m_pkthdr.len + IEEE80211_CRC_LEN >
        ic->ic_rtsthreshold;
    erp = !basic && p->hw_rate >= 4 &&
        (ic->ic_flags & IEEE80211_F_USEPROT) != 0;
    if (erp && ic->ic_protmode == IEEE80211_PROT_NONE)
        erp = false;
    if (erp && ic->ic_protmode != IEEE80211_PROT_CTSONLY &&
        ic->ic_protmode != IEEE80211_PROT_RTSCTS)
        return EINVAL;
    if (!threshold_rts && !erp)
        return 0;
    if (rs->rs_nrates == 0 || rs->rs_nrates > sizeof(rs->rs_rates))
        return EOPNOTSUPP;

    /*
     * Linux RTL8723BE exposes RTS/CTS-to-self and an explicit RTS rate.
     * Use a negotiated BASIC legacy rate, never faster than this data
     * frame or the pinned Linux 24-Mbps RTS ceiling. ERP protection must
     * also be heard by CCK-only stations. Missing legal BASIC coverage is
     * an error, not permission to invent an unsupported control rate.
     */
    cck_only = cck_only || erp;
    for (i = 0; i < rs->rs_nrates; i++) {
        if ((rs->rs_rates[i] & IEEE80211_RATE_BASIC) == 0)
            continue;
        candidate = rs->rs_rates[i] & IEEE80211_RATE_VAL;
        if (candidate > rate || candidate > 48 || candidate <= best)
            continue;
        for (j = 0; j < sizeof(legacy); j++)
            if (legacy[j] == candidate)
                break;
        if (j == sizeof(legacy) || (cck_only && j >= 4))
            continue;
        best = candidate;
        best_hw = (uint8_t)j;
    }
    if (best == 0)
        return EOPNOTSUPP;
    p->rts_rate = best_hw;
    p->rts_enable = true;
    p->cts2self = !threshold_rts && erp &&
        ic->ic_protmode == IEEE80211_PROT_CTSONLY;
    /* Long preamble, 20 MHz and primary subchannel are explicit defaults. */
    p->rts_short = false;
    p->rts_sc = 0;
    return 0;
}

/*
 * Success replaces/frees the original with one exclusively writable MPDU.
 * Failure frees only the private candidate; *mp and the node stay owned
 * by this caller. The cipher's monotonically consumed PN is never reset.
 */
static int
r23be_n80211_tx_prepare(struct rtwn8723be_softc *sc,
    struct ieee80211_node *ni, struct mbuf **mp, bool require_protected)
{
    struct ieee80211com *ic;
    struct ieee80211_frame header;
    const struct ieee80211_cipher *cipher = NULL;
    struct ieee80211_key *key = NULL, *used;
    struct mbuf *original, *part, *copy;
    size_t total = 0, headroom = 0, trailer = 0, bytes;
    int hdrlen;
    bool protected_frame;

    if (sc == NULL || mp == NULL || *mp == NULL || ni == NULL ||
        !sc->sc_sw_crypto || !sc->sc_use_sw_sec ||
        sc->sc_hw_security_enabled || !sc->sc_security_policy_valid)
        return EINVAL;
    ic = &sc->sc_ic;
    if ((ic->ic_flags & IEEE80211_F_DATAPAD) != 0)
        return EOPNOTSUPP;
    original = *mp;
    if ((original->m_flags & M_PKTHDR) == 0 ||
        original->m_pkthdr.len < (int)sizeof(header) ||
        original->m_pkthdr.len > RTWN8723BE_RX_BUFFER_SIZE ||
        original->m_nextpkt != NULL)
        return EINVAL;
    /* Bound-check the chain before m_copydata, which otherwise can panic. */
    for (part = original; part != NULL; part = part->m_next) {
        if (part->m_len < 0 ||
            (size_t)part->m_len > RTWN8723BE_RX_BUFFER_SIZE - total)
            return EINVAL;
        total += (size_t)part->m_len;
    }
    if (total != (size_t)original->m_pkthdr.len)
        return EINVAL;
    m_copydata(original, 0, sizeof(header), &header);
    if ((header.i_fc[0] & IEEE80211_FC0_VERSION_MASK) !=
        IEEE80211_FC0_VERSION_0 ||
        ((header.i_fc[0] & IEEE80211_FC0_TYPE_MASK) !=
        IEEE80211_FC0_TYPE_MGT &&
        (header.i_fc[0] & IEEE80211_FC0_TYPE_MASK) !=
        IEEE80211_FC0_TYPE_DATA) ||
        (header.i_fc[1] & IEEE80211_FC1_MORE_FRAG) != 0 ||
        (header.i_seq[0] & IEEE80211_SEQ_FRAG_MASK) != 0)
        return EOPNOTSUPP;
    hdrlen = ieee80211_hdrspace(ic, &header);
    if (hdrlen < (int)sizeof(header) || (size_t)hdrlen > total)
        return EINVAL;
    protected_frame = (header.i_fc[1] & IEEE80211_FC1_WEP) != 0;
    if (require_protected && !protected_frame)
        return EACCES;
    if (protected_frame) {
        if (IEEE80211_IS_MULTICAST(header.i_addr1) ||
            ni->ni_ucastkey.wk_cipher == &ieee80211_cipher_none) {
            if (ic->ic_def_txkey == IEEE80211_KEYIX_NONE ||
                ic->ic_def_txkey >= IEEE80211_WEP_NKID)
                return EACCES;
            key = &ic->ic_nw_keys[ic->ic_def_txkey];
        } else {
            key = &ni->ni_ucastkey;
        }
        cipher = key->wk_cipher;
        if (cipher == NULL || key->wk_private == NULL ||
            (key->wk_flags & (IEEE80211_KEY_SWCRYPT |
            IEEE80211_KEY_XMIT)) != (IEEE80211_KEY_SWCRYPT |
            IEEE80211_KEY_XMIT) ||
            cipher->ic_cipher != IEEE80211_CIPHER_AES_CCM ||
            cipher->ic_header != 8 || cipher->ic_trailer != 8 ||
            cipher->ic_miclen != 0 || key->wk_keylen != 16 ||
            key->wk_keytsc >= 0x0000ffffffffffffULL)
            return EACCES;
        headroom = cipher->ic_header;
        trailer = cipher->ic_trailer;
    }
    if (total > RTWN8723BE_RX_BUFFER_SIZE - headroom - trailer)
        return EFBIG;
    bytes = total + headroom + trailer;
    copy = m_gethdr(M_NOWAIT, MT_DATA);
    if (copy == NULL)
        return ENOBUFS;
    MEXTMALLOC(copy, bytes, M_NOWAIT);
    if ((copy->m_flags & M_EXT) == 0) {
        m_freem(copy);
        return ENOBUFS;
    }
    copy->m_data += headroom;
    copy->m_len = (int)total;
    copy->m_pkthdr.len = (int)total;
    M_CLEARCTX(copy);
    m_copydata(original, 0, (int)total, mtod(copy, void *));
    if (M_READONLY(copy) || M_LEADINGSPACE(copy) < (int)headroom ||
        M_TRAILINGSPACE(copy) < (int)trailer) {
        m_freem(copy);
        return EIO;
    }
    if (protected_frame) {
        /*
         * NetBSD's pointer-by-value crypto API can replace/free its local
         * m. Exact headroom and a contiguous MAC header prevent BOTH
         * its M_PREPEND allocation and m_pullup relocation branches.
         */
        used = ieee80211_crypto_encap(ic, ni, copy);
        if (used != key || (used->wk_flags & IEEE80211_KEY_SWCRYPT) == 0 ||
            copy->m_next != NULL ||
            copy->m_pkthdr.len != (int)bytes ||
            copy->m_len != copy->m_pkthdr.len) {
            m_freem(copy);
            return EACCES;
        }
    }
    m_freem(original);
    *mp = copy;
    return 0;
}

static bool
r23be_n80211_tx_running(struct rtwn8723be_net80211 *n, struct ifnet *ifp)
{
    return n != NULL && n->registered && n->sc != NULL &&
        n == &n->sc->sc_net80211 &&
        ifp == &n->sc->sc_ec.ec_if && ifp->if_softc == n &&
        (ifp->if_flags & IFF_RUNNING) != 0 &&
        n->sc->sc_sw_crypto && n->sc->sc_use_sw_sec &&
        !n->sc->sc_hw_security_enabled &&
        n->sc->sc_security_policy_valid &&
        (n->sc->sc_ic.ic_flags & IEEE80211_F_DATAPAD) == 0 &&
        n->tx_key_update_depth == 0 && n->tx_key_epoch != UINT64_MAX &&
        n->sc->sc_ic.ic_crypto.cs_key_update_begin == r23be_n80211_tx_key_begin &&
        n->sc->sc_ic.ic_crypto.cs_key_update_end == r23be_n80211_tx_key_end &&
        rtwn8723be_datapath_running_ready(n->sc->sc_datapath);
}

struct r23be_n80211_tx_context {
    uint64_t key_epoch;
    struct ieee80211_channel *channel;
    uint16_t channel_flags;
    uint16_t channel_freq;
    uint16_t default_key;
    int state;
    uint32_t security_flags;
    int mode;
    uint8_t bssid[IEEE80211_ADDR_LEN];
};

static int
r23be_n80211_tx_context_take(struct rtwn8723be_net80211 *n,
    struct ieee80211_node *ni, struct r23be_n80211_tx_context *context)
{
    struct ieee80211com *ic = &n->sc->sc_ic;
    struct ieee80211_channel *channel = ic->ic_curchan;

    if (channel == NULL || channel == IEEE80211_CHAN_ANYC)
        return EINVAL;
    context->key_epoch = n->tx_key_epoch;
    context->channel = channel;
    context->channel_flags = channel->ic_flags;
    context->channel_freq = channel->ic_freq;
    context->default_key = ic->ic_def_txkey;
    context->state = ic->ic_state;
    context->security_flags = ic->ic_flags &
        (IEEE80211_F_PRIVACY | IEEE80211_F_WPA);
    context->mode = ic->ic_curmode;
    IEEE80211_ADDR_COPY(context->bssid, ni->ni_bssid);
    return 0;
}

static bool
r23be_n80211_tx_context_valid(struct rtwn8723be_net80211 *n,
    struct ieee80211_node *ni, struct mbuf *m,
    const struct r23be_n80211_tx_context *context)
{
    struct ieee80211com *ic = &n->sc->sc_ic;
    const struct ieee80211_frame *wh;

    if (context->key_epoch != n->tx_key_epoch ||
        context->channel != ic->ic_curchan ||
        context->channel == NULL ||
        context->channel == IEEE80211_CHAN_ANYC ||
        context->channel_flags != context->channel->ic_flags ||
        context->channel_freq != context->channel->ic_freq ||
        context->state != ic->ic_state ||
        context->mode != ic->ic_curmode ||
        context->security_flags != (ic->ic_flags &
        (IEEE80211_F_PRIVACY | IEEE80211_F_WPA)) ||
        context->default_key != ic->ic_def_txkey ||
        !IEEE80211_ADDR_EQ(context->bssid, ni->ni_bssid) ||
        m->m_len < (int)sizeof(*wh))
        return false;
    wh = mtod(m, const struct ieee80211_frame *);
    /* STA data must still target the actual current BSS after callbacks. */
    if ((wh->i_fc[0] & IEEE80211_FC0_TYPE_MASK) ==
        IEEE80211_FC0_TYPE_DATA &&
        (ic->ic_state != IEEE80211_S_RUN || ni != ic->ic_bss ||
        ic->ic_bss == NULL ||
        !IEEE80211_ADDR_EQ(wh->i_addr1, ic->ic_bss->ni_bssid)))
        return false;
    return true;
}

void
rtwn8723be_net80211_tx_start(struct rtwn8723be_softc *sc, struct ifnet *ifp)
{
    struct rtwn8723be_net80211 *n;
    struct ieee80211com *ic;
    struct ieee80211_node *ni = NULL;
    struct rtwn8723be_tx_params rate;
    struct ether_header *eh;
    struct ieee80211_frame *wh;
    struct r23be_n80211_tx_context context;
    struct mbuf *m = NULL;
    bool require_protected, is_eapol;
    int error, s;

    if (sc == NULL || ifp == NULL)
        return;
    n = &sc->sc_net80211;
    ic = &sc->sc_ic;
    s = splnet();
    if (!r23be_n80211_tx_running(n, ifp)) {
        splx(s);
        return;
    }
    if (n->tx_busy) {
        n->tx_again = true;
        splx(s);
        return;
    }
    n->tx_busy = true;
    n->tx_again = false;
    for (;;) {
        if (!r23be_n80211_tx_running(n, ifp))
            break;
        if (n->tx_pending_m != NULL) {
            m = n->tx_pending_m;
            ni = n->tx_pending_ni;
            rate = n->tx_pending_rate;
            context.key_epoch = n->tx_pending_key_epoch;
            context.channel = n->tx_pending_channel;
            context.channel_flags = n->tx_pending_channel_flags;
            context.channel_freq = n->tx_pending_channel_freq;
            context.default_key = n->tx_pending_defkey;
            context.state = n->tx_pending_state;
            context.security_flags = n->tx_pending_security_flags;
            context.mode = n->tx_pending_mode;
            IEEE80211_ADDR_COPY(context.bssid, n->tx_pending_bssid);
            n->tx_pending_m = NULL;
            n->tx_pending_ni = NULL;
            if (ni == NULL)
                goto drop;
            wh = mtod(m, struct ieee80211_frame *);
            if ((wh->i_fc[0] & IEEE80211_FC0_TYPE_MASK) ==
                IEEE80211_FC0_TYPE_DATA &&
                (ic->ic_state != IEEE80211_S_RUN || ni != ic->ic_bss))
                goto drop;
            goto submit; /* Already encrypted; never consume another PN. */
        }
        /* New management traffic precedes normal Ethernet queue dequeue. */
        IF_DEQUEUE(&ic->ic_mgtq, m);
        require_protected = false;
        if (m != NULL) {
            if ((m->m_flags & M_PKTHDR) == 0)
                goto drop;
            ni = M_GETCTX(m, struct ieee80211_node *);
            M_CLEARCTX(m);
            if (ni == NULL)
                goto drop;
            if (r23be_n80211_tx_context_take(n, ni, &context) != 0)
                goto drop;
        } else {
            if (ic->ic_state != IEEE80211_S_RUN)
                break;
            IFQ_DEQUEUE(&ifp->if_snd, m);
            if (m == NULL)
                break;
            if ((m->m_flags & M_PKTHDR) == 0 ||
                m->m_pkthdr.len < (int)sizeof(*eh))
                goto drop;
            if (m->m_len < (int)sizeof(*eh)) {
                m = m_pullup(m, sizeof(*eh));
                if (m == NULL)
                    goto drop;
            }
            eh = mtod(m, struct ether_header *);
            is_eapol = eh->ether_type == htons(ETHERTYPE_PAE);
            ni = ieee80211_find_txnode(ic, eh->ether_dhost);
            if (ni == NULL)
                goto drop;
            if (r23be_n80211_tx_context_take(n, ni, &context) != 0)
                goto drop;
            require_protected = !is_eapol &&
                (context.security_flags & IEEE80211_F_PRIVACY) != 0;
            bpf_mtap(ifp, m, BPF_D_OUT);
            m = ieee80211_encap(ic, m, ni);
            if (m == NULL)
                goto drop; /* encap has already consumed/freed the mbuf. */
        }
        error = r23be_n80211_tx_prepare(sc, ni, &m, require_protected);
        if (error != 0)
            goto drop;
        bpf_mtap3(ic->ic_rawbpf, m, BPF_D_OUT);
submit:
        /* Read rate/ERP/RTS policy after every potentially reentrant callback. */
        error = r23be_n80211_tx_rate(sc, ni, m, &rate);
        if (error != 0)
            goto drop;
        /* A ciphertext cannot cross key, channel or association epochs. */
        if (!r23be_n80211_tx_running(n, ifp) ||
            !r23be_n80211_tx_context_valid(n, ni, m, &context))
            goto drop;
        error = rtwn8723be_datapath_enqueue_80211(sc->sc_datapath,
            m, ni, true, &rate);
        if (error == 0) {
            m = NULL;
            ni = NULL; /* Both resources belong to the DMA slot now. */
            if_statinc(ifp, if_opackets);
            continue;
        }
        if (error == EBUSY) {
            n->tx_pending_m = m;
            n->tx_pending_ni = ni;
            n->tx_pending_rate = rate;
            n->tx_pending_key_epoch = context.key_epoch;
            n->tx_pending_channel = context.channel;
            n->tx_pending_channel_flags = context.channel_flags;
            n->tx_pending_channel_freq = context.channel_freq;
            n->tx_pending_defkey = context.default_key;
            n->tx_pending_state = context.state;
            n->tx_pending_security_flags = context.security_flags;
            n->tx_pending_mode = context.mode;
            IEEE80211_ADDR_COPY(n->tx_pending_bssid, context.bssid);
            m = NULL;
            ni = NULL;
            ifp->if_flags |= IFF_OACTIVE;
            /*
             * A synchronous completion can arrive before OACTIVE was
             * published. Every observed wake belongs to this attempt;
             * never suppress a later frame's wake because an earlier
             * frame already required a retry.
             */
            if (n->tx_again &&
                r23be_n80211_tx_running(n, ifp)) {
                n->tx_again = false;
                ifp->if_flags &= ~IFF_OACTIVE;
                continue;
            }
            break;
        }
drop:
        r23be_n80211_tx_free_frames(m);
        m = NULL;
        if (ni != NULL) {
            ieee80211_free_node(ni);
            ni = NULL;
        }
        if_statinc(ifp, if_oerrors);
    }
    n->tx_busy = false;
    splx(s);
}

struct rtwn8723be_net80211 *
rtwn8723be_net80211_tx_owner(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_net80211 *n;

    if (sc == NULL)
        return NULL;
    n = &sc->sc_net80211;
    if (!n->registered || n->sc != sc ||
        n->methods.tx_start != rtwn8723be_net80211_tx_start)
        return NULL;
    return n;
}

void
rtwn8723be_net80211_tx_complete(void *arg, unsigned int qid, size_t reclaimed)
{
    struct rtwn8723be_net80211 *n = arg;
    struct ifnet *ifp;
    int s;

    if (n == NULL || reclaimed == 0 || qid >= RTWN8723BE_TX_QUEUE_COUNT)
        return;
    s = splnet();
    if (n->sc == NULL) {
        splx(s);
        return;
    }
    ifp = &n->sc->sc_ec.ec_if;
    if (!r23be_n80211_tx_running(n, ifp)) {
        splx(s);
        return;
    }
    ifp->if_flags &= ~IFF_OACTIVE;
    if (n->tx_busy)
        n->tx_again = true;
    else
        if_start_lock(ifp);
    splx(s);
}
/* END NATIVE NET80211 TX QUEUE CONSUMER */
