#!/usr/bin/env python3
"""Mechanically port both frozen RTL8723B BTC algorithms to per-device state.

Only OS includes, diagnostics/delays and mutable storage placement change.
Every source input must match its pinned Git blob before generation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

PIN = 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'
BASE = 'drivers/net/wireless/realtek/rtlwifi/'
INPUTS = {
    'btcoexist/halbtcoutsrc.h': 'd8d88a98980601d4dc10c512761a58d029858444',
    'btcoexist/halbtc8723b1ant.h': 'a4506d838dc74e74986a7c7daa28fc6348f0dd79',
    'btcoexist/halbtc8723b2ant.h': '08aad6ef4046c2f6f9dd45067f1d6507050c555c',
    'btcoexist/halbtc8723b1ant.c': '379193b2442879a0b95d3f62e4d8fad1a2b5c22e',
    'btcoexist/halbtc8723b2ant.c': '7a71f063015ab771f030ecf7354c0e4aa4fcca60',
    'wifi.h': 'f1830ddcdd8c19fb742c1b3409b162e8a2d5d3a8',
}

TOKEN = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\b[A-Za-z_]\w*\b', re.S)

def code_replace(text, replacements):
    return TOKEN.sub(lambda m: replacements.get(m.group(), m.group()), text)

def close_brace(text, opening):
    # Lexical braces, excluding strings/chars/comments.
    tokens = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    level = 0
    for m in tokens.finditer(text, opening):
        if m.group() == '{': level += 1
        elif m.group() == '}':
            level -= 1
            if level == 0: return m.end()
    raise ValueError('unterminated C function')

def per_device(source, antenna):
    for line in (
        f'static struct coex_dm_8723b_{antenna}ant glcoex_dm_8723b_{antenna}ant;\n',
        f'static struct coex_dm_8723b_{antenna}ant *coex_dm = &glcoex_dm_8723b_{antenna}ant;\n',
        f'static struct coex_sta_8723b_{antenna}ant glcoex_sta_8723b_{antenna}ant;\n',
        f'static struct coex_sta_8723b_{antenna}ant *coex_sta = &glcoex_sta_8723b_{antenna}ant;\n',
    ):
        assert source.count(line) == 1
        source = source.replace(line, '')
    assert source.count('#include "halbt_precomp.h"') == 1
    source = source.replace('#include "halbt_precomp.h"', '#include "rtwn8723be_btc_engine.h"')
    # Version constants are never modified. All algorithm mutable storage
    # now belongs to the device, including function-local historical state.
    source = re.sub(r'^static u32 (glcoex_ver\w+) =', r'static const u32 \1 =', source, flags=re.M)
    fields, changes, chunks, cursor = [], [], [], 0
    pattern = re.compile(r'^(?:static\s+)?(?:void|u8|u32|bool)\s+(\w+)\s*\([^;]*?\)\s*\{', re.M)
    for m in pattern.finditer(source):
        if m.start() < cursor: continue
        opening = m.end() - 1
        end = close_brace(source, opening)
        body = source[m.start():end]
        local = {}
        for sm in re.finditer(r'^\tstatic (u8|u16|u32|s32|bool) ([a-z_\w, ]+);', body, re.M):
            for name in sm.group(2).split(','):
                name = name.strip()
                assert re.fullmatch(r'[a-z_]\w*', name)
                field = m.group(1) + '__' + name
                fields.append((sm.group(1), field))
                local[name] = f'r23be_btc_state(btcoexist)->history{antenna}.{field}'
                changes.append({'function': m.group(1), 'local': name, 'field': field, 'type': sm.group(1)})
        body = re.sub(r'^\tstatic (u8|u16|u32|s32|bool) [a-z_\w, ]+;\n', '', body, flags=re.M)
        body = code_replace(body, {'btcoex':'btcoexist'})
        body = code_replace(body, local)
        body = code_replace(body, {
            'coex_dm': f'(&r23be_btc_state(btcoexist)->dm{antenna})',
            'coex_sta': f'(&r23be_btc_state(btcoexist)->sta{antenna})',
        })
        # rtlpriv was used only as the debug context in these exact files.
        body = re.sub(r'^\tstruct rtl_priv \*rtlpriv = btcoexist->adapter;\n', '', body, flags=re.M)
        body = body.replace('rtl_dbg(rtlpriv,', 'rtwn8723be_btc_debug(btcoexist,')
        body = re.sub(r'\bmdelay\((\d+)\)', r'rtwn8723be_btc_delay(btcoexist, \1)', body)
        chunks += [source[cursor:m.start()], body]
        cursor = end
    chunks.append(source[cursor:])
    result = ''.join(chunks)
    assert not re.search(r'^\tstatic (?:u8|u16|u32|s32|bool) [\w, ]+;', result, re.M)
    assert 'rtlpriv' not in result and 'mdelay(' not in result
    assert not re.search(r'\bglcoex_(dm|sta)\b', result)
    return result, fields, changes

def generate(linux_tree):
    raw, source_proof = {}, {}
    for path, expected in INPUTS.items():
        data = (linux_tree / BASE / path).read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        assert blob == expected, (path, blob, expected)
        raw[path] = data.decode('utf-8')
        source_proof[BASE+path] = {'git_blob':blob,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    output = {}
    histories, transforms = {}, {}
    for antenna in (1,2):
        src, fields, changes = per_device(raw[f'btcoexist/halbtc8723b{antenna}ant.c'], antenna)
        output[f'src/rtwn8723be_btc{antenna}_linux.inc'] = src
        header = raw[f'btcoexist/halbtc8723b{antenna}ant.h']
        if antenna == 1:
            header = '#ifndef _R23BE_BTC1_TYPES_H_\n#define _R23BE_BTC1_TYPES_H_\n' + header + '\n#endif\n'
        output[f'src/rtwn8723be_btc{antenna}_types.h'] = header
        histories[antenna] = fields
        transforms[str(antenna)] = changes
    h = raw['btcoexist/halbtcoutsrc.h'].split('bool halbtc_is_wifi_uplink(',1)[0]
    h = h.replace('#include\t"../wifi.h"', '#include "rtwn8723be_btc_os_types.h"')
    assert h.count('\tstruct completion bt_mp_comp;') == 1
    h = h.replace('\tstruct completion bt_mp_comp;',
        '\t/* Native MP completion is owned by sc_btc_mp, not Linux completion. */\n'
        '\tvoid *r23be_state;\n'
        '\tvoid (*r23be_delay_ms)(void *, unsigned int);\n'
        '\tvoid (*r23be_debug)(void *, unsigned long, int, const char *, va_list);')
    output['src/rtwn8723be_btc_linux_types.h'] = h + '\n#endif\n'
    dm = re.search(r'enum dm_info_query \{.*?\n\};', raw['wifi.h'], re.S).group()
    output['src/rtwn8723be_btc_dm_types.h'] = dm + '\n'
    history = ['/* SPDX-License-Identifier: GPL-2.0 */',
               '/* Generated function-local histories: zero initial state, per device. */']
    for antenna in (1,2):
        history.append(f'struct rtwn8723be_btc_history{antenna} {{')
        history.extend(f'    {ty} {name};' for ty,name in histories[antenna])
        history.append('};')
    output['src/rtwn8723be_btc_history.h'] = '\n'.join(history) + '\n'
    proof = {'linux_pin':PIN,'sources':source_proof,'history_transforms':transforms,
             'generated_sha256':{p:hashlib.sha256(s.encode()).hexdigest() for p,s in output.items()},
             'layer':'algorithm/state layer; OS providers and full lifecycle remain required',
             'unchanged':'hardware register/firmware command order, conditions, values and algorithm calculations'}
    output['src/rtwn8723be_btc_source.json'] = json.dumps(proof,indent=2) + '\n'
    return output

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--linux-tree',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--check',action='store_true')
    a = p.parse_args()
    for path,data in generate(a.linux_tree).items():
        dest = a.output / path
        if a.check:
            assert dest.read_bytes() == data.encode(), path
        else:
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(data.encode())
    print('BTC_BOTH_ALGORITHMS_PINNED_PER_DEVICE', 'CHECK' if a.check else 'GENERATED')

if __name__ == '__main__': main()
