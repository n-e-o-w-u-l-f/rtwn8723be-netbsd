/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Native implementations of the direct-I/O RTL8723BE coexistence providers.
 * Frozen Linux reference:
 *   rtlwifi/btcoexist/halbtcoutsrc.c @ fd179f8a05be3ccae366b9b96e176b51fbe54aab
 *
 * The original provider ABI hides I/O failures in void/scalar callbacks.
 * NetBSD must not silently continue with fabricated values, so every
 * fallible operation records the first failure in the native BTC owner.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>

#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_btc_native.h"
#include "rtwn8723be_btc_providers_native.h"
#include "rtwn8723be_h2c_native.h"
#include "rtwn8723be_rf_serial.h"

static unsigned int
btc_shift32(uint32_t mask)
{
    unsigned int shift = 0;

    KASSERT(mask != 0);
    while ((mask & 1U) == 0) {
        mask >>= 1;
        shift++;
    }
    return shift;
}

static struct rtwn8723be_softc *
btc_sc(void *context)
{
    struct btc_coexist *btc = context;

    if (btc == NULL || btc->adapter == NULL)
        return NULL;
    return btc->adapter;
}

static bool
btc_mmio_range(const struct rtwn8723be_softc *sc, uint32_t reg, size_t width)
{
    return sc != NULL && sc->sc_mapped && width != 0 &&
        reg <= sc->sc_mapsize && sc->sc_mapsize - reg >= width;
}

static bool
btc_provider_ready(struct rtwn8723be_softc *sc)
{
    return sc != NULL && rtwn8723be_btc_native_provider_ready(sc);
}

static void
btc_provider_fail(struct rtwn8723be_softc *sc, int error)
{
    if (sc != NULL && error != 0)
        rtwn8723be_btc_native_provider_error(sc, error);
}

static uint8_t
btc_read_1(void *context, uint32_t reg)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return 0;
    if (!btc_mmio_range(sc, reg, 1)) {
        btc_provider_fail(sc, EINVAL);
        return 0;
    }
    return rtwn8723be_read_1(sc, reg);
}

static uint16_t
btc_read_2(void *context, uint32_t reg)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return 0;
    if (!btc_mmio_range(sc, reg, 2)) {
        btc_provider_fail(sc, EINVAL);
        return 0;
    }
    return rtwn8723be_read_2(sc, reg);
}

static uint32_t
btc_read_4(void *context, uint32_t reg)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return 0;
    if (!btc_mmio_range(sc, reg, 4)) {
        btc_provider_fail(sc, EINVAL);
        return 0;
    }
    return rtwn8723be_read_4(sc, reg);
}

static void
btc_write_1(void *context, uint32_t reg, uint32_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return;
    if (!btc_mmio_range(sc, reg, 1)) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    rtwn8723be_write_1(sc, reg, (uint8_t)data);
}

static void
btc_write_1_mask(void *context, uint32_t reg, uint32_t mask, uint8_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint8_t original;
    unsigned int shift;

    if (!btc_provider_ready(sc))
        return;
    if (!btc_mmio_range(sc, reg, 1) ||
        (mask != 0xffffffffU && (mask == 0 || (mask & ~0xffU) != 0))) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    if (mask == 0xffffffffU) {
        rtwn8723be_write_1(sc, reg, data);
        return;
    }

    original = rtwn8723be_read_1(sc, reg);
    shift = btc_shift32(mask);
    data = (uint8_t)((original & ~(uint8_t)mask) |
        (((uint32_t)data << shift) & mask));
    rtwn8723be_write_1(sc, reg, data);
}

static void
btc_write_2(void *context, uint32_t reg, uint16_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return;
    if (!btc_mmio_range(sc, reg, 2)) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    rtwn8723be_write_2(sc, reg, data);
}

static void
btc_write_4(void *context, uint32_t reg, uint32_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return;
    if (!btc_mmio_range(sc, reg, 4)) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    rtwn8723be_write_4(sc, reg, data);
}

