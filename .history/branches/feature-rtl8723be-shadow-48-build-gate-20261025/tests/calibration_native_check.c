#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_rf_serial.h"

static uint32_t bb[0x1000U / 4U], rf[256];
static uint8_t mac[0x1000U];
static unsigned int mmio, acquire_count, release_count, iqk_shots, thermal_count;
static unsigned int revoke_at;
static bool held;
static int acquire_error, released_error;
static struct rtwn8723be_calibration_inputs published;
static struct rtwn8723be_softc *expected_sc;

static unsigned int shift(uint32_t mask)
{
    unsigned int n = 0;
    assert(mask != 0);
    while ((mask & (1U << n)) == 0)
        n++;
    return n;
}
static void access(struct rtwn8723be_softc *sc)
{
    assert(sc == expected_sc && held);
    assert(revoke_at == 0 || mmio < revoke_at);
    mmio++;
}
uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *sc, size_t reg)
{
    access(sc);
    assert(reg < sizeof(mac));
    return mac[reg];
}
uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *sc, size_t reg)
{
    access(sc);
    assert((reg & 3U) == 0 && reg < sizeof(bb));
    return bb[reg / 4U];
}
void rtwn8723be_write_1(struct rtwn8723be_softc *sc, size_t reg, uint8_t value)
{
    access(sc);
    assert(reg < sizeof(mac));
    mac[reg] = value;
}
void rtwn8723be_write_4(struct rtwn8723be_softc *sc, size_t reg, uint32_t value)
{
    access(sc);
    assert((reg & 3U) == 0 && reg < sizeof(bb));
    bb[reg / 4U] = value;
    if (reg == 0xe48U && value == 0xf8000000U)
        iqk_shots++;
}
uint32_t rtwn8723be_netbsd_get_bbreg(struct rtwn8723be_softc *sc, size_t reg,
    uint32_t mask)
{
    return (rtwn8723be_read_4(sc, reg) & mask) >> shift(mask);
}
void rtwn8723be_netbsd_set_bbreg(struct rtwn8723be_softc *sc, size_t reg,
    uint32_t mask, uint32_t value)
{
    if (mask != UINT32_MAX)
        value = (rtwn8723be_read_4(sc, reg) & ~mask) | (value << shift(mask));
    rtwn8723be_write_4(sc, reg, value);
}
int rtwn8723be_rf_serial_read(const struct rtwn8723be_rf_serial_ctx *ctx,
    unsigned int path, uint32_t reg, uint32_t *value)
{
    uint32_t ignored;
    int error;
    assert(path == 0U && reg < 256U && value != NULL);
    if (!ctx->io->ready(ctx->dev))
        return ENXIO;
    error = ctx->io->read_bb(ctx->dev, 0x820U, &ignored);
    if (error == 0)
        *value = rf[reg];
    return error;
}
int rtwn8723be_rf_masked_write(const struct rtwn8723be_rf_serial_ctx *ctx,
    unsigned int path, uint32_t reg, uint32_t mask, uint32_t value)
{
    uint32_t ignored;
    int error;
    assert(path == 0U && reg < 256U && mask != 0);
    if (!ctx->io->ready(ctx->dev))
        return ENXIO;
    error = ctx->io->write_bb(ctx->dev, 0x840U, (reg << 20) | (value & 0xfffffU));
    if (error == 0) {
        ignored = (rf[reg] & ~mask) | (value << shift(mask));
        rf[reg] = ignored & 0xfffffU;
    }
    return error;
}
void delay(unsigned int usec)
{
    assert(held && (usec == 10000U || usec == 50000U));
}
static int acquire(void *arg, struct rtwn8723be_softc *sc,
    struct rtwn8723be_calibration_inputs *input)
{
    assert(arg == &published && sc == expected_sc && !held);
    acquire_count++;
    if (acquire_error != 0)
        return acquire_error;
    held = true;
    *input = published;
    return 0;
}
static bool ready(void *arg, struct rtwn8723be_softc *sc)
{
    assert(arg == &published && sc == expected_sc);
    return held && (revoke_at == 0 || mmio < revoke_at);
}
static int scan(void *arg, struct rtwn8723be_softc *sc, bool *active)
{
    assert(ready(arg, sc));
    *active = false;
    return 0;
}
static int thermal(void *arg, struct rtwn8723be_softc *sc,
    const struct rtwn8723be_calibration_context *ctx,
    struct rtwn8723be_calibration_state *state)
{
    assert(ready(arg, sc) && ctx->io->ready(ctx->arg));
    assert(state == &sc->sc_calibration);
    thermal_count++;
    return 0;
}
static void release(void *arg, struct rtwn8723be_softc *sc,
    const struct rtwn8723be_calibration_state *state, int error)
{
    assert(arg == &published && sc == expected_sc && held);
    assert(state == &sc->sc_calibration && !state->lck_inprogress);
    if (state->tracking_changed)
        published.tm_trigger = state->tm_trigger;
    release_count++;
    released_error = error;
    held = false;
}
static const struct rtwn8723be_calibration_owner owner = {
    acquire, ready, scan, NULL, release
};
static void reset(struct rtwn8723be_softc *sc)
{
    memset(sc, 0, sizeof(*sc));
    memset(bb, 0, sizeof(bb));
    memset(rf, 0, sizeof(rf));
    memset(mac, 0, sizeof(mac));
    sc->sc_mapped = sc->sc_core_initialized = sc->sc_bb_valid = true;
    sc->sc_rf_chnlval_valid = sc->sc_phy_identity_valid = true;
    sc->sc_rf_path_count_valid = sc->sc_phy_identity.pci_interface = true;
    sc->sc_linux.fw_ready = sc->sc_linux.being_init_adapter = true;
    sc->sc_linux.stage = R23BE_STAGE_RF_CALIBRATION;
    sc->sc_mapsize = 0x1000U;
    sc->sc_rf_path_count = 1U;
    sc->sc_calibration_owner = &owner;
    sc->sc_calibration_owner_arg = &published;
    published = (struct rtwn8723be_calibration_inputs){
        .rf_state_valid = true, .rf_on = true, .btc_bound = true,
        .btc_initialized = true, .btc_ant_num = 1U,
        .dm_state_valid = true, .current_channel = 1U
    };
    bb[0xe94U / 4U] = bb[0xea4U / 4U] = 0x100U << 16;
    bb[0xc80U / 4U] = bb[0xc88U / 4U] = 0x40000000U;
    expected_sc = sc;
    mmio = acquire_count = release_count = iqk_shots = thermal_count = 0;
    revoke_at = 0;
    held = false;
    acquire_error = released_error = 0;
}
int main(void)
{
    struct rtwn8723be_softc sc;
    struct rtwn8723be_calibration_owner with_thermal = owner;
    assert(rtwn8723be_netbsd_rf_calibration(NULL) == EINVAL);
    reset(&sc);
    sc.sc_calibration_owner = NULL;
    sc.sc_btcoexist = true;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == ENXIO);
    assert(mmio == 0 && acquire_count == 0 && release_count == 0);
    reset(&sc);
    sc.sc_linux.stage--;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == ENXIO && mmio == 0);
    reset(&sc);
    sc.sc_mapsize = 0xeecU;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == ENXIO && mmio == 0);
    reset(&sc);
    sc.sc_irq_enabled = true;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == ENXIO && mmio == 0);
    reset(&sc);
    acquire_error = EBUSY;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == EBUSY);
    assert(mmio == 0 && acquire_count == 1 && release_count == 0);
    reset(&sc);
    sc.sc_btcoexist = true;
    published.btc_initialized = false;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == ENXIO);
    assert(mmio == 0 && release_count == 1 && !held);
    reset(&sc);
    published.txpower_tracking = published.tm_trigger = true;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == ENOTSUP);
    assert(mmio == 0 && release_count == 1 && !held);
    reset(&sc);
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == 0);
    assert(mmio != 0 && release_count == 1 && !held && iqk_shots == 0);
    reset(&sc);
    published.btc_ant_num = 0U;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == 0);
    assert(sc.sc_calibration.iqk_initialized && iqk_shots == 12U);
    iqk_shots = 0;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == 0);
    assert(sc.sc_calibration.iqk_recovery_valid && iqk_shots == 0);
    assert(release_count == 2 && !held);
    reset(&sc);
    published.txpower_tracking = true;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == 0);
    assert(published.tm_trigger && sc.sc_calibration.tracking_changed);
    with_thermal.thermal_track = thermal;
    sc.sc_calibration_owner = &with_thermal;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == 0);
    assert(thermal_count == 1 && !published.tm_trigger);
    reset(&sc);
    published.btc_ant_num = 0U;
    revoke_at = 100U;
    assert(rtwn8723be_netbsd_rf_calibration(&sc) == ENXIO);
    assert(mmio == 100U && release_count == 1 && released_error == ENXIO && !held);
    puts("CALIBRATION_NATIVE_OWNER_CHECK_PASS unbound_btc=reject "
        "preflight=no_mmio owner_release=all_paths IQK_recovery=pass "
        "single_ant_skip=pass ownership_revoke=no_access");
    return 0;
}
