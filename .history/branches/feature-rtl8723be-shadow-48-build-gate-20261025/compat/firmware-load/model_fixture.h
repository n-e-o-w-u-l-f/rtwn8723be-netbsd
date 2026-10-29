/* SPDX-License-Identifier: GPL-2.0 */
/* Actual NetBSD production functions under explicit firmware/MMIO models. */
#ifndef FW_LOAD_FIXTURE_H
#define FW_LOAD_FIXTURE_H
#include <sys/cdefs.h>
#include <sys/types.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include <sys/bus.h>
#include "rtwn8723be_fw.h"
#include "rtwn8723be_linux_state.h"
#define _RTWN8723BE_F16_1_H_
#define R23BE_REG_SYS_FUNC_EN 0x0002
#define R23BE_REG_RSV_CTRL 0x001c
#define R23BE_REG_MCUFWDL 0x0080
#define RTWN8723BE_FIRMWARE_DRIVER "if_rtwn8723be"
#define RTWN8723BE_FIRMWARE_FILE "rtl8723befw_36.bin"
#define RTWN8723BE_FIRMWARE_NAME "rtlwifi/rtl8723befw_36.bin"
#define RTWN8723BE_FIRMWARE_ALT_FILE "rtl8723befw.bin"
#define RTWN8723BE_FIRMWARE_ALT_NAME "rtlwifi/rtl8723befw.bin"
#define KM_SLEEP 0
struct rtwn8723be_softc {
 bool sc_mapped;
 bus_space_tag_t sc_st;
 bus_space_handle_t sc_sh;
 bus_size_t sc_mapsize;
 bool sc_irq_enabled;
 struct { bool initialized; } sc_h2c;
 struct rtwn8723be_linux_state sc_linux;
 const char *sc_firmware_name;
 struct rtwn8723be_fw_image_info sc_fw_info;
 int resets, preloads, ready_calls, preload_error, ready_error;
};
struct image_slot { const uint8_t *data; size_t length; bool present; };
typedef struct image_slot *firmware_handle_t;
bool cpu_intr_p(void);
bool cpu_softintr_p(void);
int firmware_open(const char *,const char *,firmware_handle_t *);
off_t firmware_get_size(firmware_handle_t);
int firmware_read(firmware_handle_t,off_t,void *,size_t);
int firmware_close(firmware_handle_t);
void *firmware_malloc(size_t);
void firmware_free(void *,size_t);
void *kmem_alloc(size_t,int);
void kmem_free(void *,size_t);
void rtwn8723be_h2c_native_reset(struct rtwn8723be_softc *);
int rtwn8723be_netbsd_bt_preload_firmware(struct rtwn8723be_softc *);
int rtwn8723be_h2c_native_fw_ready(struct rtwn8723be_softc *);
#endif
