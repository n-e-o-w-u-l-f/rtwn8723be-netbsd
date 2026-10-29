#!/usr/bin/env python3
"""HP-only actual BTC native broker, pthread workqueue model and copy control."""
from pathlib import Path
import datetime, hashlib, json, os, platform, resource, socket
import subprocess, tempfile, time

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(os.environ.get('RTWN8723BE_HP_WORKDIR', '/root/hp-driver-port-20261005'))
if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
    raise SystemExit('REFUSED: compilation/tests are authorized only on HP/NetBSD')
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
out=WORK/('rtl-btc-native-proof-'+str(time.time_ns()));out.mkdir()
proof={'state':'RUNNING','host':socket.gethostname(),
    'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'runs':[],'negative_controls':[]}
def save():
    tmp=out/'proof.tmp';tmp.write_text(json.dumps(proof,indent=2)+'\n');tmp.replace(out/'proof.json')
save()
softc='''#ifndef BTC_NATIVE_SOFTC_MODEL_H
#define BTC_NATIVE_SOFTC_MODEL_H
#include "btc_native_kernel_model.h"
#include "rtwn8723be_btc_native.h"
#include "rtwn8723be_c2h.h"
#include "rtwn8723be_linux_state.h"
struct test_env;
struct rtwn8723be_softc {
    struct rtwn8723be_btc_native sc_btc;
    struct rtwn8723be_linux_state sc_linux;
    /* Mirror only the fields now read by the real native BT callback. */
    struct { bool initialized; } sc_h2c;
    bool sc_mapped;
    bool sc_btcoexist;
    bool sc_irq_enabled;
    struct test_env *env;
};
#endif
'''
source=ROOT/'src/rtwn8723be_btc_native.c'
try:
    with tempfile.TemporaryDirectory(prefix='rtl-btc-native-',dir=WORK) as name:
        temp=Path(name);(temp/'sys').mkdir()
        (temp/'rtwn8723be_netbsd.h').write_text(softc)
        for header in ('param.h','systm.h','cpu.h','intr.h','proc.h','mutex.h','condvar.h','workqueue.h'):
            (temp/'sys'/header).write_text('#include "btc_native_kernel_model.h"\n')
        copied=temp/source.name;copied.write_bytes(source.read_bytes())
        assert copied.read_bytes()==source.read_bytes()
        def compile_to(label,flags=()):
            exe=temp/label
            cmd=['/usr/bin/cc','-D_NETBSD_SOURCE','-std=gnu11','-O2','-g',
                '-Wall','-Wextra','-Werror','-Wshadow','-pthread',*flags,
                '-I'+str(temp),'-I'+str(ROOT/'src'),'-I'+str(ROOT/'tests'),
                str(copied),str(ROOT/'src/rtwn8723be_btc_engine.c'),
                str(ROOT/'tests/btc_algorithm_model.c'),str(ROOT/'tests/btc_native_check.c'),'-o',str(exe)]
            result=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150)
            (out/(label+'-compile.log')).write_text(result.stdout)
            if result.returncode:print(result.stdout);raise RuntimeError('compile: '+label)
            return exe,cmd
        for label,flags in [('normal',()),('ubsan',('-fsanitize=undefined','-fno-sanitize-recover=all'))]:
            exe,cmd=compile_to(label,flags)
            run=subprocess.run([str(exe)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
            (out/(label+'-run.log')).write_text(run.stdout);print(run.stdout,flush=True)
            if run.returncode:raise RuntimeError('run: '+label)
            import re
            counts=re.search(r'BTC_NATIVE_SCENARIOS=(\d+) CHECKS=(\d+)',run.stdout);assert counts
            proof['runs'].append({'kind':label,'scenarios':int(counts[1]),'checks':int(counts[2]),
                'compile_exit':0,'run_exit':0,'command':cmd});save()
        needle='memcpy(copied.info, event->payload, copied.length);'
        native=source.read_text();assert native.count(needle)==1
        copied.write_text(native.replace(needle,'memset(copied.info, 0, copied.length);'))
        exe,cmd=compile_to('negative-discard-c2h')
        run=subprocess.run([str(exe),'copy-only'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
        (out/'negative-discard-c2h-run.log').write_text(run.stdout)
        assert run.returncode!=0,'discarding copied BT info unexpectedly accepted'
        proof['negative_controls'].append({'name':'discard-c2h-copy','compile_exit':0,
            'run_exit':run.returncode,'expected':'nonzero copied-payload assertion'})
    inputs=[source,ROOT/'src/rtwn8723be_btc_native.h',ROOT/'src/rtwn8723be_btc_engine.c',
        ROOT/'src/rtwn8723be_btc_engine.h',ROOT/'tests/btc_native_check.c',
        ROOT/'tests/btc_native_kernel_model.h',ROOT/'tests/btc_algorithm_model.c',Path(__file__)]
    proof.update(state='PASSED',source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        scope='Actual native C and source dispatch with pthread-backed modeled NetBSD mutex/CV/single-worker workqueue and modeled algorithm bodies. Copied C2H data, asynchronous/synchronous stop race, overflow quarantine, first-error isolation, self-stop, context guards and allocation unwind.',
        limitations=['Algorithm bodies are modeled here and independently compared against the frozen Linux source in test_btc_algorithms.py.',
            'Real NetBSD primitive execution, 27 OS providers, state producer/MCU/RX/RF/PM owner binding and fault recovery remain OPEN.',
            'No full kernel, live Bluetooth firmware transaction, WLAN or suspend/resume acceptance.'],
        acceptance='OPEN: both complete ports and HP WLAN online')
except Exception as exc:
    proof.update(state='FAILED',error=str(exc));save();raise
save();print('BTC_NATIVE_PROOF',out,flush=True)
