/* Reuse the same fake register surface and raw Linux calibration oracle. */
#define main calibration_engine_already_covered_main
#include "calibration_check.c"
#undef main
#include "rtwn8723be_thermal.h"

void test_thermal_oracle(void *, struct rtwn8723be_thermal_state *,
    struct rtwn8723be_calibration_state *, uint8_t);

static void make_case(unsigned int variant, bool channel14,
    struct rtwn8723be_thermal_state *dm,
    struct rtwn8723be_calibration_state *cal,
    struct rtwn8723be_thermal_inputs *input)
{
    uint8_t meter = 24U;
    reset(0);
    memset(dm, 0, sizeof(*dm));
    memset(cal, 0, sizeof(*cal));
    rtwn8723be_thermal_txpower_init(dm);
    dm->cck_inch14 = channel14;
    input->eeprom_meter_valid = true;
    input->eeprom_thermalmeter = 20U;
    input->current_channel = channel14 ? 14U : 1U;
    dm->thermalvalue = dm->thermalvalue_lck = dm->thermalvalue_iqk = 20U;
    cal->iqk_matrix[0] = cal->iqk_matrix[4] = 0x100;
    if (variant == 0U)
        meter = 0U;
    if (variant == 1U)
        dm->txpower_track_control = false;
    if (variant == 2U)
        input->eeprom_thermalmeter = 0xffU;
    if (variant == 3U)
        dm->thermalvalue = 0U;
    if (variant == 5U)
        meter = 32U;
    if (variant == 6U)
        meter = 63U;
    if (variant == 7U) {
        meter = 1U;
        input->eeprom_thermalmeter = 63U;
        dm->swing_idx_cck_base = 2U;
        dm->swing_idx_ofdm_base[0] = 6U;
    }
    if (variant == 8U)
        memset(cal->iqk_matrix, 0, sizeof(cal->iqk_matrix));
    if (variant == 9U)
        cal->iqk_matrix[0] = cal->iqk_matrix[1] = 0x3ff;
    actual.rf[0x42U] = (actual.rf[0x42U] & ~0xfc00U) | ((uint32_t)meter << 10);
    expected = original = actual;
}
static void compare_cache(const struct rtwn8723be_calibration_state *actual_cal,
    const struct rtwn8723be_calibration_state *expected_cal)
{
    assert(memcmp(actual_cal->iqk_matrix, expected_cal->iqk_matrix,
        sizeof(actual_cal->iqk_matrix)) == 0);
    assert(memcmp(actual_cal->recovery, expected_cal->recovery,
        sizeof(actual_cal->recovery)) == 0);
    assert(actual_cal->iqk_initialized == expected_cal->iqk_initialized);
    assert(actual_cal->reg_e94 == expected_cal->reg_e94 &&
        actual_cal->reg_e9c == expected_cal->reg_e9c &&
        actual_cal->reg_eb4 == expected_cal->reg_eb4 &&
        actual_cal->reg_ebc == expected_cal->reg_ebc);
}
int main(void)
{
    struct rtwn8723be_thermal_state dm, reference, before;
    struct rtwn8723be_calibration_state cal, reference_cal;
    struct rtwn8723be_thermal_inputs input;
    unsigned int variant, channel, fault, calls, threshold_calls, lck_calls, i;
    uint8_t map[512] = {0}, meter = 0xaaU;
    bool ignored = true;
    static const uint8_t samples[] = {20, 28, 36, 44, 52, 60, 10, 18, 26, 34};
    map[0xbaU] = 27U;
    assert(rtwn8723be_thermal_meter_parse(map, sizeof(map), true, &meter, &ignored) == 0);
    assert(meter == 27U && !ignored);
    map[0xbaU] = 0xffU;
    assert(rtwn8723be_thermal_meter_parse(map, sizeof(map), true, &meter, &ignored) == 0);
    assert(meter == 0x18U && ignored);
    assert(rtwn8723be_thermal_meter_parse(NULL, 0U, false, &meter, &ignored) == 0);
    assert(meter == 0x18U && ignored);
    meter = 0xaaU;
    ignored = false;
    assert(rtwn8723be_thermal_meter_parse(map, 0xbaU, true, &meter, &ignored) == EINVAL);
    assert(meter == 0xaaU && !ignored);
    for (channel = 0; channel < 2U; channel++) {
        for (variant = 0; variant < 10U; variant++) {
            make_case(variant, channel != 0, &dm, &cal, &input);
            reference = dm;
            reference_cal = cal;
            assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == 0);
            test_thermal_oracle(&expected, &reference, &reference_cal,
                input.eeprom_thermalmeter);
            compare_trace();
            assert(memcmp(&dm, &reference, sizeof(dm)) == 0);
            compare_cache(&cal, &reference_cal);
            assert(!cal.lck_inprogress);
        }
    }
    make_case(4U, false, &dm, &cal, &input);
    reference = dm;
    reference_cal = cal;
    for (i = 0; i < sizeof(samples); i++) {
        actual.rf[0x42U] = expected.rf[0x42U] =
            (actual.rf[0x42U] & ~0xfc00U) | ((uint32_t)samples[i] << 10);
        actual.count = expected.count = 0;
        assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == 0);
        test_thermal_oracle(&expected, &reference, &reference_cal,
            input.eeprom_thermalmeter);
        compare_trace();
        assert(memcmp(&dm, &reference, sizeof(dm)) == 0);
        compare_cache(&cal, &reference_cal);
    }
    make_case(3U, false, &dm, &cal, &input);
    assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == 0);
    calls = actual.calls;
    for (fault = 1U; fault <= calls; fault++) {
        make_case(3U, false, &dm, &cal, &input);
        before = dm;
        actual.fail_at = fault;
        assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == EIO);
        assert(dm.last_error == EIO && dm.last_restore_error == 0);
        dm.last_error = 0;
        assert(memcmp(&dm, &before, sizeof(dm)) == 0);
        compare_rollback();
    }
    make_case(5U, false, &dm, &cal, &input);
    assert(rtwn8723be_calibration_lck(&context, &cal) == 0);
    lck_calls = actual.calls;
    make_case(5U, false, &dm, &cal, &input);
    assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == 0);
    threshold_calls = actual.calls;
    for (fault = 1U; fault <= threshold_calls; fault++) {
        make_case(5U, false, &dm, &cal, &input);
        before = dm;
        actual.fail_at = fault;
        assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == EIO);
        assert(dm.last_error == EIO && dm.last_restore_error == 0);
        dm.last_error = 0;
        assert(memcmp(&dm, &before, sizeof(dm)) == 0);
        assert(!cal.lck_inprogress);
        /* A completed LCK retains the pin's RF changes before later failure. */
        if (fault > 12U + lck_calls)
            test_oracle_lck(&original, false);
        compare_rollback();
    }
    /* A prior IQK restore error is not a restore error for a new RF read. */
    make_case(3U, false, &dm, &cal, &input);
    cal.last_restore_error = EBUSY;
    actual.fail_at = 12U;
    assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == EIO);
    assert(dm.last_restore_error == 0 && cal.last_restore_error == EBUSY);
    make_case(3U, false, &dm, &cal, &input);
    actual.fail_at = 14U;
    actual.fail_again = 15U;
    assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == EIO);
    assert(dm.last_restore_error == EIO);
    make_case(3U, false, &dm, &cal, &input);
    actual.revoke_at = 14U;
    assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == ENXIO);
    assert(actual.calls == 14U && dm.last_restore_error == ENXIO);
    make_case(3U, false, &dm, &cal, &input);
    input.eeprom_meter_valid = false;
    assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == ENXIO);
    assert(actual.calls == 0U);
    input.eeprom_meter_valid = true;
    dm.thermalvalue_avg_index = 4U;
    assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == EINVAL);
    assert(actual.calls == 0U);
    dm.thermalvalue_avg_index = 0U;
    dm.cck_inch14 = true;
    assert(rtwn8723be_thermal_callback(&context, &cal, &dm, &input) == EINVAL);
    assert(actual.calls == 0U);
    printf("THERMAL_DIFFERENTIAL_PASS variants=10 channels=1,14 "
        "rolling_samples=10 fallible_access_points=%u+%u "
        "LCK_IQK_threshold_calls=real EFUSE_meter=pass guards=pass\n",
        calls, threshold_calls);
    return 0;
}