static void
btc_write_local_1(void *context, uint32_t reg, uint8_t data)
{
    struct btc_coexist *btc = context;

    if (btc == NULL || btc->chip_interface != BTC_INTF_PCI) {
        struct rtwn8723be_softc *sc = btc_sc(context);
        if (sc != NULL)
            btc_provider_fail(sc, EINVAL);
        return;
    }
    btc_write_1(context, reg, data);
}

static void
btc_set_bb(void *context, uint32_t reg, uint32_t mask, uint32_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint32_t original;
    unsigned int shift;

    if (!btc_provider_ready(sc))
        return;
    if (!btc_mmio_range(sc, reg, 4) || mask == 0) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    if (mask == 0xffffffffU) {
        rtwn8723be_write_4(sc, reg, data);
        return;
    }
    original = rtwn8723be_read_4(sc, reg);
    shift = btc_shift32(mask);
    original = (original & ~mask) | ((data << shift) & mask);
    rtwn8723be_write_4(sc, reg, original);
}

static uint32_t
btc_get_bb(void *context, uint32_t reg, uint32_t mask)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint32_t value;

    if (!btc_provider_ready(sc))
        return 0;
    if (!btc_mmio_range(sc, reg, 4) || mask == 0) {
        btc_provider_fail(sc, EINVAL);
        return 0;
    }
    value = rtwn8723be_read_4(sc, reg);
    return (value & mask) >> btc_shift32(mask);
}

static bool
btc_rf_ready(void *arg)
{
    struct rtwn8723be_softc *sc = arg;

    return btc_provider_ready(sc) && sc->sc_core_initialized &&
        sc->sc_bb_valid && sc->sc_linux.fw_ready &&
        sc->sc_rf_path_count_valid &&
        (sc->sc_rf_path_count == 1 || sc->sc_rf_path_count == 2);
}

static int
btc_rf_read_bb(void *arg, uint32_t reg, uint32_t *value)
{
    struct rtwn8723be_softc *sc = arg;

    if (value == NULL || !btc_rf_ready(sc))
        return EINVAL;
    if (!btc_mmio_range(sc, reg, 4))
        return EINVAL;
    *value = rtwn8723be_read_4(sc, reg);
    return 0;
}

static int
btc_rf_write_bb(void *arg, uint32_t reg, uint32_t value)
{
    struct rtwn8723be_softc *sc = arg;

    if (!btc_rf_ready(sc))
        return EAGAIN;
    if (!btc_mmio_range(sc, reg, 4))
        return EINVAL;
    rtwn8723be_write_4(sc, reg, value);
    return 0;
}

static void
btc_rf_delay(void *arg, unsigned int usec)
{
    (void)arg;
    delay(usec);
}

static const struct rtwn8723be_rf_serial_io btc_rf_io = {
    .ready = btc_rf_ready,
    .read_bb = btc_rf_read_bb,
    .write_bb = btc_rf_write_bb,
    .delay_us = btc_rf_delay,
};

static void
btc_set_rf(void *context, uint8_t path, uint32_t reg,
    uint32_t mask, uint32_t data)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    struct rtwn8723be_rf_serial_ctx rf;
    int error;

    if (!btc_provider_ready(sc))
        return;
    if (path > RTWN8723BE_RF_PATH_B || mask == 0 ||
        (mask & ~RTWN8723BE_RF_FULL_MASK) != 0) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    rf.io = &btc_rf_io;
    rf.dev = sc;
    error = rtwn8723be_rf_masked_write(&rf, path, reg, mask, data);
    btc_provider_fail(sc, error);
}

