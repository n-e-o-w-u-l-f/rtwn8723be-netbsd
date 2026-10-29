#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_calibration.h"
#include "calibration_test_iface.h"

struct event { uint32_t kind, reg, mask, value; };
struct backend {
    uint32_t bb[0x1000 / 4], rf[256];
    uint8_t mac[0x1000];
    struct event events[6000];
    unsigned int count, calls, fail_at, fail_again, revoke_at;
    unsigned int trial, shots, variant, thermal_calls, scan_delays;
    bool scanning;
};
static struct backend actual, expected, original;

static unsigned int shift(uint32_t mask)
{
    unsigned int n = 0;
    assert(mask != 0);
    while ((mask & (1U << n)) == 0)
        n++;
    return n;
}
static void event(struct backend *b, uint32_t kind, uint32_t reg,
    uint32_t mask, uint32_t value)
{
    assert(b->count < sizeof(b->events) / sizeof(b->events[0]));
    b->events[b->count++] = (struct event){kind, reg, mask, value};
}
static void measurements(struct backend *b)
{
    unsigned int trial = b->trial == 0 ? 0 : b->trial - 1;
    unsigned int path = b->bb[0x948U / 4U] == 0x280U;
    unsigned int offset = 0;
    uint32_t y = 0, rx_y = 0, fail = 0;
    if (b->variant == 1U)
        fail = 1U << 28; /* Every TX attempt fails, preserving pin fallback. */
    if (b->variant == 2U && b->bb[0xe38U / 4U] == 0x82110000U)
        fail = 1U << 27; /* TX only, RX unavailable. */
    if (b->variant == 3U)
        y = rx_y = 0x3ffU; /* Signed -1 values in odd matrix elements. */
    if (b->variant == 4U)
        offset = trial == 1U ? 20U : 0U; /* Candidate 0 versus trial 2. */
    if (b->variant == 5U)
        offset = trial == 0U ? 20U : 0U; /* Candidate 1 versus trial 2. */
    if (b->variant == 6U)
        offset = trial * (path ? 9U : 11U); /* Composite candidate/fallback. */
    b->bb[0xe94U / 4U] = (0x100U + offset) << 16;
    b->bb[0xe9cU / 4U] = y << 16;
    b->bb[0xea4U / 4U] = 0x100U << 16;
    b->bb[0xeacU / 4U] = (rx_y << 16) | fail;
}
uint32_t test_bb_read_raw(void *arg, uint32_t reg, uint32_t mask)
{
    struct backend *b = arg;
    assert((reg & 3U) == 0 && reg < sizeof(b->bb));
    return (b->bb[reg / 4U] & mask) >> shift(mask);
}
void test_bb_write_raw(void *arg, uint32_t reg, uint32_t mask, uint32_t value)
{
    struct backend *b = arg;
    assert((reg & 3U) == 0 && reg < sizeof(b->bb));
    event(b, 1U, reg, mask, value);
    b->bb[reg / 4U] = (b->bb[reg / 4U] & ~mask) |
        (value << shift(mask));
    if (reg == 0x85cU && value == 0x01c00014U)
        b->trial++;
    if (reg == 0xe48U && value == 0xf8000000U) {
        b->shots++;
        measurements(b);
    }
}
uint32_t test_rf_read_raw(void *arg, unsigned int path, uint32_t reg,
    uint32_t mask)
{
    struct backend *b = arg;
    assert(path == 0U && reg < 256U);
    return (b->rf[reg] & mask) >> shift(mask);
}
void test_rf_write_raw(void *arg, unsigned int path, uint32_t reg,
    uint32_t mask, uint32_t value)
{
    struct backend *b = arg;
    assert(path == 0U && reg < 256U);
    event(b, 2U, reg, mask, value);
    b->rf[reg] = ((b->rf[reg] & ~mask) |
        (value << shift(mask))) & 0xfffffU;
}
uint32_t test_mac_read_raw(void *arg, uint32_t reg, unsigned int width)
{
    struct backend *b = arg;
    uint32_t value = 0;
    unsigned int i;
    assert((width == 1U || width == 4U) && reg + width <= sizeof(b->mac));
    for (i = 0; i < width; i++)
        value |= (uint32_t)b->mac[reg + i] << (i * 8U);
    return value;
}
void test_mac_write_raw(void *arg, uint32_t reg, unsigned int width,
    uint32_t value)
{
    struct backend *b = arg;
    unsigned int i;
    assert((width == 1U || width == 4U) && reg + width <= sizeof(b->mac));
    event(b, 3U, reg, width, width == 1U ? (uint8_t)value : value);
    for (i = 0; i < width; i++)
        b->mac[reg + i] = (uint8_t)(value >> (i * 8U));
}
void test_delay_raw(void *arg, unsigned int usec)
{
    struct backend *b = arg;
    assert(usec == 10000U || usec == 50000U || usec == 50U);
    if (usec == 50U)
        b->scan_delays++;
    event(b, 4U, usec, 0U, 0U);
}
static bool ready(void *arg)
{
    struct backend *b = arg;
    return b->revoke_at == 0 || b->calls < b->revoke_at;
}
static int access_check(struct backend *b)
{
    b->calls++;
    return b->calls == b->fail_at || b->calls == b->fail_again ? EIO : 0;
}
static int bb_read(void *arg, uint32_t r, uint32_t m, uint32_t *v)
{
    int e = access_check(arg);
    if (e == 0)
        *v = test_bb_read_raw(arg, r, m);
    return e;
}
static int bb_write(void *arg, uint32_t r, uint32_t m, uint32_t v)
{
    int e = access_check(arg);
    if (e == 0)
        test_bb_write_raw(arg, r, m, v);
    return e;
}
static int rf_read(void *arg, unsigned int p, uint32_t r, uint32_t m,
    uint32_t *v)
{
    int e = access_check(arg);
    if (e == 0)
        *v = test_rf_read_raw(arg, p, r, m);
    return e;
}
static int rf_write(void *arg, unsigned int p, uint32_t r, uint32_t m,
    uint32_t v)
{
    int e = access_check(arg);
    if (e == 0)
        test_rf_write_raw(arg, p, r, m, v);
    return e;
}
static int mac_read(void *arg, uint32_t r, unsigned int w, uint32_t *v)
{
    int e = access_check(arg);
    if (e == 0)
        *v = test_mac_read_raw(arg, r, w);
    return e;
}
static int mac_write(void *arg, uint32_t r, unsigned int w, uint32_t v)
{
    int e = access_check(arg);
    if (e == 0)
        test_mac_write_raw(arg, r, w, v);
    return e;
}
static int delay_us(void *arg, unsigned int us)
{
    int e = access_check(arg);
    if (e == 0)
        test_delay_raw(arg, us);
    return e;
}
static int scan_active(void *arg, bool *scan)
{
    struct backend *b = arg;
    int e = access_check(arg);
    if (e == 0)
        *scan = b->scanning;
    return e;
}
static int thermal(void *arg, const struct rtwn8723be_calibration_context *ctx,
    struct rtwn8723be_calibration_state *s)
{
    struct backend *b = arg;
    (void)s;
    assert(ctx->arg == arg && ctx->io->ready(arg));
    b->thermal_calls++;
    return 0;
}
static const struct rtwn8723be_calibration_io io = {
    ready, bb_read, bb_write, rf_read, rf_write, mac_read, mac_write,
    delay_us, scan_active, NULL
};
static const struct rtwn8723be_calibration_context context = {&io, &actual};

