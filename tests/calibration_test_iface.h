#ifndef CALIBRATION_TEST_IFACE_H
#define CALIBRATION_TEST_IFACE_H
#include <stdbool.h>
#include <stdint.h>
struct test_oracle_result {
    uint32_t recovery[9];
    int32_t matrix[8], reg[4];
    bool matrix_done;
};
uint32_t test_bb_read_raw(void *, uint32_t, uint32_t);
void test_bb_write_raw(void *, uint32_t, uint32_t, uint32_t);
uint32_t test_rf_read_raw(void *, unsigned int, uint32_t, uint32_t);
void test_rf_write_raw(void *, unsigned int, uint32_t, uint32_t, uint32_t);
uint32_t test_mac_read_raw(void *, uint32_t, unsigned int);
void test_mac_write_raw(void *, uint32_t, unsigned int, uint32_t);
void test_delay_raw(void *, unsigned int);
void test_oracle_iqk(void *, bool, struct test_oracle_result *);
void test_oracle_lck(void *, bool);
#endif
