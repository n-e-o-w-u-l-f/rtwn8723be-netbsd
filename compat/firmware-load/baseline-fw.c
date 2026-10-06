#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/bus.h>
#include <sys/errno.h>

#include "rtwn8723be_f16_1.h"
#include "rtwn8723be_fw.h"

static uint8_t
r23be_read_1(bus_space_tag_t st, bus_space_handle_t sh, bus_size_t reg)
{
    return bus_space_read_1(st, sh, reg);
}

static uint32_t
r23be_read_4(bus_space_tag_t st, bus_space_handle_t sh, bus_size_t reg)
{
    return bus_space_read_4(st, sh, reg);
}

static void
r23be_write_1(bus_space_tag_t st, bus_space_handle_t sh, bus_size_t reg,
    uint8_t val)
{
    bus_space_write_1(st, sh, reg, val);
}

static void
r23be_write_4(bus_space_tag_t st, bus_space_handle_t sh, bus_size_t reg,
    uint32_t val)
{
    bus_space_write_4(st, sh, reg, val);
}

void
rtwn8723be_fw_selfreset(bus_space_tag_t st, bus_space_handle_t sh)
{
    uint8_t v;

    v = r23be_read_1(st, sh, R23BE_REG_RSV_CTRL + 1);
    r23be_write_1(st, sh, R23BE_REG_RSV_CTRL + 1, v & ~(1U << 0));

    v = r23be_read_1(st, sh, R23BE_REG_SYS_FUNC_EN + 1);
    r23be_write_1(st, sh, R23BE_REG_SYS_FUNC_EN + 1, v & ~(1U << 2));
    delay(50);

    v = r23be_read_1(st, sh, R23BE_REG_RSV_CTRL + 1);
    r23be_write_1(st, sh, R23BE_REG_RSV_CTRL + 1, v | (1U << 0));

    v = r23be_read_1(st, sh, R23BE_REG_SYS_FUNC_EN + 1);
    r23be_write_1(st, sh, R23BE_REG_SYS_FUNC_EN + 1, v | (1U << 2));
}

static void
rtwn8723be_fw_download_enable(bus_space_tag_t st, bus_space_handle_t sh,
    bool enable)
{
    uint8_t v;

    if (enable) {
        v = r23be_read_1(st, sh, R23BE_REG_SYS_FUNC_EN + 1);
        r23be_write_1(st, sh, R23BE_REG_SYS_FUNC_EN + 1, v | 0x04);

        v = r23be_read_1(st, sh, R23BE_REG_MCUFWDL);
        r23be_write_1(st, sh, R23BE_REG_MCUFWDL,
            v | R23BE_MCUFWDL_EN);

        v = r23be_read_1(st, sh, R23BE_REG_MCUFWDL + 2);
        r23be_write_1(st, sh, R23BE_REG_MCUFWDL + 2, v & 0xf7);
    } else {
        v = r23be_read_1(st, sh, R23BE_REG_MCUFWDL);
        r23be_write_1(st, sh, R23BE_REG_MCUFWDL,
            v & ~R23BE_MCUFWDL_EN);
        r23be_write_1(st, sh, R23BE_REG_MCUFWDL + 1, 0);
    }
}

static int
rtwn8723be_fw_write_page(bus_space_tag_t st, bus_space_handle_t sh,
    unsigned int page, const uint8_t *buf, size_t len, size_t payload_left)
{
    uint8_t page_reg;
    size_t i;

    if (page >= R23BE_FW_MAX_PAGES || len > R23BE_FW_PAGE_SIZE)
        return EFBIG;

    page_reg = r23be_read_1(st, sh, R23BE_REG_MCUFWDL + 2);
    page_reg = (page_reg & 0xf8) | (uint8_t)(page & 0x07);
    r23be_write_1(st, sh, R23BE_REG_MCUFWDL + 2, page_reg);

    for (i = 0; i < len; i++) {
        uint8_t v = (i < payload_left) ? buf[i] : 0;
        r23be_write_1(st, sh, R23BE_FW_START_ADDR + i, v);
    }

    return 0;
}

static int
rtwn8723be_fw_write(bus_space_tag_t st, bus_space_handle_t sh,
    const uint8_t *buf, size_t len)
{
    size_t padded_len, off, page_len, payload_left;
    unsigned int page;
    int error;

    padded_len = (len + 3U) & ~3U;
    if (padded_len > (size_t)R23BE_FW_MAX_PAGES * R23BE_FW_PAGE_SIZE)
        return EFBIG;

    for (page = 0, off = 0; off < padded_len; page++, off += page_len) {
        page_len = MIN(padded_len - off, (size_t)R23BE_FW_PAGE_SIZE);
        payload_left = (off < len) ? MIN(len - off, page_len) : 0;
        error = rtwn8723be_fw_write_page(st, sh, page, buf + MIN(off, len),
            page_len, payload_left);
        if (error != 0)
            return error;
    }

    return 0;
}

int
rtwn8723be_fw_free_to_go(bus_space_tag_t st, bus_space_handle_t sh)
{
    uint32_t reg;
    unsigned int n;

    for (n = 0; n < R23BE_FW_POLL_COUNT; n++) {
        reg = r23be_read_4(st, sh, R23BE_REG_MCUFWDL);
        if (reg & R23BE_MCUFWDL_CHKSUM_RPT)
            break;
    }
    if (n == R23BE_FW_POLL_COUNT)
        return ETIMEDOUT;

    reg = r23be_read_4(st, sh, R23BE_REG_MCUFWDL);
    reg |= R23BE_MCUFWDL_RDY;
    reg &= ~R23BE_MCUFWDL_WINTINI_RDY;
    r23be_write_4(st, sh, R23BE_REG_MCUFWDL, reg);

    rtwn8723be_fw_selfreset(st, sh);

    for (n = 0; n < R23BE_FW_POLL_COUNT; n++) {
        reg = r23be_read_4(st, sh, R23BE_REG_MCUFWDL);
        if (reg & R23BE_MCUFWDL_WINTINI_RDY)
            return 0;
        delay(R23BE_FW_READY_DELAY_US);
    }

    return ETIMEDOUT;
}

int
rtwn8723be_fw_download(bus_space_tag_t st, bus_space_handle_t sh,
    const uint8_t *payload, size_t payload_len)
{
    int error;

    if (payload == NULL || payload_len == 0)
        return EINVAL;

    if (r23be_read_1(st, sh, R23BE_REG_MCUFWDL) &
        R23BE_MCUFWDL_RAM_DL_SEL) {
        rtwn8723be_fw_selfreset(st, sh);
        r23be_write_1(st, sh, R23BE_REG_MCUFWDL, 0);
    }

    rtwn8723be_fw_download_enable(st, sh, true);
    error = rtwn8723be_fw_write(st, sh, payload, payload_len);
    rtwn8723be_fw_download_enable(st, sh, false);
    if (error != 0)
        return error;

    return rtwn8723be_fw_free_to_go(st, sh);
}