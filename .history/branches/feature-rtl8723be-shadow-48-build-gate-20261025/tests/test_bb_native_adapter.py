#!/usr/bin/env python3
"""Run the native BB callback with real BB/AGC/PG engines and mocked MMIO.

Checks Linux setup order, antenna selection, crystal RMW on both success
and table failure, publication, bounds, and lifecycle preflight. This is
an isolated C regression, not a hardware acceptance result.
"""
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FAKE = r"""
#ifndef _RTWN8723BE_NETBSD_H_
#define _RTWN8723BE_NETBSD_H_
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "rtwn8723be_phy_exec.h"
#include "rtwn8723be_txpwr_pg.h"
#define R23BE_STAGE_PHY_BB 40U
struct rtwn8723be_softc {
    bool sc_mapped, sc_core_initialized, sc_efuse_autoload_ok;
    bool sc_bt_ant_valid, sc_package_valid, sc_phy_identity_valid;
    bool sc_xtal_valid, sc_irq_enabled, sc_bb_valid, sc_cck_high_power;
    size_t sc_mapsize;
    uint8_t sc_package_type, sc_single_ant_path, sc_xtal_cap;
    uint8_t sc_pwrgroup_cnt;
    struct rtwn8723be_phy_identity sc_phy_identity;
    struct rtwn8723be_txpwr_pg_state sc_txpwr_pg;
    struct { bool fw_ready, being_init_adapter, started; unsigned stage; } sc_linux;
};
uint16_t rtwn8723be_read_2(struct rtwn8723be_softc *, size_t);
uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *, size_t);
void rtwn8723be_write_1(struct rtwn8723be_softc *, size_t, uint8_t);
void rtwn8723be_write_2(struct rtwn8723be_softc *, size_t, uint16_t);
void rtwn8723be_write_4(struct rtwn8723be_softc *, size_t, uint32_t);
void rtwn8723be_netbsd_set_bbreg(struct rtwn8723be_softc *, size_t, uint32_t, uint32_t);
int rtwn8723be_netbsd_phy_bb_write(void *, uint32_t, uint32_t);
int rtwn8723be_netbsd_phy_agc_write(void *, uint32_t, uint32_t);
#endif
"""

HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_netbsd.h"
int rtwn8723be_netbsd_phy_bb_config(void *);
struct event { unsigned width; size_t reg; uint32_t value; } events[500];
static unsigned count, bb_count, agc_count, delay_count;
static unsigned fail_bb, fail_agc;
static uint32_t regs[0x1000U/4U];
static void event(unsigned width, size_t reg, uint32_t value) {
    assert(count < 500U && reg < 0x1000U);
    events[count++] = (struct event){width,reg,value};
}
uint16_t rtwn8723be_read_2(struct rtwn8723be_softc *sc, size_t reg) {
    (void)sc; assert(reg == 2U); event(2,reg,0x4000U); return 0x4000U;
}
uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *sc, size_t reg) {
    (void)sc; assert(!(reg & 3U)); event(4,reg,regs[reg/4U]); return regs[reg/4U];
}
void rtwn8723be_write_1(struct rtwn8723be_softc *sc,size_t reg,uint8_t value) {
    (void)sc; event(101,reg,value);
}
void rtwn8723be_write_2(struct rtwn8723be_softc *sc,size_t reg,uint16_t value) {
    (void)sc; event(102,reg,value);
}
void rtwn8723be_write_4(struct rtwn8723be_softc *sc,size_t reg,uint32_t value) {
    (void)sc; assert(!(reg & 3U)); event(104,reg,value); regs[reg/4U] = value;
}
void rtwn8723be_netbsd_set_bbreg(struct rtwn8723be_softc *sc,
    size_t reg,uint32_t mask,uint32_t data) {
    unsigned shift=0; assert(mask != 0);
    while (((mask >> shift) & 1U) == 0) shift++;
    uint32_t old = rtwn8723be_read_4(sc,reg);
    rtwn8723be_write_4(sc,reg,(old & ~mask) | (data << shift));
}
void delay(unsigned us) { assert(us == 1U); delay_count++; }
int rtwn8723be_netbsd_phy_bb_write(void *arg,uint32_t reg,uint32_t value) {
    if (++bb_count == fail_bb) return EIO;
    rtwn8723be_write_4(arg,reg,value); delay(1); return 0;
}
int rtwn8723be_netbsd_phy_agc_write(void *arg,uint32_t reg,uint32_t value) {
    if (++agc_count == fail_agc) return EIO;
    rtwn8723be_write_4(arg,reg,value); return 0;
}
static void valid(struct rtwn8723be_softc *sc) {
    memset(sc,0,sizeof(*sc)); memset(regs,0,sizeof(regs));
    count=bb_count=agc_count=delay_count=fail_bb=fail_agc=0;
    sc->sc_mapped=sc->sc_core_initialized=sc->sc_efuse_autoload_ok=true;
    sc->sc_bt_ant_valid=sc->sc_package_valid=sc->sc_phy_identity_valid=true;
    sc->sc_xtal_valid=sc->sc_linux.fw_ready=sc->sc_linux.being_init_adapter=true;
    sc->sc_linux.stage=R23BE_STAGE_PHY_BB; sc->sc_mapsize=0x1000U;
    sc->sc_package_type=sc->sc_phy_identity.package_type=1;
    sc->sc_phy_identity.pci_interface=true; sc->sc_xtal_cap=0x5b;
    sc->sc_pwrgroup_cnt=99;
    memset(&sc->sc_txpwr_pg,0xff,sizeof(sc->sc_txpwr_pg));
    regs[0x4c/4]=0x01020304U; regs[0x2c/4]=0xa5000aa5U;
}
#define CHECK(i,w,r,v) do { assert(events[i].width==(w)); \
    assert(events[i].reg==(r)); assert(events[i].value==(v)); } while(0)
