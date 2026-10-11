#!/usr/bin/env python3
"""Behavior contract for the pure BTC context-preparation boundary.

The context builder is deliberately only an atomic composition boundary.  It
receives a fully parsed identity plus abstract low-level and policy binders,
and returns a complete ``btc_coexist`` object only after every callback has
passed the existing engine gate.  It does not own, start, or discover any
hardware lifecycle.
"""
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CONTEXT_H = SRC / "rtwn8723be_btc_context.h"
CONTEXT_C = SRC / "rtwn8723be_btc_context.c"
ENGINE_C = SRC / "rtwn8723be_btc_engine.c"
MANIFEST = ROOT / "config" / "files.rtwn8723be_native"
NETBSD_C = SRC / "rtwn8723be_netbsd.c"


# A missing pure boundary must fail before any lower-level or policy binder
# can be mistaken for an attach/start implementation.
assert CONTEXT_H.is_file(), "missing BTC context boundary header"
assert CONTEXT_C.is_file(), "missing BTC context boundary source"

header = CONTEXT_H.read_text()
source = CONTEXT_C.read_text()
manifest = MANIFEST.read_text()

for needle in (
        "struct rtwn8723be_btc_context_identity",
        "struct rtwn8723be_btc_context_binder",
        "struct rtwn8723be_btc_context_binders",
        "rtwn8723be_btc_context_build",
        "R23BE_BTC_RAW_ANT_X2",
        "R23BE_BTC_RAW_ANT_X1"):
    assert needle in header, needle

# This boundary must remain portable and inert: it is not allowed to absorb
# the unfinished owner, softc, queue, interrupt, DMA, or net80211 lifecycle.
for forbidden in (
        "rtwn8723be_netbsd.h", "rtwn8723be_btc_native", "seed_lowlevel",
        "bt_prepare", "net80211", "ieee80211", "workqueue", "bus_",
        "dma", "pci_", "irq", "interrupt"):
    assert forbidden not in source.lower(), forbidden
assert ".bt_prepare =" not in NETBSD_C.read_text()

native_units = re.findall(
    r"^file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native$",
    manifest, re.M)
assert native_units.count("rtwn8723be_btc_context.c") == 1
assert len(native_units) == 48 and len(set(native_units)) == 48


HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "rtwn8723be_btc_context.h"
#include "rtwn8723be_btc_engine.h"

struct fixture {
    unsigned low_calls;
    unsigned policy_calls;
    unsigned sequence[2];
    int low_error;
    int policy_error;
    unsigned mode;
    struct rtwn8723be_btc_context_identity *identity_alias;
};

enum fixture_mode {
    FIXTURE_COMPLETE = 0,
    FIXTURE_PARTIAL_LOWLEVEL,
    FIXTURE_LOWLEVEL_PREBINDS_POLICY,
    FIXTURE_MUTATE_BINDED,
    FIXTURE_MUTATE_INITIALIZED,
    FIXTURE_MUTATE_STATE,
    FIXTURE_MUTATE_ADAPTER,
    FIXTURE_MUTATE_INTERFACE,
    FIXTURE_MUTATE_CONTEXT_FLAGS,
    FIXTURE_MUTATE_IDENTITY,
    FIXTURE_POLICY_MUTATES_IDENTITY,
    FIXTURE_POLICY_REPLACES_LOWLEVEL,
};