static uint32_t
btc_get_rf(void *context, uint8_t path, uint32_t reg, uint32_t mask)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    struct rtwn8723be_rf_serial_ctx rf;
    uint32_t value = 0;
    int error;

    if (!btc_provider_ready(sc))
        return 0;
    if (path > RTWN8723BE_RF_PATH_B || mask == 0 ||
        (mask & ~RTWN8723BE_RF_FULL_MASK) != 0) {
        btc_provider_fail(sc, EINVAL);
        return 0;
    }
    rf.io = &btc_rf_io;
    rf.dev = sc;
    error = rtwn8723be_rf_serial_read(&rf, path, reg, &value);
    if (error != 0) {
        btc_provider_fail(sc, error);
        return 0;
    }
    return (value & mask) >> btc_shift32(mask);
}

static void
btc_fill_h2c(void *context, uint8_t id, uint32_t length, uint8_t *command)
{
    struct rtwn8723be_softc *sc = btc_sc(context);
    int error;

    if (!btc_provider_ready(sc))
        return;
    if ((length != 0 && command == NULL) ||
        length > R23BE_H2C_MAX_PAYLOAD) {
        btc_provider_fail(sc, EINVAL);
        return;
    }
    error = rtwn8723be_h2c_native_send(sc, id, command, (size_t)length);
    btc_provider_fail(sc, error);
}

static int
btc_mp_request(struct btc_coexist *btc, uint8_t opcode, size_t length,
    enum rtwn8723be_btc_mp_field field, uint32_t *value, uint8_t *subversion)
{
    struct rtwn8723be_softc *sc = btc_sc(btc);
    struct rtwn8723be_btc_mp_reply reply;
    uint8_t command[4] = {0};
    int error;

    if (!btc_provider_ready(sc))
        return EAGAIN;
    if (length != 2U && length != 4U)
        return EINVAL;
    error = rtwn8723be_btc_mp_native_request(sc, opcode,
        command, length, true, &reply);
    if (error != 0)
        return error;
    if (reply.field != field)
        return EPROTO;
    if (value != NULL)
        *value = reply.value;
    if (subversion != NULL)
        *subversion = reply.firmware_subversion;
    return 0;
}

static void
btc_set_bt_reg(void *context, uint8_t reg_type, uint32_t offset,
    uint32_t value)
{
    struct btc_coexist *btc = context;
    struct rtwn8723be_softc *sc = btc_sc(context);
    struct rtwn8723be_btc_mp_reply reply;
    uint8_t command[4] = {0};
    int error;

    if (!btc_provider_ready(sc))
        return;

    /* Frozen halbtc_set_bt_reg(): value transaction first, then address. */
    command[2] = (uint8_t)(value & 0xffU);
    command[3] = (uint8_t)((value >> 8) & 0xffU);
    error = rtwn8723be_btc_mp_native_request(sc,
        R23BE_BT_OP_WRITE_REG_VALUE, command, sizeof(command), true, &reply);
    if (error != 0) {
        btc_provider_fail(sc, error);
        return;
    }

    memset(command, 0, sizeof(command));
    command[2] = reg_type;
    command[3] = (uint8_t)offset;
    error = rtwn8723be_btc_mp_native_request(sc,
        R23BE_BT_OP_WRITE_REG_ADDR, command, sizeof(command), true, &reply);
    btc_provider_fail(sc, error);
    (void)btc;
}

static uint32_t
btc_get_bt_reg(void *context, uint8_t reg_type, uint32_t offset)
{
    /*
     * Frozen halbtcoutsrc.c returns zero unconditionally for this provider.
     * Preserve that exact behavior; do not invent an unsupported MP read.
     */
    (void)context;
    (void)reg_type;
    (void)offset;
    return 0;
}

static uint32_t
btc_get_feature(void *context)
{
    struct btc_coexist *btc = context;
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint32_t value = 0;
    int error;

    if (btc == NULL || !btc_provider_ready(sc))
        return 0;
    if (btc->bt_info.bt_supported_feature != 0)
        return btc->bt_info.bt_supported_feature;
    error = btc_mp_request(btc, R23BE_BT_OP_FEATURE, 4,
        R23BE_BT_MP_FEATURE, &value, NULL);
    if (error != 0) {
        btc_provider_fail(sc, error);
        return 0;
    }
    btc->bt_info.bt_supported_feature = value;
    return value;
}

