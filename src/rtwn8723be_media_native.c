/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab RTL8723BE hw.c:
 * legacy STA media, HW_VAR_BSSID/BASIC_RATE/AID/SIFS/SLOT/ACK_PREAMBLE,
 * set_check_bssid, CORRECT_TSF and set_beacon_interval. Exact source
 * register order and cached BCN_CTRL/RCR semantics. Fallible native I/O
 * adds atomic cache publication and quarantine after partial operations.
 */
#include "rtwn8723be_media_native.h"

struct media_session {
    const struct rtwn8723be_media_io *io;
    void *arg;
    struct rtwn8723be_media_state *state;
    struct rtwn8723be_media_state next;
    bool touched;
};

int
rtwn8723be_media_state_seed(struct rtwn8723be_media_state *state,
    uint8_t bcn_ctrl, uint32_t receive_config)
{
    struct rtwn8723be_media_state next = {0};
    if (state == NULL)
        return EINVAL;
    next.bcn_ctrl = bcn_ctrl;
    next.receive_config = receive_config;
    next.cache_valid = true;
    *state = next;
    return 0;
}

void
rtwn8723be_media_state_invalidate(struct rtwn8723be_media_state *state)
{
    if (state != NULL) {
        state->cache_valid = false;
        state->inprogress = false;
        state->quarantined = true;
    }
}

static int
media_ready(struct media_session *s)
{
    return s->io->ready(s->arg) ? 0 : ENXIO;
}

static int
media_begin(struct media_session *s, const struct rtwn8723be_media_io *io,
    void *arg, struct rtwn8723be_media_state *state)
{
    if (s == NULL || io == NULL || state == NULL)
        return EINVAL;
    if (io->ready == NULL || io->read8 == NULL || io->read16 == NULL ||
        io->write8 == NULL || io->write16 == NULL || io->write32 == NULL)
        return ENOSYS;
    if (state->inprogress)
        return EBUSY;
    if (state->quarantined)
        return EIO;
    if (!state->cache_valid || !io->ready(arg))
        return ENXIO;
    *s = (struct media_session){io, arg, state, *state, false};
    state->inprogress = true;
    return 0;
}

static int
media_finish(struct media_session *s, int error)
{
    if (error == 0)
        error = media_ready(s);
    s->state->inprogress = false;
    if (error != 0) {
        if (s->touched)
            rtwn8723be_media_state_invalidate(s->state);
        return error;
    }
    s->next.inprogress = false;
    *s->state = s->next;
    return 0;
}

static int
media_read(struct media_session *s, unsigned int width, uint32_t reg,
    uint32_t *value)
{
    int error = media_ready(s);
    if (error != 0)
        return error;
    if (width == 1U) {
        uint8_t byte;
        error = s->io->read8(s->arg, reg, &byte);
        if (error == 0)
            *value = byte;
    } else {
        uint16_t word;
        error = s->io->read16(s->arg, reg, &word);
        if (error == 0)
            *value = word;
    }
    return error;
}

static int
media_write(struct media_session *s, unsigned int width, uint32_t reg,
    uint32_t value)
{
    int error = media_ready(s);
    if (error != 0)
        return error;
    s->touched = true;
    if (width == 1U)
        return s->io->write8(s->arg, reg, (uint8_t)value);
    if (width == 2U)
        return s->io->write16(s->arg, reg, (uint16_t)value);
    return s->io->write32(s->arg, reg, value);
}

static int
media_bcn_ctrl(struct media_session *s, uint8_t set, uint8_t clear)
{
    s->next.bcn_ctrl = (uint8_t)((s->next.bcn_ctrl | set) & ~clear);
    return media_write(s, 1U, 0x550U, s->next.bcn_ctrl);
}

static int
media_check_bssid(struct media_session *s, bool check)
{
    int error;
    if (check) {
        s->next.receive_config |= 0xc0U;
        error = media_write(s, 4U, 0x608U, s->next.receive_config);
        if (error == 0)
            error = media_bcn_ctrl(s, 0, 0x10U);
    } else {
        s->next.receive_config &= ~0xc0U;
        error = media_bcn_ctrl(s, 0x10U, 0);
        if (error == 0)
            error = media_write(s, 4U, 0x608U, s->next.receive_config);
    }
    return error;
}

int
rtwn8723be_media_set_check_bssid(const struct rtwn8723be_media_io *io,
    void *arg, struct rtwn8723be_media_state *state, bool check)
{
    struct media_session s;
    int error = media_begin(&s, io, arg, state);
    if (error != 0)
        return error;
    return media_finish(&s, media_check_bssid(&s, check));
}

