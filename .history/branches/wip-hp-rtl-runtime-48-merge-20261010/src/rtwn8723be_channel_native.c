/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Executable RTL8723BE runtime channel/TXpower binding derived from Linux
 * fd179f8a05be3ccae366b9b96e176b51fbe54aab rtl8723be/{hw,phy,rf}.c,
 * core.c and wifi.h. Callback errors add atomic publication/quarantine;
 * register order, masks, EEPROM strides and power arithmetic are source.
 *
 * sw_chnl_callback() is subtle: a zero-delay step continues its do loop.
 * It therefore performs TXpower, then RF_CHNLBW (delay=10), before its
 * unconditional break and sw_chnl()'s inprogress reset. We reproduce this
 * actual call path; no asynchronous work item or extra RF write is added.
 */
#include "rtwn8723be_channel_native.h"

#define CH_RF_MASK 0x000fffffU
#define CH_RF_CHNLBW 0x18U
#define CH_PROM_POWER 0x10U
#define CH_PROM_BOARD 0xc1U
#define CH_PROM_PATH_STRIDE 38U /* 18 bytes 2G, then 20 bytes 5G */

static int8_t
channel_signed_nibble(uint8_t value)
{
    value &= 0x0fU;
    return (int8_t)((value & 8U) != 0 ? (int)value - 16 : (int)value);
}

int
rtwn8723be_eeprom_txpower_parse(struct rtwn8723be_eeprom_txpower *out,
    const uint8_t *prom, size_t length, bool autoload_fail)
{
    struct rtwn8723be_eeprom_txpower next = {0};
    uint8_t cck[2][6], ht40[2][5];
    unsigned int path, group, count, channel, addr;

    if (out == NULL || prom == NULL || length <= CH_PROM_BOARD)
        return EINVAL;
    next.defaults = autoload_fail || prom[CH_PROM_POWER + 1U] == 0xffU;
    for (path = 0; path < 2U; path++) {
        if (next.defaults) {
            for (group = 0; group < 6U; group++)
                cck[path][group] = 0x2dU;
            for (group = 0; group < 5U; group++)
                ht40[path][group] = 0x2dU;
            next.bw20_diff[path][0] = 2;
            next.ofdm_diff[path][0] = 4;
            for (count = 1; count < 4U; count++) {
                next.bw20_diff[path][count] = -2;
                next.bw40_diff[path][count] = -2;
                next.ofdm_diff[path][count] = -2;
            }
        } else {
            addr = CH_PROM_POWER + path * CH_PROM_PATH_STRIDE;
            for (group = 0; group < 6U; group++) {
                cck[path][group] = prom[addr++];
                if (cck[path][group] == 0xffU)
                    cck[path][group] = 0x2dU;
            }
            for (group = 0; group < 5U; group++) {
                ht40[path][group] = prom[addr++];
                if (ht40[path][group] == 0xffU)
                    ht40[path][group] = 0x2dU;
            }
            for (count = 0; count < 4U; count++) {
                uint8_t value = prom[addr++];
                if (count == 0U) {
                    next.bw20_diff[path][count] = value == 0xffU ? 2 :
                        channel_signed_nibble(value >> 4);
                    next.ofdm_diff[path][count] = value == 0xffU ? 4 :
                        channel_signed_nibble(value);
                    /* Linux normal-PROM branch explicitly assigns 0. */
                    next.bw40_diff[path][count] = 0;
                } else {
                    next.bw40_diff[path][count] = value == 0xffU ? -2 :
                        channel_signed_nibble(value >> 4);
                    next.bw20_diff[path][count] = value == 0xffU ? -2 :
                        channel_signed_nibble(value);
                    value = prom[addr++];
                    next.ofdm_diff[path][count] = value == 0xffU ? -2 :
                        channel_signed_nibble(value >> 4);
                    /* low nibble is CCK diff, unused by this 1T1R path. */
                }
            }
            /* The following 20 5G bytes precede the next RF path. */
        }
        for (channel = 1; channel <= 14U; channel++) {
            /* Frozen hw.c _rtl8723be_get_chnl_group(), not a newer map. */
            group = channel < 3U ? 0U : channel < 9U ? 1U : 2U;
            next.cck[path][channel - 1U] = cck[path][group];
            next.ht40[path][channel - 1U] = ht40[path][group];
        }
    }
    if (!autoload_fail && prom[CH_PROM_BOARD] != 0xffU)
        next.regulatory = prom[CH_PROM_BOARD] & 7U;
    /*
     * Linux's autoload-fail branch leaves bw40_diff[path][0] undefined.
     * Its defined BW20 defaults remain usable; do not invent BW40 data.
     */
    next.bw40_valid = !next.defaults;
    next.valid = true;
    *out = next;
    return 0;
}

