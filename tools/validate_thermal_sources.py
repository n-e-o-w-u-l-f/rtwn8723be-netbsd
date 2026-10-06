#!/usr/bin/env python3
"""Source-only linkage of thermal tables, helpers and constants to Linux pin."""
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
    ('rtl8723be/dm.c', 'rtl8723be/dm.h', 'rtl8723be/reg.h', 'rtl8723be/hw.c', 'wifi.h')}
dm = refs['rtl8723be/dm.c']

def function(source, name):
    start = re.search(r'(?:static )?void ' + re.escape(name) + r'\(', source).start()
    opening = source.index('{', start)
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError(name)

tables = dm[dm.index('static const u32 ofdmswing_table'):
            dm.index('static const u32 edca_setting_dl')]
matrix = function(dm, 'rtl8723be_set_iqk_matrix')
matrix = matrix.replace('struct ieee80211_hw *hw', 'struct thermal_work *hw')
matrix = matrix.replace('rtl8723be_set_iqk_matrix', 'thermal_set_matrix')
matrix = matrix.replace('rtl_set_bbreg', 'thermal_set_bb')
matrix = re.sub(r'\bu8\b', 'uint8_t', matrix)
matrix = re.sub(r'\blong\b', 'int32_t', matrix)
matrix = re.sub(r'iqk_result_([xy]) = iqk_result_\1 \| 0xFFFFFC00;',
    r'iqk_result_\1 -= 0x400;', matrix)
port_tables = re.sub(r'\bu32\b', 'uint32_t', tables)
port_tables = re.sub(r'\bu8\b', 'uint8_t', port_tables)
expected = ('/* SPDX-License-Identifier: GPL-2.0 */\n'
    '/* Copyright(c) 2009-2014 Realtek Corporation. */\n'
    '/* Frozen RTL8723BE DM swing tables and adapted thermal helpers. */\n' +
    port_tables + '\n' + matrix)
actual_tables = (ROOT / 'src/rtwn8723be_thermal_linux.inc').read_text()
assert expected.rstrip('\n') == actual_tables.rstrip('\n')

body = function(dm, 'rtl8723be_dm_txpower_tracking_callback_thermalmeter')
body = body.replace('struct ieee80211_hw *hw', 'struct thermal_work *hw')
body = body.replace('rtl8723be_dm_txpower_tracking_callback_thermalmeter', 'thermal_callback_body')
body = re.sub(r'\tstruct rtl_priv \*rtlpriv = rtl_priv\(hw\);\n', '', body)
body = re.sub(r'\tstruct rtl_efuse \*rtlefuse = rtl_efuse\(rtl_priv\(hw\)\);\n', '', body)
body = re.sub(r'\tstruct rtl_dm\s*\*rtldm = rtl_dm\(rtl_priv\(hw\)\);\n', '', body)
body = re.sub(r'rtl_dbg\([\s\S]*?\);', '((void)0);', body)
for old, new in (('rtlpriv->dm.', 'hw->dm->'), ('rtldm->', 'hw->dm->'),
    ('rtlefuse->eeprom_thermalmeter', 'hw->eeprom'),
    ('rtl_get_rfreg', 'thermal_get_rf'),
    ('rtl8723be_phy_lc_calibrate', 'thermal_lck'),
    ('rtl8723be_phy_iq_calibrate', 'thermal_iqk')):
    body = body.replace(old, new)
body = re.sub(r'rtl8723be_dm_tx_power_track_set_power\(hw, BBSWING, 0,\s*index_for_channel\);',
    'thermal_set_power(hw);', body)
body = body.replace('\tu8 index_for_channel = 0;\n', '')
for old, new in (('u32', 'uint32_t'), ('u8', 'uint8_t'), ('s8', 'int8_t')):
    body = re.sub(r'\b' + old + r'\b', new, body)
expected = ('/* SPDX-License-Identifier: GPL-2.0 */\n'
    '/* Copyright(c) 2009-2014 Realtek Corporation. */\n' + body)
actual_body = (ROOT / 'src/rtwn8723be_thermal_body.inc').read_text()
assert expected.rstrip('\n') == actual_body.rstrip('\n')
oracle = (ROOT / 'tests/thermal_linux_oracle.c').read_text()
assert tables in oracle
for name in ('rtl8723be_set_iqk_matrix', 'rtl8723be_dm_tx_power_track_set_power',
             'rtl8723be_dm_txpower_tracking_callback_thermalmeter'):
    assert function(dm, name) in oracle, 'oracle differs from pin: ' + name

def macros(source):
    return dict(re.findall(r'^#define\s+([A-Za-z_0-9]+)\s+([^\s/]+)', source, re.M))
frozen = {**macros(refs['rtl8723be/reg.h']), **macros(refs['rtl8723be/dm.h']),
          **macros(refs['wifi.h'])}