static uint32_t
btc_get_supported_version(void *context)
{
    struct btc_coexist *btc = context;
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint32_t value = 0;
    int error;

    if (btc == NULL || !btc_provider_ready(sc))
        return 0;
    if (btc->bt_info.bt_supported_version != 0)
        return btc->bt_info.bt_supported_version;
    error = btc_mp_request(btc, R23BE_BT_OP_SUPPORTED_VERSION, 4,
        R23BE_BT_MP_SUPPORTED_VERSION, &value, NULL);
    if (error != 0) {
        btc_provider_fail(sc, error);
        return 0;
    }
    btc->bt_info.bt_supported_version = value;
    return value;
}

static uint32_t
btc_get_phydm_version(void *context)
{
    /* Frozen Linux provider is an intentional zero stub. */
    (void)context;
    return 0;
}

static void
btc_modify_ra_threshold(void *context, uint8_t direction, uint8_t offset)
{
    /* Frozen Linux provider is intentionally empty. */
    (void)context;
    (void)direction;
    (void)offset;
}

static uint32_t
btc_query_phy_counter(void *context, enum dm_info_query id)
{
    /* Frozen Linux provider returns zero for all three IQK counters. */
    (void)context;
    (void)id;
    return 0;
}

static uint8_t
btc_get_ant_det(void *context)
{
    struct btc_coexist *btc = context;
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint32_t value = 0;
    int error;

    if (btc == NULL || !btc_provider_ready(sc))
        return 0;
    error = btc_mp_request(btc, R23BE_BT_OP_ANT_DETECTION, 4,
        R23BE_BT_MP_ANT_DETECTION, &value, NULL);
    if (error != 0) {
        btc_provider_fail(sc, error);
        return 0;
    }
    btc->bt_info.bt_ant_det_val = (uint8_t)value;
    return btc->bt_info.bt_ant_det_val;
}

static uint8_t
btc_get_ble_scan_type(void *context)
{
    struct btc_coexist *btc = context;
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint32_t value = 0;
    int error;

    if (btc == NULL || !btc_provider_ready(sc))
        return 0;
    error = btc_mp_request(btc, R23BE_BT_OP_BLE_SCAN_TYPE, 4,
        R23BE_BT_MP_BLE_SCAN_TYPE, &value, NULL);
    if (error != 0) {
        btc_provider_fail(sc, error);
        return 0;
    }
    btc->bt_info.bt_ble_scan_type = (uint8_t)value;
    return btc->bt_info.bt_ble_scan_type;
}

static uint32_t
btc_get_ble_scan_para(void *context, uint8_t scan_type)
{
    struct btc_coexist *btc = context;
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint32_t value = 0;
    int error;

    (void)scan_type; /* Frozen Linux ignores this argument. */
    if (btc == NULL || !btc_provider_ready(sc))
        return 0;
    error = btc_mp_request(btc, R23BE_BT_OP_BLE_SCAN_PARAMETERS, 4,
        R23BE_BT_MP_BLE_SCAN_PARAMETERS, &value, NULL);
    if (error != 0) {
        btc_provider_fail(sc, error);
        return 0;
    }
    btc->bt_info.bt_ble_scan_para = value;
    return value;
}

