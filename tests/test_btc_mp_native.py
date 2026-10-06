#!/usr/bin/env python3
"""HP-only actual native MP C, pthread kernel/CV model and semantic controls."""
from pathlib import Path
import datetime, hashlib, json, os, platform, re, resource, shutil
import socket, subprocess, tempfile, time

ROOT = Path(__file__).resolve().parents[1]
WORK = Path('/root/hp-driver-port-20261005')
LINUX = Path(os.environ.get('RTWN8723BE_LINUX_TREE', '/root/linux-rtl8723be-ref-fresh'))
PIN = 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'
if platform.system() != 'NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
    raise SystemExit('REFUSED: compilation/tests are authorized only on HP/NetBSD')
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
assert subprocess.check_output(['git', '-C', str(LINUX), 'rev-parse', 'HEAD'], text=True).strip() == PIN
def frozen(path):
    return subprocess.check_output(['git', '-C', str(LINUX), 'show', PIN +
        ':drivers/net/wireless/realtek/rtlwifi/btcoexist/' + path], text=True)
reference = frozen('halbtcoutsrc.c')
start = reference.index('bool halbtc_send_bt_mp_operation(')
send = reference[start:reference.index('\nstatic void halbtc_leave_lps(', start)]
assert re.search(r'fill_h2c_cmd\(rtlpriv->mac80211.hw,\s*0x67,', send)
assert send.index('reinit_completion(') < send.index('fill_h2c_cmd(')
assert re.search(r'cmd_buffer,\s*[24],\s*200\)', reference)
source = ROOT / 'src/rtwn8723be_btc_mp_native.c'
native = source.read_text()
# Activation remains a real lifecycle obligation, not a fabricated BTC owner.
for path in (ROOT / 'src').glob('*.c'):
    if path != source:
        assert not re.search(r'\brtwn8723be_btc_mp_native_activate\s*\(', path.read_text()), path
