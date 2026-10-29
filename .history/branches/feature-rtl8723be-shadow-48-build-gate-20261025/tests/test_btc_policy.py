#!/usr/bin/env python3
"""Behavior contract for the unbound Linux BTC get/set policy port.

The policy deliberately has no NetBSD PCI, DMA, IRQ or net80211 dependency.
It translates only the portable decisions made by halbtcoutsrc.c.  A future
whole-driver owner supplies coherent Wi-Fi snapshots and performs the two
real OS actions (aggregation and LPS) before this policy may be bound.
"""
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
POLICY_H = SRC / "rtwn8723be_btc_policy.h"
POLICY_C = SRC / "rtwn8723be_btc_policy.c"
TYPES_H = SRC / "rtwn8723be_btc_linux_types.h"
MANIFEST = ROOT / "config" / "files.rtwn8723be_native"


header = POLICY_H.read_text()
source = POLICY_C.read_text()
types = TYPES_H.read_text()
manifest = MANIFEST.read_text()

for needle in (
        "rtwn8723be_btc_policy_init",
        "rtwn8723be_btc_policy_get",
        "rtwn8723be_btc_policy_set",
        "rtwn8723be_btc_policy_bind",
        "struct rtwn8723be_btc_wifi_snapshot",
        "struct rtwn8723be_btc_policy_ops"):
    assert needle in header, needle

# This translation layer must stay independent of the as-yet-unfinished
# whole-driver owner.  Hardware activation belongs in that owner, not here.
for forbidden in (
        "net80211", "ieee80211", "pci_", "bus_", "dma", "workqueue",
        "rtwn8723be_btc_native", "rtwn8723be_linux_adapter"):
    assert forbidden not in source.lower(), forbidden

assert "void *r23be_policy;" in types
assert manifest.count("rtwn8723be_btc_policy.c") == 1
native_units = re.findall(
    r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native$",
    manifest, re.M)
assert len(native_units) == 48 and len(set(native_units)) == 48


HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "rtwn8723be_btc_policy.h"

struct fixture {
    struct rtwn8723be_btc_wifi_snapshot snapshot;
    uint64_t now_msec;
    int snapshot_error;
    int clock_error;
    int aggregate_error;
    int enter_error;
    int leave_error;
    unsigned snapshot_calls;
    unsigned clock_calls;
    unsigned aggregate_calls;
    unsigned enter_calls;
    unsigned leave_calls;
    unsigned bt_query_calls;
    enum rtwn8723be_btc_policy_bt_query last_bt_query;
    unsigned fault_calls;
    int last_fault;
};

static int
snapshot(void *arg, struct rtwn8723be_btc_wifi_snapshot *out)
{
    struct fixture *f = arg;

    ++f->snapshot_calls;
    if (f->snapshot_error != 0)
        return f->snapshot_error;
    *out = f->snapshot;
    return 0;
}

static int
clock_msec(void *arg, uint64_t *out)
{
    struct fixture *f = arg;

    ++f->clock_calls;
    if (f->clock_error != 0)
        return f->clock_error;
    *out = f->now_msec;
    return 0;
}

static int
aggregate_apply(void *arg, const struct btc_bt_info *info)
{
    struct fixture *f = arg;

    ++f->aggregate_calls;
    assert(info->bt_ctrl_agg_buf_size);
    return f->aggregate_error;
}

static int
lps_enter(void *arg)
{
    struct fixture *f = arg;

    ++f->enter_calls;
    return f->enter_error;
}

static int
lps_leave(void *arg)
{
    struct fixture *f = arg;

    ++f->leave_calls;
    return f->leave_error;
}

static void
fault(void *arg, int error)
{
    struct fixture *f = arg;

    ++f->fault_calls;
    f->last_fault = error;
}

static u32
supported_version(void *arg)
{
    (void)arg;
    return UINT32_C(0x11223344);
}

static u32
phy_counter(void *arg, enum dm_info_query id)
{
    (void)arg;
    return UINT32_C(0x100) + id;
}

static int
bt_query(void *arg, struct btc_coexist *btc,
    enum rtwn8723be_btc_policy_bt_query query, uint32_t *out)
{
    (void)arg;
    (void)btc;
    ++((struct fixture *)arg)->bt_query_calls;
    ((struct fixture *)arg)->last_bt_query = query;
    switch (query) {
    case R23BE_BTC_POLICY_BT_PATCH_VERSION:
        *out = UINT32_C(0x1234);
        return 0;
    case R23BE_BTC_POLICY_BT_DEVICE_INFO:
        *out = UINT32_C(0x56789abc);
        return 0;
    case R23BE_BTC_POLICY_BT_FORBIDDEN_SLOT:
        *out = UINT32_C(0x10203040);
        return 0;
    default:
        return EINVAL;
    }
}

