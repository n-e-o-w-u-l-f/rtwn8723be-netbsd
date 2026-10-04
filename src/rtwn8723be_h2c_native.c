/* SPDX-License-Identifier: GPL-2.0 */
/* Native NetBSD transport: Linux PCIe mailbox registers via bus_space.
 * Never called in interrupt context; callers serialize with stop/detach.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <sys/intr.h>
#include <sys/mutex.h>

#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_h2c_native.h"

static bool
r23be_h2c_mmio_ready(const struct rtwn8723be_softc *sc)
{
    return sc != NULL && sc->sc_h2c.initialized &&
        sc->sc_mapped && sc->sc_mapsize >=
        R23BE_REG_HMEBOX_EXT_3 + 4U;
}

static int
r23be_h2c_lock(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    if (sc == NULL || !sc->sc_h2c.initialized)
        return ENXIO;
    mutex_enter(&sc->sc_h2c.lock);
    return 0;
}

static void
r23be_h2c_unlock(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    mutex_exit(&sc->sc_h2c.lock);
}

static int
r23be_h2c_read_1(void *arg, uint16_t reg, uint8_t *out)
{
    struct rtwn8723be_softc *sc = arg;

    if (out == NULL || !r23be_h2c_mmio_ready(sc) ||
        reg != R23BE_REG_HMETFR)
        return EINVAL;
    *out = rtwn8723be_read_1(sc, reg);
    return 0;
}

static int
r23be_h2c_write_1(void *arg, uint16_t reg, uint8_t value)
{
    struct rtwn8723be_softc *sc = arg;
    bool main, ext;

    if (!r23be_h2c_mmio_ready(sc))
        return ENXIO;
    main = reg >= R23BE_REG_HMEBOX_0 &&
        reg < R23BE_REG_HMEBOX_3 + 4U;
    ext = reg >= R23BE_REG_HMEBOX_EXT_0 &&
        reg < R23BE_REG_HMEBOX_EXT_3 + 4U;
    if (!main && !ext)
        return EINVAL;
    rtwn8723be_write_1(sc, reg, value);
    return 0;
}

static void
r23be_h2c_delay(void *arg, unsigned int usec)
{
    (void)arg;
    delay(usec);
}

static struct rtwn8723be_h2c_ops
r23be_h2c_ops(struct rtwn8723be_softc *sc)
{
    const struct rtwn8723be_h2c_ops ops = {
        .ctx = sc,
        .lock = r23be_h2c_lock,
        .unlock = r23be_h2c_unlock,
        .read_1 = r23be_h2c_read_1,
        .write_1 = r23be_h2c_write_1,
        .delay_us = r23be_h2c_delay,
    };

    return ops;
}

int
rtwn8723be_h2c_native_init(struct rtwn8723be_softc *sc)
{
    if (sc == NULL)
        return EINVAL;
    if (sc->sc_h2c.initialized)
        return EALREADY;
    mutex_init(&sc->sc_h2c.lock, MUTEX_DEFAULT, IPL_NONE);
    sc->sc_h2c.sc = sc;
    rtwn8723be_h2c_reset(&sc->sc_h2c.state);
    sc->sc_h2c.initialized = true;
    return 0;
}

void
rtwn8723be_h2c_native_reset(struct rtwn8723be_softc *sc)
{
    if (sc == NULL || !sc->sc_h2c.initialized)
        return;
    mutex_enter(&sc->sc_h2c.lock);
    rtwn8723be_h2c_reset(&sc->sc_h2c.state);
    mutex_exit(&sc->sc_h2c.lock);
}

void
rtwn8723be_h2c_native_fini(struct rtwn8723be_softc *sc)
{
    if (sc == NULL || !sc->sc_h2c.initialized)
        return;
    /* Owner must already have quiesced all H2C users. */
    rtwn8723be_h2c_native_reset(sc);
    sc->sc_h2c.initialized = false;
    mutex_destroy(&sc->sc_h2c.lock);
    sc->sc_h2c.sc = NULL;
}

int
rtwn8723be_h2c_native_fw_ready(struct rtwn8723be_softc *sc)
{
    if (!r23be_h2c_mmio_ready(sc))
        return ENXIO;
    if (!sc->sc_linux.being_init_adapter ||
        sc->sc_linux.stage != R23BE_STAGE_FIRMWARE_DOWNLOAD)
        return EAGAIN;
    mutex_enter(&sc->sc_h2c.lock);
    /* Firmware upload just completed its real checksum/ready handshake. */
    rtwn8723be_h2c_reset(&sc->sc_h2c.state);
    sc->sc_h2c.state.firmware_ready = true;
    mutex_exit(&sc->sc_h2c.lock);
    return 0;
}

int
rtwn8723be_h2c_native_send(struct rtwn8723be_softc *sc,
    uint8_t id, const uint8_t *payload, size_t len)
{
    struct rtwn8723be_h2c_ops ops;

    if (!r23be_h2c_mmio_ready(sc))
        return ENXIO;
    if (!sc->sc_linux.fw_ready ||
        (!sc->sc_linux.being_init_adapter && !sc->sc_linux.started))
        return EAGAIN;
    ops = r23be_h2c_ops(sc);
    return rtwn8723be_h2c_send(&sc->sc_h2c.state,
        &ops, id, payload, len);
}

int
rtwn8723be_h2c_native_media_status(struct rtwn8723be_softc *sc,
    bool connected)
{
    const uint8_t payload[3] = { connected ? 1U : 0U, 0, 0 };

    return rtwn8723be_h2c_native_send(sc, 1U,
        payload, sizeof(payload));
}
