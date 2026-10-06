#define main hw_disable_core_already_covered_main
#include "hw_disable_check.c"
#undef main
#include "rtwn8723be_netbsd.h"
static struct {
    bool owned, valid, idle;
    int acquire_error;
    unsigned int acquired, released;
} stop_owner;
static int owner_acquire(void *arg, struct rtwn8723be_softc *sc,
    struct rtwn8723be_hw_disable_inputs *input,
    struct rtwn8723be_hw_disable_state *state)
{
    assert(arg == &stop_owner && sc->sc_mapped && !stop_owner.owned);
    stop_owner.acquired++;
    if (stop_owner.acquire_error)
        return stop_owner.acquire_error;
    stop_owner.owned = true;
    input->state_valid = stop_owner.valid;
    input->rf_idle = stop_owner.idle;
    input->driver_is_goingto_unload = true;
    input->rfoff_reason = 0U;
    state->cur_ps_level = 0x100U;
    state->mac_link_state = 2U;
    return 0;
}
static bool owner_ready(void *arg, struct rtwn8723be_softc *sc)
{
    assert(arg == &stop_owner && sc->sc_mapped);
    return stop_owner.owned && ready(&actual);
}
static void owner_release(void *arg, struct rtwn8723be_softc *sc,
    const struct rtwn8723be_hw_disable_state *state, int error)
{
    (void)state;
    (void)error;
    assert(arg == &stop_owner && stop_owner.owned && sc->sc_mapped);
    stop_owner.released++;
    stop_owner.owned = false;
}
static const struct rtwn8723be_hw_disable_owner owner = {
    owner_acquire, owner_ready, owner_release
};
uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *sc, size_t reg)
{
    assert(sc->sc_mapped && stop_owner.owned && ready(&actual));
    actual.calls++;
    return disable_raw_read(&actual, (uint32_t)reg);
}
void rtwn8723be_write_1(struct rtwn8723be_softc *sc, size_t reg, uint8_t value)
{
    assert(sc->sc_mapped && stop_owner.owned && ready(&actual));
    actual.calls++;
    disable_raw_write(&actual, (uint32_t)reg, value);
}
int rtwn8723be_netbsd_poweroff_adapter(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    assert(stop_owner.owned && ready(&actual));
    sc->sc_linux.mac_func_enable = sc->sc_linux.fw_ready = false;
    return poweroff(&actual);
}
static void native_reset(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_hw_disable_inputs input;
    memset(sc, 0, sizeof(*sc));
    memset(&stop_owner, 0, sizeof(stop_owner));
    stop_owner.valid = stop_owner.idle = true;
    reset(&sc->sc_hw_disable, &input);
    sc->sc_mapped = sc->sc_core_initialized = sc->sc_linux.started = true;
    sc->sc_linux.fw_ready = sc->sc_linux.mac_func_enable = true;
    sc->sc_linux.stage = R23BE_STAGE_STOPPING;
    sc->sc_mapsize = 4096U;
    sc->sc_hw_disable_owner = &owner;
    sc->sc_hw_disable_owner_arg = &stop_owner;
    sc->sc_bcn_ctrl_val = 0x1dU;
    sc->sc_sw_led0 = 1U;
    sc->sc_led_opendrain = true;
    sc->sc_calibration.iqk_initialized = true;
    sc->sc_calibration.cache[0] = 0x12345678U;
}
int main(void)
{
    struct rtwn8723be_softc sc;
    unsigned int calls, revoke;
    native_reset(&sc);
    sc.sc_hw_disable_owner = NULL;
    assert(rtwn8723be_netbsd_hw_disable(&sc) == ENXIO);
    assert(actual.calls == 0U && stop_owner.acquired == 0U);
    native_reset(&sc);
    sc.sc_hal_started = true;
    assert(rtwn8723be_netbsd_hw_disable(&sc) == EAGAIN && actual.calls == 0U);
    native_reset(&sc);
    sc.sc_irq_enabled = true;
    assert(rtwn8723be_netbsd_hw_disable(&sc) == EAGAIN && actual.calls == 0U);
    native_reset(&sc);
    sc.sc_linux.stage = 49U;
    assert(rtwn8723be_netbsd_hw_disable(&sc) == EAGAIN && actual.calls == 0U);
    native_reset(&sc);
    sc.sc_mapsize = 0x554U;
    assert(rtwn8723be_netbsd_hw_disable(&sc) == EAGAIN && actual.calls == 0U);
    native_reset(&sc);
    stop_owner.acquire_error = EIO;
    assert(rtwn8723be_netbsd_hw_disable(&sc) == EIO);
    assert(actual.calls == 0U && stop_owner.released == 0U);
    native_reset(&sc);
    stop_owner.valid = false;
    assert(rtwn8723be_netbsd_hw_disable(&sc) == ENXIO);
    assert(actual.calls == 0U && stop_owner.released == 1U && !stop_owner.owned);
    native_reset(&sc);
    stop_owner.idle = false;
    assert(rtwn8723be_netbsd_hw_disable(&sc) == EBUSY);
    assert(actual.calls == 0U && stop_owner.released == 1U);
    native_reset(&sc);
    assert(rtwn8723be_netbsd_hw_disable(&sc) == 0);
    calls = actual.calls;
    assert(stop_owner.released == 1U && !stop_owner.owned);
    assert(sc.sc_hw_disable.powered_off && sc.sc_bcn_ctrl_val == 0x1dU);
    assert(!sc.sc_linux.mac_func_enable && !sc.sc_linux.fw_ready);
    assert(sc.sc_calibration.iqk_initialized && sc.sc_calibration.cache[0] == 0x12345678U);
    native_reset(&sc);
    actual.fail_at = calls;
    assert(rtwn8723be_netbsd_hw_disable(&sc) == EIO);
    assert(stop_owner.released == 1U && !stop_owner.owned);
    assert(sc.sc_hw_disable.poweroff_attempted && !sc.sc_hw_disable.powered_off);
    for (revoke = 1U; revoke < calls; revoke++) {
        native_reset(&sc);
        actual.revoke_at = revoke;
        assert(rtwn8723be_netbsd_hw_disable(&sc) == ENXIO);
        assert(actual.calls == revoke && actual.power_calls == 0U);
        assert(stop_owner.released == 1U && !stop_owner.owned);
        assert(sc.sc_calibration.iqk_initialized && sc.sc_calibration.cache[0] == 0x12345678U);
    }
    printf("HW_DISABLE_NATIVE_OWNER_PASS unbound=reject preflight=no_MMIO "
        "release=all_acquired_paths IQK_preserved=pass revocations=%u poweroff_failure=pass\n",
        calls - 1U);
    return 0;
}