static const struct rtwn8723be_btc_policy_ops ops = {
    .snapshot = snapshot,
    .clock_msec = clock_msec,
    .aggregate_apply = aggregate_apply,
    .lps_enter = lps_enter,
    .lps_leave = lps_leave,
    .bt_query = bt_query,
    .fault = fault,
};

static void
get_value(struct rtwn8723be_btc_policy *policy, struct btc_coexist *btc,
    u8 type, void *out, bool want_result)
{
    bool source_result = !want_result;

    assert(rtwn8723be_btc_policy_get(policy, btc, type, out,
        &source_result) == 0);
    assert(source_result == want_result);
}

static void
set_value(struct rtwn8723be_btc_policy *policy, struct btc_coexist *btc,
    u8 type, void *in, bool want_result)
{
    bool source_result = !want_result;

    assert(rtwn8723be_btc_policy_set(policy, btc, type, in,
        &source_result) == 0);
    assert(source_result == want_result);
}

int
main(void)
{
    struct fixture f = {
        .snapshot = {
            .station_linked = false,
            .any_client_connected = true,
            .busy = true,
            .scanning = true,
            .linking = true,
            .in_4way = true,
            .under_5g = true,
            .ap_mode = false,
            .encryption_enabled = true,
            .under_b_mode = false,
            .rssi = -47,
            .bandwidth = BTC_WIFI_BW_HT40,
            .traffic_direction = BTC_WIFI_TRAFFIC_RX,
            .firmware_version = UINT32_C(0x778899aa),
            .dot11_channel = 0,
            .ap_count = 36,
        },
        .now_msec = 9001,
    };
    struct rtwn8723be_btc_policy policy = {0};
    struct rtwn8723be_btc_policy_ops bad = ops;
    struct btc_coexist btc = {0};
    bool value, source_result;
    u8 byte;
    u32 word;

    bad.lps_leave = NULL;
    assert(rtwn8723be_btc_policy_init(&policy, &bad, &f) == ENOSYS);
    assert(rtwn8723be_btc_policy_init(&policy, &ops, &f) == 0);
    assert(rtwn8723be_btc_policy_bind(&btc, &policy) == 0);
    assert(btc.r23be_policy == &policy);
    assert(btc.btc_get != NULL && btc.btc_set != NULL);
    btc.pwr_mode_val[0] = 0x5a;
    btc.btc_get_bt_coex_supported_version = supported_version;
    btc.btc_phydm_query_phy_counter = phy_counter;

    value = false;
    get_value(&policy, &btc, BTC_GET_BL_WIFI_CONNECTED, &value, true);
    assert(value);
    value = false;
    get_value(&policy, &btc, BTC_GET_BL_WIFI_BUSY, &value, true);
    assert(value);
    byte = 0;
    get_value(&policy, &btc, BTC_GET_BL_WIFI_DUAL_BAND_CONNECTED, &byte, true);
    assert(byte == BTC_MULTIPORT_SCC);
    byte = 0;
    get_value(&policy, &btc, BTC_GET_U1_WIFI_CENTRAL_CHNL, &byte, true);
    assert(byte == 1);
    f.snapshot.dot11_channel = 11;
    get_value(&policy, &btc, BTC_GET_U1_WIFI_DOT11_CHNL, &byte, true);
    assert(byte == 11);
    word = 0;
    get_value(&policy, &btc, BTC_GET_U4_WIFI_FW_VER, &word, true);
    assert(word == UINT32_C(0x778899aa));
    word = 0;
    get_value(&policy, &btc, BTC_GET_U4_WIFI_LINK_STATUS, &word, true);
    assert(word == ((UINT32_C(1) << 16) | WIFI_AP_CONNECTED));
    word = 0;
    get_value(&policy, &btc, BTC_GET_U4_SUPPORTED_VERSION, &word, true);
    assert(word == UINT32_C(0x11223344));
    word = 0;
    get_value(&policy, &btc, BTC_GET_U4_WIFI_IQK_OK, &word, true);
    assert(word == UINT32_C(0x100) + DM_INFO_IQK_OK);
    word = 0;
    get_value(&policy, &btc, BTC_GET_U4_BT_PATCH_VER, &word, true);
    assert(word == UINT32_C(0x1234) && f.bt_query_calls == 1 &&
        f.last_bt_query == R23BE_BTC_POLICY_BT_PATCH_VERSION);
    word = 0;
    get_value(&policy, &btc, BTC_GET_U4_BT_DEVICE_INFO, &word, true);
    assert(word == UINT32_C(0x56789abc) && f.bt_query_calls == 2 &&
        f.last_bt_query == R23BE_BTC_POLICY_BT_DEVICE_INFO);
    word = 0;
    get_value(&policy, &btc, BTC_GET_U4_BT_FORBIDDEN_SLOT_VAL, &word, true);
    assert(word == UINT32_C(0x10203040) && f.bt_query_calls == 3 &&
        f.last_bt_query == R23BE_BTC_POLICY_BT_FORBIDDEN_SLOT);
    byte = 0xa5;
    get_value(&policy, &btc, BTC_GET_U1_MAC_PHY_MODE, &byte, false);
    assert(byte == 0xa5); /* Linux leaves unsupported output unchanged. */

    value = true;
    set_value(&policy, &btc, BTC_SET_BL_BT_DISABLE, &value, true);
    assert(btc.bt_info.bt_disabled);

    f.snapshot.ap_mode = true;
    set_value(&policy, &btc, BTC_SET_ACT_ENTER_LPS, NULL, true);
    assert(f.enter_calls == 0 && !btc.bt_info.bt_ctrl_lps &&
        !btc.bt_info.bt_lps_on);
    f.snapshot.ap_mode = false;
    set_value(&policy, &btc, BTC_SET_ACT_ENTER_LPS, NULL, true);
    assert(f.enter_calls == 1 && btc.bt_info.bt_ctrl_lps &&
        btc.bt_info.bt_lps_on);
    set_value(&policy, &btc, BTC_SET_ACT_NORMAL_LPS, NULL, true);
    assert(f.leave_calls == 1 && !btc.bt_info.bt_ctrl_lps &&
        !btc.bt_info.bt_lps_on);

    value = true;
    set_value(&policy, &btc, BTC_SET_BL_BT_CTRL_AGG_SIZE, &value, true);
    byte = 7;
    set_value(&policy, &btc, BTC_SET_U1_AGG_BUF_SIZE, &byte, true);
    set_value(&policy, &btc, BTC_SET_ACT_AGGREGATE_CTRL, NULL, true);
    assert(f.aggregate_calls == 1 && btc.bt_info.pre_bt_ctrl_agg_buf_size &&
        btc.bt_info.pre_agg_buf_size == 7);
    f.now_msec = 10000;
    byte = 9;
    set_value(&policy, &btc, BTC_SET_U1_AGG_BUF_SIZE, &byte, true);
    set_value(&policy, &btc, BTC_SET_ACT_AGGREGATE_CTRL, NULL, true);
    assert(f.aggregate_calls == 1 && btc.bt_info.pre_agg_buf_size == 7);
    f.now_msec = 18002;
    set_value(&policy, &btc, BTC_SET_ACT_AGGREGATE_CTRL, NULL, true);
    assert(f.aggregate_calls == 2 && btc.bt_info.pre_agg_buf_size == 9);
    value = true;
    set_value(&policy, &btc, BTC_SET_BL_TO_REJ_AP_AGG_PKT, &value, true);
    f.now_msec = 27003;
    set_value(&policy, &btc, BTC_SET_ACT_AGGREGATE_CTRL, NULL, true);
    assert(f.aggregate_calls == 2 && btc.bt_info.pre_reject_agg_pkt);

    value = false;
    set_value(&policy, &btc, BTC_SET_BL_TO_REJ_AP_AGG_PKT, &value, true);
    f.aggregate_error = EIO;
    f.now_msec = 36004;
    source_result = true;
    assert(rtwn8723be_btc_policy_set(&policy, &btc,
        BTC_SET_ACT_AGGREGATE_CTRL, NULL, &source_result) == EIO);
    assert(!source_result && f.last_fault == EIO);
    f.aggregate_error = 0;

    source_result = true;
    assert(rtwn8723be_btc_policy_set(&policy, &btc,
        BTC_SET_ACT_GET_BT_RSSI, NULL, &source_result) == 0);
    assert(!source_result);
    source_result = false;
    assert(rtwn8723be_btc_policy_set(&policy, &btc,
        BTC_SET_MIMO_PS_MODE, NULL, &source_result) == 0);
    assert(source_result);

    f.snapshot_error = EIO;
    source_result = true;
    assert(rtwn8723be_btc_policy_get(&policy, &btc,
        BTC_GET_BL_WIFI_BUSY, &value, &source_result) == EIO);
    assert(!source_result && f.last_fault == EIO);
    value = true;
    assert(!btc.btc_get(&btc, BTC_GET_BL_WIFI_BUSY, &value));
    assert(f.fault_calls >= 2 && f.last_fault == EIO);
    f.snapshot_error = 0;

    rtwn8723be_btc_policy_fini(&policy);
    assert(rtwn8723be_btc_policy_bind(&btc, &policy) == ENXIO);
    puts("RTL_BTC_POLICY_C11_UBSAN_OK");
    return 0;
}
"""


with tempfile.TemporaryDirectory(prefix="rtl-btc-policy-") as name:
    work = Path(name)
    source_file = work / "btc_policy_check.c"
    binary = work / "btc_policy_check"
    source_file.write_text(HARNESS)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=undefined", "-fno-sanitize-recover=all",
         "-I", str(SRC), str(POLICY_C), str(source_file), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
