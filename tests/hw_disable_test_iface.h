#ifndef _HW_DISABLE_TEST_IFACE_H_
#define _HW_DISABLE_TEST_IFACE_H_
#include "rtwn8723be_hw_disable.h"
struct disable_event { uint32_t reg; uint8_t kind, value; };
struct disable_backend {
    uint8_t bytes[4096];
    struct disable_event events[128];
    unsigned int events_count, calls, power_calls, fail_at, fail_again, revoke_at;
};
uint8_t disable_raw_read(void *, uint32_t);
void disable_raw_write(void *, uint32_t, uint8_t);
void disable_raw_poweroff(void *);
void disable_oracle(void *, struct rtwn8723be_hw_disable_state *,
    const struct rtwn8723be_hw_disable_inputs *, bool *);
#endif
