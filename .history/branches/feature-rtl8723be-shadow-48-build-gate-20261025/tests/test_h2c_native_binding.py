#!/usr/bin/env python3
"""Compile actual H2C NetBSD-adapter function bodies with mock MMIO/mutex.
This is host C11/UBSan, NOT a NetBSD kernel object or real PCI hardware test.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = root / "src"
native = (src / "rtwn8723be_h2c_native.c").read_text()
header = (src / "rtwn8723be_h2c_native.h").read_text()
netbsd = (src / "rtwn8723be_netbsd.c").read_text()
attach = (src / "rtwn8723be_native.c").read_text()
manifest = (root / "config/files.rtwn8723be_native").read_text()
for word in ("struct rtwn8723be_h2c_state state", "kmutex_t lock",
             "bool initialized"):
    assert word in header
for name in ("rtwn8723be_h2c.c", "rtwn8723be_h2c_native.c"):
    assert re.search(r"^file\s+dev/pci/" + re.escape(name) +
                     r"\s+rtwn8723be_native\s*$", manifest, re.M), name
assert "error = rtwn8723be_h2c_native_init(sc);" in netbsd
assert "error = rtwn8723be_btc_mp_native_init(sc);" in netbsd
assert "error = rtwn8723be_h2c_native_fw_ready(sc);" in netbsd
assert "rtwn8723be_h2c_native_reset(sc);" in netbsd
assert "rtwn8723be_h2c_native_fini(sc);" in attach
assert "struct rtwn8723be_h2c_native sc_h2c;" in (
    src / "rtwn8723be_netbsd.h").read_text()
anchor = "static bool\nr23be_h2c_mmio_ready("
assert native.count(anchor) == 1
body = native[native.index(anchor):]
regs = (src / "rtwn8723be_f16_1.h").read_text()
defines = []
for key in ("HMETFR", "HMEBOX_0", "HMEBOX_3",
            "HMEBOX_EXT_0", "HMEBOX_EXT_3"):
    match = re.search(r"^#define\s+R23BE_REG_" + key +
                      r"\s+(0x[0-9a-fA-F]+)", regs, re.M)
    assert match, key
    defines.append("#define R23BE_REG_" + key + " " + match[1])
code = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include "rtwn8723be_h2c.h"
#define MUTEX_DEFAULT 0
#define IPL_NONE 0
#define R23BE_STAGE_FIRMWARE_DOWNLOAD 3
typedef int kmutex_t;
static int mutex_count;
static void mutex_init(kmutex_t *m,int kind,int ipl) {
    assert(kind==0 && ipl==0); *m=0;
}
static void mutex_enter(kmutex_t *m) {assert(!*m); *m=1;mutex_count++;}
static void mutex_exit(kmutex_t *m) {assert(*m); *m=0;mutex_count--;}
static void mutex_destroy(kmutex_t *m) {assert(!*m);}
struct native {
    struct rtwn8723be_softc *sc;
    struct rtwn8723be_h2c_state state;
    kmutex_t lock;
    uint64_t firmware_generation;
    bool initialized;
};
struct linux_state {
    bool being_init_adapter, fw_ready, started;
    int stage;
};
struct rtwn8723be_softc {
    struct native sc_h2c;
    struct linux_state sc_linux;
    bool sc_mapped;
    size_t sc_mapsize;
    uint8_t reg[0x200];
    unsigned int reads, writes;
};
static uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *sc,size_t reg) {
    assert(mutex_count==1 && reg < sizeof(sc->reg));
    sc->reads++;return sc->reg[reg];
}
static void rtwn8723be_write_1(struct rtwn8723be_softc *sc,
                               size_t reg,uint8_t value) {
    assert(mutex_count==1 && reg < sizeof(sc->reg));
    sc->writes++;sc->reg[reg]=value;
}
static void delay(unsigned int n) {assert(n==10);}
""" + "\n".join(defines) + "\n" + body + r"""
int main(void) {
    struct rtwn8723be_softc sc={0};
    uint8_t payload[]={0x22,0x33,0x44,0x55};
    assert(rtwn8723be_h2c_native_init(&sc)==0);
    assert(rtwn8723be_h2c_native_init(&sc)==EALREADY);
    sc.sc_mapped=true;
    sc.sc_mapsize=0x200;
    assert(rtwn8723be_h2c_native_fw_ready(&sc)==EAGAIN);
    sc.sc_linux.being_init_adapter=true;
    sc.sc_linux.stage=R23BE_STAGE_FIRMWARE_DOWNLOAD;
    assert(rtwn8723be_h2c_native_fw_ready(&sc)==0);
    assert(!sc.sc_linux.fw_ready);
    assert(sc.sc_h2c.firmware_generation==1);
    assert(rtwn8723be_h2c_native_fw_ready(&sc)==EALREADY);
    assert(sc.sc_h2c.firmware_generation==1);
    assert(rtwn8723be_h2c_native_send(&sc,5,payload,4)==EAGAIN);
    sc.sc_linux.fw_ready=true;
    assert(rtwn8723be_h2c_native_send(&sc,5,payload,4)==0);
    assert(sc.reg[0x1f0]==0x55);
    assert(sc.reg[0x1d0]==5 && sc.reg[0x1d1]==0x22 &&
           sc.reg[0x1d2]==0x33 && sc.reg[0x1d3]==0x44);
    assert(sc.sc_h2c.state.next_box==1);
    sc.sc_linux.started=true;
    sc.sc_linux.being_init_adapter=false;
    assert(rtwn8723be_h2c_native_media_status(&sc,true)==0);
    assert(sc.reg[0x1d4]==1 && sc.reg[0x1d5]==1 &&
           sc.reg[0x1d6]==0 && sc.reg[0x1d7]==0);
    rtwn8723be_h2c_native_reset(&sc);
    assert(!sc.sc_h2c.state.firmware_ready);
    assert(rtwn8723be_h2c_native_send(&sc,5,payload,4)==EAGAIN);
    sc.sc_linux.being_init_adapter=true;
    sc.sc_linux.stage=R23BE_STAGE_FIRMWARE_DOWNLOAD;
    assert(rtwn8723be_h2c_native_fw_ready(&sc)==0);
    assert(sc.sc_h2c.firmware_generation==2);
    rtwn8723be_h2c_native_reset(&sc);
    sc.sc_h2c.firmware_generation=UINT64_MAX;
    assert(rtwn8723be_h2c_native_fw_ready(&sc)==EOVERFLOW);
    assert(!sc.sc_h2c.state.firmware_ready);
    sc.sc_mapped=false;
    assert(rtwn8723be_h2c_native_send(&sc,5,payload,4)==ENXIO);
    rtwn8723be_h2c_native_fini(&sc);
    assert(!sc.sc_h2c.initialized && mutex_count==0);
    puts("RTL_H2C_NATIVE_BINDING_C11_UBSAN_OK");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-h2c-native-") as tmp:
    file = Path(tmp) / "main.c"
    exe = Path(tmp) / "main"
    file.write_text(code)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all", "-I", str(src),
                    str(src / "rtwn8723be_h2c.c"), str(file), "-o", str(exe)],
                   check=True)
    subprocess.run([str(exe)], check=True)
