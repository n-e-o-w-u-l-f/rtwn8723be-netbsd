#!/usr/bin/env python3
"""Exercise native DBI/MDIO transactions, frozen ASPM order and timeout failure.

Real production adapter C runs under UBSan with a protocol/MMIO model. This
does not establish physical PCIe or wireless runtime acceptance.
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
typedef size_t bus_size_t;
#define R23BE_STAGE_ASPM_RESTORE 35U
struct rtwn8723be_softc {
 bool sc_mapped, sc_core_initialized, sc_bb_valid, sc_rf_chnlval_valid;
 bool sc_efuse_autoload_ok, sc_package_valid, sc_phy_identity_valid;
 bool sc_irq_enabled, sc_aspm_backdoor_valid;
 size_t sc_mapsize;
 uint8_t sc_package_type;
 struct { bool pci_interface; uint8_t package_type; } sc_phy_identity;
 struct { bool fw_ready, being_init_adapter, started; unsigned stage; } sc_linux;
};
uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *, size_t);
uint16_t rtwn8723be_read_2(struct rtwn8723be_softc *, size_t);
void rtwn8723be_write_1(struct rtwn8723be_softc *, size_t, uint8_t);
void rtwn8723be_write_2(struct rtwn8723be_softc *, size_t, uint16_t);
#endif
"""
HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_netbsd.h"
int rtwn8723be_netbsd_dbi_read(void *, uint16_t, uint8_t *);
int rtwn8723be_netbsd_dbi_write(void *, uint16_t, uint8_t);
int rtwn8723be_netbsd_mdio_read(void *, uint8_t, uint16_t *);
int rtwn8723be_netbsd_mdio_write(void *, uint8_t, uint16_t);
int rtwn8723be_netbsd_enable_aspm_backdoor(void *);
struct event { unsigned width; size_t reg; uint16_t value; } events[4096];
static unsigned count, delays, busy_reads, pending, transaction, fail_at;
static bool stuck;
static uint8_t mmio[0x1000], dbi[0x1000];
static uint16_t mdio[32];
static const uint8_t indices[] = {1,4,6,7,8,9,10,11};
static const uint16_t values[] = {0x0663,0x7544,0xb880,0x4000,0x9003,0x0d03,0x4037,0x0070};
static void event(unsigned width,size_t reg,uint16_t v) {
 assert(count<4096 && reg<0x1000); events[count++]=(struct event){width,reg,v};
}
uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *sc,size_t reg) {
 (void)sc; uint8_t v=mmio[reg];
 if (reg==0x352 || reg==0x358) {
  if (stuck || (fail_at && transaction==fail_at)) { /* keep command busy */ }
  else if (pending) --pending;
  else { mmio[reg]=0; v=0; }
 }
 event(1,reg,v); return v;
}
uint16_t rtwn8723be_read_2(struct rtwn8723be_softc *sc,size_t reg) {
 (void)sc; assert(!(reg&1U)); uint16_t v=mmio[reg]|((uint16_t)mmio[reg+1]<<8);
 event(2,reg,v);return v;
}
void rtwn8723be_write_2(struct rtwn8723be_softc *sc,size_t reg,uint16_t v) {
 (void)sc;assert(!(reg&1U));event(102,reg,v);mmio[reg]=(uint8_t)v;mmio[reg+1]=(uint8_t)(v>>8);
}
void rtwn8723be_write_1(struct rtwn8723be_softc *sc,size_t reg,uint8_t v) {
 (void)sc;event(101,reg,v);mmio[reg]=v;
 if (reg==0x352) {
  unsigned addr=(mmio[0x350]|((unsigned)mmio[0x351]<<8))&0xffcU;
  pending=busy_reads;++transaction;
  if (v==2) for (unsigned i=0;i<4;i++) mmio[0x34c+i]=dbi[addr+i];
  else { assert(v==1);unsigned mask=mmio[0x351]>>4;
   for(unsigned i=0;i<4;i++) if(mask&(1U<<i)) dbi[addr+i]=mmio[0x348+i];
  }
 } else if (reg==0x358) {
  unsigned addr=v&31U;pending=busy_reads;++transaction;
  if(v&0x40) {mmio[0x356]=(uint8_t)mdio[addr];mmio[0x357]=(uint8_t)(mdio[addr]>>8);}
  else {assert(v&0x20);mdio[addr]=mmio[0x354]|((uint16_t)mmio[0x355]<<8);}
 }
}
void delay(unsigned usec) {assert(usec==10);++delays;}
static void valid(struct rtwn8723be_softc *sc) {
 memset(sc,0,sizeof(*sc));memset(mmio,0,sizeof(mmio));memset(dbi,0,sizeof(dbi));memset(mdio,0,sizeof(mdio));
 count=delays=busy_reads=pending=transaction=fail_at=0;stuck=false;
 sc->sc_mapped=sc->sc_core_initialized=sc->sc_bb_valid=sc->sc_rf_chnlval_valid=true;
 sc->sc_efuse_autoload_ok=sc->sc_package_valid=sc->sc_phy_identity_valid=true;
 sc->sc_linux.fw_ready=sc->sc_linux.being_init_adapter=true;sc->sc_mapsize=0x1000;
 sc->sc_linux.stage=R23BE_STAGE_ASPM_RESTORE;
 sc->sc_package_type=sc->sc_phy_identity.package_type=1;sc->sc_phy_identity.pci_interface=true;
}
#define CHECK(i,w,r,v) do {assert(events[i].width==(w));assert(events[i].reg==(r));assert(events[i].value==(v));}while(0)
#define BLOCK(field,val) do {valid(&sc);sc.field=(val);sc.sc_aspm_backdoor_valid=true; \
 assert(rtwn8723be_netbsd_enable_aspm_backdoor(&sc)==ENXIO);assert(!sc.sc_aspm_backdoor_valid && count==0);}while(0)