static u8 read_1(void *ctx, u32 reg) { (void)ctx; (void)reg; return 0; }
static u8 read_1_replaced(void *ctx, u32 reg)
{ (void)ctx; (void)reg; return 1; }
static void write_1(void *ctx, u32 reg, u32 value)
{ (void)ctx; (void)reg; (void)value; }
static void write_1_mask(void *ctx, u32 reg, u32 mask, u8 value)
{ (void)ctx; (void)reg; (void)mask; (void)value; }
static u16 read_2(void *ctx, u32 reg) { (void)ctx; (void)reg; return 0; }
static void write_2(void *ctx, u32 reg, u16 value)
{ (void)ctx; (void)reg; (void)value; }
static u32 read_4(void *ctx, u32 reg) { (void)ctx; (void)reg; return 0; }
static void write_4(void *ctx, u32 reg, u32 value)
{ (void)ctx; (void)reg; (void)value; }
static void write_local_1(void *ctx, u32 reg, u8 value)
{ (void)ctx; (void)reg; (void)value; }
static void set_bb(void *ctx, u32 reg, u32 mask, u32 value)
{ (void)ctx; (void)reg; (void)mask; (void)value; }
static u32 get_bb(void *ctx, u32 reg, u32 mask)
{ (void)ctx; (void)reg; (void)mask; return 0; }
static void set_rf(void *ctx, u8 path, u32 reg, u32 mask, u32 value)
{ (void)ctx; (void)path; (void)reg; (void)mask; (void)value; }
static u32 get_rf(void *ctx, u8 path, u32 reg, u32 mask)
{ (void)ctx; (void)path; (void)reg; (void)mask; return 0; }
static void fill_h2c(void *ctx, u8 id, u32 length, u8 *buffer)
{ (void)ctx; (void)id; (void)length; (void)buffer; }
static void display(void *ctx, u8 type, struct seq_file *seq)
{ (void)ctx; (void)type; (void)seq; }
static bool get_value(void *ctx, u8 type, void *value)
{ (void)ctx; (void)type; (void)value; return true; }
static bool set_value(void *ctx, u8 type, void *value)
{ (void)ctx; (void)type; (void)value; return true; }
static void set_bt_reg(void *ctx, u8 type, u32 offset, u32 value)
{ (void)ctx; (void)type; (void)offset; (void)value; }
static u32 get_bt_reg(void *ctx, u8 type, u32 offset)
{ (void)ctx; (void)type; (void)offset; return 0; }
static u32 get_feature(void *ctx) { (void)ctx; return 0; }
static u32 get_version(void *ctx) { (void)ctx; return 0; }
static u32 get_phydm_version(void *ctx) { (void)ctx; return 0; }
static void modify_ra(void *ctx, u8 direction, u8 offset)
{ (void)ctx; (void)direction; (void)offset; }
static u32 query_phy(void *ctx, enum dm_info_query id)
{ (void)ctx; (void)id; return 0; }
static u8 get_ant_det(void *ctx) { (void)ctx; return 0; }
static u8 get_ble_type(void *ctx) { (void)ctx; return 0; }
static u32 get_ble_parameters(void *ctx, u8 type)
{ (void)ctx; (void)type; return 0; }
static bool get_afh(void *ctx, u8 type, u8 *map)
{ (void)ctx; (void)type; (void)map; return true; }
static void delay_ms(void *ctx, unsigned int delay)
{ (void)ctx; (void)delay; }

static int
bind_lowlevel(void *arg, struct btc_coexist *btc)
{
    struct fixture *fixture = arg;

    ++fixture->low_calls;
    fixture->sequence[0] = fixture->low_calls + fixture->policy_calls;
    if (fixture->low_error != 0)
        return fixture->low_error;
    btc->btc_read_1byte = read_1;
    btc->btc_write_1byte = write_1;
    btc->btc_write_1byte_bitmask = write_1_mask;
    btc->btc_read_2byte = read_2;
    btc->btc_write_2byte = write_2;
    btc->btc_read_4byte = read_4;
    btc->btc_write_4byte = write_4;
    btc->btc_write_local_reg_1byte = write_local_1;
    btc->btc_set_bb_reg = set_bb;
    btc->btc_get_bb_reg = get_bb;
    btc->btc_set_rf_reg = set_rf;
    btc->btc_get_rf_reg = get_rf;
    btc->btc_fill_h2c = fill_h2c;
    btc->btc_disp_dbg_msg = display;
    btc->btc_set_bt_reg = set_bt_reg;
    btc->btc_get_bt_reg = get_bt_reg;
    btc->btc_get_bt_coex_supported_feature = get_feature;
    btc->btc_get_bt_coex_supported_version = get_version;
    btc->btc_get_bt_phydm_version = get_phydm_version;
    btc->btc_phydm_modify_ra_pcr_threshold = modify_ra;
    btc->btc_phydm_query_phy_counter = query_phy;
    btc->btc_get_ant_det_val_from_bt = get_ant_det;
    btc->btc_get_ble_scan_type_from_bt = get_ble_type;
    btc->btc_get_ble_scan_para_from_bt = get_ble_parameters;
    btc->btc_get_bt_afh_map_from_bt = get_afh;
    btc->r23be_delay_ms = delay_ms;

    if (fixture->mode == FIXTURE_PARTIAL_LOWLEVEL)
        btc->btc_get_ble_scan_para_from_bt = NULL;
    if (fixture->mode == FIXTURE_LOWLEVEL_PREBINDS_POLICY) {
        btc->btc_get = get_value;
        btc->btc_set = set_value;
    }
    if (fixture->mode == FIXTURE_MUTATE_BINDED)
        btc->binded = false;
    if (fixture->mode == FIXTURE_MUTATE_INITIALIZED)
        btc->initialized = true;
    if (fixture->mode == FIXTURE_MUTATE_STATE)
        btc->r23be_state = fixture;
    if (fixture->mode == FIXTURE_MUTATE_ADAPTER)
        btc->adapter = fixture;
    if (fixture->mode == FIXTURE_MUTATE_INTERFACE)
        btc->chip_interface = BTC_INTF_USB;
    if (fixture->mode == FIXTURE_MUTATE_CONTEXT_FLAGS) {
        btc->stop_coex_dm = true;
        btc->manual_control = true;
    }
    if (fixture->mode == FIXTURE_MUTATE_IDENTITY) {
        assert(fixture->identity_alias != NULL);
        fixture->identity_alias->raw_ant_num = R23BE_BTC_RAW_ANT_X1;
    }
    return 0;
}

