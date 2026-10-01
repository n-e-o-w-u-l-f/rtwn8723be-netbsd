/* SPDX-License-Identifier: GPL-2.0
 * Linux RTL8723BE PHY table interpreter translated for NetBSD.
 * Frozen Linux reference: fd179f8a05be3ccae366b9b96e176b51fbe54aab.
 */
#ifndef _RTWN8723BE_PHY_EXEC_H_
#define _RTWN8723BE_PHY_EXEC_H_

#include <sys/types.h>
#include <stdint.h>

/* Inputs to rtl8723be/phy.c:_rtl8723be_check_positive(). */
struct rtwn8723be_phy_identity {
    uint8_t cut_version;
    uint8_t package_type;
    uint8_t board_type;
    uint8_t type_glna;
    uint8_t type_gpa;
    uint8_t type_alna;
    uint8_t type_apa;
    bool pci_interface;
};

struct rtwn8723be_pg_entry;
typedef int (*rtwn8723be_phy_write_fn)(void *, uint32_t, uint32_t);
typedef int (*rtwn8723be_phy_pg_fn)(void *,
    const struct rtwn8723be_pg_entry *);

bool rtwn8723be_phy_check_positive(const struct rtwn8723be_phy_identity *,
    uint32_t, uint32_t);
int rtwn8723be_phy_run_bb(void *, rtwn8723be_phy_write_fn);
int rtwn8723be_phy_run_agc(void *, rtwn8723be_phy_write_fn);
int rtwn8723be_phy_run_radio_a(const struct rtwn8723be_phy_identity *,
    void *, rtwn8723be_phy_write_fn);
int rtwn8723be_phy_run_pg(void *, rtwn8723be_phy_pg_fn);

#endif /* _RTWN8723BE_PHY_EXEC_H_ */
