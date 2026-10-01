/* SPDX-License-Identifier: GPL-2.0
 * Frozen Linux rtl8723be/phy.c table interpreter -> portable NetBSD C.
 * Hardware writes and Linux's table-specific delay tokens are deliberately
 * delegated to the platform writer.  Never MMIO-write a Radio-A condition.
 */
#include <sys/types.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>

#include "rtwn8723be_phy_tables.h"
#include "rtwn8723be_phy_exec.h"

bool
rtwn8723be_phy_check_positive(const struct rtwn8723be_phy_identity *id,
    uint32_t condition1, uint32_t condition2)
{
    uint8_t board;
    uint32_t driver1, driver2, mask = 0;

    if (id == NULL)
        return false;

    /* Same board-bit rearrangement as _rtl8723be_check_positive(). */
    board = ((id->board_type >> 4) & 1U) |
        (((id->board_type >> 3) & 1U) << 1) |
        (((id->board_type >> 7) & 1U) << 2) |
        (((id->board_type >> 6) & 1U) << 3) |
        (((id->board_type >> 2) & 1U) << 4);

    driver1 = ((uint32_t)id->cut_version << 24) |
        (4U << 16) | ((uint32_t)id->package_type << 12) |
        ((id->pci_interface ? 1U : 2U) << 8) | board;
    driver2 = (uint32_t)id->type_glna |
        ((uint32_t)id->type_gpa << 8) |
        ((uint32_t)id->type_alna << 16) |
        ((uint32_t)id->type_apa << 24);

    /* Package/cut are value comparisons, not bit-subset comparisons. */
    if ((condition1 & 0x0000f000U) != 0 &&
        (condition1 & 0x0000f000U) != (driver1 & 0x0000f000U))
        return false;
    if ((condition1 & 0x0f000000U) != 0 &&
        (condition1 & 0x0f000000U) != (driver1 & 0x0f000000U))
        return false;

    condition1 &= 0x00ff0fffU;
    driver1 &= 0x00ff0fffU;
    if ((condition1 & driver1) != condition1)
        return false;

    if ((condition1 & 0x0fU) == 0)
        return true;
    if ((condition1 & 1U) != 0)
        mask |= 0x000000ffU;
    if ((condition1 & 2U) != 0)
        mask |= 0x0000ff00U;
    if ((condition1 & 4U) != 0)
        mask |= 0x00ff0000U;
    if ((condition1 & 8U) != 0)
        mask |= 0xff000000U;
    return (condition2 & mask) == (driver2 & mask);
}

/*
 * Linux rtl8723be_phy_config_with_headerfile() uses a non-nesting IF /
 * ELSE-IF / ELSE / ENDIF state machine.  BIT30 negative-condition records
 * are consumed but have no state-changing behavior in the frozen source.
 */
static int
rtwn8723be_phy_run_pairs(
    const struct rtwn8723be_init_pair *table, size_t count,
    const struct rtwn8723be_phy_identity *id, void *ctx,
    rtwn8723be_phy_write_fn apply)
{
    bool matched = true, skipped = false;
    size_t i;
    int error;

    if (table == NULL || apply == NULL)
        return EINVAL;
    for (i = 0; i < count; i++) {
        const uint32_t reg = table[i].reg;
        const uint32_t value = table[i].value;
        unsigned int cond;

        if ((reg & 0xc0000000U) != 0) {
            if ((reg & 0x80000000U) != 0) {
                cond = (reg >> 28) & 3U;
                if (cond == 3) {
                    matched = true;
                    skipped = false;
                } else if (cond == 2) {
                    matched = !skipped;
                } else if (skipped) {
                    matched = false;
                } else if (rtwn8723be_phy_check_positive(id,
                    reg, value)) {
                    matched = true;
                    skipped = true;
                } else {
                    matched = false;
                    skipped = false;
                }
            }
            /* BIT30 alone: no-op in the pinned Linux implementation. */
            continue;
        }
        if (matched) {
            error = apply(ctx, reg, value);
            if (error != 0)
                return error;
        }
    }
    return 0;
}

int
rtwn8723be_phy_run_bb(void *ctx, rtwn8723be_phy_write_fn apply)
{
    return rtwn8723be_phy_run_pairs(rtwn8723be_phy_table,
        RTWN8723BE_PHY_TABLE_COUNT, NULL, ctx, apply);
}

int
rtwn8723be_phy_run_agc(void *ctx, rtwn8723be_phy_write_fn apply)
{
    return rtwn8723be_phy_run_pairs(rtwn8723be_agc_table,
        RTWN8723BE_AGC_TABLE_COUNT, NULL, ctx, apply);
}

int
rtwn8723be_phy_run_radio_a(const struct rtwn8723be_phy_identity *id,
    void *ctx, rtwn8723be_phy_write_fn apply)
{
    if (id == NULL)
        return EINVAL;
    return rtwn8723be_phy_run_pairs(rtwn8723be_radio_a_table,
        RTWN8723BE_RADIO_A_TABLE_COUNT, id, ctx, apply);
}

int
rtwn8723be_phy_run_pg(void *ctx, rtwn8723be_phy_pg_fn store)
{
    size_t i;
    int error;

    if (store == NULL)
        return EINVAL;
    for (i = 0; i < RTWN8723BE_PG_TABLE_COUNT; i++) {
        const struct rtwn8723be_pg_entry *p = &rtwn8723be_pg_table[i];

        if (p->band >= 0xcdcdcdcdU)
            continue;
        error = store(ctx, p);
        if (error != 0)
            return error;
    }
    return 0;
}
