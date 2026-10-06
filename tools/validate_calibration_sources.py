#!/usr/bin/env python3
"""Validate checked-in calibration bodies/constants against exact git blobs.

No compilation occurs here. The frozen tree is always read with git show at
PIN; a branch, working tree, missing tree, or cached unchecked oracle is never
substituted. The only production transformations allowed are enumerated below.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess

PIN = 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'
ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'drivers/net/wireless/realtek/rtlwifi/'
parser = argparse.ArgumentParser()
parser.add_argument('--linux-tree', type=Path, default=Path(os.environ.get(
    'RTWN8723BE_LINUX_TREE', '/root/linux-rtl8723be-ref-fresh')))
parser.add_argument('--report', type=Path)
args = parser.parse_args()
paths = ('rtl8723be/phy.c', 'rtl8723com/phy_common.c', 'rtl8723be/reg.h',
         'rtl8723be/phy.h', 'wifi.h')
refs = {path: subprocess.check_output(['git', '-C', str(args.linux_tree),
    'show', PIN + ':' + PREFIX + path]).decode() for path in paths}

def function(source, name):
    pattern = r'(?:static )?(?:u8|void|bool) ' + re.escape(name) + r'\('
    start = re.search(pattern, source)
    if start is None:
        raise AssertionError('missing pinned function: ' + name)
    opening = source.index('{', start.start())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start.start():index + 1]
    raise AssertionError('unterminated pinned function: ' + name)

names = ('_rtl8723be_phy_path_a_iqk', '_rtl8723be_phy_path_a_rx_iqk',
    '_rtl8723be_phy_path_b_iqk', '_rtl8723be_phy_path_b_rx_iqk',
    '_rtl8723be_phy_path_b_fill_iqk_matrix',
    '_rtl8723be_phy_simularity_compare', '_rtl8723be_phy_iq_calibrate')
common_names = ('rtl8723_phy_path_a_fill_iqk_matrix',)
body = '\n\n'.join([function(refs['rtl8723be/phy.c'], n) for n in names] +
    [function(refs['rtl8723com/phy_common.c'], n) for n in common_names])
body = body.replace('struct ieee80211_hw *hw', 'struct calibration_work *hw')
body = re.sub(r'\tstruct rtl_priv \*rtlpriv = rtl_priv\(hw\);\n', '', body)
body = re.sub(r'\tstruct rtl_phy \*rtlphy = &rtlpriv->phy;\n', '', body)
for old, new in (('rtlphy->adda_backup', 'hw->adda_backup'),
                ('rtlphy->iqk_mac_backup', 'hw->mac_backup'),
                ('rtlphy->iqk_bb_backup', 'hw->bb_backup'),
                ('rtlphy->rfpi_enable', 'hw->rfpi_enable')):
    body = body.replace(old, new)
body = re.sub(r'rtl_dbg\([\s\S]*?\);', '((void)0);', body)
body = re.sub(r'mdelay\(([^)]*)\)', r'cal_delay(hw, (\1) * 1000U)', body)
renames = {
    '_rtl8723be_phy_path_a_iqk': 'cal_path_a_tx',
    '_rtl8723be_phy_path_a_rx_iqk': 'cal_path_a_rx',
    '_rtl8723be_phy_path_b_iqk': 'cal_path_b_tx',
    '_rtl8723be_phy_path_b_rx_iqk': 'cal_path_b_rx',
    '_rtl8723be_phy_path_b_fill_iqk_matrix': 'cal_fill_b',
    '_rtl8723be_phy_simularity_compare': 'cal_compare',
    '_rtl8723be_phy_iq_calibrate': 'cal_iqk_trial',
    'rtl8723_phy_path_a_fill_iqk_matrix': 'cal_fill_a',
    'rtl_get_bbreg': 'cal_get_bb', 'rtl_set_bbreg': 'cal_set_bb',
    'rtl_set_rfreg': 'cal_set_rf', 'rtl8723_save_adda_registers': 'cal_save_bb',
    'rtl8723_phy_reload_adda_registers': 'cal_reload_bb',
    'rtl8723_phy_save_mac_registers': 'cal_save_mac',
    'rtl8723_phy_reload_mac_registers': 'cal_reload_mac',
    'rtl8723_phy_path_adda_on': 'cal_adda_on',
    'rtl8723_phy_mac_setting_calibration': 'cal_mac_calibration',
}
for old, new in renames.items():
    body = body.replace(old, new)
for old, new in (('u32', 'uint32_t'), ('u8', 'uint8_t'), ('s32', 'int32_t'),
                 ('long', 'int32_t')):
    body = re.sub(r'\b' + old + r'\b', new, body)
body = body.replace('void cal_fill_a(', 'static void cal_fill_a(')
body = re.sub(r'(static bool cal_compare[^{]*\{)', r'\1\n\t(void)hw;', body)
# Explicit bounded ten-bit signed arithmetic replaces LP64 unsigned masks.
# The emitted register fields are differential-tested against the raw body.
body = body.replace('y = y | 0xFFFFFC00;', 'y -= 0x400;')
body = re.sub(r'tmp([12]) = result\[(c[12])\]\[i\] \| 0xFFFFFC00;',
    r'tmp\1 = result[\2][i] - 0x400;', body)

def macros(source):
    return dict(re.findall(r'^#define\s+([A-Za-z_0-9]+)\s+([^\s/]+)', source, re.M))
reg_macros = macros(refs['rtl8723be/reg.h'])
without_comments = re.sub(r'/\*[\s\S]*?\*/', '', body)
tokens = list(dict.fromkeys(re.findall(
    r'\b(?:R[A-Z][A-Z_0-9]*|MASK[A-Z0-9]+)\b', without_comments)))
tokens.remove('RF90_PATH_A')
tokens.extend(('RF_T_METER', 'MASK12BITS', 'REG_TXPAUSE'))
defs = '\n'.join('#define ' + n + ' ' + reg_macros[n] for n in tokens)
expected = ('/* SPDX-License-Identifier: GPL-2.0 */\n'
    '/* Copyright(c) 2009-2014 Realtek Corporation. */\n'
    '/* Mechanically adapted frozen Linux IQK helpers; see provenance report. */\n\n' +
    defs + '\n#define RF90_PATH_A 0U\n#define IQK_ADDA_REG_NUM 16U\n'
    '#define IQK_MAC_REG_NUM 4U\n#define IQK_BB_REG_NUM 9U\n'
    '#define IQK_DELAY_TIME 10U\n#define MAX_TOLERANCE 5U\n'
    '#define BIT(n) (UINT32_C(1) << (n))\n\n' + body)
actual = (ROOT / 'src/rtwn8723be_calibration_linux.inc').read_text()
assert actual.rstrip('\n') == expected.rstrip('\n'), \
    'production calibration include differs from exact allowed frozen-source transformations'

oracle = (ROOT / 'tests/calibration_linux_oracle.c').read_text()
phy = refs['rtl8723be/phy.c']
begin = phy.index('static u8 _rtl8723be_phy_path_a_iqk(')
end = phy.index('bool rtl8723be_phy_set_io_cmd', begin)
assert phy[begin:end] in oracle, 'embedded Linux IQK/LCK function block differs from pin'
oracle_common = ('rtl8723_phy_path_a_fill_iqk_matrix', 'rtl8723_save_adda_registers',
    'rtl8723_phy_save_mac_registers', 'rtl8723_phy_reload_adda_registers',
    'rtl8723_phy_reload_mac_registers', 'rtl8723_phy_path_adda_on',
    'rtl8723_phy_mac_setting_calibration')
for name in oracle_common:
    assert function(refs['rtl8723com/phy_common.c'], name) in oracle, \
        'embedded Linux common helper differs from pin: ' + name

oracle_defs = macros(oracle)
frozen_defs = {**macros(refs['rtl8723be/phy.h']), **macros(refs['wifi.h'])}
for name in tokens:
    assert oracle_defs[name] == reg_macros[name], 'oracle register constant differs: ' + name
for name in ('IQK_ADDA_REG_NUM', 'IQK_MAC_REG_NUM', 'IQK_BB_REG_NUM',
             'IQK_MATRIX_REG_NUM', 'IQK_DELAY_TIME', 'MAX_TOLERANCE',
             'TARGET_CHNL_NUM_2G_5G'):
    assert int(oracle_defs[name], 0) == int(frozen_defs[name], 0), \
        'oracle algorithm constant differs: ' + name
assert int(oracle_defs['ROFDM0_AGCRSSITABLE'].rstrip('U'), 0) == int(reg_macros['ROFDM0_AGCRSSITABLE'], 0)
assert int(oracle_defs['ROFDM0_RXIQEXTANTA'].rstrip('U'), 0) == int(reg_macros['ROFDM0_RXIQEXTANTA'], 0)
for name in ('RF90_PATH_A', 'RF90_PATH_B'):
    match = re.search(r'\b' + name + r' = (\d+)', refs['wifi.h'])
    assert match and int(oracle_defs[name].rstrip('U'), 0) == int(match[1])
hw_enum = re.search(r'enum hardware_type \{([\s\S]*?)\};', refs['wifi.h'])[1]
hardware_types = re.findall(r'^\s*(HARDWARE_TYPE_\w+)\s*,?', hw_enum, re.M)
for name in ('HARDWARE_TYPE_RTL8723AE', 'HARDWARE_TYPE_RTL8723BE'):
    assert int(oracle_defs[name], 0) == hardware_types.index(name), \
        'oracle hardware identity constant differs: ' + name
assert oracle.count('priv.rtlhal.hw_type = HARDWARE_TYPE_RTL8723BE;') == 2

report = {'state': 'PASSED', 'linux_pin': PIN,
    'source_sha256': {PREFIX + p: hashlib.sha256(s.encode()).hexdigest()
        for p, s in refs.items()},
    'production_include_sha256': hashlib.sha256(actual.encode()).hexdigest(),
    'oracle_sha256': hashlib.sha256(oracle.encode()).hexdigest(),
    'production_functions': list(names + common_names),
    'oracle_common_functions': list(oracle_common),
    'limitation': 'source linkage validation only; hardware and owner integration OPEN'}
if args.report:
    args.report.write_text(json.dumps(report, indent=2) + '\n')
print('CALIBRATION_FROZEN_SOURCE_VALIDATION_PASS production_helpers=8 '
      'oracle_IQK_LCK_block=exact oracle_common=7 constants=pin')
