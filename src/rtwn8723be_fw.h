#ifndef _RTWN8723BE_FW_H_
#define _RTWN8723BE_FW_H_

#include <sys/types.h>
#include <sys/bus.h>

#define R23BE_FW_HEADER_SIZE            32
#define R23BE_FW_START_ADDR             0x1000
#define R23BE_FW_PAGE_SIZE              4096
#define R23BE_FW_MAX_PAGES              8
#define R23BE_FW_MAX_FILE_SIZE          0x8000U
#define R23BE_FW_POLL_COUNT             6000
#define R23BE_FW_READY_DELAY_US         5000

#define R23BE_MCUFWDL_EN                (1U << 0)
#define R23BE_MCUFWDL_RDY               (1U << 1)
#define R23BE_MCUFWDL_CHKSUM_RPT        (1U << 2)
#define R23BE_MCUFWDL_WINTINI_RDY       (1U << 6)
#define R23BE_MCUFWDL_RAM_DL_SEL        (1U << 7)

struct rtwn8723be_fw_image_info {
    size_t payload_offset;
    size_t payload_length;
    uint16_t signature;
    uint16_t version;
    uint16_t ram_code_size;
    uint8_t subversion;
    bool has_header;
};

int rtwn8723be_fw_image_parse(const uint8_t *, size_t,
    struct rtwn8723be_fw_image_info *);
void rtwn8723be_fw_selfreset(bus_space_tag_t, bus_space_handle_t);
int rtwn8723be_fw_download(bus_space_tag_t, bus_space_handle_t,
    const uint8_t *, size_t);
int rtwn8723be_fw_free_to_go(bus_space_tag_t, bus_space_handle_t);

#endif