static void reset(unsigned int variant)
{
    unsigned int i;
    memset(&actual, 0, sizeof(actual));
    for (i = 0; i < sizeof(actual.bb) / sizeof(actual.bb[0]); i++)
        actual.bb[i] = 0xa0000000U + i;
    for (i = 0; i < 256U; i++)
        actual.rf[i] = 0x90000U + i;
    for (i = 0; i < sizeof(actual.mac); i++)
        actual.mac[i] = (uint8_t)(i ^ 0x5aU);
    actual.bb[0xe28U / 4U] = 0;
    actual.bb[0xc80U / 4U] = actual.bb[0xc88U / 4U] = 0x40000000U;
    actual.variant = variant;
    expected = original = actual;
}
static void compare_trace(void)
{
    unsigned int i;
    assert(actual.count == expected.count);
    for (i = 0; i < actual.count; i++) {
        if (memcmp(&actual.events[i], &expected.events[i],
                sizeof(actual.events[i])) != 0) {
            fprintf(stderr, "trace mismatch at %u: actual %x %x %x %x, "
                "Linux %x %x %x %x\n", i,
                actual.events[i].kind, actual.events[i].reg,
                actual.events[i].mask, actual.events[i].value,
                expected.events[i].kind, expected.events[i].reg,
                expected.events[i].mask, expected.events[i].value);
            assert(false);
        }
    }
}
static void compare_rollback(void)
{
    unsigned int i;
    for (i = 0; i < sizeof(actual.bb) / sizeof(actual.bb[0]); i++) {
        /* Read-only measurement results can change after a one-shot. */
        if (i == 0xe94U / 4U || i == 0xe9cU / 4U ||
            i == 0xea4U / 4U || i == 0xeacU / 4U)
            continue;
        assert(actual.bb[i] == original.bb[i]);
    }
    assert(memcmp(actual.rf, original.rf, sizeof(actual.rf)) == 0);
    assert(memcmp(actual.mac, original.mac, sizeof(actual.mac)) == 0);
}
int main(void)
{
    struct rtwn8723be_calibration_state state;
    struct test_oracle_result oracle;
    struct rtwn8723be_calibration_inputs input = {
        .rf_state_valid = true, .rf_on = true,
        .btc_bound = true, .btc_initialized = true, .btc_ant_num = 0U,
        .dm_state_valid = true, .current_channel = 1U
    };
    unsigned int variant, fault, calls, recovery_calls, lck_calls, count;
    for (variant = 0; variant < 7U; variant++) {
        reset(variant);
        memset(&state, 0, sizeof(state));
        memset(&oracle, 0, sizeof(oracle));
        assert(rtwn8723be_calibration_iqk(&context, &state, false) == 0);
        test_oracle_iqk(&expected, false, &oracle);
        compare_trace();
        assert(memcmp(state.recovery, oracle.recovery,
            sizeof(state.recovery)) == 0);
        assert(memcmp(state.iqk_matrix, oracle.matrix,
            sizeof(state.iqk_matrix)) == 0);
        assert(state.iqk_matrix_done == oracle.matrix_done);
        assert(state.reg_e94 == oracle.reg[0] && state.reg_e9c == oracle.reg[1]);
        assert(state.reg_eb4 == oracle.reg[2] && state.reg_ebc == oracle.reg[3]);
        assert(state.iqk_initialized && state.iqk_recovery_valid &&
            !state.lck_inprogress);
        actual.count = expected.count = 0;
        assert(rtwn8723be_calibration_iqk(&context, &state, true) == 0);
        test_oracle_iqk(&expected, true, &oracle);
        compare_trace();
        assert(actual.count == 9U);
    }
    reset(0);
    memset(&state, 0, sizeof(state));
    assert(rtwn8723be_calibration_iqk(&context, &state, false) == 0);
    calls = actual.calls;
    for (fault = 1; fault <= calls; fault++) {
        reset(0);
        memset(&state, 0, sizeof(state));
        actual.fail_at = fault;
        assert(rtwn8723be_calibration_iqk(&context, &state, false) == EIO);
        assert(!state.lck_inprogress && !state.iqk_initialized &&
            state.last_restore_error == 0);
        compare_rollback();
    }
    reset(0);
    memset(&state, 0, sizeof(state));
    state.iqk_initialized = state.iqk_recovery_valid = true;
    memset(state.recovery, 0x12, sizeof(state.recovery));
    assert(rtwn8723be_calibration_iqk(&context, &state, true) == 0);
    recovery_calls = actual.calls;
    for (fault = 1; fault <= recovery_calls; fault++) {
        reset(0);
        state.iqk_initialized = state.iqk_recovery_valid = true;
        actual.fail_at = fault;
        assert(rtwn8723be_calibration_iqk(&context, &state, true) == EIO);
        assert(!state.lck_inprogress);
        compare_rollback();
    }
    for (variant = 0; variant < 4U; variant++) {
        reset(0);
        actual.mac[0xd03U] = expected.mac[0xd03U] =
            (variant & 1U) != 0 ? 0x75U : 0x05U;
        actual.scanning = (variant & 2U) != 0;
        memset(&state, 0, sizeof(state));
        assert(rtwn8723be_calibration_lck(&context, &state) == 0);
        test_oracle_lck(&expected, actual.scanning);
        compare_trace();
        assert(actual.scan_delays == (actual.scanning ? 40U : 0U));
        assert(!state.lck_inprogress);
    }
    reset(0);
    memset(&state, 0, sizeof(state));
    assert(rtwn8723be_calibration_lck(&context, &state) == 0);
    lck_calls = actual.calls;
    for (fault = 1; fault <= lck_calls; fault++) {
        reset(0);
        memset(&state, 0, sizeof(state));
        actual.fail_at = fault;
        assert(rtwn8723be_calibration_lck(&context, &state) == EIO);
        assert(!state.lck_inprogress && state.last_restore_error == 0);
        compare_rollback();
    }
    reset(0);
    memset(&state, 0, sizeof(state));
    input.btc_initialized = false;
    assert(rtwn8723be_calibration_run(&context, &state, &input) == ENXIO);
    assert(actual.calls == 0 && actual.count == 0);
    input.btc_initialized = true;
    input.btc_bound = false;
    assert(rtwn8723be_calibration_run(&context, &state, &input) == ENXIO);
    input.btc_bound = true;
    input.dm_state_valid = false;
    assert(rtwn8723be_calibration_run(&context, &state, &input) == ENXIO);
    input.dm_state_valid = true;
    input.txpower_tracking = input.tm_trigger = true;
    assert(rtwn8723be_calibration_run(&context, &state, &input) == ENOTSUP);
    assert(actual.calls == 0 && actual.count == 0);
    input.tm_trigger = false;
    input.btc_ant_num = 1U;
    assert(rtwn8723be_calibration_run(&context, &state, &input) == 0);
    assert(actual.shots == 0 && state.tm_trigger && state.tracking_changed);
    assert(actual.events[0].kind == 1U && actual.events[0].reg == 0x92cU);
    assert(actual.events[1].kind == 2U && actual.events[1].reg == 0x42U);
    reset(0);
    input.tm_trigger = true;
    {
        struct rtwn8723be_calibration_io with_thermal = io;
        const struct rtwn8723be_calibration_context ctx = {&with_thermal, &actual};
        with_thermal.thermal_track = thermal;
        assert(rtwn8723be_calibration_run(&ctx, &state, &input) == 0);
        assert(actual.thermal_calls == 1U && !state.tm_trigger);
    }
    reset(0);
    input.rf_on = false;
    assert(rtwn8723be_calibration_run(&context, &state, &input) == 0);
    assert(actual.calls == 0 && actual.count == 0 && !state.tracking_changed);
    input.rf_on = true;
    input.txpower_tracking = input.tm_trigger = false;
    reset(0);
    memset(&state, 0, sizeof(state));
    actual.fail_at = 100U;
    actual.fail_again = 101U;
    assert(rtwn8723be_calibration_iqk(&context, &state, false) == EIO);
    assert(state.last_restore_error == EIO && !state.iqk_recovery_valid);
    reset(0);
    memset(&state, 0, sizeof(state));
    actual.revoke_at = 100U;
    assert(rtwn8723be_calibration_iqk(&context, &state, false) == ENXIO);
    count = actual.calls;
    assert(count == 100U && state.last_restore_error == ENXIO &&
        !state.lck_inprogress);
    assert(rtwn8723be_calibration_iqk(NULL, &state, false) == EINVAL);
    state.lck_inprogress = true;
    assert(rtwn8723be_calibration_iqk(&context, &state, false) == EBUSY);
    assert(rtwn8723be_calibration_lck(&context, &state) == EBUSY);
    printf("CALIBRATION_DIFFERENTIAL_PASS IQK_variants=7 recovery=7 "
        "LCK_variants=4 fault_points=%u+%u+%u owner_guards=pass "
        "restore_errors=pass\n", calls, recovery_calls, lck_calls);
    return 0;
}