int main(void) {
 struct rtwn8723be_softc sc;uint8_t b=0xa5;uint16_t w=0xa55a;
 assert(rtwn8723be_netbsd_enable_aspm_backdoor(NULL)==EINVAL);
 BLOCK(sc_mapped,false);BLOCK(sc_core_initialized,false);BLOCK(sc_bb_valid,false);
 BLOCK(sc_rf_chnlval_valid,false);BLOCK(sc_efuse_autoload_ok,false);BLOCK(sc_package_valid,false);
 BLOCK(sc_phy_identity_valid,false);BLOCK(sc_phy_identity.pci_interface,false);
 BLOCK(sc_phy_identity.package_type,2);BLOCK(sc_linux.fw_ready,false);
 BLOCK(sc_linux.being_init_adapter,false);BLOCK(sc_linux.started,true);
 BLOCK(sc_linux.stage,36);BLOCK(sc_irq_enabled,true);BLOCK(sc_mapsize,0x358);
 valid(&sc);
 assert(rtwn8723be_netbsd_dbi_read(&sc,0x1000,&b)==EINVAL);
 assert(rtwn8723be_netbsd_dbi_read(&sc,0,NULL)==EINVAL);
 assert(rtwn8723be_netbsd_dbi_write(&sc,0x1000,0)==EINVAL);
 assert(rtwn8723be_netbsd_mdio_read(&sc,32,&w)==EINVAL);
 assert(rtwn8723be_netbsd_mdio_read(&sc,0,NULL)==EINVAL);
 assert(rtwn8723be_netbsd_mdio_write(&sc,32,0)==EINVAL);assert(count==0);
 for(unsigned lane=0;lane<4;lane++) {
  valid(&sc);dbi[0x70c+lane]=(uint8_t)(0x60+lane);
  assert(rtwn8723be_netbsd_dbi_read(&sc,(uint16_t)(0x70c+lane),&b)==0 && b==0x60+lane);
  CHECK(0,102,0x350,0x70c);CHECK(1,101,0x352,2);CHECK(3,1,0x34c+lane,0x60+lane);
  count=0;assert(rtwn8723be_netbsd_dbi_write(&sc,(uint16_t)(0x70c+lane),0x91)==0);
  CHECK(0,101,0x348+lane,0x91);CHECK(1,102,0x350,0x70c|(1U<<(lane+12)));CHECK(2,101,0x352,1);
  assert(dbi[0x70c+lane]==0x91 && delays==0);
 }
 for(unsigned poll=0;poll<=21;poll++) {
  valid(&sc);busy_reads=poll;mdio[5]=0xbeef;w=0xa55a;
  int error=rtwn8723be_netbsd_mdio_read(&sc,5,&w);
  assert(delays==(poll<21?poll:20));assert(error==(poll<21?0:ETIMEDOUT));
  assert(w==(poll<21?0xbeef:0xa55a));CHECK(0,101,0x358,0x45);
 }
 valid(&sc);stuck=true;b=0xa5;
 assert(rtwn8723be_netbsd_dbi_read(&sc,0x719,&b)==ETIMEDOUT && b==0xa5 && delays==20);
 valid(&sc);stuck=true;assert(rtwn8723be_netbsd_dbi_write(&sc,0x719,0x31)==ETIMEDOUT && delays==20);
 valid(&sc);stuck=true;assert(rtwn8723be_netbsd_mdio_write(&sc,5,0x1234)==ETIMEDOUT && delays==20);
 CHECK(0,102,0x354,0x1234);CHECK(1,101,0x358,0x25);
 valid(&sc);dbi[0x70f]=3;dbi[0x719]=0xa1;
 assert(rtwn8723be_netbsd_enable_aspm_backdoor(&sc)==0 && sc.sc_aspm_backdoor_valid);
 assert(transaction==20 && dbi[0x70f]==0xbb && dbi[0x719]==0xb9);
 for(unsigned i=0;i<8;i++) assert(mdio[indices[i]]==values[i]);
 valid(&sc);for(unsigned i=0;i<8;i++) mdio[indices[i]]=values[i];
 assert(rtwn8723be_netbsd_enable_aspm_backdoor(&sc)==0 && transaction==12);
 /* Every transaction, including writes, must abort all later programming. */
 for(unsigned failure=1;failure<=20;failure++) {
  valid(&sc);fail_at=failure;sc.sc_aspm_backdoor_valid=true;
  assert(rtwn8723be_netbsd_enable_aspm_backdoor(&sc)==ETIMEDOUT);
  assert(transaction==failure && delays==20 && !sc.sc_aspm_backdoor_valid);
 }
 puts("RTL_ASPM_NATIVE_C11_UBSAN_OK: lanes, widths, 20-poll boundary, frozen order, fail-stop");
 return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="rtl-aspm-native-") as directory:
    target = Path(directory)
    (target / "sys").mkdir()
    (target / "sys/systm.h").write_text("void delay(unsigned int);\n")
    if platform.system() != "NetBSD":
        (target / "sys/errno.h").write_text("#include <errno.h>\n")
    (target / "rtwn8723be_netbsd.h").write_text(FAKE)
    (target / "harness.c").write_text(HARNESS)
    sources = [str(target / "harness.c")]
    native = SRC / "rtwn8723be_aspm_native.c"
    if native.exists():
        shutil.copyfile(SRC / "rtwn8723be_os_compat.h", target / "rtwn8723be_os_compat.h")
        shutil.copyfile(SRC / "rtwn8723be_aspm_native.h", target / "rtwn8723be_aspm_native.h")
        (target / "native.c").write_text(
            '#define __KERNEL_RCSID(a,b) _Static_assert(1, "kernel rcsid")\n' + native.read_text())
        sources.append(str(target / "native.c"))
    binary = target / "aspm-test"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                    "-fsanitize=undefined", "-fno-sanitize-recover=all",
                    "-I", str(target), *sources, "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
