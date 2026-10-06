/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Native implementations of the direct-I/O RTL8723BE coexistence providers.
 * Frozen Linux reference:
 *   rtlwifi/btcoexist/halbtcoutsrc.c @ fd179f8a05be3ccae366b9b96e176b51fbe54aab
 *
 * The original provider ABI hides I/O failures in void/scalar callbacks.
 * NetBSD must not silently continue with fabricated values, so every
 * fallible operation records the first failure in the native BTC owner.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>

#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_btc_native.h"
#include "rtwn8723be_btc_providers_native.h"
#include "rtwn8723be_h2c_native.h"
#include "rtwn8723be_rf_serial.h"

static unsigned int
btc_shift32(uint32_t mask)
{
    unsigned int shift = 0;

    KASSERT(mask != 0);
    while ((mask & 1U) == 0) {
        mask >>= 1;
        shift++;
    }
    return shift;
}

static struct rtwn8723be_softc *
btc_sc(void *context)
{
    struct btc_coexist *btc = context;

    if (btc == NULL || btc->adapter == NULL)
        return NULL;
    return btc->adapter;
}

static bool
btc_mmio_range(const struct rtwn8723be_softc *sc, uint32_t reg, size_t width)
{
    return sc != NULL && sc->sc_mapped && width != 0 &&
        reg <= sc->sc_mapsize && sc->sc_mapsize - reg >= width;
}

static bool
btc_provider_ready(struct rtwn8723be_softc *sc)
{
    return sc != NULL && rtwn8723be_btc_native_provider_ready(sc);
}

static void
btc_provider_fail(struct rtwn8723be_softc *sc, int error)
{
    if (sc != NULL && error != 0)
        rtwn8723be_btc_native_provider_error(sc, error);
}

static uint8_t
btc_read_1(void *context, uint32_t reg)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return 0;
    if (!btc_mmio_range(sc, reg, 1)) {
        btc_provider_fail(sc, EINVAL);
        return 0;
    }
    return rtwn8723be_read_1(sc, reg);
}

static uint16_t
btc_read_2(void *context, uint32_t reg)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return 0;
    if (!btc_mmio_range(sc, reg, 2)) {
        btc_provider_fail(sc, EINVAL);
        return 0;
    }
    return rtwn8723be_read_2(sc, reg);
}

static uint32_t
btc_read_4(void *context, uint32_t reg)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return 0;
    if (!btc_mmio_range(sc, reg, 4)) {
        btc_provider_fail(sc, EINVAL);
        return 0;
    }
    return rtwn8723be_read_4(sc, reg);
}

static void
btc_write_1(void *context, uint32_t reg, uint32_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return;
    if (!btc_mmio_range(sc, reg, 1)) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    rtwn8723be_write_1(sc, reg, (uint8_t)data);
}

static void
btc_write_1_mask(void *context, uint32_t reg, uint32_t mask, uint8_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint8_t original;
    unsigned int shift;

    if (!btc_provider_ready(sc))
        return;
    if (!btc_mmio_range(sc, reg, 1) ||
        (mask != 0xffffffffU && (mask == 0 || (mask & ~0xffU) != 0))) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    if (mask == 0xffffffffU) {
        rtwn8723be_write_1(sc, reg, data);
        return;
    }

    original = rtwn8723be_read_1(sc, reg);
    shift = btc_shift32(mask);
    data = (uint8_t)((original & ~(uint8_t)mask) |
        (((uint32_t)data << shift) & mask));
    rtwn8723be_write_1(sc, reg, data);
}

static void
btc_write_2(void *context, uint32_t reg, uint16_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return;
    if (!btc_mmio_range(sc, reg, 2)) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    rtwn8723be_write_2(sc, reg, data);
}

static void
btc_write_4(void *context, uint32_t reg, uint32_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return;
    if (!btc_mmio_range(sc, reg, 4)) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    rtwn8723be_write_4(sc, reg, data);
}

static void
btc_write_local_1(void *context, uint32_t reg, uint8_t data)
{
    struct btc_coexist *btc = context;

    if (btc == NULL || btc->chip_interface != BTC_INTF_PCI) {
        struct rtwn8723be_softc *sc = btc_sc(context);
        if (sc != NULL)
            btc_provider_fail(sc, EINVAL);
        return;
    }
    btc_write_1(context, reg, data);
}

static void
btc_set_bb(void *context, uint32_t reg, uint32_t mask, uint32_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint32_t original;
    unsigned int shift;

    if (!btc_provider_ready(sc))
        return;
    if (!btc_mmio_range(sc, reg, 4) || mask == 0) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    if (mask == 0xffffffffU) {
        rtwn8723be_write_4(sc, reg, data);
        return;
    }
    original = rtwn8723be_read_4(sc, reg);
    shift = btc_shift32(mask);
    original = (original & ~mask) | ((data << shift) & mask);
    rtwn8723be_write_4(sc, reg, original);
}

