/* SPDX-License-Identifier: GPL-2.0 */
#include "btc_algorithm_model.h"

static u64 hash_bytes(u64 h,const void *ptr,size_t len)
{
    const u8 *p=ptr;while(len--){h^=*p++;h*=UINT64_C(1099511628211);}return h;
}
static u64 snapshot(const struct btc_model *m,const struct rtwn8723be_btc_state *s)
{
    struct rtwn8723be_btc_state copy=*s;u64 h=UINT64_C(14695981039346656037);
    copy.btc.adapter=NULL;copy.btc.r23be_state=NULL;
    h=hash_bytes(h,&copy,sizeof(copy));h=hash_bytes(h,m->trace,m->count*sizeof(m->trace[0]));
    return h;
}

static void differential(unsigned int ant,unsigned int path,unsigned int seed)
{
    struct btc_model *raw=calloc(1,sizeof(*raw)),*port=calloc(1,sizeof(*port));
    struct btc_coexist original,input;struct rtwn8723be_btc_state s;
    unsigned int step,operations=0;
    assert(raw&&port);memset(&s,0,sizeof(s));
    btc_model_init(raw,&original,ant,path,seed);btc_model_init(port,&input,ant,path,seed);
    assert(rtwn8723be_btc_engine_init(&s,&input)==0);
    for(step=0;step<516;++step) {
        struct rtwn8723be_btc_event x,y;
        btc_model_inputs(raw,seed,step);btc_model_inputs(port,seed,step);
        raw->count=port->count=0;x=btc_model_event(seed,step,ant,raw);y=x;
        if(x.kind==R23BE_BTC_DISPLAY)y.diagnostic=&port->sink;
        if(step==515)x.kind=y.kind=R23BE_BTC_HALT;
        btc_reference_current=&original;
        if(ant==1) {
            struct coex_dm_8723b_1ant dm;struct coex_sta_8723b_1ant sta;
            btc_reference1(&original,&x,&dm,&sta);
            assert(rtwn8723be_btc_engine_execute(&s,&y)==0);
            assert(!memcmp(&dm,&s.dm1,sizeof(dm)));assert(!memcmp(&sta,&s.sta1,sizeof(sta)));
        } else {
            struct coex_dm_8723b_2ant dm;struct coex_sta_8723b_2ant sta;
            btc_reference2(&original,&x,&dm,&sta);
            assert(rtwn8723be_btc_engine_execute(&s,&y)==0);
            assert(!memcmp(&dm,&s.dm2,sizeof(dm)));assert(!memcmp(&sta,&s.sta2,sizeof(sta)));
        }
        btc_context_equal(&original,&s.btc);btc_model_equal(raw,port);operations+=port->count;
    }
    printf("BTC_DIFFERENTIAL ant=%u path=%u seed=%u EVENTS=516 OPERATIONS=%u\n",ant,path,seed,operations);
    free(raw);free(port);
}
static void isolation(unsigned int ant,unsigned int path,unsigned int seed)
{
    struct btc_model *m[4];struct rtwn8723be_btc_state s[4];struct btc_coexist input;
    unsigned int i,step;u64 expected[2][516];
    memset(s,0,sizeof(s));
    for(i=0;i<4;++i){m[i]=calloc(1,sizeof(*m[i]));assert(m[i]);btc_model_init(m[i],&input,ant,path,seed+(i%2U)*17U);assert(!rtwn8723be_btc_engine_init(&s[i],&input));}
    /* Each isolated baseline consumes all of its sequence before the second
     * device. Then run those same sequences interleaved in the other pair. */
    for(i=0;i<2;++i)for(step=0;step<516;++step){struct rtwn8723be_btc_event e;btc_model_inputs(m[i],seed+i*17U,step);m[i]->count=0;e=btc_model_event(seed+i*17U,step,ant,m[i]);assert(!rtwn8723be_btc_engine_execute(&s[i],&e));expected[i][step]=snapshot(m[i],&s[i]);}
    for(step=0;step<516;++step)for(i=2;i<4;++i){struct rtwn8723be_btc_event e;btc_model_inputs(m[i],seed+(i%2U)*17U,step);m[i]->count=0;e=btc_model_event(seed+(i%2U)*17U,step,ant,m[i]);assert(!rtwn8723be_btc_engine_execute(&s[i],&e));assert(snapshot(m[i],&s[i])==expected[i%2U][step]);}
    for(i=0;i<2;++i){btc_model_equal(m[i],m[i+2]);btc_state_equal(&s[i],&s[i+2]);}
    printf("BTC_ISOLATION ant=%u path=%u seed=%u EVENTS=2064\n",ant,path,seed);
    for(i=0;i<4;++i)free(m[i]);
}
static void rejects(void)
{
    struct btc_model *m=calloc(1,sizeof(*m));struct btc_coexist input,copy;
    struct rtwn8723be_btc_state s,before;struct rtwn8723be_btc_event e;
    unsigned int cases=0;assert(m);btc_model_init(m,&input,1,0,1);
#define MISSING(field) do { copy=input;copy.field=NULL;memset(&s,0,sizeof(s));before=s;assert(rtwn8723be_btc_engine_init(&s,&copy)==ENOSYS);assert(!memcmp(&s,&before,sizeof(s))&&m->count==0);++cases;} while(0)
    MISSING(btc_read_1byte);MISSING(btc_write_1byte);MISSING(btc_write_1byte_bitmask);
    MISSING(btc_read_2byte);MISSING(btc_write_2byte);MISSING(btc_read_4byte);MISSING(btc_write_4byte);
    MISSING(btc_write_local_reg_1byte);MISSING(btc_set_bb_reg);MISSING(btc_get_bb_reg);
    MISSING(btc_set_rf_reg);MISSING(btc_get_rf_reg);MISSING(btc_fill_h2c);MISSING(btc_disp_dbg_msg);
    MISSING(btc_get);MISSING(btc_set);MISSING(btc_set_bt_reg);MISSING(btc_get_bt_reg);
    MISSING(btc_get_bt_coex_supported_feature);MISSING(btc_get_bt_coex_supported_version);
    MISSING(btc_get_bt_phydm_version);MISSING(btc_phydm_modify_ra_pcr_threshold);
    MISSING(btc_phydm_query_phy_counter);MISSING(btc_get_ant_det_val_from_bt);
    MISSING(btc_get_ble_scan_type_from_bt);MISSING(btc_get_ble_scan_para_from_bt);
    MISSING(btc_get_bt_afh_map_from_bt);MISSING(r23be_delay_ms);
#undef MISSING
    memset(&s,0,sizeof(s));assert(!rtwn8723be_btc_engine_init(&s,&input));before=s;
    assert(rtwn8723be_btc_engine_init(&s,&input)==EALREADY);++cases;
    memset(&e,0,sizeof(e));e.kind=R23BE_BTC_INFO;
    assert(rtwn8723be_btc_engine_execute(&s,&e)==EINVAL);++cases;
    e.length=11;assert(rtwn8723be_btc_engine_execute(&s,&e)==EINVAL);++cases;
    e.kind=R23BE_BTC_EVENT_COUNT;assert(rtwn8723be_btc_engine_execute(&s,&e)==EINVAL);++cases;
    e.kind=R23BE_BTC_DISPLAY;assert(rtwn8723be_btc_engine_execute(&s,&e)==EINVAL);++cases;
    assert(!memcmp(&s,&before,sizeof(s))&&m->count==0);
    input.board_info.btdm_ant_num=2;memset(&s,0,sizeof(s));assert(!rtwn8723be_btc_engine_init(&s,&input));before=s;
    e.kind=R23BE_BTC_RF_STATUS;assert(rtwn8723be_btc_engine_execute(&s,&e)==ENOTSUP);++cases;
    assert(!memcmp(&s,&before,sizeof(s))&&m->count==0);
    printf("BTC_REJECT_CASES=%u\n",cases);free(m);
}
int main(int argc,char **argv)
{
    unsigned int ant,path,seed;
    if(argc==2&&!strcmp(argv[1],"rejects")){rejects();return 0;}
    assert(argc==5);ant=(unsigned int)strtoul(argv[2],NULL,10);path=(unsigned int)strtoul(argv[3],NULL,10);seed=(unsigned int)strtoul(argv[4],NULL,10);
    if(!strcmp(argv[1],"isolation"))isolation(ant,path,seed);
    else {assert(!strcmp(argv[1],"differential"));differential(ant,path,seed);}
    return 0;
}
