/* SPDX-License-Identifier: GPL-2.0 */
/* RTL8723BE PCIe H2C mailbox; frozen Linux rtl8723be/fw.c.
 * Independent portable transport, not yet bound to the NetBSD lifecycle.
 */
#ifndef _RTWN8723BE_H2C_H_
#define _RTWN8723BE_H2C_H_

#include "rtwn8723be_os_compat.h"

#define R23BE_H2C_BOX_COUNT    4U
#define R23BE_H2C_MAIL_LEN     4U
#define R23BE_H2C_MAX_PAYLOAD  7U
#define R23BE_H2C_POLL_LIMIT 100U
#define R23BE_H2C_POLL_DELAY_US 10U

struct rtwn8723be_h2c_state {
    uint8_t next_box;
    bool firmware_ready;
    bool faulted;
};

/* lock/unlock MUST serialize all senders; use an adaptive, process-context
 * NetBSD mutex. Never invoke this transport from a hard/soft IRQ or with
 * interrupts masked. read/write must report MMIO failures if detectable.
 */
struct rtwn8723be_h2c_ops {
    void *ctx;
    int (*lock)(void *);
    void (*unlock)(void *);
    int (*read_1)(void *, uint16_t, uint8_t *);
    int (*write_1)(void *, uint16_t, uint8_t);
    void (*delay_us)(void *, unsigned int);
};

/* Called only after a real firmware reset; always invalidates readiness. */
void rtwn8723be_h2c_reset(struct rtwn8723be_h2c_state *);
/* Caller may set firmware_ready only after MCUFWDL_WINTINI_RDY is verified.
 * A failed/partial transaction requires reset and firmware reinitialization.
 */
int rtwn8723be_h2c_send(struct rtwn8723be_h2c_state *,
    const struct rtwn8723be_h2c_ops *, uint8_t,
    const uint8_t *, size_t);
/* Pinned Linux rtl8723be_set_fw_media_status_rpt_cmd(): command ID 1,
 * three payload bytes: association bit, MACID 0, MACID_End 0.
 */
int rtwn8723be_h2c_media_status(struct rtwn8723be_h2c_state *,
    const struct rtwn8723be_h2c_ops *, bool connected);

#endif
