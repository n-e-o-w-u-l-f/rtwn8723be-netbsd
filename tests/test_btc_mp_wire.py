#!/usr/bin/env python3
"""HP-only actual wire C tests against pinned constants/body and guard pages."""
from pathlib import Path
import hashlib,json,os,platform,re,shutil,socket,subprocess,tempfile,time
assert platform.system()=='NetBSD' and socket.gethostname().startswith('hp-tpnw121')
ROOT=Path(__file__).resolve().parents[1];WORK=Path('/root/hp-driver-port-20261005')
LINUX=Path(os.environ.get('RTWN8723BE_LINUX_TREE','/root/linux-rtl8723be-ref-fresh'))
PIN='fd179f8a05be3ccae366b9b96e176b51fbe54aab'
assert subprocess.check_output(['git','-C',str(LINUX),'rev-parse','HEAD'],text=True).strip()==PIN
def frozen(path):return subprocess.check_output(['git','-C',str(LINUX),'show',PIN+':drivers/net/wireless/realtek/rtlwifi/btcoexist/'+path],text=True)
header=frozen('halbtcoutsrc.h');source=frozen('rtl_btc.c');send=frozen('halbtcoutsrc.c')
constants={name:int(value,0) for name,value in re.findall(r'\b(BT_(?:OP|SEQ)_\w+)\s*=\s*(0x[0-9a-fA-F]+|\d+)',header)}
start=source.index('void rtl_btc_btmpinfo_notify(')
end=source.index('\nbool rtl_btc_is_limited_dig(',start)
body=source[start:end].replace('rtl_btc_btmpinfo_notify','reference_btmp_notify',1)
assert 'case BT_OP_GET_BT_FORBIDDEN_SLOT_VAL:' in body
assert constants['BT_OP_GET_BT_FORBIDDEN_SLOT_VAL']==49 and constants['BT_SEQ_GET_BT_FORB_SLOT_VAL']==11
start_send=send.index('bool halbtc_send_bt_mp_operation(');end_send=send.index('\nstatic void halbtc_leave_lps(',start_send)
request=send[start_send:end_send]
pairs=re.findall(r'case\s+(BT_OP_\w+):\s*req_num\s*=\s*(BT_SEQ_\w+);',request)
assert len(pairs)==11,len(pairs)
seq=[0]*256
for op,key in pairs:seq[constants[op]]=constants[key]
# Extents independently follow the actual frozen payload loads.
need=[4]*16
for key,n in [('BT_SEQ_GET_BT_VERSION',6),('BT_SEQ_GET_AFH_MAP_L',7),
    ('BT_SEQ_GET_AFH_MAP_M',7),('BT_SEQ_GET_AFH_MAP_H',5),
    ('BT_SEQ_GET_BT_COEX_SUPPORTED_FEATURE',5),('BT_SEQ_GET_BT_COEX_SUPPORTED_VERSION',5),
    ('BT_SEQ_GET_BT_BLE_SCAN_PARA',7),('BT_SEQ_GET_BT_DEVICE_INFO',7)]:
 need[constants[key]]=n
reference=r"""typedef uint8_t u8;
typedef uint16_t u16;
typedef uint16_t __le16;
typedef uint32_t __le32;
struct btc_bt_info {
 u16 bt_real_fw_ver;u8 bt_fw_ver;
 uint32_t afh_map_l,afh_map_m;uint16_t afh_map_h;
 uint32_t bt_supported_feature,bt_supported_version;
 uint8_t bt_ant_det_val,bt_ble_scan_type;uint32_t bt_ble_scan_para,bt_device_info,bt_forb_slot_val;
};
struct model_completion { unsigned done; };
struct btc_coexist { struct btc_bt_info bt_info;struct model_completion bt_mp_comp; };
struct rtl_priv { struct btc_coexist *context; };
#define rtl_btc_coexist(p) ((p)->context)
#define rtl_dbg(...) ((void)0)
#define le32_to_cpu(x) le32toh(x)
#define le16_to_cpu(x) le16toh(x)
static void complete(struct model_completion *c) { c->done++; }
"""
reference+=''.join('#define '+name+' '+str(value)+'\n' for name,value in sorted(constants.items()))+body
reference+='\nstatic const uint8_t gold_request_sequence[256]={'+','.join(map(str,seq))+'};\n'
reference+='static const uint8_t gold_min_length[16]={'+','.join(map(str,need))+'};\n'
out=WORK/('rtl-btc-mp-wire-proof-'+str(time.time_ns()));out.mkdir()
with tempfile.TemporaryDirectory(prefix='rtl-btc-mp-wire-',dir=WORK) as name:
 temp=Path(name);(temp/'btc_mp_reference.inc').write_text(reference)
 command=['/usr/bin/cc','-D_NETBSD_SOURCE','-std=gnu11','-O2','-g','-Wall','-Wextra','-Werror','-Wshadow','-fsanitize=undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'src'),'-I'+str(temp),str(ROOT/'src/rtwn8723be_btc_mp.c'),str(ROOT/'src/rtwn8723be_c2h.c'),str(ROOT/'tests/btc_mp_wire_check.c'),'-o',str(temp/'check')]
 run=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150)
 (out/'compile.log').write_text(run.stdout)
 if run.returncode:print(run.stdout);raise SystemExit(run.returncode)
 run=subprocess.run([str(temp/'check')],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
 (out/'run.log').write_text(run.stdout);print(run.stdout)
 if run.returncode:raise SystemExit(run.returncode)
 shutil.copyfile(temp/'btc_mp_reference.inc',out/'btc_mp_reference.inc')
 proof={'state':'PASSED','host':socket.gethostname(),'linux_pin':PIN,'command':command,
    'compile_exit':0,'run_exit':0,'request_opcode_sequence_pairs':pairs,'response_min_lengths':need,
    'frozen_sha256':{name:hashlib.sha256(text.encode()).hexdigest() for name,text in [('halbtcoutsrc.h',header),('rtl_btc.c',source),('halbtcoutsrc.c',send)]},
    'compiled_source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'src/rtwn8723be_btc_mp.c',ROOT/'src/rtwn8723be_btc_mp.h',ROOT/'src/rtwn8723be_c2h.c',ROOT/'tests/btc_mp_wire_check.c']},
    'scope':'actual wire functions and frozen well-formed-body comparison; explicit reference-only completion model, no native BTC context/transaction/lifetime/WLAN claim',
    'forbidden_slot_source_case_unreachable':True,'acceptance':'OPEN: full BTC/native transaction and full port/HP WLAN online'}
 (out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
 print('BT_MP_WIRE_PROOF',out)
