/* SPDX-License-Identifier: GPL-2.0 */
/* Frozen-source trace comparison, bounded image parsing and actual owner body. */
#include "model_fixture.h"
enum { READ1=1, READ4, WRITE1, WRITE4, DELAY };
struct event { unsigned int kind, reg; uint32_t value; };
struct trace {
 struct event events[100000];
 size_t count;
 uint8_t regs[0x2100];
 unsigned int checksum_at, ready_at, checksum_reads, ready_reads;
 bool ready_phase;
};
static struct trace *delay_trace;
static unsigned int cases;
#define CHECK(c,tag) do { if (!(c)) { fprintf(stderr,"FW_CHECK_FAIL %s\n",tag); exit(77); } } while (0)
static void event(struct trace *t,unsigned int kind,unsigned int reg,uint32_t value)
{
 CHECK(t->count<100000,"TRACE_CAPACITY");
 t->events[t->count++]=(struct event){kind,reg,value};
}
uint8_t bus_space_read_1(bus_space_tag_t t,bus_space_handle_t h,bus_size_t reg)
{
 (void)h; CHECK(reg<sizeof(t->regs),"READ1_BOUNDS");
 uint8_t v=t->regs[reg];event(t,READ1,(unsigned int)reg,v);return v;
}
uint32_t bus_space_read_4(bus_space_tag_t t,bus_space_handle_t h,bus_size_t reg)
{
 (void)h;CHECK(reg==R23BE_REG_MCUFWDL,"READ4_REGISTER");
 uint32_t v=0x00800100U;
 if (t->ready_phase) {
  t->ready_reads++;
  if(t->ready_at && t->ready_reads>=t->ready_at)v|=R23BE_MCUFWDL_WINTINI_RDY;
 } else {
  t->checksum_reads++;
  if(t->checksum_at && t->checksum_reads>=t->checksum_at)v|=R23BE_MCUFWDL_CHKSUM_RPT;
 }
 event(t,READ4,(unsigned int)reg,v);return v;
}
void bus_space_write_1(bus_space_tag_t t,bus_space_handle_t h,bus_size_t reg,uint8_t v)
{
 (void)h;CHECK(reg<sizeof(t->regs),"WRITE1_BOUNDS");t->regs[reg]=v;
 event(t,WRITE1,(unsigned int)reg,v);
}
void bus_space_write_4(bus_space_tag_t t,bus_space_handle_t h,bus_size_t reg,uint32_t v)
{
 (void)h;CHECK(reg==R23BE_REG_MCUFWDL,"WRITE4_REGISTER");
 t->ready_phase=true;event(t,WRITE4,(unsigned int)reg,v);
}
void delay(unsigned int usec){event(delay_trace,DELAY,0,usec);}
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;
#define BIT(n) (1U<<(n))
#define REG_SYS_FUNC_EN R23BE_REG_SYS_FUNC_EN
#define REG_RSV_CTRL R23BE_REG_RSV_CTRL
#define REG_MCUFWDL R23BE_REG_MCUFWDL
#define FWDL_CHKSUM_RPT R23BE_MCUFWDL_CHKSUM_RPT
#define MCUFWDL_RDY R23BE_MCUFWDL_RDY
#define WINTINI_RDY R23BE_MCUFWDL_WINTINI_RDY
#define FW_8192C_POLLING_DELAY 5
#define FW_8192C_PAGE_SIZE 4096
#define START_ADDRESS 0x1000
#define INTF_PCI 1
#define INTF_USB 2
#define rtl_dbg(priv,...) do { (void)(priv); } while(0)
#define pr_err(...) do {} while(0)
#define udelay(x) delay(x)
#define mdelay(x) delay((x)*1000U)
#define le16_to_cpu(x) (x)
enum version_8723e { VERSION_MODEL=0 };
struct rtlwifi_firmware_header {
 u16 signature; u8 category,function;u16 version;u8 subversion,reserved1;
 u8 month,date,hour,minute;u16 ram_code_size,reserved2;u32 svn_idx;u8 reserved3[12];
};
struct ieee80211_hw;
struct rtl_hal {
 int interface;enum version_8723e version;u8 *pfirmware;u32 fwsize;
 u16 fw_version;u8 fw_subversion;
};
struct rtl_hal_ops { bool (*is_fw_header)(struct rtlwifi_firmware_header *); };
struct rtl_hal_cfg { struct rtl_hal_ops *ops; };
struct rtl_priv {
 struct trace *trace;struct rtl_hal rtlhal;u32 max_fw_size;struct rtl_hal_cfg *cfg;
};
struct ieee80211_hw { struct rtl_priv *priv; };
static struct rtl_priv *rtl_priv(struct ieee80211_hw *hw){return hw->priv;}
static struct rtl_hal *rtl_hal(struct rtl_priv *p){return &p->rtlhal;}
static u8 rtl_read_byte(struct rtl_priv *p,u32 reg){return bus_space_read_1(p->trace,0,reg);}
static u32 rtl_read_dword(struct rtl_priv *p,u32 reg){return bus_space_read_4(p->trace,0,reg);}
static void rtl_write_byte(struct rtl_priv *p,u32 reg,u8 v){bus_space_write_1(p->trace,0,reg,v);}
static void rtl_write_dword(struct rtl_priv *p,u32 reg,u32 v){bus_space_write_4(p->trace,0,reg,v);}
static void _rtl_fw_block_write_usb(struct ieee80211_hw *hw,u8 *data,u32 size)
{(void)hw;(void)data;(void)size;CHECK(false,"USB_UNREACHABLE_FOR_PCI");}
void rtl8723ae_firmware_selfreset(struct ieee80211_hw *hw)
{(void)hw;CHECK(false,"AE_UNREACHABLE_FOR_BE");}
/* Frozen Linux compares u32 counters with its int max_count argument. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#include "linux_reference.inc"
#pragma GCC diagnostic pop
static struct trace *trace_new(unsigned int c,unsigned int ready)
{
 struct trace *t=calloc(1,sizeof(*t));CHECK(t!=NULL,"ALLOC");
 memset(t->regs,0xa5,sizeof(t->regs));t->regs[R23BE_REG_MCUFWDL]=0;
 t->checksum_at=c;t->ready_at=ready;return t;
}
static void equal_trace(struct trace *n,struct trace *l,const char *tag)
{
 if(n->count!=l->count || memcmp(n->events,l->events,n->count*sizeof(n->events[0]))!=0) {
  fprintf(stderr,"TRACE_COUNTS native=%zu linux=%zu\n",n->count,l->count);
  CHECK(false,tag);
 }cases++;
}
static void free_to_go_cases(void)
{
 const unsigned int cs[]={1,2,5998,5999,6000,6001,0};
 const unsigned int rs[]={1,2,5999,6000,6001,0};
 for(size_t i=0;i<sizeof(cs)/sizeof(cs[0]);i++)
 for(size_t j=0;j<sizeof(rs)/sizeof(rs[0]);j++){
  struct trace *n=trace_new(cs[i],rs[j]),*l=trace_new(cs[i],rs[j]);
  struct rtl_priv p={.trace=l};struct ieee80211_hw hw={.priv=&p};
  delay_trace=n;int a=rtwn8723be_fw_free_to_go(n,0);
  delay_trace=l;int b=rtl8723_fw_free_to_go(&hw,true,6000);
  CHECK((a==0)==(b==0),"POLL_RESULT_PARITY");
  equal_trace(n,l,"POLL_TRACE_PARITY");free(n);free(l);
 }
}
static bool no_header(struct rtlwifi_firmware_header *h){(void)h;return false;}
static void download_cases(void)
{
 const size_t sizes[]={1,2,3,4,5,7,4093,4094,4095,4096,4097,8191,32765,32766,32767,32768};
 struct rtl_hal_ops ops={.is_fw_header=no_header};struct rtl_hal_cfg cfg={.ops=&ops};
 for(size_t i=0;i<sizeof(sizes)/sizeof(sizes[0]);i++)for(unsigned int reset=0;reset<2;reset++){
  size_t len=sizes[i];u8 *data=calloc(1,len+32);CHECK(data!=NULL,"ALLOC");
  for(size_t j=0;j<len;j++)data[j]=(u8)(j*13U+7U);
  struct trace *n=trace_new(1,1),*l=trace_new(1,1);
  n->regs[REG_MCUFWDL]=l->regs[REG_MCUFWDL]=(reset?0x80:0);
  struct rtl_priv p={.trace=l,.max_fw_size=32768,.cfg=&cfg};
  p.rtlhal.interface=INTF_PCI;p.rtlhal.pfirmware=data;p.rtlhal.fwsize=(u32)len;
  struct ieee80211_hw hw={.priv=&p};
  delay_trace=n;CHECK(rtwn8723be_fw_download(n,0,data,len)==0,"NATIVE_DOWNLOAD");
  delay_trace=l;CHECK(rtl8723_download_fw(&hw,true,6000)==0,"REFERENCE_DOWNLOAD");
  equal_trace(n,l,"DOWNLOAD_TRACE_PARITY");free(data);free(n);free(l);
 }
 struct trace *n=trace_new(1,1);uint8_t byte=0;
 CHECK(rtwn8723be_fw_download(n,0,NULL,1)==EINVAL,"NULL_PAYLOAD");
 CHECK(rtwn8723be_fw_download(n,0,&byte,0)==EINVAL,"EMPTY_PAYLOAD");
 CHECK(rtwn8723be_fw_download(n,0,&byte,32769)==EFBIG,"OVERSIZE_PAYLOAD");
 CHECK(rtwn8723be_fw_download(n,0,&byte,SIZE_MAX)==EFBIG,"PADDING_OVERFLOW");
 CHECK(n->count==0,"INVALID_NO_MMIO");cases+=4;free(n);
}
static bool model_hard_interrupt, model_soft_interrupt;
bool cpu_intr_p(void){return model_hard_interrupt;}
bool cpu_softintr_p(void){return model_soft_interrupt;}
static struct image_slot primary,alternative;
static int open_calls,close_calls,read_calls,allocations,read_error,model_close_error,allocation_error;
int firmware_open(const char *driver,const char *name,firmware_handle_t *out)
{
 CHECK(strcmp(driver,RTWN8723BE_FIRMWARE_DRIVER)==0,"FIRMWARE_DRIVER");
 open_calls++;
 struct image_slot *slot=strcmp(name,RTWN8723BE_FIRMWARE_FILE)==0?&primary:&alternative;
 if(!slot->present)
  return ENOENT;
 *out=slot;
 return 0;
}
off_t firmware_get_size(firmware_handle_t f){return (off_t)f->length;}
int firmware_read(firmware_handle_t f,off_t off,void *out,size_t len)
{
 read_calls++;if(read_error)return read_error;
 CHECK(off>=0 && (size_t)off<=f->length && len<=f->length-(size_t)off,"FIRMWARE_READ_BOUNDS");
 memcpy(out,f->data+(size_t)off,len);return 0;
}
int firmware_close(firmware_handle_t f){CHECK(f!=NULL,"CLOSE");close_calls++;return model_close_error;}
void *kmem_alloc(size_t len,int flags){(void)flags;allocations++;void *p=malloc(len);CHECK(p!=NULL,"ALLOC");return p;}
void kmem_free(void *ptr,size_t len){(void)len;CHECK(ptr!=NULL,"FREE");allocations--;free(ptr);}
void *firmware_malloc(size_t len)
{if(allocation_error)return NULL;return kmem_alloc(len,KM_SLEEP);}
void firmware_free(void *ptr,size_t len){kmem_free(ptr,len);}
void rtwn8723be_h2c_native_reset(struct rtwn8723be_softc *sc){sc->resets++;}
int rtwn8723be_netbsd_bt_preload_firmware(struct rtwn8723be_softc *sc)
{CHECK(close_calls==1,"VNODE_CLOSED_BEFORE_PRELOAD");sc->preloads++;return sc->preload_error;}
int rtwn8723be_h2c_native_fw_ready(struct rtwn8723be_softc *sc)
{sc->ready_calls++;return sc->ready_error;}
#include "native_owner.inc"
static uint8_t *read_image(const char *path,size_t *length)
{
 FILE *f=fopen(path,"rb");CHECK(f!=NULL,"OPEN_IMAGE");
 CHECK(fseek(f,0,SEEK_END)==0,"SEEK_IMAGE");long size=ftell(f);CHECK(size>32,"IMAGE_SIZE");
 rewind(f);*length=(size_t)size;uint8_t *data=malloc(*length);CHECK(data!=NULL,"ALLOC");
 CHECK(fread(data,1,*length,f)==*length,"READ_IMAGE");fclose(f);return data;
}
static void slots_reset(void){open_calls=close_calls=read_calls=read_error=model_close_error=allocation_error=0;CHECK(allocations==0,"NO_LEAK");}
static struct rtwn8723be_softc softc_new(struct trace *t)
{
 struct rtwn8723be_softc sc={.sc_mapped=true,.sc_st=t,
  .sc_mapsize=R23BE_FW_START_ADDR+R23BE_FW_PAGE_SIZE};
 sc.sc_h2c.initialized=true;sc.sc_linux.being_init_adapter=true;
 sc.sc_linux.stage=R23BE_STAGE_FIRMWARE_DOWNLOAD;
 return sc;
}
static void owner_cases(uint8_t *a,size_t alen,uint8_t *b,size_t blen)
{
 struct trace *t=trace_new(1,1);delay_trace=t;
 struct rtwn8723be_softc sc=softc_new(t);
 primary=(struct image_slot){a,alen,false};alternative=(struct image_slot){b,blen,true};slots_reset();
 CHECK(rtwn8723be_netbsd_download_firmware(&sc)==0,"FALLBACK_LOAD");
 CHECK(open_calls==2 && close_calls==1 && allocations==0,"FALLBACK_RESOURCE");
 CHECK(sc.sc_fw_info.version==15 && sc.sc_fw_info.subversion==17,"FALLBACK_METADATA");
 CHECK(sc.sc_firmware_name && strcmp(sc.sc_firmware_name,RTWN8723BE_FIRMWARE_ALT_NAME)==0,"FALLBACK_NAME");
 CHECK(sc.preloads==1 && sc.ready_calls==1,"FALLBACK_STAGE_ORDER");cases++;free(t);
 t=trace_new(1,1);delay_trace=t;sc=softc_new(t);
 primary=(struct image_slot){a,alen,true};slots_reset();
 CHECK(rtwn8723be_netbsd_download_firmware(&sc)==0,"PRIMARY_LOAD");
 CHECK(open_calls==1 && sc.sc_fw_info.version==36 && sc.sc_fw_info.subversion==0,"PRIMARY_METADATA");
 CHECK(sc.sc_fw_info.payload_offset==32 && sc.sc_fw_info.payload_length==alen-32,"PRIMARY_EXTENT");
 CHECK(close_calls==1 && allocations==0,"PRIMARY_RESOURCE");cases++;free(t);
 const int failures[]={EIO,ENOMEM};
 for(size_t i=0;i<2;i++){
  t=trace_new(1,1);delay_trace=t;sc=softc_new(t);sc.preload_error=failures[i];
  slots_reset();CHECK(rtwn8723be_netbsd_download_firmware(&sc)==failures[i],"PRELOAD_ERROR");
  CHECK(sc.ready_calls==0 && t->count==0 && close_calls==1 && allocations==0,"PRELOAD_UNWIND");
  CHECK(sc.sc_fw_info.payload_length==0 && sc.sc_firmware_name==NULL,"FAILED_IDENTITY_CLEAR");
  cases++;free(t);
 }
 t=trace_new(1,1);delay_trace=t;sc=softc_new(t);
 slots_reset();read_error=EIO;CHECK(rtwn8723be_netbsd_download_firmware(&sc)==EIO,"READ_ERROR");
 CHECK(t->count==0 && close_calls==1 && allocations==0 && sc.preloads==0,"READ_UNWIND");cases++;free(t);
 t=trace_new(1,1);delay_trace=t;sc=softc_new(t);
 slots_reset();model_close_error=EIO;CHECK(rtwn8723be_netbsd_download_firmware(&sc)==EIO,"CLOSE_ERROR");
 CHECK(t->count==0 && close_calls==1 && allocations==0 && sc.preloads==0,"CLOSE_UNWIND");cases++;free(t);
 t=trace_new(1,1);delay_trace=t;sc=softc_new(t);
 slots_reset();allocation_error=ENOMEM;CHECK(rtwn8723be_netbsd_download_firmware(&sc)==ENOMEM,"ALLOC_ERROR");
 CHECK(t->count==0 && close_calls==1 && allocations==0 && read_calls==0,"ALLOC_UNWIND");cases++;free(t);
 const size_t invalid[]={0,32769,32};
 const int invalid_errno[]={EINVAL,EFBIG,EMSGSIZE};
 for(size_t i=0;i<3;i++){
  primary.length=invalid[i];t=trace_new(1,1);delay_trace=t;sc=softc_new(t);
  slots_reset();CHECK(rtwn8723be_netbsd_download_firmware(&sc)==invalid_errno[i],"INVALID_FILE");
  CHECK(open_calls==1 && close_calls==1 && t->count==0 && allocations==0 && sc.ready_calls==0,"INVALID_NO_FALLBACK");
  cases++;free(t);
 }
 primary.length=alen;
 t=trace_new(1,1);delay_trace=t;sc=softc_new(t);sc.ready_error=EAGAIN;
 slots_reset();CHECK(rtwn8723be_netbsd_download_firmware(&sc)==EAGAIN,"H2C_BINDING_ERROR");
 CHECK(sc.ready_calls==1 && allocations==0 && sc.sc_fw_info.payload_length==0,"H2C_BINDING_UNWIND");cases++;free(t);
 t=trace_new(1,0);delay_trace=t;sc=softc_new(t);slots_reset();
 CHECK(rtwn8723be_netbsd_download_firmware(&sc)!=0,"HANDSHAKE_ERROR_PROPAGATED");
 CHECK(sc.ready_calls==0 && close_calls==1 && allocations==0 && sc.sc_firmware_name==NULL,"HANDSHAKE_UNWIND");cases++;free(t);
 primary.present=alternative.present=false;t=trace_new(1,1);sc=softc_new(t);slots_reset();
 CHECK(rtwn8723be_netbsd_download_firmware(&sc)==ENOENT,"BOTH_MISSING");
 CHECK(open_calls==2 && t->count==0 && close_calls==0 && allocations==0,"MISSING_NO_SIDE_EFFECT");cases++;free(t);
 CHECK(rtwn8723be_netbsd_download_firmware(NULL)==ENXIO,"NULL_OWNER");cases++;
 for(unsigned int i=0;i<9;i++){
  t=trace_new(1,1);sc=softc_new(t);slots_reset();
  int expected=EAGAIN;
  switch(i){
  case 0:sc.sc_linux.being_init_adapter=false;break;
  case 1:sc.sc_linux.stage=R23BE_STAGE_PROBED;break;
  case 2:sc.sc_linux.started=true;break;
  case 3:sc.sc_h2c.initialized=false;break;
  case 4:sc.sc_mapsize--;expected=ENXIO;break;
  case 5:model_hard_interrupt=true;expected=EWOULDBLOCK;break;
  case 6:model_soft_interrupt=true;expected=EWOULDBLOCK;break;
  case 7:sc.sc_irq_enabled=true;break;
  case 8:sc.sc_linux.fw_ready=true;break;
  }
  CHECK(rtwn8723be_netbsd_download_firmware(&sc)==expected,"INIT_CONTEXT_GUARD");
  CHECK(open_calls==0 && close_calls==0 && allocations==0 && t->count==0 && sc.resets==0,"GUARD_NO_SIDE_EFFECTS");
  model_hard_interrupt=model_soft_interrupt=false;cases++;free(t);
 }
}
#ifndef BASELINE_POLL
static void parser_cases(uint8_t *a,size_t len)
{
 struct rtwn8723be_fw_image_info info,unchanged;
 memset(&info,0xa5,sizeof(info));unchanged=info;
 CHECK(rtwn8723be_fw_image_parse(NULL,1,&info)==EINVAL && memcmp(&info,&unchanged,sizeof(info))==0,"NULL_PARSE");
 CHECK(rtwn8723be_fw_image_parse(a,0,&info)==EINVAL,"EMPTY_PARSE");
 CHECK(rtwn8723be_fw_image_parse(a,32769,&info)==EFBIG,"OVERSIZE_PARSE");
 CHECK(rtwn8723be_fw_image_parse(a,32,&info)==EMSGSIZE,"HEADER_ONLY");
 CHECK(rtwn8723be_fw_image_parse(a,2,&info)==EMSGSIZE,"TRUNCATED_HEADER");
 CHECK(memcmp(&info,&unchanged,sizeof(info))==0,"PARSE_FAILURE_OUTPUT");
 CHECK(rtwn8723be_fw_image_parse(a,len,&info)==0 && info.has_header,"VALID_PARSE");
 CHECK(info.version==36 && info.subversion==0 && info.payload_offset==32,"VALID_METADATA");
 uint8_t raw[7]={0x12,0x34,0,0,0xab,0xcd,0xef};
 CHECK(rtwn8723be_fw_image_parse(raw,sizeof(raw),&info)==0 && !info.has_header && info.payload_offset==0 && info.payload_length==7,"RAW_IMAGE");
 CHECK(info.version==0xcdab && info.subversion==0xef,"RAW_METADATA");
 CHECK(rtwn8723be_fw_image_parse(raw,1,&info)==0 && info.version==0 && info.payload_length==1,"ZERO_FILLED_HEADER");
 uint8_t copy[40];memcpy(copy,a,40);copy[12]=0;copy[13]=0;copy[7]=0xff;
 CHECK(rtwn8723be_fw_image_parse(copy,40,&info)==0 && info.ram_code_size==0 && info.payload_length==8,"RAM_LENGTH_METADATA_ONLY");
 CHECK(info.subversion==0,"SUBVERSION_ONE_BYTE");cases+=12;
}
#endif
int main(int argc,char **argv)
{
 CHECK(argc==3,"ARGS");
#ifdef BASELINE_OWNER
 size_t alen,blen;uint8_t *a=read_image(argv[1],&alen),*b=read_image(argv[2],&blen);
 owner_cases(a,alen,b,blen);
#else
 free_to_go_cases();download_cases();
 size_t alen,blen;uint8_t *a=read_image(argv[1],&alen),*b=read_image(argv[2],&blen);
#ifndef BASELINE_POLL
 parser_cases(a,alen);owner_cases(a,alen,b,blen);
#endif
#endif
 free(a);free(b);printf("FW_ACTUAL_SOURCE_REFERENCE_PASS cases=%u\n",cases);return 0;
}