int
rtwn8723be_media_set_network(const struct rtwn8723be_media_io *io, void *arg,
    struct rtwn8723be_media_state *state, bool linked)
{
    struct media_session s;
    uint32_t msr, value;
    int error;
    if (io == NULL || io->led_control == NULL)
        return ENOSYS;
    error = media_begin(&s, io, arg, state);
    if (error != 0)
        return error;
    error = media_read(&s, 1U, 0x102U, &msr); /* source reads MSR first */
    if (error == 0)
        error = media_read(&s, 1U, 0x422U, &value);
    if (error == 0)
        error = media_write(&s, 1U, 0x422U, value & ~0x40U);
    if (error == 0)
        error = media_write(&s, 1U, 0x541U, 0x64U);
    if (error == 0)
        error = media_read(&s, 1U, 0x542U, &value);
    if (error == 0)
        error = media_write(&s, 1U, 0x542U, value & ~1U);
    if (error == 0)
        error = media_bcn_ctrl(&s, 0, 2U); /* enable_bcn_sub_func */
    if (error == 0)
        error = media_write(&s, 1U, 0x102U,
            (msr & 0xfcU) | (linked ? 2U : 0U));
    if (error == 0)
        error = media_ready(&s);
    if (error == 0) {
        s.touched = true;
        error = io->led_control(arg, linked ? 2U : 3U);
    }
    if (error == 0)
        error = media_write(&s, 1U, 0x511U, 0x66U);
    if (error == 0)
        error = media_check_bssid(&s, linked);
    s.next.linked = linked;
    return media_finish(&s, error);
}

int
rtwn8723be_media_set_bssid(const struct rtwn8723be_media_io *io, void *arg,
    struct rtwn8723be_media_state *state, const uint8_t bssid[6])
{
    struct media_session s;
    unsigned int i;
    int error;
    if (bssid == NULL)
        return EINVAL;
    error = media_begin(&s, io, arg, state);
    if (error != 0)
        return error;
    for (i = 0; i < 6U; i++) {
        error = media_write(&s, 1U, 0x618U + i, bssid[i]);
        if (error != 0)
            break;
    }
    memcpy(s.next.bssid, bssid, 6U);
    return media_finish(&s, error);
}

int
rtwn8723be_media_basic_rate_bitmap(const uint8_t *rates, size_t count,
    uint16_t *bitmap)
{
    static const uint8_t legacy[] = {2, 4, 11, 22, 12, 18, 24, 36,
        48, 72, 96, 108};
    uint16_t next = 0;
    size_t i, j;
    if (rates == NULL || bitmap == NULL || count == 0U || count > 15U)
        return EINVAL;
    for (i = 0; i < count; i++) {
        for (j = 0; j < sizeof(legacy); j++)
            if ((rates[i] & 0x7fU) == legacy[j])
                break;
        if (j == sizeof(legacy))
            return EOPNOTSUPP;
        if ((rates[i] & 0x80U) != 0)
            next |= (uint16_t)(1U << j);
    }
    *bitmap = next;
    return 0;
}

int
rtwn8723be_media_set_basic_rates(const struct rtwn8723be_media_io *io,
    void *arg, struct rtwn8723be_media_state *state, uint16_t bitmap)
{
    struct media_session s;
    uint16_t value = (bitmap & 0x15fU) | 1U;
    uint16_t scan = value;
    uint8_t rate_index = 0;
    int error = media_begin(&s, io, arg, state);
    if (error != 0)
        return error;
    error = media_write(&s, 1U, 0x440U, value & 0xffU);
    if (error == 0)
        error = media_write(&s, 1U, 0x441U, value >> 8);
    while (scan > 1U) {
        scan >>= 1;
        rate_index++;
    }
    if (error == 0)
        error = media_write(&s, 1U, 0x480U, rate_index);
    s.next.basic_rates = value;
    return media_finish(&s, error);
}

int
rtwn8723be_media_set_aid(const struct rtwn8723be_media_io *io, void *arg,
    struct rtwn8723be_media_state *state, unsigned int aid)
{
    struct media_session s;
    uint32_t value;
    int error;
    if (aid > 0x3fffU)
        return EINVAL;
    error = media_begin(&s, io, arg, state);
    if (error != 0)
        return error;
    error = media_read(&s, 2U, 0x6a8U, &value);
    if (error == 0)
        error = media_write(&s, 2U, 0x6a8U, (value & 0xc000U) | aid);
    s.next.aid = (uint16_t)aid;
    return media_finish(&s, error);
}

int
rtwn8723be_media_set_preamble(const struct rtwn8723be_media_io *io,
    void *arg, struct rtwn8723be_media_state *state, bool short_preamble)
{
    struct media_session s;
    uint32_t value;
    int error = media_begin(&s, io, arg, state);
    if (error != 0)
        return error;
    error = media_read(&s, 1U, 0x66aU, &value);
    if (error == 0)
        error = media_write(&s, 1U, 0x66aU,
            short_preamble ? value | 2U : value & 0xfdU);
    s.next.short_preamble = short_preamble;
    return media_finish(&s, error);
}

