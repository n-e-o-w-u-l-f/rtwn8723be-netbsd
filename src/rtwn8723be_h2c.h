/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_H2C_H_
#define _RTWN8723BE_H2C_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/*
 * 8723BE H2C mailbox transport, from pinned Linux rtl8723be/fw.c.
 * A command is 1..7 PAYLOAD bytes, plus one element-ID byte.
 * Each box is four bytes; optional extension is four more bytes.
 * The caller owns a kernel-safe SERIALIZATION lock and must not call this
 * sleepable/10us-poll transport in hard-interrupt context.
 */
#define RTWN8723BE_H2C_BOX_COUNT       4U
#define RTWN8723BE_H2C_MAX_PAYLOAD     7U
#define RTWN8723BE_H2C_HMETFR          0x01ccU
#define RTWN8723BE_H2C_BOX_BASE       0x01d0U
#define RTWN8723BE_H2C_BOX_EXT_BASE   0x01f0U
#define RTWN8723BE_H2C_BOX_STRIDE     4U
#define RTWN8723BE_H2C_POLL_ATTEMPTS  100U
#define RTWN8723BE_H2C_POLL_DELAY_US  10U

struct rtwn8723be_h2c_transport {
    void *arg;
    bool (*firmware_ready)(void *);
    int (*acquire)(void *);
    void (*release)(void *);
    int (*read_1)(void *, uint16_t, uint8_t *);
    int (*write_1)(void *, uint16_t, uint8_t);
    void (*delay_us)(void *, unsigned int);
    uint8_t next_box;
    /*
     * A failed byte write may leave a partially visible command. Do not
     * reuse the mailbox until a verified firmware/transport reset.
     */
    bool poisoned;
};

/* Returns 0, EINVAL, ENOSYS, EAGAIN, ETIMEDOUT, EIO or callback error. */
int rtwn8723be_h2c_send(struct rtwn8723be_h2c_transport *,
    uint8_t element_id, const uint8_t *payload, size_t payload_len);

/*
 * Only call after an externally VERIFIED firmware/MCU mailbox reset and
 * while no H2C sender can run. In particular, do not call on write failure.
 */
void rtwn8723be_h2c_reset_after_firmware_reset(
    struct rtwn8723be_h2c_transport *);

#endif /* _RTWN8723BE_H2C_H_ */
