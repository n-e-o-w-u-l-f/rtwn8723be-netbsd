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
    int error;

    if (n == NULL || !n->registered || n->sc == NULL)
        return ENXIO;
    sc = n->sc;
    if (n->methods.hw_start == NULL || n->methods.hw_stop == NULL ||
        n->methods.tx_start == NULL)
        return ENOSYS;
    /* NetBSD ifconfig down/up must permit a clean restarted adapter. */
    if ((sc->sc_linux.stage != R23BE_STAGE_PROBED &&
        sc->sc_linux.stage != R23BE_STAGE_STOPPED) ||
        !sc->sc_irq_dispatch_ready || sc->sc_ih == NULL ||
        !sc->sc_rings_allocated || !sc->sc_mapped)
        return EAGAIN;

    /*
     * hw_start must complete Linux-order hw_init(), irq enable, RX config,
     * mark_hal_start and the datapath bridge's start + unwind on failure.
     * A partially initialized device must NEVER be marked IFF_RUNNING.
     */
    error = n->methods.hw_start(sc);
    if (error != 0)
        return error;
    if (!sc->sc_linux.started || !sc->sc_linux.fw_ready ||
        sc->sc_linux.stage != R23BE_STAGE_RUNNING) {
        int stop_error = n->methods.hw_stop(sc);
        return stop_error != 0 ? stop_error : EIO;
    }
    ifp->if_flags |= IFF_RUNNING;
    ifp->if_flags &= ~IFF_OACTIVE;
    return 0;
}

static int
rtwn8723be_n80211_ifstop(struct rtwn8723be_net80211 *n)
{
    struct ifnet *ifp;

    if (n == NULL || !n->registered)
        return ENXIO;
    ifp = &n->sc->sc_ec.ec_if;
    /* Stop further net80211 dequeue BEFORE stopping hardware/interrupts. */
    ifp->if_flags &= ~(IFF_RUNNING | IFF_OACTIVE);
    ifp->if_timer = 0;
    /* Detach may stop an interface that was registered but never started. */
    if (!n->sc->sc_linux.started &&
        (n->sc->sc_linux.stage == R23BE_STAGE_PROBED ||
         n->sc->sc_linux.stage == R23BE_STAGE_STOPPED))
        return 0;
    if (!n->sc->sc_linux.started ||
        n->sc->sc_linux.stage != R23BE_STAGE_RUNNING)
        return EBUSY; /* An interrupted stop needs explicit recovery. */
    if (n->methods.hw_stop == NULL)
        return ENOSYS;
    return n->methods.hw_stop(n->sc);
}

static void
rtwn8723be_n80211_ifstart(struct ifnet *ifp)
{
    struct rtwn8723be_net80211 *n = ifp->if_softc;

    if (n == NULL || !n->registered ||
        (ifp->if_flags & (IFF_RUNNING | IFF_OACTIVE)) != IFF_RUNNING ||
        n->methods.tx_start == NULL)
        return;
    /* Real 802.11 framing/TX node lifetime is owned by the HW method. */
    n->methods.tx_start(n->sc, ifp);
}

static int
rtwn8723be_n80211_ioctl(struct ifnet *ifp, u_long cmd, void *data)
{
    struct rtwn8723be_net80211 *n = ifp->if_softc;
    struct ieee80211com *ic;
    int error = 0, s;

    if (n == NULL || !n->registered)
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
        }
        break;
    case SIOCADDMULTI:
    case SIOCDELMULTI:
        error = ether_ioctl(ifp, cmd, data);
        /* Multicast filter programming requires full hardware callbacks. */
        if (error == ENETRESET && (ifp->if_flags & IFF_RUNNING) == 0)
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
    return 0;
}

int
rtwn8723be_net80211_register(struct rtwn8723be_net80211 *n,
    struct rtwn8723be_softc *sc,
    const struct rtwn8723be_net80211_methods *methods)
{
    struct ieee80211com *ic;
    struct ifnet *ifp;
    unsigned int ch;

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

    n->sc = sc;
    n->methods = *methods;
    ic = &sc->sc_ic;
    ifp = &sc->sc_ec.ec_if;
    ic->ic_ifp = ifp;
    ic->ic_phytype = IEEE80211_T_OFDM;
    ic->ic_opmode = IEEE80211_M_STA;
    ic->ic_state = IEEE80211_S_INIT;
    /* Claim only currently implemented station-mode 2.4-GHz capabilities. */
    ic->ic_caps = IEEE80211_C_SHPREAMBLE | IEEE80211_C_SHSLOT;
    ic->ic_sup_rates[IEEE80211_MODE_11B] = ieee80211_std_rateset_11b;
    ic->ic_sup_rates[IEEE80211_MODE_11G] = ieee80211_std_rateset_11g;
    for (ch = 1; ch <= 14; ch++) {
        ic->ic_channels[ch].ic_freq =
            ieee80211_ieee2mhz(ch, IEEE80211_CHAN_2GHZ);
        ic->ic_channels[ch].ic_flags =
            IEEE80211_CHAN_CCK | IEEE80211_CHAN_OFDM |
            IEEE80211_CHAN_DYN | IEEE80211_CHAN_2GHZ;
    }

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
    ifp->if_percpuq = if_percpuq_create(ifp);
    if (ifp->if_percpuq == NULL) {
        ieee80211_ifdetach(ic);
        if_detach(ifp);
        n->sc = NULL;
        memset(&n->methods, 0, sizeof(n->methods));
        return ENOMEM;
    }
    if_register(ifp);
    ieee80211_media_init(ic, rtwn8723be_n80211_media_change,
        ieee80211_media_status);
    n->registered = true;
    ieee80211_announce(ic);
    return 0;
}

void
rtwn8723be_net80211_unregister(struct rtwn8723be_net80211 *n)
{
    struct ifnet *ifp;
    int s;

    if (n == NULL || !n->registered || n->sc == NULL)
        return;
    s = splnet();
    ifp = &n->sc->sc_ec.ec_if;
    if (rtwn8723be_n80211_ifstop(n) != 0) {
        splx(s);
        return; /* Retain registered resources on failed hardware stop. */
    }
    ieee80211_ifdetach(&n->sc->sc_ic);
    if_detach(ifp);
    n->registered = false;
    n->sc = NULL;
    memset(&n->methods, 0, sizeof(n->methods));
    splx(s);
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
    if ((n->sc->sc_ec.ec_if.if_flags & IFF_RUNNING) == 0)
        return ENETDOWN;

    m = m_devget((char *)(uintptr_t)frame, (int)length, 0,
        &n->sc->sc_ec.ec_if);
    if (m == NULL)
        return ENOBUFS;
    ic = &n->sc->sc_ic;
    s = splnet();
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
