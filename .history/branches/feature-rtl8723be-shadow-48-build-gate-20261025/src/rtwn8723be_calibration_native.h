/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_CALIBRATION_NATIVE_H_
#define _RTWN8723BE_CALIBRATION_NATIVE_H_
#include "rtwn8723be_calibration.h"
struct rtwn8723be_softc;

/*
 * A real RF/BTC/DM lifecycle owner must publish this binding after its
 * context initialization. EEPROM BT presence/antenna flags do not do so.
 * Acquire excludes detach, power-off, RF/channel changes and parallel
 * calibration; the exclusion must support the calibration delay periods.
 * ready remains true until release, unless ownership/power is revoked.
 * release ALWAYS releases, including an engine failure, and commits a
 * tracking_changed meter flag to the actual DM context if set. A later
 * LCK failure must not forget a successfully triggered thermal meter.
 */
struct rtwn8723be_calibration_owner {
    int (*acquire)(void *, struct rtwn8723be_softc *,
        struct rtwn8723be_calibration_inputs *);
    bool (*ready)(void *, struct rtwn8723be_softc *);
    int (*scan_active)(void *, struct rtwn8723be_softc *, bool *);
    int (*thermal_track)(void *, struct rtwn8723be_softc *,
        const struct rtwn8723be_calibration_context *,
        struct rtwn8723be_calibration_state *);
    void (*release)(void *, struct rtwn8723be_softc *,
        const struct rtwn8723be_calibration_state *, int);
};

int rtwn8723be_netbsd_rf_calibration(void *);
#endif
