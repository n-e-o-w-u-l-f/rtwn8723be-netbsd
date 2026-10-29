#!/usr/bin/env python3
"""HP-only frozen Linux vs actual port C trace/state and device isolation."""
from pathlib import Path
import datetime, hashlib, json, os, platform, re, resource, socket
import subprocess, tempfile, time

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(os.environ.get('RTWN8723BE_HP_WORKDIR',
                           '/root/hp-driver-port-20261005'))
LINUX = Path(os.environ.get('RTWN8723BE_LINUX_TREE', '/root/linux-rtl8723be-ref-fresh'))
PIN = 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'
if platform.system() != 'NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
    raise SystemExit('REFUSED: compilation/tests are authorized only on HP/NetBSD')
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
assert subprocess.check_output(['git','-C',str(LINUX),'rev-parse','HEAD'],text=True).strip() == PIN
subprocess.run(['python3', '-B', str(ROOT/'tools/generate_btc_algorithms.py'),
    '--linux-tree',str(LINUX),'--check'],check=True)
out = WORK / ('rtl-btc-algorithm-proof-' + str(time.time_ns()))
out.mkdir()
proof = {'state':'RUNNING','host':socket.gethostname(),'linux_pin':PIN,
    'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'runs':[],'negative_controls':[]}
def save():
    tmp=out/'proof.tmp';tmp.write_text(json.dumps(proof,indent=2)+'\n');tmp.replace(out/'proof.json')
save()

def raw(ant):
    return subprocess.check_output(['git','-C',str(LINUX),'show',PIN+
        ':drivers/net/wireless/realtek/rtlwifi/btcoexist/halbtc8723b'+str(ant)+'ant.c'],text=True)

def wrapper(ant, source):
    prefix='ex_btc8723b'+str(ant)+'ant_'
    names=sorted(set(re.findall(r'\b'+prefix+r'\w+',source)))
    code=''.join('#define '+name+' ref_'+name+'\n' for name in names)
    code+='#include "btc_algorithm_model.h"\n#include "raw'+str(ant)+'.c"\n'
    code+='void btc_reference'+str(ant)+'(struct btc_coexist *b,const struct rtwn8723be_btc_event *e,\n'
    code+='struct coex_dm_8723b_'+str(ant)+'ant *dm,struct coex_sta_8723b_'+str(ant)+'ant *sta)\n{\n'
    code+='u8 copied[10];memcpy(copied,e->info,e->length);switch(e->kind){\n'
    entries={'POWER_ON':'power_on_setting(b)','INIT_DM':'init_coex_dm(b)',
        'INIT_HW':'init_hwconfig(b,e->value!=0)' if ant==1 else 'init_hwconfig(b)',
        'IPS':'ips_notify(b,e->value)','LPS':'lps_notify(b,e->value)',
        'SCAN':'scan_notify(b,e->value)','CONNECT':'connect_notify(b,e->value)',
        'MEDIA':'media_status_notify(b,e->value)','SPECIAL_PACKET':'special_packet_notify(b,e->value)',
        'INFO':'bt_info_notify(b,copied,e->length)','HALT':'halt_notify(b)',
        'PNP':'pnp_notify(b,e->value)','PERIODIC':'periodical(b)',
        'DISPLAY':'display_coex_info(b,e->diagnostic)'}
    if ant==1: entries['RF_STATUS']='rf_status_notify(b,e->value)'
    else: entries['PRELOAD']='pre_load_firmware(b)'
    for kind,call in entries.items():code+='case R23BE_BTC_'+kind+':'+prefix+call+';break;\n'
    if ant==1: code+='case R23BE_BTC_PRELOAD:break;\n'
    code+='default:assert(false);}\n*dm=*coex_dm;*sta=*coex_sta;\n}\n'
    return code

try:
    with tempfile.TemporaryDirectory(prefix='rtl-btc-algorithms-',dir=WORK) as name:
        temp=Path(name)
        (temp/'halbt_precomp.h').write_text('''#include "btc_algorithm_model.h"
struct rtl_priv;
static inline void btc_reference_debug(unsigned long c,int l,const char *f,...) {(void)c;(void)l;(void)f;}
#define rtl_dbg(ctx,c,l,...) do {(void)(ctx);btc_reference_debug(c,l,__VA_ARGS__);}while(0)
#define mdelay(ms) btc_reference_delay(ms)
''')
        for ant in (1,2):
            source=raw(ant);(temp/('raw'+str(ant)+'.c')).write_text(source)
            (temp/('reference'+str(ant)+'.c')).write_text(wrapper(ant,source))
        def compile_to(exe, flags=(), mutated=False):
            cmd=['/usr/bin/cc','-D_NETBSD_SOURCE','-std=gnu11','-O2','-g',
                '-Wall','-Wextra','-Werror','-Wshadow','-Wno-unused-parameter',*flags,
                '-I'+str(temp),'-I'+str(ROOT/'src'),'-I'+str(ROOT/'tests'),
                str(temp/'reference1.c'),str(temp/'reference2.c'),
                str(temp/'mutated.c' if mutated else ROOT/'src/rtwn8723be_btc1.c'),
                str(ROOT/'src/rtwn8723be_btc2.c'),str(ROOT/'src/rtwn8723be_btc_engine.c'),
                str(ROOT/'tests/btc_algorithm_model.c'),str(ROOT/'tests/btc_algorithm_check.c'),'-o',str(exe)]
            result=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150)
            (out/(exe.name+'-compile.log')).write_text(result.stdout)
            if result.returncode: print(result.stdout);raise RuntimeError('compile: '+exe.name)
            return cmd
        for label,flags in [('normal',()),('ubsan',('-fsanitize=undefined','-fno-sanitize-recover=all'))]:
            exe=temp/label;cmd=compile_to(exe,flags);logs=[];events=operations=scenarios=0
            cases=[['rejects']]+[[mode,str(ant),str(path),str(seed)]
                for mode in ('differential','isolation') for ant in (1,2) for path in (0,1) for seed in (1,2,3,9)]
            for args in cases:
                run=subprocess.run([str(exe),*args],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
                logs.append(run.stdout);(out/(label+'-run.log')).write_text(''.join(logs))
                if run.returncode:print(run.stdout);raise RuntimeError('run: '+str(args))
                scenarios+=1
                for count in re.findall(r'EVENTS=(\d+)',run.stdout): events+=int(count)
                for count in re.findall(r'OPERATIONS=(\d+)',run.stdout): operations+=int(count)
            proof['runs'].append({'kind':label,'scenarios':scenarios,'events':events,
                'differential_operations':operations,'compile_exit':0,'run_exit':0,'command':cmd})
            save();print('BTC_ALGORITHM',label,'SCENARIOS',scenarios,'EVENTS',events,'OPERATIONS',operations,flush=True)
        # Deliberately restoring shared function histories must fail semantic
        # isolation assertions after compiling successfully.
        source=(ROOT/'src/rtwn8723be_btc1_linux.inc').read_text()
        needle='r23be_btc_state(btcoexist)->history1.'
        assert source.count(needle)>20
        source=source.replace(needle,'test_shared_history.')
        source=source.replace('#include "rtwn8723be_btc_engine.h"',
            '#include "rtwn8723be_btc_engine.h"\nstatic struct rtwn8723be_btc_history1 test_shared_history;')
        (temp/'mutated.inc').write_text(source);(temp/'mutated.c').write_text('#include "mutated.inc"\n')
        exe=temp/'negative-shared-history';compile_to(exe,mutated=True)
        run=subprocess.run([str(exe),'isolation','1','0','3'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
        (out/'negative-shared-history-run.log').write_text(run.stdout)
        assert run.returncode!=0,'shared histories unexpectedly accepted'
        proof['negative_controls'].append({'name':'shared-function-histories',
            'compile_exit':0,'run_exit':run.returncode,'expected':'nonzero isolation assertion'})
    inputs=list((ROOT/'src').glob('rtwn8723be_btc*'))+[ROOT/'tools/generate_btc_algorithms.py',Path(__file__),
        ROOT/'tests/btc_algorithm_model.h',ROOT/'tests/btc_algorithm_model.c',ROOT/'tests/btc_algorithm_check.c']
    proof.update(state='PASSED',source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        scope='Actual unmodified pinned Linux algorithm bodies vs actual port C. Exact IO/H2C/get/set/delay traces, DM/STA/context and per-step device isolation under modeled callbacks.',
        limitations=['Callback test model does not prove the real 27 NetBSD providers, state producers or full lifecycle.',
            'Diagnostic format strings are compared; rendered Linux %Nph formatting remains a native sink obligation.',
            'Native kernel object compilation and physical WLAN/PM/recovery acceptance remain separate gates.'],
        acceptance='OPEN: both complete ports and HP WLAN online')
except Exception as exc:
    proof.update(state='FAILED',error=str(exc));save();raise
save();print('BTC_ALGORITHM_PROOF',out,flush=True)
