/* SPDX-License-Identifier: GPL-2.0 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_hw_disable_native.h"

struct disable_native_session {
    struct rtwn8723be_softc *sc;
    const struct rtwn8723be_hw_disable_owner *owner;
    void *arg;
    bool acquired;
};
static bool
disable_native_phase(const struct rtwn8723be_softc *sc)
{
    return sc != NULL && sc->sc_mapped && sc->sc_core_initialized &&
        sc->sc_linux.stage == R23BE_STAGE_STOPPING && sc->sc_linux.started &&
        !sc->sc_hal_started && !sc->sc_irq_enabled &&
        sc->sc_mapsize >= 0x1000U;
}
static bool
disable_native_ready(void *arg)
{
    struct disable_native_session *s = arg;
    return s->acquired && disable_native_phase(s->sc) &&
        s->owner->ready(s->arg, s->sc);
}
static int
disable_native_reg(void *arg, uint32_t reg)
{
    struct disable_native_session *s = arg;
    if (!disable_native_ready(arg))
        return ENXIO;
    if (reg >= s->sc->sc_mapsize)
        return EINVAL;
    return 0;
}
static int
disable_native_read(void *arg, uint32_t reg, uint8_t *value)
{
    struct disable_native_session *s = arg;
    int error = disable_native_reg(arg, reg);
    if (error == 0)
        *value = rtwn8723be_read_1(s->sc, reg);
    return error;
}
static int
disable_native_write(void *arg, uint32_t reg, uint8_t value)
{
    struct disable_native_session *s = arg;
    int error = disable_native_reg(arg, reg);
    if (error == 0)
        rtwn8723be_write_1(s->sc, reg, value);
    return error;
}
static int
disable_native_poweroff(void *arg)
{
    struct disable_native_session *s = arg;
    if (!disable_native_ready(arg))
        return ENXIO;
    /* Existing real MMIO/pwrseq/firmware engine runs under the owner's hold. */
    return rtwn8723be_netbsd_poweroff_adapter(s->sc);
}
int
rtwn8723be_netbsd_hw_disable(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    struct disable_native_session s;
    struct rtwn8723be_hw_disable_state state;
    struct rtwn8723be_hw_disable_inputs input;
    const struct rtwn8723be_hw_disable_owner *owner;
    static const struct rtwn8723be_hw_disable_io io = {
        disable_native_ready, disable_native_read, disable_native_write,
        disable_native_poweroff
    };
    int error;
    if (sc == NULL)
        return EINVAL;
    if (!disable_native_phase(sc))
        return EAGAIN;
    owner = sc->sc_hw_disable_owner;
    if (owner == NULL || owner->acquire == NULL || owner->ready == NULL ||
        owner->release == NULL)
        return ENXIO;
    memset(&input, 0, sizeof(input));
    state = sc->sc_hw_disable;
    error = owner->acquire(sc->sc_hw_disable_owner_arg, sc, &input, &state);
    if (error != 0)
        return error;
    s.sc = sc;
    s.owner = owner;
    s.arg = sc->sc_hw_disable_owner_arg;
    s.acquired = true;
    input.led_pin = sc->sc_sw_led0;
    input.led_opendrain = sc->sc_led_opendrain;
    state.bcn_ctrl = sc->sc_bcn_ctrl_val;
    error = rtwn8723be_hw_disable(&io, &s, &state, &input);
    sc->sc_bcn_ctrl_val = state.bcn_ctrl;
    sc->sc_hw_disable = state;
    owner->release(s.arg, sc, &state, error);
    return error;
}