int
rtwn8723be_channel_state_seed(struct rtwn8723be_channel_state *state,
    const uint32_t values[2], unsigned int rf_paths)
{
    struct rtwn8723be_channel_state next = {0};
    if (state == NULL || values == NULL || rf_paths != 1U ||
        (values[0] & ~CH_RF_MASK) != 0 ||
        (values[1] & ~CH_RF_MASK) != 0)
        return EINVAL;
    next.rf_chnlval[0] = values[0];
    next.rf_chnlval[1] = values[1];
    next.rf_valid = true;
    *state = next;
    return 0;
}

void
rtwn8723be_channel_state_invalidate(struct rtwn8723be_channel_state *state)
{
    if (state != NULL) {
        state->valid = false;
        state->power_valid = false;
        state->rf_valid = false;
        state->inprogress = false;
        state->quarantined = true;
    }
}

int
rtwn8723be_channel_power_indices(const struct rtwn8723be_eeprom_txpower *ee,
    const struct rtwn8723be_txpwr_pg_state *pg, unsigned int channel,
    unsigned int bandwidth, uint8_t out[R23BE_CHANNEL_RATE_COUNT])
{
    uint8_t next[R23BE_CHANNEL_RATE_COUNT];
    unsigned int rate, section, shift;
    uint8_t power;
    if (ee == NULL || pg == NULL || out == NULL || !ee->valid ||
        channel < 1U || channel > 14U || bandwidth > R23BE_CHANNEL_BW40)
        return EINVAL;
    if (bandwidth == R23BE_CHANNEL_BW40 && !ee->bw40_valid)
        return ENODATA;
    for (rate = 0; rate < R23BE_CHANNEL_RATE_COUNT; rate++) {
        power = rate < 4U ? ee->cck[0][channel - 1U] :
            ee->ht40[0][channel - 1U];
        if (rate >= 4U && rate <= 11U)
            power = (uint8_t)(power + ee->ofdm_diff[0][0]);
        if (rate >= 12U) {
            power = (uint8_t)(power +
                (bandwidth == R23BE_CHANNEL_BW20 ?
                 ee->bw20_diff[0][0] : ee->bw40_diff[0][0]));
        }
        if (rate < 4U) {
            section = rate == 0U ? 2U : 3U;
            shift = rate <= 1U ? 8U : rate * 8U;
        } else if (rate < 12U) {
            section = (rate - 4U) / 4U;
            shift = ((rate - 4U) % 4U) * 8U;
        } else {
            section = 4U + (rate - 12U) / 4U;
            shift = ((rate - 12U) % 4U) * 8U;
        }
        if (ee->regulatory != 2U)
            power = (uint8_t)(power +
                (uint8_t)(pg->offset[0][0][0][section] >> shift));
        next[rate] = power > 0x3fU ? 0x3fU : power;
    }
    memcpy(out, next, sizeof(next));
    return 0;
}

static int
channel_ready(const struct rtwn8723be_channel_io *io, void *arg)
{
    return io->ready(arg) ? 0 : ENXIO;
}