static int
media_sifs(struct media_session *s, uint16_t value)
{
    int error = media_write(s, 1U, 0x515U, value & 0xffU);
    if (error == 0)
        error = media_write(s, 1U, 0x517U, value >> 8);
    if (error == 0)
        error = media_write(s, 1U, 0x429U, value & 0xffU);
    if (error == 0)
        error = media_write(s, 1U, 0x63bU, value & 0xffU);
    if (error == 0)
        error = media_write(s, 2U, 0x63eU, 0x0e0eU);
    s->next.sifs = value;
    return error;
}

int
rtwn8723be_media_set_sifs(const struct rtwn8723be_media_io *io, void *arg,
    struct rtwn8723be_media_state *state, uint16_t sifs, bool ht)
{
    struct media_session s;
    int error;
    if (ht)
        return EOPNOTSUPP;
    error = media_begin(&s, io, arg, state);
    if (error != 0)
        return error;
    return media_finish(&s, media_sifs(&s, sifs));
}

static int
media_slot(struct media_session *s, unsigned int slot, unsigned int method,
    bool acm)
{
    static const uint8_t queue_bits[4] = {2U, 0U, 4U, 8U};
    uint32_t value;
    unsigned int ac;
    int error = media_write(s, 1U, 0x51bU, slot);
    for (ac = 0; error == 0 && ac < 4U; ac++) {
        error = media_ready(s);
        if (error != 0)
            break;
        s->touched = true;
        error = s->io->edca_reset(s->arg, ac);
        if (error == 0 && method != 2U) {
            error = media_read(s, 1U, 0x5c0U, &value);
            if (error == 0) {
                value |= 1U; /* Source adds bit0 for method != SW(2). */
                value = acm ? value | queue_bits[ac] : value & ~queue_bits[ac];
                error = media_write(s, 1U, 0x5c0U, value);
            }
        }
    }
    s->next.slot_time = (uint8_t)slot;
    return error;
}

static int
media_slot_preflight(const struct rtwn8723be_media_io *io, unsigned int slot,
    unsigned int method)
{
    if ((slot != 9U && slot != 20U) || method > 2U)
        return EINVAL;
    if (io == NULL || io->edca_reset == NULL)
        return ENOSYS;
    return 0;
}

int
rtwn8723be_media_set_slot(const struct rtwn8723be_media_io *io, void *arg,
    struct rtwn8723be_media_state *state, unsigned int slot,
    unsigned int method, bool acm)
{
    struct media_session s;
    int error = media_slot_preflight(io, slot, method);
    if (error == 0)
        error = media_begin(&s, io, arg, state);
    if (error != 0)
        return error;
    return media_finish(&s, media_slot(&s, slot, method, acm));
}

int
rtwn8723be_media_channel_access(const struct rtwn8723be_media_io *io,
    void *arg, struct rtwn8723be_media_state *state, unsigned int slot,
    unsigned int method, bool acm, bool ht)
{
    struct media_session s;
    int error;
    if (ht)
        return EOPNOTSUPP;
    error = media_slot_preflight(io, slot, method);
    if (error == 0)
        error = media_begin(&s, io, arg, state);
    if (error != 0)
        return error;
    error = media_slot(&s, slot, method, acm);
    if (error == 0)
        error = media_sifs(&s, 0x0a0aU);
    return media_finish(&s, error);
}

int
rtwn8723be_media_set_tsf(const struct rtwn8723be_media_io *io, void *arg,
    struct rtwn8723be_media_state *state, uint64_t tsf)
{
    struct media_session s;
    int error = media_begin(&s, io, arg, state);
    if (error != 0)
        return error;
    error = media_bcn_ctrl(&s, 0, 8U);
    if (error == 0)
        error = media_write(&s, 4U, 0x560U, (uint32_t)tsf);
    if (error == 0)
        error = media_write(&s, 4U, 0x564U, (uint32_t)(tsf >> 32));
    if (error == 0)
        error = media_bcn_ctrl(&s, 8U, 0);
    s.next.tsf = tsf;
    return media_finish(&s, error);
}

int
rtwn8723be_media_set_beacon_interval(const struct rtwn8723be_media_io *io,
    void *arg, struct rtwn8723be_media_state *state, unsigned int interval)
{
    struct media_session s;
    bool was_enabled = false, held = false;
    int error, restore_error;
    if (interval == 0U || interval > 0xffffU)
        return EINVAL;
    if (io == NULL || io->irq_disable == NULL || io->irq_restore == NULL)
        return ENOSYS;
    error = media_begin(&s, io, arg, state);
    if (error != 0)
        return error;
    error = media_ready(&s);
    if (error == 0) {
        s.touched = true;
        error = io->irq_disable(arg, &was_enabled);
        held = error == 0;
    }
    if (error == 0)
        error = media_write(&s, 2U, 0x554U, interval);
    if (held) {
        restore_error = io->irq_restore(arg, was_enabled);
        if (error == 0)
            error = restore_error;
    }
    s.next.beacon_interval = (uint16_t)interval;
    return media_finish(&s, error);
}