out = WORK / ('rtl-btc-mp-native-proof-' + str(time.time_ns()))
out.mkdir()
proof = {'state': 'RUNNING', 'host': socket.gethostname(),
    'started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'linux_pin': PIN, 'runs': [], 'negative_controls': []}
def save():
    temp = out / 'proof.tmp'
    temp.write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    temp.replace(out / 'proof.json')
save()
model = r'''
#ifndef BTC_MP_KERNEL_MODEL_H
#define BTC_MP_KERNEL_MODEL_H
#include <sys/types.h>
#include <sys/time.h>
#include <time.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <assert.h>
#include <string.h>
#include <pthread.h>
#include <sched.h>
#define KASSERT(x) assert(x)
#define MUTEX_DEFAULT 0
#define IPL_NONE 0
#define IPL_SOFTNET 4
#define DEFAULT_TIMEOUT_EPSILON ((const struct bintime *)0)
typedef struct kmutex { pthread_mutex_t p; } kmutex_t;
typedef struct kcondvar { pthread_cond_t p; const char *name; } kcondvar_t;
bool cpu_intr_p(void);
bool cpu_softintr_p(void);
bool mutex_owned(kmutex_t *);
void mutex_init(kmutex_t *,int,int);
void mutex_destroy(kmutex_t *);
void mutex_enter(kmutex_t *);
void mutex_exit(kmutex_t *);
void cv_init(kcondvar_t *,const char *);
void cv_destroy(kcondvar_t *);
void cv_wait(kcondvar_t *,kmutex_t *);
int cv_timedwaitbt(kcondvar_t *,kmutex_t *,struct bintime *,const struct bintime *);
void cv_signal(kcondvar_t *);
void cv_broadcast(kcondvar_t *);
#endif
'''
softc = r'''
#ifndef BTC_MP_SOFTC_MODEL_H
#define BTC_MP_SOFTC_MODEL_H
#include "btc_mp_kernel_model.h"
#include "rtwn8723be_h2c_native.h"
#include "rtwn8723be_btc_mp_native.h"
struct test_env;
struct rtwn8723be_softc {
    struct rtwn8723be_btc_mp_native sc_btc_mp;
    struct rtwn8723be_h2c_native sc_h2c;
    struct { bool being_init_adapter,fw_ready,started; } sc_linux;
    bool sc_mapped,sc_irq_enabled;
    volatile uint32_t sc_irq_pending[2];
    struct test_env *env;
};
#endif
'''
try:
    with tempfile.TemporaryDirectory(prefix='rtl-btc-mp-native-', dir=WORK) as name:
        temp = Path(name); (temp / 'sys').mkdir()
        (temp / 'btc_mp_kernel_model.h').write_text(model)
        (temp / 'rtwn8723be_netbsd.h').write_text(softc)
        for header in ('param.h','systm.h','cpu.h','intr.h',
                       'mutex.h','condvar.h','timevar.h'):
            (temp / 'sys' / header).write_text('#include "btc_mp_kernel_model.h"\n')
        copied = temp / source.name
        copied.write_bytes(source.read_bytes())
        assert copied.read_bytes() == source.read_bytes()
        for flag, label in (([], 'normal'), (['-fsanitize=undefined',
                '-fno-sanitize-recover=all'], 'ubsan')):
            exe = temp / label
            cmd = ['/usr/bin/cc','-D_NETBSD_SOURCE','-std=gnu11','-O2','-g',
                '-Wall','-Wextra','-Werror','-Wshadow','-pthread',*flag,
                '-I'+str(temp),'-I'+str(ROOT/'src'),str(copied),
                str(ROOT/'src/rtwn8723be_btc_mp.c'),
                str(ROOT/'tests/btc_mp_native_check.c'),'-o',str(exe)]
            compile_run = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=150)
            (out / (label+'-compile.log')).write_text(compile_run.stdout)
            if compile_run.returncode:
                print(compile_run.stdout); raise RuntimeError('compile failed: '+label)
            run = subprocess.run([str(exe)], text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=90)
            (out / (label+'-run.log')).write_text(run.stdout)
            print(run.stdout, flush=True)
            if run.returncode: raise RuntimeError('run failed: '+label)
            counts = re.search(r'BTC_MP_NATIVE_SCENARIOS=(\d+) CHECKS=(\d+)', run.stdout)
            assert counts
            proof['runs'].append({'kind':label,'compile_exit':0,'run_exit':0,
                'scenarios':int(counts[1]),'checks':int(counts[2]),'command':cmd})
            save()
        controls = [
            ('unmatched-reply', 'reply.sequence == mp->expected_sequence',
             'true', '--negative-match'),
            ('not-armed-before-send', 'mp->pending = wait_reply;',
             'mp->pending = false;', '--negative-arm')]
        for label, original, replacement, mode in controls:
            assert native.count(original) == 1
            copied.write_text(native.replace(original,replacement), encoding='utf-8')
            exe = temp / label
            cmd = ['/usr/bin/cc','-D_NETBSD_SOURCE','-std=gnu11','-O2','-g',
                '-Wall','-Wextra','-Werror','-Wshadow','-pthread',
                '-I'+str(temp),'-I'+str(ROOT/'src'),str(copied),
                str(ROOT/'src/rtwn8723be_btc_mp.c'),
                str(ROOT/'tests/btc_mp_native_check.c'),'-o',str(exe)]
            compilation = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=150)
            (out / (label+'-compile.log')).write_text(compilation.stdout)
            assert compilation.returncode == 0, compilation.stdout
            run = subprocess.run([str(exe),mode], text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=90)
            (out / (label+'-run.log')).write_text(run.stdout)
            assert run.returncode != 0, label + ' semantic control unexpectedly passed'
            proof['negative_controls'].append({'name':label,'compile_exit':0,
                'run_exit':run.returncode,'expected':'nonzero semantic assertion'})
            save()
    inputs = [source, ROOT/'src/rtwn8723be_btc_mp_native.h',
        ROOT/'src/rtwn8723be_h2c_native.h', ROOT/'src/rtwn8723be_btc_mp.c',
        ROOT/'src/rtwn8723be_btc_mp.h', ROOT/'tests/btc_mp_native_check.c',
        Path(__file__)]
    proof.update(state='PASSED', compiled_source_sha256={str(p):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        frozen_sha256=hashlib.sha256(reference.encode()).hexdigest(),
        scope='Unmodified native C with explicit pthread mutex/CV/context, H2C and softc models. Real NetBSD object compilation is a separate gate.',
        limitations=['Activation and C2H consumer binding await a real full BTC/MCU/RX/IRQ owner.',
            'No physical firmware, whole driver, kernel link, WLAN, PM or recovery acceptance.',
            'Fixed opcode sequences cannot distinguish duplicate older same-opcode replies; reset generation is not a wire nonce.'],
        acceptance='OPEN: complete both full ports and actual HP WLAN online')
except Exception as exc:
    proof.update(state='FAILED',error=str(exc)); save(); raise
save()
print('BTC_MP_NATIVE_PROOF',out,flush=True)
