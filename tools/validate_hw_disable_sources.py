#!/usr/bin/env python3
"""Link embedded raw card-disable oracle and constants to frozen Linux blobs."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
PIN = 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'
PREFIX = 'drivers/net/wireless/realtek/rtlwifi/'
ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--linux-tree', type=Path, default=Path(os.environ.get(
    'RTWN8723BE_LINUX_TREE', '/root/linux-rtl8723be-ref-fresh')))
p.add_argument('--report', type=Path)
a = p.parse_args()
refs = {path: subprocess.check_output(['git', '-C', str(a.linux_tree),
    'show', PIN + ':' + PREFIX + path]).decode() for path in
    ('rtl8723be/hw.c', 'rtl8723be/led.c', 'rtl8723be/reg.h',
     'rtl8723be/sw.c', 'wifi.h')}
def function(source, name):
    match = re.search(r'^(?:static )?(?:void|int|bool) ' + name + r'\(', source, re.M)
    assert match is not None, name
    opening = source.index('{', match.start())
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return source[match.start():i + 1]
    raise AssertionError(name)
oracle = (ROOT / 'tests/hw_disable_linux_oracle.c').read_text()
names = {'rtl8723be/hw.c': ('_rtl8723be_set_bcn_ctrl_reg',
    '_rtl8723be_stop_tx_beacon', '_rtl8723be_resume_tx_beacon',
    '_rtl8723be_enable_bcn_sub_func', '_rtl8723be_disable_bcn_sub_func',
    '_rtl8723be_set_media_status', 'rtl8723be_card_disable'),
    'rtl8723be/led.c': ('rtl8723be_sw_led_on', 'rtl8723be_sw_led_off',
    '_rtl8723be_sw_led_control', 'rtl8723be_led_control'),
    'rtl8723be/sw.c': ('rtl8723be_get_btc_status',)}
for path, funcs in names.items():
    for name in funcs:
        assert function(refs[path], name) in oracle, name + ' differs from pin'
for name in ('led_ctl_mode', 'rtl_led_pin', 'rtl_link_state'):
    enum = re.search(r'enum ' + name + r'\s*\{[\s\S]*?\};', refs['wifi.h']).group(0)
    assert enum in oracle
def macros(source):
    return dict(re.findall(r'^#define\s+(\w+)\s+([^\n]+)', source, re.M))
frozen = {**macros(refs['rtl8723be/reg.h']), **macros(refs['wifi.h'])}
source = (ROOT / 'src/rtwn8723be_hw_disable.c').read_text()
actual, oracle_macros = macros(source), macros(oracle)
registers = ('REG_FWHW_TXQ_CTRL', 'REG_TBTT_PROHIBIT', 'REG_BCN_CTRL',
             'REG_BCNTCFG', 'REG_LEDCFG1', 'REG_LEDCFG2', 'REG_MAC_PINMUX_CFG')
for name in registers:
    assert int(actual['R23HD_' + name].rstrip('U'), 0) == int(frozen[name], 0), name
    assert int(oracle_macros[name], 0) == int(frozen[name], 0), name
assert re.fullmatch(r'\(REG_CR \+ 2\)', frozen['MSR'])
assert int(frozen['REG_CR'], 0) + 2 == int(actual['R23HD_MSR'].rstrip('U'), 0)
assert int(oracle_macros['MSR'], 0) == int(actual['R23HD_MSR'].rstrip('U'), 0)
assert frozen['RF_CHANGE_BY_PS'] == 'BIT(29)'
assert frozen['RT_RF_OFF_LEVL_HALT_NIC'] == 'BIT(3)'
assert actual['R23HD_RF_CHANGE_BY_PS'] == '(UINT32_C(1) << 29)'
assert actual['R23HD_HALT_NIC'] == '(UINT32_C(1) << 3)'
assert 'MAC80211_NOLINK = 0,' in refs['wifi.h']
assert re.search(r'enum rtl_led_pin\s*\{\s*LED_PIN_GPIO0,\s*LED_PIN_LED0,\s*LED_PIN_LED1', refs['wifi.h'])
assert '\treturn true;' in function(refs['rtl8723be/sw.c'], 'rtl8723be_get_btc_status')
assert 'phy.iqk_initialized' not in source
report = {'state': 'PASSED', 'linux_pin': PIN,
    'source_sha256': {PREFIX + path: hashlib.sha256(content.encode()).hexdigest()
                      for path, content in refs.items()},
    'oracle_sha256': hashlib.sha256(oracle.encode()).hexdigest(),
    'production_sha256': hashlib.sha256(source.encode()).hexdigest(),
    'frozen_functions': 12,
    'limitation': 'Exact frozen oracle bodies/constants; adapted fallible production '
                  'sequence requires differential tests and real stop/lifetime owner.'}
if a.report:
    a.report.write_text(json.dumps(report, indent=2) + '\n')
print('HW_DISABLE_FROZEN_SOURCE_VALIDATION_PASS raw_functions=12 enums=pin '
      'registers=pin HAL_btc_capability=true IQK_cache=preserved')
