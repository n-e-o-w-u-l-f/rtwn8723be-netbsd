/* SPDX-License-Identifier: GPL-2.0 */
/*
 * NetBSD 03d918f6d0e81fa05b8f1160eca0628ad39988a6 binding for real
 * RTL8723BE initialization IQK/LCK. A bound initialized BTC/DM/RF owner is
 * required; neither sc_btcoexist nor an EEPROM antenna count grants one.
 * Only the exclusive RF_CALIBRATION initialization phase is supported.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_calibration_native.h"
#include "rtwn8723be_rf_serial.h"

struct cal_native_session {
    struct rtwn8723be_softc *sc;
    const struct rtwn8723be_calibration_owner *owner;
    void *owner_arg;
    bool acquired;
    struct rtwn8723be_rf_serial_ctx rf;
};

static bool
cal_native_phase(struct rtwn8723be_softc *sc)
{
    return sc != NULL && sc->sc_mapped && sc->sc_core_initialized &&
        sc->sc_bb_valid && sc->sc_linux.fw_ready &&
        sc->sc_rf_chnlval_valid && sc->sc_phy_identity_valid &&
        sc->sc_rf_path_count_valid && sc->sc_rf_path_count == 1U &&
        sc->sc_phy_identity.pci_interface &&
        sc->sc_linux.being_init_adapter && !sc->sc_linux.started &&
        !sc->sc_irq_enabled &&
        sc->sc_linux.stage == R23BE_STAGE_RF_CALIBRATION &&
        sc->sc_mapsize >= 0xeecU + sizeof(uint32_t);
}

static bool
cal_native_ready(void *arg)
{
    struct cal_native_session *session = arg;
    return session != NULL && session->acquired &&
        cal_native_phase(session->sc) &&
        session->sc->sc_calibration_owner == session->owner &&
        session->sc->sc_calibration_owner_arg == session->owner_arg &&
        session->owner->ready(session->owner_arg, session->sc);
}

static int
cal_native_reg(void *arg, uint32_t reg, unsigned int width)
{
    struct cal_native_session *session = arg;
    if (!cal_native_ready(arg))
        return ENXIO;
    if ((width != 1U && width != 4U) ||
        (width == 4U && (reg & 3U) != 0) ||
        reg > session->sc->sc_mapsize ||
        session->sc->sc_mapsize - reg < width)
        return EINVAL;
    return 0;
}

static int
cal_native_read_bb(void *arg, uint32_t reg, uint32_t mask, uint32_t *value)
{
    struct cal_native_session *session = arg;
    int error;
    if (value == NULL || mask == 0)
        return EINVAL;
    error = cal_native_reg(arg, reg, 4U);
    if (error != 0)
        return error;
    *value = rtwn8723be_netbsd_get_bbreg(session->sc, reg, mask);
    return 0;
}

static int
cal_native_write_bb(void *arg, uint32_t reg, uint32_t mask, uint32_t value)
{
    struct cal_native_session *session = arg;
    int error;
    if (mask == 0)
        return EINVAL;
    error = cal_native_reg(arg, reg, 4U);
    if (error != 0)
        return error;
    rtwn8723be_netbsd_set_bbreg(session->sc, reg, mask, value);
    return 0;
}

static int
cal_native_rf_read_bb(void *arg, uint32_t reg, uint32_t *value)
{
    return cal_native_read_bb(arg, reg, UINT32_MAX, value);
}

static int
cal_native_rf_write_bb(void *arg, uint32_t reg, uint32_t value)
{
    return cal_native_write_bb(arg, reg, UINT32_MAX, value);
}

static int
cal_native_read_rf(void *arg, unsigned int path, uint32_t reg, uint32_t mask,
    uint32_t *value)
{
    struct cal_native_session *session = arg;
    uint32_t raw;
    unsigned int shift = 0;
    int error;
    if (value == NULL || mask == 0 ||
        (mask & ~RTWN8723BE_RF_FULL_MASK) != 0 || path != 0U)
        return EINVAL;
    error = rtwn8723be_rf_serial_read(&session->rf, path, reg, &raw);
    if (error != 0)
        return error;
    while ((mask & (1U << shift)) == 0)
        shift++;
    *value = (raw & mask) >> shift;
    return 0;
}

static int
cal_native_write_rf(void *arg, unsigned int path, uint32_t reg, uint32_t mask,
    uint32_t value)
{
    struct cal_native_session *session = arg;
    if (path != 0U)
        return EINVAL;
    return rtwn8723be_rf_masked_write(&session->rf, path, reg, mask, value);
}

static int
cal_native_read_mac(void *arg, uint32_t reg, unsigned int width,
    uint32_t *value)
{
    struct cal_native_session *session = arg;
    int error;
    if (value == NULL)
        return EINVAL;
    error = cal_native_reg(arg, reg, width);
    if (error != 0)
        return error;
    *value = width == 1U ? rtwn8723be_read_1(session->sc, reg) :
        rtwn8723be_read_4(session->sc, reg);
    return 0;
}

static int
cal_native_write_mac(void *arg, uint32_t reg, unsigned int width,
    uint32_t value)
{
    struct cal_native_session *session = arg;
    int error = cal_native_reg(arg, reg, width);
    if (error != 0)
        return error;
    if (width == 1U)
        rtwn8723be_write_1(session->sc, reg, (uint8_t)value);
    else
        rtwn8723be_write_4(session->sc, reg, value);
    return 0;
}

static int
cal_native_delay(void *arg, unsigned int usec)
{
    if (!cal_native_ready(arg))
        return ENXIO;
    delay(usec);
    return cal_native_ready(arg) ? 0 : ENXIO;
}

static void
cal_native_rf_delay(void *arg, unsigned int usec)
{
    /* Existing RF-serial ABI checks ready before each surrounding access. */
    (void)arg;
    delay(usec);
}