static int
channel_write_power(const struct rtwn8723be_channel_io *io, void *arg,
    const uint8_t power[R23BE_CHANNEL_RATE_COUNT], bool *touched)
{
    static const uint32_t registers[R23BE_CHANNEL_RATE_COUNT] = {
        0xe08U, 0x86cU, 0x86cU, 0x86cU,
        0xe00U, 0xe00U, 0xe00U, 0xe00U,
        0xe04U, 0xe04U, 0xe04U, 0xe04U,
        0xe10U, 0xe10U, 0xe10U, 0xe10U,
        0xe14U, 0xe14U, 0xe14U, 0xe14U
    };
    unsigned int rate, shift;
    int error;
    for (rate = 0; rate < R23BE_CHANNEL_RATE_COUNT; rate++) {
        error = channel_ready(io, arg);
        if (error != 0)
            return error;
        shift = rate < 4U ? (rate <= 1U ? 8U : rate * 8U) :
            ((rate - 4U) % 4U) * 8U;
        *touched = true; /* An errored native write may still have reached HW. */
        error = io->write_bb(arg, registers[rate], 0xffU << shift,
            power[rate]);
        if (error != 0)
            return error;
    }
    return 0;
}

static int
channel_write8(const struct rtwn8723be_channel_io *io, void *arg,
    uint32_t reg, uint8_t value, bool *touched)
{
    int error = channel_ready(io, arg);
    if (error != 0)
        return error;
    *touched = true;
    return io->write8(arg, reg, value);
}

static int
channel_write_bb(const struct rtwn8723be_channel_io *io, void *arg,
    uint32_t reg, uint32_t mask, uint32_t value, bool *touched)
{
    int error = channel_ready(io, arg);
    if (error != 0)
        return error;
    *touched = true;
    return io->write_bb(arg, reg, mask, value);
}

static int
channel_write_rf(const struct rtwn8723be_channel_io *io, void *arg,
    uint32_t value, bool *touched)
{
    int error = channel_ready(io, arg);
    if (error != 0)
        return error;
    *touched = true;
    return io->write_rf(arg, 0U, CH_RF_CHNLBW, CH_RF_MASK, value);
}

static int
channel_bandwidth(const struct rtwn8723be_channel_io *io, void *arg,
    unsigned int bandwidth, unsigned int prime_sc, uint32_t *rf,
    bool *touched)
{
    uint8_t opmode, rrsr;
    int error;
    error = channel_ready(io, arg);
    if (error != 0)
        return error;
    error = io->read8(arg, 0x603U, &opmode); /* REG_BWOPMODE */
    if (error != 0)
        return error;
    error = channel_ready(io, arg);
    if (error != 0)
        return error;
    error = io->read8(arg, 0x442U, &rrsr); /* source reads even for 20MHz */
    if (error != 0)
        return error;
    error = channel_write8(io, arg, 0x603U,
        bandwidth == R23BE_CHANNEL_BW20 ? (uint8_t)(opmode | 4U) :
        (uint8_t)(opmode & ~4U), touched);
    if (error != 0)
        return error;
    if (bandwidth == R23BE_CHANNEL_BW40) {
        error = channel_write8(io, arg, 0x442U,
            (uint8_t)((rrsr & 0x90U) | (prime_sc << 5)), touched);
        if (error != 0)
            return error;
    }
    error = channel_write_bb(io, arg, 0x800U, 1U, bandwidth, touched);
    if (error != 0)
        return error;
    error = channel_write_bb(io, arg, 0x900U, 1U, bandwidth, touched);
    if (error != 0)
        return error;
    if (bandwidth == R23BE_CHANNEL_BW40) {
        error = channel_write_bb(io, arg, 0xa00U, 0x10U,
            prime_sc >> 1, touched);
        if (error != 0)
            return error;
        error = channel_write_bb(io, arg, 0xd00U, 0xc00U,
            prime_sc, touched);
        if (error != 0)
            return error;
        error = channel_write_bb(io, arg, 0x818U, 0x0c000000U,
            prime_sc == R23BE_CHANNEL_SC_LOWER ? 2U : 1U, touched);
        if (error != 0)
            return error;
    }
    *rf = (*rf & 0xfffff3ffU) |
        (bandwidth == R23BE_CHANNEL_BW20 ? 0xc00U : 0x400U);
    return channel_write_rf(io, arg, *rf, touched);
}