#define BLOCK(field,value,expected) do { valid(&sc); sc.field=(value); \
    sc.sc_bb_valid=true; assert(rtwn8723be_netbsd_phy_bb_config(&sc)==(expected)); \
    assert(!sc.sc_bb_valid && count==0 && bb_count==0 && agc_count==0); } while(0)
int main(void) {
    struct rtwn8723be_softc sc;
    assert(rtwn8723be_netbsd_phy_bb_config(NULL)==EINVAL);
    BLOCK(sc_mapped,false,ENXIO); BLOCK(sc_core_initialized,false,ENXIO);
    BLOCK(sc_efuse_autoload_ok,false,ENXIO); BLOCK(sc_bt_ant_valid,false,ENXIO);
    BLOCK(sc_package_valid,false,ENXIO); BLOCK(sc_phy_identity_valid,false,ENXIO);
    BLOCK(sc_xtal_valid,false,ENXIO); BLOCK(sc_irq_enabled,true,ENXIO);
    BLOCK(sc_linux.fw_ready,false,ENXIO); BLOCK(sc_linux.being_init_adapter,false,ENXIO);
    BLOCK(sc_linux.started,true,ENXIO); BLOCK(sc_linux.stage,41U,ENXIO);
    BLOCK(sc_phy_identity.pci_interface,false,ENXIO);
    BLOCK(sc_phy_identity.package_type,2U,ENXIO);
    BLOCK(sc_single_ant_path,2U,EINVAL); BLOCK(sc_mapsize,0x94bU,ENXIO);
    BLOCK(sc_mapsize,0xa00U,EINVAL); /* table closure checked before setup MMIO */
    for (unsigned antenna=0; antenna<2; ++antenna) {
        valid(&sc); sc.sc_single_ant_path=antenna;
        assert(rtwn8723be_netbsd_phy_bb_config(&sc)==0);
        assert(sc.sc_bb_valid && sc.sc_cck_high_power && sc.sc_pwrgroup_cnt==0);
        assert(bb_count==193U && agc_count==131U && delay_count==193U);
        CHECK(0,2,2U,0x4000U); CHECK(1,102,2U,0x6003U);
        CHECK(2,101,0x1fU,7U); CHECK(3,101,2U,0xe3U);
        CHECK(4,4,0x4cU,0x01020304U); CHECK(5,104,0x4cU,0x01820304U);
        CHECK(6,101,0x25U,0x80U); CHECK(7,104,0x948U,antenna ? 0U : 0x280U);
        assert(events[count-3].reg==0x824U && events[count-3].width==4U);
        assert(regs[0x2c/4U]==((0xa5000aa5U & ~0xfff000U) | (0x6dbU << 12)));
        assert(sc.sc_txpwr_pg.offset[1][3][3][11]==0U);
        assert(sc.sc_txpwr_pg.base24[0][0][1]!=0U);
    }
    valid(&sc); fail_bb=1; sc.sc_bb_valid=true;
    assert(rtwn8723be_netbsd_phy_bb_config(&sc)==EIO);
    assert(!sc.sc_bb_valid && bb_count==1U && agc_count==0U);
    assert(events[count-1].reg==0x2cU); /* Linux programs crystal after table error */
    valid(&sc); fail_agc=1;
    assert(rtwn8723be_netbsd_phy_bb_config(&sc)==EIO);
    assert(!sc.sc_bb_valid && bb_count==193U && agc_count==1U);
    assert(sc.sc_pwrgroup_cnt==0U && events[count-1].reg==0x2cU);
    puts("RTL_BB_NATIVE_C11_UBSAN_OK: Linux order, PG, antenna, bounds, errors");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-bb-native-") as directory:
    target = Path(directory)
    for header in ("rtwn8723be_os_compat.h", "rtwn8723be_phy_exec.h",
                   "rtwn8723be_phy_bb_sequence.h", "rtwn8723be_txpwr_pg.h"):
        shutil.copyfile(SRC / header, target / header)
    native_header = SRC / "rtwn8723be_bb_native.h"
    if native_header.exists():
        shutil.copyfile(native_header, target / native_header.name)
    (target / "sys").mkdir()
    (target / "sys/systm.h").write_text("void delay(unsigned int);\n")
    if platform.system() != "NetBSD":
        (target / "sys/errno.h").write_text("#include <errno.h>\n")
    (target / "rtwn8723be_netbsd.h").write_text(FAKE)
    (target / "harness.c").write_text(HARNESS)
    sources = [str(target / "harness.c")]
    native = SRC / "rtwn8723be_bb_native.c"
    if native.exists():
        (target / "native.c").write_text(
            '#define __KERNEL_RCSID(a,b) _Static_assert(1, "kernel rcsid")\n' + native.read_text())
        sources.append(str(target / "native.c"))
    sources.extend(str(SRC / f) for f in (
        "rtwn8723be_phy_bb_sequence.c", "rtwn8723be_phy_exec.c", "rtwn8723be_txpwr_pg.c"))
    binary = target / "bb-test"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                    "-fsanitize=undefined", "-fno-sanitize-recover=all",
                    "-I", str(target), *sources, "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
