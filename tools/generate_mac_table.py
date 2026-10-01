#!/usr/bin/env python3
"""Extract the exact unconditional RTL8723BE MAC table from frozen Linux."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess

PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
SOURCE = "drivers/net/wireless/realtek/rtlwifi/rtl8723be/table.c"

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--linux-tree", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    head = subprocess.check_output(
        ["git", "-C", str(args.linux_tree), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if head != PIN:
        raise ValueError(f"wrong Linux source HEAD: {head} != {PIN}")
    source = (args.linux_tree / SOURCE).read_text()
    match = re.search(
        r"\bu32\s+RTL8723BEMAC_1T_ARRAY\[\]\s*=\s*\{(.*?)\};",
        source, flags=re.S,
    )
    if not match:
        raise ValueError("pinned RTL8723BEMAC_1T_ARRAY not found")
    raw = re.sub(r"/\*.*?\*/|//[^\n]*", "", match.group(1), flags=re.S)
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    if any(re.fullmatch(r"0[xX][0-9a-fA-F]+", t) is None for t in tokens):
        raise ValueError("conditional/unsupported MAC table token")
    values = [int(t, 16) for t in tokens]
    if len(values) % 2 or not values:
        raise ValueError("MAC table must contain complete register/value pairs")
    pairs = list(zip(values[::2], values[1::2]))
    for reg, value in pairs:
        if reg >= 0x800 or value > 0xff:
            raise ValueError(f"unsupported MAC entry {reg:#x}, {value:#x}")
        if reg & ((1 << 30) | (1 << 31)):
            raise ValueError("conditional table entry requires interpreter")
    output = [
        "/* Generated from frozen Linux " + PIN + ". Do not hand-edit.",
        " * Source: " + SOURCE,
        " * Table SHA256: " + hashlib.sha256(match.group(1).encode()).hexdigest(),
        " */",
        "#ifndef _RTWN8723BE_MAC_TABLE_H_",
        "#define _RTWN8723BE_MAC_TABLE_H_",
        "#include <sys/types.h>",
        "struct rtwn8723be_reg8_init { uint16_t reg; uint8_t value; };",
        "static const struct rtwn8723be_reg8_init rtwn8723be_mac_table[] = {",
    ]
    output += [f"    {{ 0x{reg:03x}, 0x{value:02x} }}," for reg, value in pairs]
    output += [
        "};",
        "#define RTWN8723BE_MAC_TABLE_COUNT \\",
        "    (sizeof(rtwn8723be_mac_table) / sizeof(rtwn8723be_mac_table[0]))",
        "#endif",
        "",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(output))
    print(f"MAC_TABLE_OK entries={len(pairs)} HEAD={head}")

if __name__ == "__main__":
    main()
