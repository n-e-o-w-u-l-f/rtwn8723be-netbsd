/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Explicitly join existing net80211 and C2H consumers to the one shared
 * RX DMA dispatch.arg used by the NetBSD old-TRX ring drain.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>

#include "rtwn8723be_rx_binding.h"

static int
rtwn8723be_rx_binding_frame(void *arg, const uint8_t *data,
    size_t length, const struct rtwn8723be_rx_packet *packet)
{
    struct rtwn8723be_rx_binding *binding = arg;

    if (binding == NULL || binding->net == NULL ||
        !binding->net->registered)
        return ENXIO;
    return rtwn8723be_net80211_rx_frame(binding->net, data,
        length, packet);
}

static int
rtwn8723be_rx_binding_c2h(void *arg, const uint8_t *data,
    size_t length, const struct rtwn8723be_rx_packet *packet)
{
    struct rtwn8723be_rx_binding *binding = arg;

    if (binding == NULL || binding->net == NULL ||
        !binding->net->registered)
        return ENXIO;
    return rtwn8723be_c2h_native_receive(&binding->firmware,
        data, length, packet);
}

int
rtwn8723be_rx_binding_init(struct rtwn8723be_rx_binding *binding,
    struct rtwn8723be_net80211 *net,
    const struct rtwn8723be_c2h_handlers *firmware)
{
    if (binding == NULL || net == NULL || firmware == NULL)
        return EINVAL;
    if (binding->net != NULL || binding->dispatch.arg != NULL)
        return EBUSY; /* Caller must not rebind an active IRQ context. */
    if (!net->registered || net->sc == NULL)
        return ENXIO;

    /*
     * These callbacks are required by the supported station datapath.
     * BT consumers are mandatory only for a coexistent Bluetooth board;
     * the C2H router still rejects an unexpected BT event if absent.
     */
    if (firmware->tx_report == NULL ||
        firmware->ra_report == NULL ||
        (net->sc->sc_btcoexist &&
         (firmware->bt_info == NULL || firmware->bt_mp == NULL)))
        return ENOSYS;

    /*
     * A non-NULL handler pointer is not a live Bluetooth consumer.
     * Initialization and real MCU-ready/old-RX-drain MP activation must
     * precede publishing the shared RX callbacks on coexistence boards.
     * The external lifecycle owner serializes this admission against
     * STOPPING, MP/BTC fini and IRQ/softint quiescence.
     */
    if (net->sc->sc_btcoexist &&
        (!net->sc->sc_btc.initialized ||
         !net->sc->sc_btc_mp.initialized ||
         !net->sc->sc_btc_mp.active))
        return EAGAIN;

    /* The caller must provide zero-initialized, IRQ-quiesced storage. */
    memset(binding, 0, sizeof(*binding));
    binding->net = net;
    binding->firmware = *firmware;
    binding->dispatch.arg = binding;
    binding->dispatch.frame = rtwn8723be_rx_binding_frame;
    binding->dispatch.c2h = rtwn8723be_rx_binding_c2h;
    return 0;
}