static int
bind_policy(void *arg, struct btc_coexist *btc)
{
    struct fixture *fixture = arg;

    ++fixture->policy_calls;
    fixture->sequence[1] = fixture->low_calls + fixture->policy_calls;
    if (fixture->policy_error != 0)
        return fixture->policy_error;
    btc->btc_get = get_value;
    btc->btc_set = set_value;
    if (fixture->mode == FIXTURE_POLICY_MUTATES_IDENTITY) {
        assert(fixture->identity_alias != NULL);
        fixture->identity_alias->raw_ant_num = R23BE_BTC_RAW_ANT_X1;
    }
    if (fixture->mode == FIXTURE_POLICY_REPLACES_LOWLEVEL)
        btc->btc_read_1byte = read_1_replaced;
    return 0;
}

/* The context test calls the real engine callback gate.  These stubs only
 * satisfy unrelated algorithm-dispatch symbols in the separately linked
 * engine object; the test never executes the algorithms. */
#define STUB0(name) void name(struct btc_coexist *btc) { (void)btc; }
#define STUB1(name) void name(struct btc_coexist *btc, u8 type) \
    { (void)btc; (void)type; }
#define STUB_INFO(name) void name(struct btc_coexist *btc, u8 *buf, u8 len) \
    { (void)btc; (void)buf; (void)len; }
#define STUB_DISPLAY(name) void name(struct btc_coexist *btc, struct seq_file *seq) \
    { (void)btc; (void)seq; }
STUB0(ex_btc8723b1ant_power_on_setting)
void ex_btc8723b1ant_init_hwconfig(struct btc_coexist *btc, bool wifi_only)
{ (void)btc; (void)wifi_only; }
STUB0(ex_btc8723b1ant_init_coex_dm)
STUB1(ex_btc8723b1ant_ips_notify)
STUB1(ex_btc8723b1ant_lps_notify)
STUB1(ex_btc8723b1ant_scan_notify)
STUB1(ex_btc8723b1ant_connect_notify)
STUB1(ex_btc8723b1ant_media_status_notify)
STUB1(ex_btc8723b1ant_special_packet_notify)
STUB_INFO(ex_btc8723b1ant_bt_info_notify)
STUB1(ex_btc8723b1ant_rf_status_notify)
STUB0(ex_btc8723b1ant_halt_notify)
STUB1(ex_btc8723b1ant_pnp_notify)
STUB0(ex_btc8723b1ant_periodical)
STUB_DISPLAY(ex_btc8723b1ant_display_coex_info)
STUB0(ex_btc8723b2ant_power_on_setting)
STUB0(ex_btc8723b2ant_pre_load_firmware)
STUB0(ex_btc8723b2ant_init_hwconfig)
STUB0(ex_btc8723b2ant_init_coex_dm)
STUB1(ex_btc8723b2ant_ips_notify)
STUB1(ex_btc8723b2ant_lps_notify)
STUB1(ex_btc8723b2ant_scan_notify)
STUB1(ex_btc8723b2ant_connect_notify)
STUB1(ex_btc8723b2ant_media_status_notify)
STUB1(ex_btc8723b2ant_special_packet_notify)
STUB_INFO(ex_btc8723b2ant_bt_info_notify)
STUB0(ex_btc8723b2ant_halt_notify)
STUB1(ex_btc8723b2ant_pnp_notify)
STUB0(ex_btc8723b2ant_periodical)
STUB_DISPLAY(ex_btc8723b2ant_display_coex_info)

static void
seed_sentinel(struct btc_coexist *out)
{
    memset(out, 0xa5, sizeof(*out));
}

