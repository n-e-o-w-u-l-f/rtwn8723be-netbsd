#!/usr/bin/env python3
"""Source contract and portable oracle for frozen Linux BTC byte bitmask RMW.

This is NOT a NetBSD native build, hardware-I/O test or WLAN acceptance.
Reference: rtlwifi/btcoexist/halbtcoutsrc.c:
halbtc_bitmask_write_1byte() at Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "src/rtwn8723be_btc_provider_native.c").read_text(
    encoding="utf-8"
)
start = source.index("static void btc_mask1(")
end = source.index("static void btc_setbb(", start)
body = source[start:end]

# A missing final '& mask' silently changes bits outside the requested field.
required = "v = (u8)((old & ~mask) | ((v << shift) & mask));"
if body.count(required) != 1:
    raise AssertionError("BTC byte RMW must mask shifted data (Linux parity)")
for fragment in (
    "mask &= 0xffU;",
    "if (mask == 0)",
    "rtwn8723be_btc_native_provider_error(btc_sc(b), EINVAL);",
    "if (mask != 0xffU)",
    "rtwn8723be_read_1(btc_sc(b), r)",
    "rtwn8723be_write_1(btc_sc(b), r, v);",
):
    if fragment not in body:
        raise AssertionError("missing BTC byte provider guard: " + fragment)

def linux_result(original: int, mask: int, value: int) -> int:
    mask &= 0xff
    if not mask:
        raise ValueError("zero mask must fail before hardware write")
    if mask == 0xff:
        return value & 0xff
    shift = (mask & -mask).bit_length() - 1
    return ((original & ~mask) | ((value << shift) & mask)) & 0xff

cases = 0
for original in (0x00, 0x3c, 0xa5, 0xff):
    for mask in range(1, 256):
        for value in (0x00, 0x01, 0x0f, 0x55, 0xff):
            actual = linux_result(original, mask, value)
            if ((actual ^ original) & (~mask & 0xff)) != 0:
                raise AssertionError("unmasked bit modified")
            if mask == 0xff and actual != value:
                raise AssertionError("full-mask byte write changed")
            cases += 1

if linux_result(0xaa, 0x0c, 0xff) != 0xae:
    raise AssertionError("Linux reference counterexample failed")
if ((0xaa & ~0x0c) | (0xff << 2)) & 0xff != 0xfe:
    raise AssertionError("negative-case mutation did not reproduce the bug")
try:
    linux_result(0xff, 0, 0)
except ValueError:
    pass
else:
    raise AssertionError("zero mask accepted")

print(f"BTC_BYTE_MASK_SOURCE_ORACLE_OK: {cases} portable cases; no native/hardware test")