static int
channel_preflight(const struct rtwn8723be_channel_io *io, void *arg,
    const struct rtwn8723be_channel_state *state, bool full)
{
    if (io == NULL || state == NULL)
        return EINVAL;
    if (io->ready == NULL || io->write_bb == NULL ||
        (full && (io->read8 == NULL || io->write8 == NULL ||
        io->write_rf == NULL || io->delay_ms == NULL ||
        io->channel_access == NULL)))
        return ENOSYS;
    if (state->inprogress)
        return EBUSY;
    if (state->quarantined)
        return EIO;
    if (!state->rf_valid)
        return ENXIO;
    return channel_ready(io, arg);
}

int
rtwn8723be_channel_apply(const struct rtwn8723be_channel_io *io, void *arg,
    struct rtwn8723be_channel_state *state,
    const struct rtwn8723be_eeprom_txpower *ee,
    const struct rtwn8723be_txpwr_pg_state *pg, unsigned int primary,
    unsigned int bandwidth, unsigned int prime_sc, bool ht)
{
    struct rtwn8723be_channel_state next;
    unsigned int channel = primary;
    bool touched = false;
    int error;
    if (primary < 1U || primary > 14U || bandwidth > R23BE_CHANNEL_BW40 ||
        (bandwidth == R23BE_CHANNEL_BW20 && prime_sc != 0U) ||
        (bandwidth == R23BE_CHANNEL_BW40 &&
         (prime_sc < 1U || prime_sc > 2U || !ht)))
        return EINVAL;
    if (bandwidth == R23BE_CHANNEL_BW40) {
        if (prime_sc == R23BE_CHANNEL_SC_LOWER)
            channel += 2U;
        else if (primary <= 2U)
            return EINVAL;
        else
            channel -= 2U;
    }
    if (channel < 1U || channel > 14U)
        return EINVAL;
    error = channel_preflight(io, arg, state, true);
    if (error != 0)
        return error;
    next = *state;
    error = rtwn8723be_channel_power_indices(ee, pg, channel, bandwidth,
        next.power_index);
    if (error != 0)
        return error;
    state->inprogress = true;
    error = channel_write_power(io, arg, next.power_index, &touched);
    if (error != 0)
        goto failed;
    next.rf_chnlval[0] = (next.rf_chnlval[0] & 0xfffffc00U) | channel;
    error = channel_write_rf(io, arg, next.rf_chnlval[0], &touched);
    if (error != 0)
        goto failed;
    error = channel_ready(io, arg);
    if (error == 0)
        error = io->delay_ms(arg, 10U);
    if (error != 0)
        goto failed;
    error = channel_ready(io, arg);
    if (error == 0)
        error = io->channel_access(arg, ht);
    if (error != 0)
        goto failed;
    error = channel_bandwidth(io, arg, bandwidth, prime_sc,
        &next.rf_chnlval[0], &touched);
    if (error != 0)
        goto failed;
    error = channel_ready(io, arg);
    if (error != 0)
        goto failed;
    next.current_channel = (uint8_t)channel;
    next.primary_channel = (uint8_t)primary;
    next.current_bw = (uint8_t)bandwidth;
    next.prime_sc = (uint8_t)prime_sc;
    next.valid = true;
    next.power_valid = true;
    next.inprogress = false;
    *state = next;
    return 0;
failed:
    state->inprogress = false;
    if (touched)
        rtwn8723be_channel_state_invalidate(state);
    return error;
}

int
rtwn8723be_channel_txpower_refresh(const struct rtwn8723be_channel_io *io,
    void *arg, struct rtwn8723be_channel_state *state,
    const struct rtwn8723be_eeprom_txpower *ee,
    const struct rtwn8723be_txpwr_pg_state *pg)
{
    uint8_t power[R23BE_CHANNEL_RATE_COUNT];
    bool touched = false;
    int error = channel_preflight(io, arg, state, false);
    if (error != 0)
        return error;
    if (!state->valid || !state->power_valid)
        return ENXIO;
    error = rtwn8723be_channel_power_indices(ee, pg,
        state->current_channel, state->current_bw, power);
    if (error != 0)
        return error;
    state->inprogress = true;
    error = channel_write_power(io, arg, power, &touched);
    if (error == 0)
        error = channel_ready(io, arg);
    state->inprogress = false;
    if (error != 0) {
        if (touched)
            rtwn8723be_channel_state_invalidate(state);
        return error;
    }
    memcpy(state->power_index, power, sizeof(power));
    return 0;
}