static void
assert_unchanged(const struct btc_coexist *out,
    const struct btc_coexist *before)
{
    assert(memcmp(out, before, sizeof(*out)) == 0);
}

static struct rtwn8723be_btc_context_binders
complete_binders(struct fixture *fixture)
{
    const struct rtwn8723be_btc_context_binders binders = {
        .lowlevel = { .bind = bind_lowlevel, .arg = fixture },
        .policy = { .bind = bind_policy, .arg = fixture },
    };

    return binders;
}

static void
check_two_antenna_defaults(void)
{
    int adapter_marker;
    struct fixture fixture = {0};
    const struct rtwn8723be_btc_context_identity identity = {
        .adapter = &adapter_marker,
        .identity_valid = true,
        .hwpg_bt_present = false,
        .raw_ant_num = R23BE_BTC_RAW_ANT_X2,
        .single_ant_path = 1,
        .package_type = 2,
    };
    const struct rtwn8723be_btc_context_binders binders =
        complete_binders(&fixture);
    struct btc_coexist out = {0};

    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) == 0);
    assert(fixture.low_calls == 1 && fixture.policy_calls == 1);
    assert(fixture.sequence[0] == 1 && fixture.sequence[1] == 2);
    assert(out.binded && out.adapter == &adapter_marker);
    assert(out.chip_interface == BTC_INTF_PCI);
    assert(out.statistics.cnt_bind == 1);
    assert(out.board_info.bt_chip_type == BTC_CHIP_RTL8723B);
    assert(out.board_info.pg_ant_num == 2 && out.board_info.btdm_ant_num == 2);
    assert(out.board_info.single_ant_path == 1);
    assert(out.board_info.btdm_ant_pos == BTC_ANTENNA_AT_MAIN_PORT);
    assert(out.board_info.tfbga_package);
    assert(!out.bt_info.bt_ctrl_buf_size && out.bt_info.agg_buf_size == 5);
    assert(!out.bt_info.increase_scan_dev_num && !out.bt_info.miracast_plus_bt);
    assert(!out.bt_info.bt_ctrl_agg_buf_size);
    assert(!out.initialized && out.r23be_state == NULL);
    assert(rtwn8723be_btc_callbacks_ready(&out) == 0);
}

static void
check_one_antenna_mapping(void)
{
    int adapter_marker;
    struct fixture fixture = {0};
    const struct rtwn8723be_btc_context_identity identity = {
        .adapter = &adapter_marker,
        .identity_valid = true,
        .hwpg_bt_present = true,
        .raw_ant_num = R23BE_BTC_RAW_ANT_X1,
        .single_ant_path = 0,
        .package_type = 1,
    };
    const struct rtwn8723be_btc_context_binders binders =
        complete_binders(&fixture);
    struct btc_coexist out = {0};

    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) == 0);
    assert(out.board_info.pg_ant_num == 1 && out.board_info.btdm_ant_num == 1);
    assert(out.board_info.single_ant_path == 0);
    assert(!out.board_info.tfbga_package);
}

