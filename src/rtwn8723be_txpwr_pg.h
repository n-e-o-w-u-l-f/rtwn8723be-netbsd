/* SPDX-License-Identifier: GPL-2.0
 * Linux rtl8723be/phy.c PHY-PG absolute-to-relative TX power port.
 * Reference: fd179f8a05be3ccae366b9b96e176b51fbe54aab.
 * Pure staging/transform layer, not a hardware writer or RF calibrator.
 */
#ifndef _RTWN8723BE_TXPWR_PG_H_
#define _RTWN8723BE_TXPWR_PG_H_
#include <sys/types.h>
#include <stdint.h>
#include <stdbool.h>
#include "rtwn8723be_phy_exec.h"

#define RTWN8723BE_PG_BANDS 2U
#define RTWN8723BE_PG_PATHS 4U
#define RTWN8723BE_PG_TXNUM 4U
#define RTWN8723BE_PG_SECTIONS 12U
#define RTWN8723BE_PG_BASE_SECTIONS 4U

struct rtwn8723be_txpwr_pg_state {
    /* Mirrors Linux rtl_phy.tx_power_by_rate_offset[band][path][txnum][section]. */
    uint32_t offset[RTWN8723BE_PG_BANDS][RTWN8723BE_PG_PATHS]
                   [RTWN8723BE_PG_TXNUM][RTWN8723BE_PG_SECTIONS];
    /* Mirrors Linux txpwr_by_rate_base_24g[path][txnum][CCK/OFDM/MCS0/MCS8]. */
    uint8_t base24[RTWN8723BE_PG_PATHS][RTWN8723BE_PG_TXNUM]
                  [RTWN8723BE_PG_BASE_SECTIONS];
};

void rtwn8723be_txpwr_pg_reset(struct rtwn8723be_txpwr_pg_state *);
int rtwn8723be_txpwr_pg_store(void *, const struct rtwn8723be_pg_entry *);
void rtwn8723be_txpwr_pg_convert(struct rtwn8723be_txpwr_pg_state *);
#endif /* _RTWN8723BE_TXPWR_PG_H_ */