static int
cal_native_scan(void *arg, bool *active)
{
    struct cal_native_session *session = arg;
    if (!cal_native_ready(arg))
        return ENXIO;
    return session->owner->scan_active(session->owner_arg, session->sc,
        active);
}

static int
cal_native_thermal(void *arg,
    const struct rtwn8723be_calibration_context *ctx,
    struct rtwn8723be_calibration_state *state)
{
    struct cal_native_session *session = arg;
    if (!cal_native_ready(arg))
        return ENXIO;
    return session->owner->thermal_track(session->owner_arg, session->sc,
        ctx, state);
}

static const struct rtwn8723be_rf_serial_io cal_native_rf_io = {
    .ready = cal_native_ready,
    .read_bb = cal_native_rf_read_bb,
    .write_bb = cal_native_rf_write_bb,
    .delay_us = cal_native_rf_delay,
};

int
rtwn8723be_netbsd_rf_calibration(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct cal_native_session session;
    struct rtwn8723be_calibration_inputs input;
    struct rtwn8723be_calibration_context ctx;
    struct rtwn8723be_calibration_io io = {
        .ready = cal_native_ready,
        .read_bb = cal_native_read_bb,
        .write_bb = cal_native_write_bb,
        .read_rf = cal_native_read_rf,
        .write_rf = cal_native_write_rf,
        .read_mac = cal_native_read_mac,
        .write_mac = cal_native_write_mac,
        .delay_us = cal_native_delay,
        .scan_active = cal_native_scan,
    };
    const struct rtwn8723be_calibration_owner *owner;
    int error;
    if (sc == NULL)
        return EINVAL;
    if (!cal_native_phase(sc))
        return ENXIO;
    owner = sc->sc_calibration_owner;
    if (owner == NULL || owner->acquire == NULL || owner->ready == NULL ||
        owner->scan_active == NULL || owner->release == NULL)
        return ENXIO;
    memset(&session, 0, sizeof(session));
    memset(&input, 0, sizeof(input));
    session.sc = sc;
    session.owner = owner;
    session.owner_arg = sc->sc_calibration_owner_arg;
    error = owner->acquire(session.owner_arg, sc, &input);
    if (error != 0)
        return error;
    session.acquired = true;
    session.rf.io = &cal_native_rf_io;
    session.rf.dev = &session;
    if (owner->thermal_track != NULL)
        io.thermal_track = cal_native_thermal;
    ctx.io = &io;
    ctx.arg = &session;
    error = rtwn8723be_calibration_run(&ctx, &sc->sc_calibration, &input);
    owner->release(session.owner_arg, sc, &sc->sc_calibration, error);
    session.acquired = false;
    return error;
}