static void
check_failures_are_atomic(void)
{
    int adapter_marker;
    struct fixture fixture = {0};
    struct rtwn8723be_btc_context_identity identity = {
        .adapter = &adapter_marker,
        .identity_valid = true,
        .hwpg_bt_present = false,
        .raw_ant_num = R23BE_BTC_RAW_ANT_X2,
        .single_ant_path = 0,
        .package_type = 1,
    };
    struct rtwn8723be_btc_context_binders binders = complete_binders(&fixture);
    struct btc_coexist out, before;

    assert(rtwn8723be_btc_context_build(NULL, &identity, &binders) == EINVAL);
    assert(fixture.low_calls == 0 && fixture.policy_calls == 0);
    seed_sentinel(&out); before = out;
    assert(rtwn8723be_btc_context_build(&out, NULL, &binders) == EINVAL);
    assert(fixture.low_calls == 0 && fixture.policy_calls == 0);
    assert_unchanged(&out, &before);
    seed_sentinel(&out); before = out;
    assert(rtwn8723be_btc_context_build(&out, &identity, NULL) == EINVAL);
    assert(fixture.low_calls == 0 && fixture.policy_calls == 0);
    assert_unchanged(&out, &before);

    seed_sentinel(&out); before = out;
    binders.lowlevel.bind = NULL;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) == ENOSYS);
    assert_unchanged(&out, &before);

    binders = complete_binders(&fixture);
    binders.policy.bind = NULL;
    seed_sentinel(&out); before = out;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) == ENOSYS);
    assert(fixture.low_calls == 0 && fixture.policy_calls == 0);
    assert_unchanged(&out, &before);

    binders = complete_binders(&fixture);
    seed_sentinel(&out); before = out;
    fixture.low_error = EIO;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) == EIO);
    assert(fixture.policy_calls == 0);
    assert_unchanged(&out, &before);
    fixture.low_error = 0;

    seed_sentinel(&out); before = out;
    fixture.policy_error = EBUSY;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) == EBUSY);
    assert_unchanged(&out, &before);
    fixture.policy_error = 0;

    for (fixture.mode = FIXTURE_PARTIAL_LOWLEVEL;
         fixture.mode <= FIXTURE_MUTATE_INTERFACE; ++fixture.mode) {
        seed_sentinel(&out); before = out;
        assert(rtwn8723be_btc_context_build(&out, &identity, &binders) != 0);
        assert_unchanged(&out, &before);
    }
    fixture.mode = FIXTURE_COMPLETE;
    fixture.low_calls = 0;
    fixture.policy_calls = 0;

    seed_sentinel(&out); before = out;
    identity.identity_valid = false;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) == ENXIO);
    assert(fixture.low_calls == 0 && fixture.policy_calls == 0);
    assert_unchanged(&out, &before);
    identity.identity_valid = true;
    identity.raw_ant_num = 2;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) == EINVAL);
    assert(fixture.low_calls == 0 && fixture.policy_calls == 0);
    assert_unchanged(&out, &before);
    identity.raw_ant_num = R23BE_BTC_RAW_ANT_X2;
    identity.single_ant_path = 2;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) == EINVAL);
    assert(fixture.low_calls == 0 && fixture.policy_calls == 0);
    assert_unchanged(&out, &before);
    identity.single_ant_path = 0;
    identity.adapter = NULL;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) == EINVAL);
    assert(fixture.low_calls == 0 && fixture.policy_calls == 0);
    assert_unchanged(&out, &before);
    identity.adapter = &adapter_marker;

    fixture.mode = FIXTURE_MUTATE_CONTEXT_FLAGS;
    seed_sentinel(&out); before = out;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) != 0);
    assert_unchanged(&out, &before);

    fixture.mode = FIXTURE_MUTATE_IDENTITY;
    fixture.identity_alias = &identity;
    seed_sentinel(&out); before = out;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) != 0);
    assert_unchanged(&out, &before);
    assert(identity.raw_ant_num == R23BE_BTC_RAW_ANT_X1);
    identity.raw_ant_num = R23BE_BTC_RAW_ANT_X2;
    fixture.identity_alias = NULL;

    fixture.mode = FIXTURE_POLICY_MUTATES_IDENTITY;
    fixture.identity_alias = &identity;
    seed_sentinel(&out); before = out;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) != 0);
    assert_unchanged(&out, &before);
    assert(identity.raw_ant_num == R23BE_BTC_RAW_ANT_X1);
    identity.raw_ant_num = R23BE_BTC_RAW_ANT_X2;
    fixture.identity_alias = NULL;

    fixture.mode = FIXTURE_POLICY_REPLACES_LOWLEVEL;
    seed_sentinel(&out); before = out;
    assert(rtwn8723be_btc_context_build(&out, &identity, &binders) != 0);
    assert_unchanged(&out, &before);
    fixture.mode = FIXTURE_COMPLETE;
}

int
main(void)
{
    check_two_antenna_defaults();
    check_one_antenna_mapping();
    check_failures_are_atomic();
    puts("RTL_BTC_CONTEXT_C11_UBSAN_OK");
    return 0;
}
"""


with tempfile.TemporaryDirectory(prefix="rtl-btc-context-") as name:
    work = Path(name)
    source_file = work / "btc_context_check.c"
    engine_object = work / "btc_engine_check.o"
    binary = work / "btc_context_check"
    source_file.write_text(HARNESS)
    # The existing dispatch source intentionally uses GNU empty variadic-macro
    # calls.  Compile that existing object in its established GNU mode, while
    # keeping this new pure boundary and its C harness strict C11/UBSan.
    subprocess.run(
        ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
         "-fsanitize=undefined", "-fno-sanitize-recover=all",
         "-I", str(SRC), "-c", str(ENGINE_C), "-o", str(engine_object)],
        check=True,
    )
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=undefined", "-fno-sanitize-recover=all",
         "-I", str(SRC), str(CONTEXT_C), str(source_file), str(engine_object),
         "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
