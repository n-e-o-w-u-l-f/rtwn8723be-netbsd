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
    /* Detach may stop an interface that was registered but never started. */
    if (!n->sc->sc_linux.started) {
        if (rtwn8723be_net80211_unstarted_detach_allowed(
            &n->sc->sc_linux))
            return 0;
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
    if (methods->hw_start == NULL || methods->hw_stop == NULL ||
        methods->tx_start == NULL)
        return ENOSYS;
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
