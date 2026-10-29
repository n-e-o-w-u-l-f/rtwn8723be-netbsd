/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual wire functions plus frozen-source well-formed reference comparison.
 * Guard pages test native rejection of short/untrusted payloads. */
#include <sys/types.h>
#include <sys/mman.h>
#include <sys/endian.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include "rtwn8723be_btc_mp.h"
#include "rtwn8723be_c2h.h"
#include "btc_mp_reference.inc"

static unsigned long cases;
static int
route_mp(void *arg, const struct rtwn8723be_c2h_event *event)
{
    assert(event->id == R23BE_C2H_BT_MP && event->fast);
    return rtwn8723be_btc_mp_decode(event->payload, event->payload_length, arg);
}
static void
test_guard_boundaries(void)
{
    long size = sysconf(_SC_PAGESIZE);
    assert(size > 0);
    uint8_t *mem = mmap(NULL, (size_t)size * 2, PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mem != MAP_FAILED);
    assert(mprotect(mem + size, (size_t)size, PROT_NONE) == 0);
    for (unsigned seq=0; seq<16; seq++) {
        for (size_t len=0; len<=10; len++) {
            uint8_t *p = mem + size - len;
            if (len) memset(p, 0x88, len);
            if (len > 0) p[0]=1;
            if (len > 2) p[2]=(uint8_t)(seq<<4);
            struct rtwn8723be_btc_mp_reply out, saved;
            memset(&out,0xa5,sizeof(out));saved=out;
            int rc=rtwn8723be_btc_mp_decode(p,len,&out);
            unsigned need=gold_min_length[seq];
            if (len<need) {
                assert(rc==EMSGSIZE);
                assert(memcmp(&out,&saved,sizeof(out))==0);
            } else {
                assert(rc==0 && out.completes && out.from_bt_firmware);
                assert(out.sequence==seq);
            }
            cases++;
        }
    }
    for (unsigned ext=0; ext<256; ext++) {
        uint8_t *p=mem+size-4;
        p[0]=(uint8_t)ext;p[1]=0xff;p[2]=0xff;p[3]=0xff;
        struct rtwn8723be_btc_mp_reply out;
        assert(rtwn8723be_btc_mp_decode(p,4,&out)==0);
        if(ext!=1)assert(!out.completes && !out.from_bt_firmware);
        else assert(out.completes && out.field==R23BE_BT_MP_NONE);
        cases++;
    }
    assert(munmap(mem,(size_t)size*2)==0);
}
static void
test_request_encoding(void)
{
    for(unsigned op=0;op<256;op++) {
        for(unsigned bits=0;bits<256;bits++) {
            uint8_t command[]={ (uint8_t)bits,0xa5,0x11,0x22,0x33,0x44,0x55 };
            assert(rtwn8723be_btc_mp_prepare((uint8_t)op,command,sizeof(command))==0);
            assert(command[0]==(uint8_t)(bits | (gold_request_sequence[op]<<4)));
            assert(command[1]==op && command[2]==0x11 && command[6]==0x55);
            cases++;
        }
    }
    uint8_t p[]={0xaa,0xbb};
    assert(rtwn8723be_btc_mp_prepare(0,p,1)==EMSGSIZE && p[0]==0xaa && p[1]==0xbb);
    assert(rtwn8723be_btc_mp_prepare(0,NULL,2)==EINVAL);
}
static void
test_reference_responses(void)
{
    _Alignas(8) uint8_t memory[16]={0};
    uint8_t *p=memory+1; /* Raw frozen le32 data at payload+3 is aligned. */
    p[0]=1;p[1]=0xee;p[3]=0x44;p[4]=0x33;p[5]=0x22;p[6]=0x12;
    for(unsigned seq=0;seq<16;seq++) {
        p[2]=(uint8_t)((seq<<4)|0xf);
        struct btc_coexist frozen={0};
        struct rtl_priv adapter={.context=&frozen};
        struct rtwn8723be_btc_mp_reply out;
        reference_btmp_notify(&adapter,p,7);
        assert(rtwn8723be_btc_mp_decode(p,7,&out)==0);
        assert(frozen.bt_mp_comp.done==1 && out.completes);
        switch(out.field) {
        case R23BE_BT_MP_VERSION:
            assert(out.value==frozen.bt_info.bt_real_fw_ver);
            assert(out.firmware_subversion==frozen.bt_info.bt_fw_ver);break;
        case R23BE_BT_MP_AFH_L:assert(out.value==frozen.bt_info.afh_map_l);break;
        case R23BE_BT_MP_AFH_M:assert(out.value==frozen.bt_info.afh_map_m);break;
        case R23BE_BT_MP_AFH_H:assert(out.value==frozen.bt_info.afh_map_h);break;
        case R23BE_BT_MP_FEATURE:assert(out.value==frozen.bt_info.bt_supported_feature);break;
        case R23BE_BT_MP_SUPPORTED_VERSION:assert(out.value==frozen.bt_info.bt_supported_version);break;
        case R23BE_BT_MP_ANT_DETECTION:assert(out.value==frozen.bt_info.bt_ant_det_val);break;
        case R23BE_BT_MP_BLE_SCAN_PARAMETERS:assert(out.value==frozen.bt_info.bt_ble_scan_para);break;
        case R23BE_BT_MP_BLE_SCAN_TYPE:assert(out.value==frozen.bt_info.bt_ble_scan_type);break;
        case R23BE_BT_MP_DEVICE_INFO:assert(out.value==frozen.bt_info.bt_device_info);break;
        default:assert(out.field==R23BE_BT_MP_NONE);break;
        }
        assert(frozen.bt_info.bt_forb_slot_val==0);
        cases++;
    }
    p[2]=0x30;p[6]=0xff;
    struct rtwn8723be_btc_mp_reply out;
    assert(rtwn8723be_btc_mp_decode(p,7,&out)==0 && out.value==0xff223344U);
}
static void
test_route_and_copy(void)
{
    uint8_t packet[]={R23BE_C2H_BT_MP,0x7f,1,0,0x70,0xaa,0xbb};
    struct rtwn8723be_btc_mp_reply out;
    struct rtwn8723be_c2h_handlers handlers={.arg=&out,.bt_mp=route_mp};
    assert(rtwn8723be_c2h_route(packet,sizeof(packet),&handlers)==0);
    assert(out.field==R23BE_BT_MP_FEATURE && out.value==0xbbaa);
    memset(packet,0,sizeof(packet));
    assert(out.value==0xbbaa);
    struct rtwn8723be_btc_mp_reply before=out;
    assert(rtwn8723be_btc_mp_decode(NULL,7,&out)==EINVAL);
    assert(memcmp(&out,&before,sizeof(out))==0);
    assert(rtwn8723be_btc_mp_decode(packet,7,NULL)==EINVAL);
}
int main(void)
{
    test_guard_boundaries();test_request_encoding();
    test_reference_responses();test_route_and_copy();
    printf("BT_MP_WIRE_FROZEN_REFERENCE_GUARD_PAGES_ENCODING_COPY_PASS cases=%lu\n",cases);
    puts("Full native BTC transaction, firmware wait/owner lifetime and WLAN acceptance remain OPEN");
    return 0;
}
