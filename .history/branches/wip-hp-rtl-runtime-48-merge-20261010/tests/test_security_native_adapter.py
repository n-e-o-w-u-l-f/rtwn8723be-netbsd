#!/usr/bin/env python3
"""Execute the native Linux security-config callback with mocked byte MMIO.

Software crypto follows the upstream deliberate no-write branch. The native
policy must first be established by the OS network adapter; no implicit default
may enable hardware crypto. CAM key lifecycle and traffic acceptance are separate.
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
#define R23BE_STAGE_SECURITY 34U
struct rtwn8723be_softc {
 bool sc_mapped, sc_core_initialized, sc_bb_valid, sc_rf_chnlval_valid;
 bool sc_efuse_autoload_ok, sc_package_valid, sc_phy_identity_valid;
 bool sc_irq_enabled, sc_security_policy_valid, sc_security_configured;
 bool sc_hw_security_enabled, sc_sw_crypto, sc_use_sw_sec, sc_use_defaultkey;
 size_t sc_mapsize;
 uint8_t sc_package_type;
 struct { bool pci_interface; uint8_t package_type; } sc_phy_identity;
 struct { bool fw_ready, being_init_adapter, started, mac_func_enable; unsigned stage; } sc_linux;
};
void rtwn8723be_write_1(struct rtwn8723be_softc *, size_t, uint8_t);
#endif
"""
HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_netbsd.h"
int rtwn8723be_netbsd_enable_hw_security(void *);
static unsigned count;
static size_t registers[2];
static uint8_t values[2];
void rtwn8723be_write_1(struct rtwn8723be_softc *sc,size_t reg,uint8_t value) {
 (void)sc;assert(count<2);registers[count]=reg;values[count++]=value;
}
static void valid(struct rtwn8723be_softc *sc) {
 memset(sc,0,sizeof(*sc));count=0;
 sc->sc_mapped=sc->sc_core_initialized=sc->sc_bb_valid=sc->sc_rf_chnlval_valid=true;
 sc->sc_efuse_autoload_ok=sc->sc_package_valid=sc->sc_phy_identity_valid=true;
 sc->sc_security_policy_valid=true;sc->sc_mapsize=0x1000;
 sc->sc_linux.fw_ready=sc->sc_linux.being_init_adapter=sc->sc_linux.mac_func_enable=true;
 sc->sc_linux.stage=R23BE_STAGE_SECURITY;
 sc->sc_package_type=sc->sc_phy_identity.package_type=1;sc->sc_phy_identity.pci_interface=true;
}
#define BLOCK(field,val) do {valid(&sc);sc.field=(val);sc.sc_security_configured=sc.sc_hw_security_enabled=true; \
 assert(rtwn8723be_netbsd_enable_hw_security(&sc)==ENXIO); \
 assert(!sc.sc_security_configured && !sc.sc_hw_security_enabled && count==0);}while(0)
int main(void) {
 struct rtwn8723be_softc sc;
 assert(rtwn8723be_netbsd_enable_hw_security(NULL)==EINVAL);
 BLOCK(sc_mapped,false);BLOCK(sc_core_initialized,false);BLOCK(sc_bb_valid,false);
 BLOCK(sc_rf_chnlval_valid,false);BLOCK(sc_efuse_autoload_ok,false);BLOCK(sc_package_valid,false);
 BLOCK(sc_phy_identity_valid,false);BLOCK(sc_phy_identity.pci_interface,false);
 BLOCK(sc_phy_identity.package_type,2);BLOCK(sc_linux.fw_ready,false);
 BLOCK(sc_linux.being_init_adapter,false);BLOCK(sc_linux.mac_func_enable,false);
 BLOCK(sc_linux.started,true);BLOCK(sc_linux.stage,35);BLOCK(sc_irq_enabled,true);
 BLOCK(sc_mapsize,0x680);BLOCK(sc_security_policy_valid,false);
 for(unsigned sw=0;sw<4;sw++) for(unsigned def=0;def<2;def++) {
  valid(&sc);sc.sc_sw_crypto=(sw&1)!=0;sc.sc_use_sw_sec=(sw&2)!=0;sc.sc_use_defaultkey=def!=0;
  assert(rtwn8723be_netbsd_enable_hw_security(&sc)==0 && sc.sc_security_configured);
  if(sw) { assert(count==0 && !sc.sc_hw_security_enabled); }
  else {assert(count==2 && sc.sc_hw_security_enabled);
   assert(registers[0]==0x101 && values[0]==2);
   assert(registers[1]==0x680 && values[1]==(def?0xcf:0xcc));
  }
 }
 puts("RTL_SECURITY_NATIVE_C11_UBSAN_OK: configured policy, SW/HW branches, byte order, default keys");
 return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-security-native-") as directory:
    target = Path(directory)
    (target / "sys").mkdir()
    (target / "sys/systm.h").write_text("/* MMIO adapter prototypes in fake softc. */\n")
    if platform.system() != "NetBSD":
        (target / "sys/errno.h").write_text("#include <errno.h>\n")
    (target / "rtwn8723be_netbsd.h").write_text(FAKE)
    (target / "harness.c").write_text(HARNESS)
    sources = [str(target / "harness.c")]
    native = SRC / "rtwn8723be_security_native.c"
    if native.exists():
        for name in ("rtwn8723be_security_native.h", "rtwn8723be_os_compat.h"):
            shutil.copyfile(SRC / name, target / name)
        (target / "native.c").write_text(
            '#define __KERNEL_RCSID(a,b) _Static_assert(1, "kernel rcsid")\n' + native.read_text())
        sources.append(str(target / "native.c"))
    binary = target / "security-test"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                    "-fsanitize=undefined", "-fno-sanitize-recover=all",
                    "-I", str(target), *sources, "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
