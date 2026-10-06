/* SPDX-License-Identifier: GPL-2.0 */
/* Deterministic callback test model; this is NOT a production OS provider. */
#include "btc_algorithm_model.h"

struct btc_coexist *btc_reference_current;
static struct btc_model *model(void *ctx) { return ((struct btc_coexist *)ctx)->adapter; }
static struct btc_trace *trace(void *ctx, u32 op, u32 a, u32 b, u32 c, u32 d)
{
    struct btc_model *m = model(ctx);
    struct btc_trace *t;
    assert(m->count < sizeof(m->trace) / sizeof(m->trace[0]));
    t = &m->trace[m->count++]; memset(t, 0, sizeof(*t));
    t->op = op; t->a = a; t->b = b; t->c = c; t->d = d; return t;
}
static u32 load(struct btc_model *m, u32 reg, unsigned int width)
{
    u32 v = 0; unsigned int i; assert(reg + width <= sizeof(m->mmio));
    for (i = 0; i < width; ++i) v |= (u32)m->mmio[reg + i] << (8 * i);
    return v;
}
static void store(struct btc_model *m, u32 reg, unsigned int width, u32 v)
{
    unsigned int i; assert(reg + width <= sizeof(m->mmio));
    for (i = 0; i < width; ++i) m->mmio[reg + i] = (u8)(v >> (8 * i));
}
static u8 read1(void *ctx,u32 reg) { u8 v=(u8)load(model(ctx),reg,1); trace(ctx,1,reg,1,v,0);return v; }
static u16 read2(void *ctx,u32 reg) { u16 v=(u16)load(model(ctx),reg,2);trace(ctx,1,reg,2,v,0);return v; }
static u32 read4(void *ctx,u32 reg) { u32 v=load(model(ctx),reg,4);trace(ctx,1,reg,4,v,0);return v; }
static void write1(void *ctx,u32 reg,u32 v) { trace(ctx,2,reg,1,v,0);store(model(ctx),reg,1,v); }
static void write2(void *ctx,u32 reg,u16 v) { trace(ctx,2,reg,2,v,0);store(model(ctx),reg,2,v); }
static void write4(void *ctx,u32 reg,u32 v) { trace(ctx,2,reg,4,v,0);store(model(ctx),reg,4,v); }
static unsigned int shift(u32 mask) { unsigned int s=0;assert(mask);while(!(mask&1)){++s;mask>>=1;}return s; }
static void mask1(void *ctx,u32 reg,u32 mask,u8 v) { u32 old=load(model(ctx),reg,1);trace(ctx,3,reg,mask,v,0);store(model(ctx),reg,1,(old&~mask)|(((u32)v<<shift(mask))&mask)); }
static void local1(void *ctx,u32 reg,u8 v) {trace(ctx,4,reg,1,v,0);store(model(ctx),reg,1,v);}
static void bbset(void *ctx,u32 reg,u32 mask,u32 v) {u32 old=load(model(ctx),reg,4);trace(ctx,5,reg,mask,v,0);store(model(ctx),reg,4,(old&~mask)|((v<<shift(mask))&mask));}
static u32 bbget(void *ctx,u32 reg,u32 mask) {u32 v=(load(model(ctx),reg,4)&mask)>>shift(mask);trace(ctx,6,reg,mask,v,0);return v;}
static void rfset(void *ctx,u8 path,u32 reg,u32 mask,u32 v) {struct btc_model *m=model(ctx);assert(path<4&&reg<256);trace(ctx,7,path,reg,mask,v);m->rf[path][reg]=(m->rf[path][reg]&~mask)|((v<<shift(mask))&mask);}
static u32 rfget(void *ctx,u8 path,u32 reg,u32 mask) {u32 v;assert(path<4&&reg<256);v=(model(ctx)->rf[path][reg]&mask)>>shift(mask);trace(ctx,8,path,reg,mask,v);return v;}
static void h2c(void *ctx,u8 id,u32 len,u8 *data) {struct btc_trace *t;assert(len<=16);t=trace(ctx,9,id,len,0,0);memcpy(t->bytes,data,len);}
static void dbgmsg(void *ctx,u8 kind,struct seq_file *sink) {(void)sink;trace(ctx,10,kind,0,0,0);}
static bool get(void *ctx,u8 kind,void *out)
{
    struct btc_model *m=model(ctx);u32 v;unsigned int n;
    assert(kind<BTC_GET_MAX&&out);v=m->inputs[kind];
    if (kind<=BTC_GET_BL_RF4CE_CONNECTED||kind==BTC_GET_BL_BT_SCO_BUSY) {bool b=v!=0;memcpy(out,&b,sizeof(b));n=sizeof(b);v=b;}
    else if(kind>=BTC_GET_U1_WIFI_DOT11_CHNL&&kind<=BTC_GET_U1_LPS_MODE) {u8 b=(u8)v;memcpy(out,&b,1);n=1;v=b;}
    else {memcpy(out,&v,4);n=4;}
    trace(ctx,11,kind,n,v,0);return true;
}
static bool set(void *ctx,u8 kind,void *in)
{
    unsigned int n=0;u32 v=0;
    assert(kind<BTC_SET_MAX);
    if(kind<=BTC_SET_BL_MIRACAST_PLUS_BT||kind==BTC_SET_BL_BT_SCO_BUSY||kind==BTC_SET_ACT_DISABLE_LOW_POWER) n=sizeof(bool);
    else if((kind>=BTC_SET_U1_RSSI_ADJ_VAL_FOR_AGC_TABLE_ON&&kind<=BTC_SET_U1_AGG_BUF_SIZE)||
        (kind>=BTC_SET_U1_RSSI_ADJ_VAL_FOR_1ANT_COEX_TYPE&&kind<=BTC_SET_U1_1ANT_RPWM)||
        kind==BTC_SET_ACT_ANTPOSREGRISTRY_CTRL||kind==BTC_SET_ACT_SEND_MIMO_PS) n=1;
    else if(kind==BTC_SET_ACT_UPDATE_RAMASK) n=4;
    if(n) {assert(in);memcpy(&v,in,n);}
    trace(ctx,12,kind,n,v,0);
    if(kind==BTC_SET_ACT_ENTER_LPS) model(ctx)->inputs[BTC_GET_U1_LPS_MODE]=1;
    if(kind==BTC_SET_ACT_LEAVE_LPS||kind==BTC_SET_ACT_NORMAL_LPS) model(ctx)->inputs[BTC_GET_U1_LPS_MODE]=0;
    return true;
}
static void btset(void *ctx,u8 type,u32 reg,u32 v) {assert(type<5&&reg<256);trace(ctx,13,type,reg,v,0);model(ctx)->bt[type][reg]=v;}
static u32 btget(void *ctx,u8 type,u32 reg) {u32 v;assert(type<5&&reg<256);v=model(ctx)->bt[type][reg];trace(ctx,14,type,reg,v,0);return v;}
static u32 feature(void *ctx) {trace(ctx,15,1,0,0,0);return 0x1234;}
static u32 version(void *ctx) {trace(ctx,15,2,0,0,0);return 0x2345;}
static u32 phydm(void *ctx) {trace(ctx,15,3,0,0,0);return 0x3456;}
static void threshold(void *ctx,u8 dir,u8 offset) {trace(ctx,16,dir,offset,0,0);}
static u32 counter(void *ctx,enum dm_info_query id) {u32 v=17U+(u32)id*29U;trace(ctx,17,(u32)id,v,0,0);return v;}
static u8 antdet(void *ctx) {trace(ctx,18,1,0,0,0);return 1;}
static u8 blescan(void *ctx) {trace(ctx,18,2,0,0,0);return 3;}
static u32 blepara(void *ctx,u8 kind) {trace(ctx,18,3,kind,0,0);return 0x44332211;}
static bool afh(void *ctx,u8 kind,u8 *out) {unsigned int i;trace(ctx,18,4,kind,0,0);for(i=0;i<10;++i)out[i]=(u8)(i*23U);return true;}
static void delay(void *ctx,unsigned int ms) {trace(ctx,19,ms,0,0,0);}
void btc_reference_delay(unsigned int ms) {assert(btc_reference_current);delay(btc_reference_current,ms);}
static void diagnostic(void *arg,const char *fmt,va_list ap)
{
    /* Exact formatting strings, with no host-specific %p addresses. Hardware
     * reads and algorithm values are compared separately, not printf output. */
    struct btc_model *m=arg;struct btc_coexist ctx;u32 hash=2166136261U;
    (void)ap;while(*fmt) {hash^=(u8)*fmt++;hash*=16777619U;}
    memset(&ctx,0,sizeof(ctx));ctx.adapter=m;trace(&ctx,20,hash,0,0,0);
}
void btc_model_inputs(struct btc_model *m,unsigned int seed,unsigned int step)
{
    u32 v=seed*1664525U+step*1013904223U;unsigned int i;
    for(i=0;i<BTC_GET_MAX;++i)m->inputs[i]=(v>>(i%23U))&1U;
    m->inputs[BTC_GET_S4_WIFI_RSSI]=((step+seed)%3U==0)?20U:((step+seed)%3U==1?45U:80U);
    m->inputs[BTC_GET_S4_HS_RSSI]=35;
    m->inputs[BTC_GET_U4_WIFI_BW]=(step+seed)%3U;
    m->inputs[BTC_GET_U4_WIFI_TRAFFIC_DIRECTION]=(step+seed)%2U;
    m->inputs[BTC_GET_U4_WIFI_FW_VER]=((step+seed)%2U)?0x180002:0x100000;
    m->inputs[BTC_GET_U4_WIFI_LINK_STATUS]=((step+seed)%3U)<<16|WIFI_STA_CONNECTED;
    m->inputs[BTC_GET_U4_BT_PATCH_VER]=0x4321;
    m->inputs[BTC_GET_U1_WIFI_DOT11_CHNL]=(step+seed)%14U+1;
    m->inputs[BTC_GET_U1_WIFI_CENTRAL_CHNL]=(step+seed)%14U+1;
    m->inputs[BTC_GET_U1_AP_NUM]=(step+seed)%60U;
    m->inputs[BTC_GET_U1_IOT_PEER]=(step+seed)%BTC_IOT_PEER_MAX;
    m->inputs[BTC_GET_U1_LPS_MODE]=(step+seed)%2U;
    /* Exercise both zero and nonzero Bluetooth counters and old/new CCK. */
    store(m,0x770,4,(step%5U==0)?0:((step*43U&0xffffU)<<16)|(step*29U&0xffffU));
    store(m,0x774,4,(step%5U==0)?0:((step*97U&0xffffU)<<16)|(step*103U&0xffffU));
    store(m,0xf88,4,step*149U);store(m,0xf84,4,step*53U);
    store(m,0xf94,4,step*79U);store(m,0xf90,4,step*101U);
}
void btc_model_init(struct btc_model *m,struct btc_coexist *b,unsigned int ant,unsigned int path,unsigned int seed)
{
    unsigned int i;memset(m,0,sizeof(*m));memset(b,0,sizeof(*b));
    for(i=0;i<sizeof(m->mmio);++i)m->mmio[i]=(u8)(seed+i*13U);
    btc_model_inputs(m,seed,0);m->sink.arg=m;m->sink.vprintf=diagnostic;
    b->adapter=m;b->binded=true;b->chip_interface=BTC_INTF_PCI;
    b->board_info.bt_chip_type=BTC_CHIP_RTL8723B;b->board_info.pg_ant_num=(u8)ant;
    b->board_info.btdm_ant_num=(u8)ant;b->board_info.single_ant_path=(u8)path;
    b->board_info.btdm_ant_pos=(u8)path;b->board_info.tfbga_package=(seed&1U)!=0;
    b->auto_report_1ant=(seed&2U)!=0;b->auto_report_2ant=(seed&2U)!=0;
    b->btc_read_1byte=read1;b->btc_read_2byte=read2;b->btc_read_4byte=read4;
    b->btc_write_1byte=write1;b->btc_write_2byte=write2;b->btc_write_4byte=write4;
    b->btc_write_1byte_bitmask=mask1;b->btc_write_local_reg_1byte=local1;
    b->btc_set_bb_reg=bbset;b->btc_get_bb_reg=bbget;b->btc_set_rf_reg=rfset;b->btc_get_rf_reg=rfget;
    b->btc_fill_h2c=h2c;b->btc_disp_dbg_msg=dbgmsg;b->btc_get=get;b->btc_set=set;
    b->btc_set_bt_reg=btset;b->btc_get_bt_reg=btget;b->btc_get_bt_coex_supported_feature=feature;
    b->btc_get_bt_coex_supported_version=version;b->btc_get_bt_phydm_version=phydm;
    b->btc_phydm_modify_ra_pcr_threshold=threshold;b->btc_phydm_query_phy_counter=counter;
    b->btc_get_ant_det_val_from_bt=antdet;b->btc_get_ble_scan_type_from_bt=blescan;
    b->btc_get_ble_scan_para_from_bt=blepara;b->btc_get_bt_afh_map_from_bt=afh;b->r23be_delay_ms=delay;
}
struct rtwn8723be_btc_event btc_model_event(unsigned int seed,unsigned int step,unsigned int ant,struct btc_model *m)
{
    struct rtwn8723be_btc_event e;unsigned int i;u32 v=seed*1103515245U+step*12345U;
    memset(&e,0,sizeof(e));
    if(step<4) {e.kind=(enum rtwn8723be_btc_event_kind)step;e.value=(u8)(seed&1U);return e;}
    /* Ensure every notification and both sides of every binary input occur.
     * Alternating BT info / periodic drives the static adaptive histories. */
    if(step%4U==0)e.kind=R23BE_BTC_INFO;
    else if(step%4U==1)e.kind=R23BE_BTC_PERIODIC;
    else e.kind=(enum rtwn8723be_btc_event_kind)(R23BE_BTC_IPS+(step/4U)%12U);
    if(e.kind==R23BE_BTC_RF_STATUS&&ant==2)e.kind=R23BE_BTC_PERIODIC;
    if(e.kind==R23BE_BTC_HALT)e.kind=R23BE_BTC_INIT_DM; /* terminal HALT at end */
    e.value=(u8)((step/48U+seed)&1U);
    if(e.kind==R23BE_BTC_SPECIAL_PACKET)e.value=(u8)((step/48U+seed)%5U);
    if(e.kind==R23BE_BTC_PNP)e.value=(u8)((step/48U+seed)%3U);
    e.length=(u8)(1+(step/4U+seed)%10U);
    for(i=0;i<10;++i)e.info[i]=(u8)(v>>(i%4U)*8U);
    e.info[0]=(u8)((step/4U+seed)%4U);e.info[1]=(u8)((step/4U)*7U+seed);
    e.info[2]=(u8)((step/4U)&0x7fU);e.info[3]=(u8)((step/4U+seed)%100U);
    e.info[4]=(u8)((step/4U+seed)%16U);e.info[6]=(u8)((step/4U+seed)%60U);
    if(e.kind==R23BE_BTC_DISPLAY)e.diagnostic=&m->sink;
    return e;
}
void btc_model_equal(const struct btc_model *a,const struct btc_model *b)
{
    unsigned int i;if(a->count!=b->count)fprintf(stderr,"trace count %u != %u\n",a->count,b->count);
    assert(a->count==b->count);
    for(i=0;i<a->count;++i)if(memcmp(&a->trace[i],&b->trace[i],sizeof(a->trace[i]))) {
        const struct btc_trace *x=&a->trace[i],*y=&b->trace[i];
        fprintf(stderr,"trace[%u] (%u,%x,%x,%x,%x) != (%u,%x,%x,%x,%x)\n",i,x->op,x->a,x->b,x->c,x->d,y->op,y->a,y->b,y->c,y->d);abort();
    }
    assert(!memcmp(a->mmio,b->mmio,sizeof(a->mmio)));
    assert(!memcmp(a->rf,b->rf,sizeof(a->rf))&&!memcmp(a->bt,b->bt,sizeof(a->bt)));
    assert(!memcmp(a->inputs,b->inputs,sizeof(a->inputs)));
}
void btc_context_equal(const struct btc_coexist *a,const struct btc_coexist *b)
{
    struct btc_coexist x=*a,y=*b;
    x.adapter=y.adapter=NULL;x.r23be_state=y.r23be_state=NULL;
    assert(!memcmp(&x,&y,sizeof(x)));
}
void btc_state_equal(const struct rtwn8723be_btc_state *a,const struct rtwn8723be_btc_state *b)
{
    assert(a->prepared==b->prepared);btc_context_equal(&a->btc,&b->btc);
    assert(!memcmp(&a->dm1,&b->dm1,sizeof(a->dm1))&&!memcmp(&a->sta1,&b->sta1,sizeof(a->sta1)));
    assert(!memcmp(&a->dm2,&b->dm2,sizeof(a->dm2))&&!memcmp(&a->sta2,&b->sta2,sizeof(a->sta2)));
    assert(!memcmp(&a->history1,&b->history1,sizeof(a->history1))&&!memcmp(&a->history2,&b->history2,sizeof(a->history2)));
}