static bool
btc_get_afh_map(void *context, uint8_t map_type, uint8_t *map)
{
    struct btc_coexist *btc = context;
    struct rtwn8723be_softc *sc = btc_sc(context);
    uint32_t low = 0, middle = 0, high = 0;
    int error;

    (void)map_type; /* Frozen Linux ignores this selector. */
    if (btc == NULL || map == NULL || !btc_provider_ready(sc))
        return false;

    error = btc_mp_request(btc, R23BE_BT_OP_AFH_L, 2,
        R23BE_BT_MP_AFH_L, &low, NULL);
    if (error == 0)
        error = btc_mp_request(btc, R23BE_BT_OP_AFH_M, 2,
            R23BE_BT_MP_AFH_M, &middle, NULL);
    if (error == 0)
        error = btc_mp_request(btc, R23BE_BT_OP_AFH_H, 2,
            R23BE_BT_MP_AFH_H, &high, NULL);
    if (error != 0) {
        btc_provider_fail(sc, error);
        return false;
    }

    btc->bt_info.afh_map_l = low;
    btc->bt_info.afh_map_m = middle;
    btc->bt_info.afh_map_h = (uint16_t)high;
    map[0] = (uint8_t)low;
    map[1] = (uint8_t)(low >> 8);
    map[2] = (uint8_t)(low >> 16);
    map[3] = (uint8_t)(low >> 24);
    map[4] = (uint8_t)middle;
    map[5] = (uint8_t)(middle >> 8);
    map[6] = (uint8_t)(middle >> 16);
    map[7] = (uint8_t)(middle >> 24);
    map[8] = (uint8_t)high;
    map[9] = (uint8_t)(high >> 8);
    return true;
}

static void
btc_display_debug(void *context, uint8_t type, struct seq_file *m)
{
    /*
     * The frozen statistics/link displays are empty; Wi-Fi display is purely
     * diagnostic. NetBSD has no seq_file ABI, so retain a side-effect-free
     * diagnostic provider rather than fabricating state or touching hardware.
     */
    (void)context;
    (void)type;
    (void)m;
}

static void
btc_delay_ms(void *context, unsigned int ms)
{
    struct rtwn8723be_softc *sc = btc_sc(context);

    if (!btc_provider_ready(sc))
        return;
    while (ms-- != 0)
        delay(1000);
}

int
rtwn8723be_btc_native_seed_lowlevel(struct btc_coexist *btc,
    struct rtwn8723be_softc *sc)
{
    if (btc == NULL || sc == NULL)
        return EINVAL;
    if (btc->adapter != NULL && btc->adapter != sc)
        return EBUSY;

    btc->adapter = sc;
    btc->chip_interface = BTC_INTF_PCI;
    btc->btc_read_1byte = btc_read_1;
    btc->btc_write_1byte = btc_write_1;
    btc->btc_write_1byte_bitmask = btc_write_1_mask;
    btc->btc_read_2byte = btc_read_2;
    btc->btc_write_2byte = btc_write_2;
    btc->btc_read_4byte = btc_read_4;
    btc->btc_write_4byte = btc_write_4;
    btc->btc_write_local_reg_1byte = btc_write_local_1;
    btc->btc_set_bb_reg = btc_set_bb;
    btc->btc_get_bb_reg = btc_get_bb;
    btc->btc_set_rf_reg = btc_set_rf;
    btc->btc_get_rf_reg = btc_get_rf;
    btc->btc_fill_h2c = btc_fill_h2c;
    btc->btc_disp_dbg_msg = btc_display_debug;
    btc->btc_set_bt_reg = btc_set_bt_reg;
    btc->btc_get_bt_reg = btc_get_bt_reg;
    btc->btc_get_bt_coex_supported_feature = btc_get_feature;
    btc->btc_get_bt_coex_supported_version = btc_get_supported_version;
    btc->btc_get_bt_phydm_version = btc_get_phydm_version;
    btc->btc_phydm_modify_ra_pcr_threshold = btc_modify_ra_threshold;
    btc->btc_phydm_query_phy_counter = btc_query_phy_counter;
    btc->btc_get_ant_det_val_from_bt = btc_get_ant_det;
    btc->btc_get_ble_scan_type_from_bt = btc_get_ble_scan_type;
    btc->btc_get_ble_scan_para_from_bt = btc_get_ble_scan_para;
    btc->btc_get_bt_afh_map_from_bt = btc_get_afh_map;
    btc->r23be_delay_ms = btc_delay_ms;
    return 0;
}
