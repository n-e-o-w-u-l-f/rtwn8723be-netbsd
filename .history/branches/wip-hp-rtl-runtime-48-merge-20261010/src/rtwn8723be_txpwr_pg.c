/* SPDX-License-Identifier: GPL-2.0
 * Frozen Linux rtl8723be/phy.c:_rtl8723be_store_tx_power_by_rate(),
 * _rtl8723be_phy_store_txpower_by_rate_base() and
 * _rtl8723be_phy_convert_txpower_dbm_to_relative_value().
 *
 * The source's section-index selection, BCD decoding and absolute-value
 * differences are preserved. Linux converts RF path A only, although it
 * extracts base values for both RF paths A and B. No MMIO occurs here.
 */
#include "rtwn8723be_os_compat.h"
#include "rtwn8723be_txpwr_pg.h"

void
rtwn8723be_txpwr_pg_reset(struct rtwn8723be_txpwr_pg_state *s)
{
    if (s != NULL)
        *s = (struct rtwn8723be_txpwr_pg_state){0};
}

/* Frozen Linux _rtl8723be_get_rate_section_index() and reg.h names. */
static unsigned int
rtwn8723be_pg_section(uint32_t reg)
{
    switch (reg) {
    case 0xe00: case 0x830: return 0; /* RATE18_06 */
    case 0xe04: case 0x834: return 1; /* RATE54_24 */
    case 0xe08: case 0x838: return 2; /* CCK1_MCS32 */
    case 0x86c:             return 3; /* B_CCK11_A_CCK2_11 */
    case 0xe10: case 0x83c: return 4; /* MCS03_MCS00 */
    case 0xe14: case 0x848: return 5; /* MCS07_MCS04 */
    case 0xe18: case 0x84c: return 6; /* MCS11_MCS08 */
    case 0xe1c: case 0x868: return 7; /* MCS15_MCS12 */
    default:
        reg &= 0xfff;
        if (reg >= 0xc20 && reg <= 0xc4c)
            return (reg - 0xc20) / 4;
        if (reg >= 0xe20 && reg <= 0xe4c)
            return (reg - 0xe20) / 4;
        return 0; /* Linux's default section index. */
    }
}

int
rtwn8723be_txpwr_pg_store(void *arg, const struct rtwn8723be_pg_entry *p)
{
    struct rtwn8723be_txpwr_pg_state *s = arg;
    unsigned int section;

    if (s == NULL || p == NULL)
        return EINVAL;
    /* The table runner drops Linux's 0xcdcdcdcd sentinel before callback. */
    if (p->band >= RTWN8723BE_PG_BANDS ||
        p->path >= RTWN8723BE_PG_PATHS ||
        p->txnum >= RTWN8723BE_PG_TXNUM)
        return EINVAL;
    section = rtwn8723be_pg_section(p->reg);
    if (section >= RTWN8723BE_PG_SECTIONS)
        return EINVAL;
    /* Linux stores the whole data word; mask is not applied here. */
    s->offset[p->band][p->path][p->txnum][section] = p->value;
    return 0;
}

static uint8_t
rtwn8723be_pg_bcd(uint8_t v)
{
    /* Match Linux: no extra validation/clamping of the BCD source. */
    return (uint8_t)(((v >> 4) * 10U) + (v & 0x0fU));
}

static uint8_t
rtwn8723be_pg_msb_base(uint32_t v)
{
    return rtwn8723be_pg_bcd((uint8_t)(v >> 24));
}

static uint32_t
rtwn8723be_pg_to_relative(uint32_t data, unsigned int start,
                           unsigned int end, uint8_t base)
{
    uint32_t out = 0;
    int i;

    for (i = 3; i >= 0; --i) {
        uint8_t value = (uint8_t)(data >> (i * 8));
        if ((unsigned int)i >= start && (unsigned int)i <= end) {
            value = rtwn8723be_pg_bcd(value);
            value = (value > base) ? (uint8_t)(value - base) :
                                     (uint8_t)(base - value);
        }
        out = (out << 8) | value;
    }
    return out;
}

void
rtwn8723be_txpwr_pg_convert(struct rtwn8723be_txpwr_pg_state *s)
{
    uint32_t (*off)[RTWN8723BE_PG_TXNUM][RTWN8723BE_PG_SECTIONS];
    uint8_t base;
    unsigned int path;

    if (s == NULL)
        return;
    off = s->offset[0]; /* BAND_ON_2_4G */

    /* Linux derives bases for path A and B before converting any offsets. */
    for (path = 0; path <= 1; ++path) {
        uint8_t cck = (path == 0) ? (uint8_t)(off[path][0][3] >> 24) :
                                    (uint8_t)off[path][0][3];
        s->base24[path][0][0] = rtwn8723be_pg_bcd(cck);
        s->base24[path][0][1] = rtwn8723be_pg_msb_base(off[path][0][1]);
        s->base24[path][0][2] = rtwn8723be_pg_msb_base(off[path][0][5]);
        s->base24[path][1][3] = rtwn8723be_pg_msb_base(off[path][1][7]);
    }

    /* Linux converts RF90_PATH_A only; path B remains unmodified. */
    base = s->base24[0][0][0]; /* CCK, RF_1TX */
    off[0][0][2] = rtwn8723be_pg_to_relative(off[0][0][2], 1, 1, base);
    off[0][0][3] = rtwn8723be_pg_to_relative(off[0][0][3], 1, 3, base);

    base = s->base24[0][0][1]; /* OFDM, RF_1TX */
    off[0][0][0] = rtwn8723be_pg_to_relative(off[0][0][0], 0, 3, base);
    off[0][0][1] = rtwn8723be_pg_to_relative(off[0][0][1], 0, 3, base);

    base = s->base24[0][0][2]; /* HT_MCS0_MCS7, RF_1TX */
    off[0][0][4] = rtwn8723be_pg_to_relative(off[0][0][4], 0, 3, base);
    off[0][0][5] = rtwn8723be_pg_to_relative(off[0][0][5], 0, 3, base);

    base = s->base24[0][1][3]; /* HT_MCS8_MCS15, RF_2TX */
    off[0][1][6] = rtwn8723be_pg_to_relative(off[0][1][6], 0, 3, base);
    off[0][1][7] = rtwn8723be_pg_to_relative(off[0][1][7], 0, 3, base);
}
