#!/usr/bin/env python3
"""Compile the actual NetBSD EFUSE identity callback, exercising its guards.

Strict C11/UBSan with mocked register/EFUSE I/O, NOT a hardware runtime test.
"""
from pathlib import Path
import subprocess
import tempfile

src = Path(__file__).resolve().parents[1] / "src"
body = (src / "rtwn8723be_netbsd.c").read_text()
start = body.index("int\nrtwn8723be_netbsd_read_eeprom_info(void *arg)")
stop = body.index("\nint\nrtwn8723be_netbsd_init_sw_vars(void *arg)", start)
body = body[start:stop]

code = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#define RTWN8723BE_PACKAGE_DEFAULT 0
#define RTWN8723BE_ANT_MAIN 0
#define RTWN8723BE_ANT_AUX 1
#define R23BE_REG_SYS_CFG1 0xfc
#define R23BE_REG_SYS_CFG 0xf0
#define R23BE_REG_9346CR 0x0a
#define R23BE_REG_MULTI_FUNC_CTRL 0x68
#define R23BE_EEPROM_ID 0x8129
#define R23BE_EEPROM_VID 0xd6
#define R23BE_EEPROM_DID 0xd8
#define R23BE_EEPROM_SVID 0xda
#define R23BE_EEPROM_SMID 0xdc
#define R23BE_EEPROM_MAC_ADDR 0xd0
#define R23BE_EEPROM_RF_BT_SETTING 0xc3
#define R23BE_EEPROM_XTAL_8723BE 0xb9
struct rtwn8723be_phy_identity {
    uint8_t cut_version, package_type, board_type;
    uint8_t type_glna, type_gpa, type_alna, type_apa;
    bool pci_interface;
};
struct rtwn8723be_softc {
    bool sc_mapped, sc_package_valid, sc_phy_identity_valid;
    bool sc_rf_path_count_valid, sc_xtal_valid;
    bool sc_rf_chnlval_valid, sc_bb_valid;
    bool sc_bt_ant_valid, sc_boot_from_efuse, sc_efuse_autoload_ok;
    bool sc_btcoexist, sc_led_opendrain;
    uint8_t sc_package_type, sc_rf_path_count, sc_xtal_cap;
    uint8_t sc_btdm_ant_num, sc_single_ant_path;
    uint16_t sc_eeprom_id, sc_eeprom_vid, sc_eeprom_did;
    uint16_t sc_eeprom_svid, sc_eeprom_smid;
    uint8_t sc_efuse_map[512], sc_macaddr[6];
    struct rtwn8723be_phy_identity sc_phy_identity;
    uint8_t cr9346, injected_package;
    uint32_t syscfg1, syscfg, multi;
    int shadow_error, package_error;
    unsigned int shadow_reads, package_reads;
};
static uint16_t rtwn8723be_le16(const uint8_t *p) {
    return (uint16_t)(p[0] | (uint16_t)(p[1] << 8));
}
static uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *sc,
                                 uint32_t reg) {
    assert(reg == R23BE_REG_9346CR);
    return sc->cr9346;
}
static uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *sc,
                                  uint32_t reg) {
    switch (reg) {
    case R23BE_REG_SYS_CFG1: return sc->syscfg1;
    case R23BE_REG_SYS_CFG: return sc->syscfg;
    case R23BE_REG_MULTI_FUNC_CTRL: return sc->multi;
    default: assert(0); return 0;
    }
}
static int rtwn8723be_netbsd_efuse_shadow_read(
    struct rtwn8723be_softc *sc) {
    sc->shadow_reads++;
    return sc->shadow_error;
}
static int rtwn8723be_netbsd_package_power(void *ctx, bool enabled) {
    assert(ctx != NULL); (void)enabled; return 0;
}
static int rtwn8723be_netbsd_package_read_byte(
    void *ctx, uint16_t address, uint8_t *result) {
    assert(ctx != NULL && address == 0x1fb && result != NULL);
    *result = 5; return 0;
}
typedef int (*power_fn)(void *, bool);
typedef int (*read_fn)(void *, uint16_t, uint8_t *);
static int rtwn8723be_package_read(void *ctx, power_fn p,
    read_fn r, uint8_t *value) {
    struct rtwn8723be_softc *sc = ctx;
    assert(p != NULL && r != NULL && value != NULL);
    sc->package_reads++;
    if (sc->package_error) return sc->package_error;
    *value = sc->injected_package;
    return 0;
}
""" + body + r"""
static struct rtwn8723be_softc seed(void) {
    struct rtwn8723be_softc sc = {0};
    sc.sc_mapped = true;
    sc.sc_rf_chnlval_valid = sc.sc_bb_valid = true;
    sc.cr9346 = 0x20;
    sc.syscfg1 = 0x06;
    sc.syscfg = 0xa000;
    sc.multi = 1u << 18;
    sc.sc_efuse_map[0] = 0x29;
    sc.sc_efuse_map[1] = 0x81;
    sc.sc_efuse_map[R23BE_EEPROM_MAC_ADDR] = 0x02;
    sc.sc_efuse_map[R23BE_EEPROM_MAC_ADDR + 5] = 0x89;
    sc.sc_efuse_map[R23BE_EEPROM_RF_BT_SETTING] = 0x41;
    sc.sc_efuse_map[R23BE_EEPROM_XTAL_8723BE] = 0xff;
    sc.injected_package = 2;
    return sc;
}
int main(void) {
    struct rtwn8723be_softc sc = seed();
    assert(rtwn8723be_netbsd_read_eeprom_info(&sc) == 0);
    assert(!sc.sc_rf_chnlval_valid && !sc.sc_bb_valid);
    assert(sc.sc_package_valid && sc.sc_package_type == 2);
    assert(sc.sc_phy_identity_valid && sc.sc_rf_path_count_valid);
    assert(sc.sc_rf_path_count == 1);
    assert(sc.sc_phy_identity.cut_version == 10);
    assert(sc.sc_phy_identity.package_type == 2);
    assert(sc.sc_phy_identity.board_type == 4);
    assert(sc.sc_phy_identity.pci_interface);
    assert(sc.sc_phy_identity.type_glna == 0 &&
           sc.sc_phy_identity.type_gpa == 0 &&
           sc.sc_phy_identity.type_alna == 0 &&
           sc.sc_phy_identity.type_apa == 0);
    assert(sc.sc_bt_ant_valid && sc.sc_btdm_ant_num == 1 &&
           sc.sc_single_ant_path == RTWN8723BE_ANT_AUX);
    assert(sc.sc_xtal_valid && sc.sc_xtal_cap == 0x20);
    assert(sc.shadow_reads == 1 && sc.package_reads == 1);

    sc.sc_mapped = false;
    sc.sc_rf_chnlval_valid = sc.sc_bb_valid = true;
    assert(rtwn8723be_netbsd_read_eeprom_info(&sc) == ENXIO);
    assert(!sc.sc_package_valid && !sc.sc_phy_identity_valid &&
           !sc.sc_rf_path_count_valid && !sc.sc_xtal_valid &&
           !sc.sc_bt_ant_valid && !sc.sc_rf_chnlval_valid && !sc.sc_bb_valid);

    sc = seed(); sc.syscfg1 = 0;
    assert(rtwn8723be_netbsd_read_eeprom_info(&sc) == ENODEV);
    assert(sc.shadow_reads == 0 && sc.package_reads == 0 &&
           !sc.sc_phy_identity_valid);

    sc = seed(); sc.shadow_error = EIO;
    assert(rtwn8723be_netbsd_read_eeprom_info(&sc) == EIO);
    assert(!sc.sc_phy_identity_valid && !sc.sc_rf_path_count_valid);

    sc = seed(); sc.package_error = EIO;
    assert(rtwn8723be_netbsd_read_eeprom_info(&sc) == EIO);
    assert(!sc.sc_package_valid && !sc.sc_phy_identity_valid &&
           !sc.sc_rf_path_count_valid);

    sc = seed(); sc.sc_efuse_map[R23BE_EEPROM_XTAL_8723BE] = 0x32;
    sc.multi = 0; sc.syscfg = 0x3000;
    assert(rtwn8723be_netbsd_read_eeprom_info(&sc) == 0);
    assert(sc.sc_xtal_cap == 0x32);
    assert(sc.sc_phy_identity.cut_version == 3);
    assert(sc.sc_phy_identity.board_type == 0);
    puts("RTL_PHY_IDENTITY_NATIVE_C11_UBSAN_OK");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-phy-identity-") as tmp:
    source = Path(tmp) / "harness.c"
    binary = Path(tmp) / "harness"
    source.write_text(code)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all", str(source), "-o",
                    str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
