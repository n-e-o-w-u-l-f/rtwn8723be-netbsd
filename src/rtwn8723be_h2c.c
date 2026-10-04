/* SPDX-License-Identifier: GPL-2.0 */
/* Portable, source-ordered PCIe H2C mailbox protocol, pinned Linux:
 * rtl8723be/fw.c:_rtl8723be_fill_h2c_command().
 * No NetBSD MMIO or firmware-start callback is activated by this module.
 */
#include "rtwn8723be_h2c.h"

#define R23BE_HMETFR_REG   0x01ccU
#define R23BE_HMEBOX_BASE  0x01d0U
#define R23BE_HMEBOX_EXT   0x01f0U

void
rtwn8723be_h2c_reset(struct rtwn8723be_h2c_state *state)
{
    if (state == NULL)
        return;
    state->next_box = 0;
    state->firmware_ready = false;
    state->faulted = false;
}

int
rtwn8723be_h2c_send(struct rtwn8723be_h2c_state *state,
    const struct rtwn8723be_h2c_ops *ops, uint8_t id,
    const uint8_t *payload, size_t len)
{
    uint8_t main_bytes[4] = { 0 }, ext_bytes[4] = { 0 }, pending;
    uint16_t box_reg, ext_reg;
    unsigned int poll, i;
    uint8_t box;
    int error;

    if (state == NULL || ops == NULL || ops->lock == NULL ||
        ops->unlock == NULL || ops->read_1 == NULL ||
        ops->write_1 == NULL || ops->delay_us == NULL ||
        payload == NULL || len == 0 || len > R23BE_H2C_MAX_PAYLOAD)
        return EINVAL;

    error = ops->lock(ops->ctx);
    if (error != 0)
        return error;
    if (state->faulted) {
        error = EIO;
        goto out;
    }
    if (!state->firmware_ready) {
        error = EAGAIN;
        goto out;
    }
    box = state->next_box;
    if (box >= R23BE_H2C_BOX_COUNT) {
        state->faulted = true;
        error = EIO;
        goto out;
    }
    for (poll = 0; poll < R23BE_H2C_POLL_LIMIT; poll++) {
        error = ops->read_1(ops->ctx, R23BE_HMETFR_REG, &pending);
        if (error != 0)
            goto out;
        if ((pending & (uint8_t)(1U << box)) == 0)
            break;
        if (poll + 1U < R23BE_H2C_POLL_LIMIT)
            ops->delay_us(ops->ctx, R23BE_H2C_POLL_DELAY_US);
    }
    if (poll == R23BE_H2C_POLL_LIMIT) {
        error = ETIMEDOUT;
        goto out;
    }
    main_bytes[0] = id;
    for (i = 0; i < 3U && i < len; i++)
        main_bytes[i + 1U] = payload[i];
    for (i = 3U; i < len; i++)
        ext_bytes[i - 3U] = payload[i];

    box_reg = (uint16_t)(R23BE_HMEBOX_BASE + (uint16_t)box * 4U);
    ext_reg = (uint16_t)(R23BE_HMEBOX_EXT + (uint16_t)box * 4U);
    /* Linux publishes extended bytes BEFORE the main mailbox. Any failed
     * MMIO write may have published a partial command: fail closed until
     * the owning driver has actually reset/reinitialized firmware.
     */
    if (len > 3U) {
        for (i = 0; i < R23BE_H2C_MAIL_LEN; i++) {
            error = ops->write_1(ops->ctx, (uint16_t)(ext_reg + i),
                ext_bytes[i]);
            if (error != 0) {
                state->faulted = true;
                goto out;
            }
        }
    }
    for (i = 0; i < R23BE_H2C_MAIL_LEN; i++) {
        error = ops->write_1(ops->ctx, (uint16_t)(box_reg + i),
            main_bytes[i]);
        if (error != 0) {
            state->faulted = true;
            goto out;
        }
    }
    state->next_box = (uint8_t)((box + 1U) % R23BE_H2C_BOX_COUNT);
    error = 0;
out:
    ops->unlock(ops->ctx);
    return error;
}

int
rtwn8723be_h2c_media_status(struct rtwn8723be_h2c_state *state,
    const struct rtwn8723be_h2c_ops *ops, bool connected)
{
    const uint8_t payload[3] = { connected ? 1U : 0U, 0, 0 };

    return rtwn8723be_h2c_send(state, ops, 1U,
        payload, sizeof(payload));
}
