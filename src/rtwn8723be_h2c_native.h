/* SPDX-License-Identifier: GPL-2.0 */
/* NetBSD bus_space/adaptive-mutex binding for the portable RTL8723BE H2C. */
#ifndef _RTWN8723BE_H2C_NATIVE_H_
#define _RTWN8723BE_H2C_NATIVE_H_

#include <sys/mutex.h>
#include "rtwn8723be_h2c.h"

struct rtwn8723be_softc;
struct rtwn8723be_h2c_native {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_h2c_state state;
    kmutex_t lock;
    uint64_t firmware_generation; /* increments on a fresh MCU ready handshake */
    bool initialized;
};

/* The owner must stop TX, IRQ work and firmware users before fini/reset. */
int rtwn8723be_h2c_native_init(struct rtwn8723be_softc *);
void rtwn8723be_h2c_native_fini(struct rtwn8723be_softc *);
void rtwn8723be_h2c_native_reset(struct rtwn8723be_softc *);
/* Only after the actual MCUFWDL checksum and WINTINI_RDY handshake. */
int rtwn8723be_h2c_native_fw_ready(struct rtwn8723be_softc *);
int rtwn8723be_h2c_native_send(struct rtwn8723be_softc *,
    uint8_t, const uint8_t *, size_t);
int rtwn8723be_h2c_native_media_status(struct rtwn8723be_softc *, bool);
#endif
