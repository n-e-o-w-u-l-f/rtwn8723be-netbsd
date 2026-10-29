#include "hw_disable_test_iface.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static struct disable_backend actual, expected;
uint8_t disable_raw_read(void *arg, uint32_t reg)
{
    struct disable_backend *b = arg;
    assert(reg < sizeof(b->bytes) && b->events_count < 128U);
    b->events[b->events_count++] = (struct disable_event){reg, 1U, b->bytes[reg]};
    return b->bytes[reg];
}
void disable_raw_write(void *arg, uint32_t reg, uint8_t value)
{
    struct disable_backend *b = arg;
    assert(reg < sizeof(b->bytes) && b->events_count < 128U);
    b->bytes[reg] = value;
    b->events[b->events_count++] = (struct disable_event){reg, 2U, value};
}
void disable_raw_poweroff(void *arg)
{
    struct disable_backend *b = arg;
    assert(b->events_count < 128U);
    b->power_calls++;
    b->events[b->events_count++] = (struct disable_event){0U, 3U, 0U};
}
static bool ready(void *arg)
{
    struct disable_backend *b = arg;
    return b->revoke_at == 0 || b->calls < b->revoke_at;
}
static int access_check(struct disable_backend *b)
{
    b->calls++;
    return b->calls == b->fail_at || b->calls == b->fail_again ? EIO : 0;
}
static int read_1(void *arg, uint32_t reg, uint8_t *value)
{
    int error = access_check(arg);
    if (error == 0)
        *value = disable_raw_read(arg, reg);
    return error;
}
static int write_1(void *arg, uint32_t reg, uint8_t value)
{
    int error = access_check(arg);
    if (error == 0)
        disable_raw_write(arg, reg, value);
    return error;
}
static int poweroff(void *arg)
{
    int error = access_check(arg);
    disable_raw_poweroff(arg);
    return error;
}
static const struct rtwn8723be_hw_disable_io io = {ready, read_1, write_1, poweroff};
static void reset(struct rtwn8723be_hw_disable_state *state,
    struct rtwn8723be_hw_disable_inputs *input)
{
    unsigned int i;
    memset(&actual, 0, sizeof(actual));
    memset(state, 0, sizeof(*state));
    memset(input, 0, sizeof(*input));
    for (i = 0; i < sizeof(actual.bytes); i++)
        actual.bytes[i] = (uint8_t)(i ^ 0xadU);
    state->bcn_ctrl = actual.bytes[0x550U] = 0x1dU;
    state->cur_ps_level = 0x100U;
    state->mac_link_state = 2U;
    input->state_valid = input->rf_idle = input->driver_is_goingto_unload = true;
    input->led_pin = 1U;
    input->led_opendrain = true;
}
int main(void)
{
    struct rtwn8723be_hw_disable_state state, reference, before;
    struct rtwn8723be_hw_disable_inputs input;
    unsigned int reason, unload, pin, drain, variant, fault, calls, cases = 0;
    static const uint32_t reasons[] = {0U, UINT32_C(1) << 28,
        UINT32_C(1) << 29, (UINT32_C(1) << 29) + 1U, UINT32_C(1) << 31};
    bool iqk;
    for (reason = 0; reason < 5U; reason++)
    for (unload = 0; unload < 2U; unload++)
    for (pin = 0; pin < 3U; pin++)
    for (drain = 0; drain < 2U; drain++)
    for (variant = 0; variant < 2U; variant++) {
        reset(&state, &input);
        input.rfoff_reason = reasons[reason];
        input.driver_is_goingto_unload = unload != 0;
        input.led_pin = (uint8_t)pin;
        input.led_opendrain = drain != 0;
        state.bcn_ctrl = variant == 0 ? 0x1dU : 0xffU;
        reference = state;
        expected = actual;
        iqk = variant != 0;
        assert(rtwn8723be_hw_disable(&io, &actual, &state, &input) == 0);
        disable_oracle(&expected, &reference, &input, &iqk);
        assert(iqk == (variant != 0));
        assert(actual.events_count == expected.events_count);
        assert(memcmp(actual.events, expected.events,
            actual.events_count * sizeof(actual.events[0])) == 0);
        assert(memcmp(actual.bytes, expected.bytes, sizeof(actual.bytes)) == 0);
        assert(memcmp(&state, &reference, sizeof(state)) == 0);
        cases++;
    }
    reset(&state, &input);
    assert(rtwn8723be_hw_disable(&io, &actual, &state, &input) == 0);
    calls = actual.calls;
    for (fault = 1U; fault <= calls; fault++) {
        reset(&state, &input);
        actual.fail_at = fault;
        assert(rtwn8723be_hw_disable(&io, &actual, &state, &input) == EIO);
        assert(state.last_error == EIO && state.poweroff_attempted);
        assert(state.mac_link_state == 0U && (state.cur_ps_level & 8U) != 0);
        assert(actual.power_calls == 1U);
        assert(state.powered_off == (fault != calls));
        assert(state.poweroff_error == (fault == calls ? EIO : 0));
    }
    reset(&state, &input);
    actual.fail_at = 1U;
    actual.fail_again = 6U; /* failed media read, four LED-off accesses, poweroff */
    assert(rtwn8723be_hw_disable(&io, &actual, &state, &input) == EIO);
    assert(state.poweroff_error == EIO && !state.powered_off);
    for (fault = 1U; fault <= calls; fault++) {
        reset(&state, &input);
        actual.revoke_at = fault;
        if (fault < calls) {
            assert(rtwn8723be_hw_disable(&io, &actual, &state, &input) == ENXIO);
            assert(actual.calls == fault && state.last_error == ENXIO);
            assert(!state.poweroff_attempted && actual.power_calls == 0);
        } else {
            /* Revocation after the final completed poweroff needs no I/O. */
            assert(rtwn8723be_hw_disable(&io, &actual, &state, &input) == 0);
            assert(actual.calls == fault && state.powered_off);
        }
    }
    reset(&state, &input);
    before = state;
    input.state_valid = false;
    assert(rtwn8723be_hw_disable(&io, &actual, &state, &input) == ENXIO);
    assert(actual.calls == 0 && memcmp(&state, &before, sizeof(state)) == 0);
    input.state_valid = true;
    input.rf_idle = false;
    assert(rtwn8723be_hw_disable(&io, &actual, &state, &input) == EBUSY);
    assert(actual.calls == 0);
    input.rf_idle = true;
    input.led_pin = 3U;
    assert(rtwn8723be_hw_disable(&io, &actual, &state, &input) == EINVAL);
    assert(actual.calls == 0);
    printf("HW_DISABLE_DIFFERENTIAL_PASS cases=%u access_failures=%u "
        "revocations=%u poweroff_partial=pass LED_NO_LINK=on IQK_preserved=pin\n",
        cases, calls, calls);
    return 0;
}