names = ('RF_T_METER', 'ROFDM0_XATXIQIMBALANCE', 'ROFDM0_XCTXAFE',
         'ROFDM0_ECCATHRESHOLD', 'MASKDWORD', 'MASKH4BITS',
         'TXSCALE_TABLE_SIZE', 'OFDM_TABLE_SIZE', 'CCK_TABLE_SIZE',
         'AVG_THERMAL_NUM_8723BE', 'IQK_THRESHOLD')
for name in names:
    assert int(macros(oracle)[name].rstrip('U'), 0) == int(frozen[name].rstrip('U'), 0), name
source_macros = macros((ROOT / 'src/rtwn8723be_thermal.c').read_text())
for name in names:
    if name != 'MASKDWORD':
        assert int(source_macros[name].rstrip('U'), 0) == int(frozen[name].rstrip('U'), 0), name
assert source_macros['MASKDWORD'] == 'UINT32_MAX'
for name in ('EEPROM_THERMAL_METER_88E', 'EEPROM_DEFAULT_THERMALMETER'):
    assert int(source_macros[name].rstrip('U'), 0) == int(frozen[name], 0), name
hw = refs['rtl8723be/hw.c']
assert 'hwinfo[EEPROM_THERMAL_METER_88E]' in hw
assert 'rtlefuse->eeprom_thermalmeter == 0xff || autoload_fail' in hw
assert 'rtlefuse->apk_thermalmeterignore = true;' in hw
assert re.search(r'enum pwr_track_control_method\s*\{\s*BBSWING\s*,\s*TXAGC', refs['rtl8723be/dm.h'])

# Field widths and array bounds are part of the frozen signed/clamping behavior.
header = (ROOT / 'src/rtwn8723be_thermal.h').read_text()
fields = ('txpower_tracking txpower_trackinginit done_txpower cck_inch14 '
          'txpower_track_control txpowercount tm_trigger thermalvalue '
          'thermalvalue_lck thermalvalue_iqk thermalvalue_avg '
          'thermalvalue_avg_index ofdm_index cck_index delta_power_index '
          'delta_power_index_last power_index_offset swing_idx_ofdm '
          'swing_idx_ofdm_base swing_idx_cck swing_idx_cck_base').split()
rtl_dm = re.search(r'struct rtl_dm\s*\{([\s\S]*?)^\};', refs['wifi.h'], re.M).group(1)
for name in fields:
    frozen_field = re.search(r'\b(bool|u8|s8)\s+' + name + r'(\[[^\]]+\])?;', rtl_dm)
    assert frozen_field is not None, name
    kind, bound = frozen_field.groups()
    kind = {'u8': 'uint8_t', 's8': 'int8_t'}.get(kind, kind)
    if bound:
        dimension = bound.strip('[]')
        bound = '[' + str(int(frozen.get(dimension, dimension), 0)) + ']'
    declaration = re.search(r'\b' + kind + r'\s+([^;]+);', header)
    assert any(re.search(r'\b' + name + re.escape(bound or '') + r'\s*(?:,|;)',
                         match.group(0)) for match in
               re.finditer(r'\b' + kind + r'\s+[^;]+;', header)), name
    assert re.search(r'\b' + name + re.escape(bound or '') + r'\s*(?:,|;)', oracle), name

# Validate the supported init subsection's assignment list, including order.
frozen_init = function(dm, 'rtl8723be_dm_init_txpower_tracking')
assignments = re.findall(r'rtlpriv->dm\.([^;\n]+?\s*=\s*[^;\n]+);', frozen_init)
expected_assignments = []
for item in assignments:
    item = item.replace('RF90_PATH_A', '0').replace('rtlpriv->dm.', 'dm->')
    expected_assignments.append(re.sub(r'\s+', '', item))
source = (ROOT / 'src/rtwn8723be_thermal.c').read_text()
init = source[source.index('rtwn8723be_thermal_txpower_init('):
              source.index('rtwn8723be_thermal_meter_parse(')]
actual_assignments = re.findall(r'dm->([^;\n]+?\s*=\s*[^;\n]+);', init)
actual_assignments = [re.sub(r'\s+', '', item.replace('(uint8_t)', ''))
                      for item in actual_assignments
                      if not item.startswith('txpower_state_valid')]
assert actual_assignments == expected_assignments

report = {'state': 'PASSED', 'linux_pin': PIN,
    'source_sha256': {PREFIX + path: hashlib.sha256(content.encode()).hexdigest()
        for path, content in refs.items()},
    'production_tables_sha256': hashlib.sha256(actual_tables.encode()).hexdigest(),
    'production_body_sha256': hashlib.sha256(actual_body.encode()).hexdigest(),
    'oracle_sha256': hashlib.sha256(oracle.encode()).hexdigest(),
    'limitation': 'source validation; full DM/BTC/RF owners remain OPEN'}
if a.report:
    a.report.write_text(json.dumps(report, indent=2) + '\n')
print('THERMAL_FROZEN_SOURCE_VALIDATION_PASS tables=exact body=allowed_transform '
      'oracle_helpers=3 constants=pin state_types=pin init_assignments=pin')