static uint32_t
btc_get_bb(void *context, uint32_t reg, uint32_t mask)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint32_t value;

    if (!btc_provider_ready(sc))
        return 0;
    if (!btc_mmio_range(sc, reg, 4) || mask == 0) {
        btc_provider_fail(sc, EINVAL);
        return 0;
    }
    value = rtwn8723be_read_4(sc, reg);
    return (value & mask) >> btc_shift32(mask);
}

static bool
btc_rf_ready(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    return btc_provider_ready(sc) && sc->sc_core_initialized &&
        sc->sc_bb_valid && sc->sc_linux.fw_ready &&
        sc->sc_rf_path_count_valid &&
        (sc->sc_rf_path_count == 1 || sc->sc_rf_path_count == 2);
}

static int
btc_rf_read_bb(void *arg, uint32_t reg, uint32_t *value)
{
    struct rtwn8723be_softc *sc = arg;

    if (value == NULL || !btc_rf_ready(sc))
        return EINVAL;
    if (!btc_mmio_range(sc, reg, 4))
        return EINVAL;
    *value = rtwn8723be_read_4(sc, reg);
    return 0;
}

static int
btc_rf_write_bb(void *arg, uint32_t reg, uint32_t value)
{
    struct rtwn8723be_softc *sc = arg;

    if (!btc_rf_ready(sc))
        return EAGAIN;
    if (!btc_mmio_range(sc, reg, 4))
        return EINVAL;
    rtwn8723be_write_4(sc, reg, value);
    return 0;
}

static void
btc_rf_delay(void *arg, unsigned int usec)
{
    (void)arg;
    delay(usec);
}

static const struct rtwn8723be_rf_serial_io btc_rf_io = {
    .ready = btc_rf_ready,
    .read_bb = btc_rf_read_bb,
    .write_bb = btc_rf_write_bb,
    .delay_us = btc_rf_delay,
};

static void
btc_set_rf(void *context, uint8_t path, uint32_t reg,
    uint32_t mask, uint32_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    struct rtwn8723be_rf_serial_ctx rf;
    int error;

    if (!btc_provider_ready(sc))
        return;
    if (path > RTWN8723BE_RF_PATH_B || mask == 0 ||
        (mask & ~RTWN8723BE_RF_FULL_MASK) != 0) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    rf.io = &btc_rf_io;
    rf.dev = sc;
    error = rtwn8723be_rf_masked_write(&rf, path, reg, mask, data);
    btc_provider_fail(sc, error);
}

static uint32_t
btc_get_rf(void *context, uint8_t path, uint32_t reg, uint32_t mask)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    struct rtwn8723be_rf_serial_ctx rf;
    uint32_t value = 0;
    int error;

    if (!btc_provider_ready(sc))
        return 0;
    if (path > RTWN8723BE_RF_PATH_B || mask == 0 ||
        (mask & ~RTWN8723BE_RF_FULL_MASK) != 0) {
        btc_provider_fail(sc, EINVAL);
        return 0;
    }
    rf.io = &btc_rf_io;
    rf.dev = sc;
    error = rtwn8723be_rf_serial_read(&rf, path, reg, &value);
    if (error != 0) {
        btc_provider_fail(sc, error);
        return 0;
    }
    return (value & mask) >> btc_shift32(mask);
}

static void
btc_fill_h2c(void *context, uint8_t id, uint32_t length, uint8_t *command)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    int error;

    if (!btc_provider_ready(sc))
        return;
    if ((length != 0 && command == NULL) ||
        length > R23BE_H2C_MAX_PAYLOAD) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    error = rtwn8723be_h2c_native_send(sc, id, command, (size_t)length);
    btc_provider_fail(sc, error);
}

static void
btc_delay_ms(void *context, unsigned int ms)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return;
    while (ms-- != 0)
        delay(1000);
}

int
rtwn8723be_btc_native_seed_lowlevel(struct btc_coexist *btc,
    struct rtwn8723be_softc *sc)
{
    if (btc == NULL || sc == NULL)
        return EINVAL;
    if (btc->adapter != NULL && btc->adapter != sc)
        return EBUSY;

    btc->adapter = sc;
    btc->chip_interface = BTC_INTF_PCI;
    btc->btc_read_1byte = btc_read_1;
    btc->btc_write_1byte = btc_write_1;
    btc->btc_write_1byte_bitmask = btc_write_1_mask;
    btc->btc_read_2byte = btc_read_2;
    btc->btc_write_2byte = btc_write_2;
    btc->btc_read_4byte = btc_read_4;
    btc->btc_write_4byte = btc_write_4;
    btc->btc_write_local_reg_1byte = btc_write_local_1;
    btc->btc_set_bb_reg = btc_set_bb;
    btc->btc_get_bb_reg = btc_get_bb;
    btc->btc_set_rf_reg = btc_set_rf;
    btc->btc_get_rf_reg = btc_get_rf;
    btc->btc_fill_h2c = btc_fill_h2c;
    btc->r23be_delay_ms = btc_delay_ms;
    return 0;
}
