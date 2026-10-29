#ifndef _RTWN8723BE_NETBSD_H_
#define _RTWN8723BE_NETBSD_H_
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "rtwn8723be_calibration_native.h"
#define R23BE_STAGE_RF_CALIBRATION 37U
struct rtwn8723be_softc {
    bool sc_mapped, sc_core_initialized, sc_bb_valid, sc_rf_chnlval_valid;
    bool sc_phy_identity_valid, sc_rf_path_count_valid, sc_irq_enabled;
    bool sc_btcoexist;
    unsigned int sc_rf_path_count;
    size_t sc_mapsize;
    struct { bool pci_interface; } sc_phy_identity;
    struct { bool fw_ready, being_init_adapter, started; unsigned int stage; } sc_linux;
    struct rtwn8723be_calibration_state sc_calibration;
    const struct rtwn8723be_calibration_owner *sc_calibration_owner;
    void *sc_calibration_owner_arg;
};
uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *, size_t);
uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *, size_t);
void rtwn8723be_write_1(struct rtwn8723be_softc *, size_t, uint8_t);
void rtwn8723be_write_4(struct rtwn8723be_softc *, size_t, uint32_t);
uint32_t rtwn8723be_netbsd_get_bbreg(struct rtwn8723be_softc *, size_t, uint32_t);
void rtwn8723be_netbsd_set_bbreg(struct rtwn8723be_softc *, size_t, uint32_t, uint32_t);
#endif
