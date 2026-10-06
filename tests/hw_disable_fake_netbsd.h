#ifndef _RTWN8723BE_NETBSD_H_
#define _RTWN8723BE_NETBSD_H_
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "rtwn8723be_hw_disable_native.h"
#define R23BE_STAGE_STOPPING 50U
struct rtwn8723be_softc {
    bool sc_mapped, sc_core_initialized, sc_hal_started, sc_irq_enabled;
    size_t sc_mapsize;
    struct { bool started, fw_ready, mac_func_enable; unsigned int stage; } sc_linux;
    struct { bool iqk_initialized; uint32_t cache[8]; } sc_calibration;
    struct rtwn8723be_hw_disable_state sc_hw_disable;
    const struct rtwn8723be_hw_disable_owner *sc_hw_disable_owner;
    void *sc_hw_disable_owner_arg;
    uint8_t sc_sw_led0, sc_bcn_ctrl_val;
    bool sc_led_opendrain;
};
uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *, size_t);
void rtwn8723be_write_1(struct rtwn8723be_softc *, size_t, uint8_t);
int rtwn8723be_netbsd_poweroff_adapter(void *);
#endif
