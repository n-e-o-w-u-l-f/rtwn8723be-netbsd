#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Reproduce all pinned RTL8723BE BB/AGC/PHY-PG/Radio-A tables exactly.

The RF condition words are intentionally retained as data; the NetBSD RF
callback MUST NOT run until Linux's positive/negative-condition logic and
RF serial access are ported and independently tested.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess

PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
SOURCE = "drivers/net/wireless/realtek/rtlwifi/rtl8723be/table.c"
TABLES = (
    ("RTL8723BEPHY_REG_1TARRAY", "rtwn8723be_phy_table", 2, 193),
    ("RTL8723BEAGCTAB_1TARRAY", "rtwn8723be_agc_table", 2, 131),
    ("RTL8723BEPHY_REG_ARRAY_PG", "rtwn8723be_pg_table", 6, 6),
    ("RTL8723BE_RADIOA_1TARRAY", "rtwn8723be_radio_a_table", 2, 136),
)


def extract(source: str, name: str, stride: int, count: int):
    found = re.search(
        r"\bu32\s+" + re.escape(name) + r"\[\]\s*=\s*\{(.*?)\};",
        source, flags=re.S,
    )
    if found is None:
        raise ValueError(f"missing table: {name}")
    raw = re.sub(r"/\*.*?\*/|//[^\n]*", "", found.group(1), flags=re.S)
    tokens = [part.strip() for part in raw.split(",") if part.strip()]
    if any(re.fullmatch(r"0[xX][0-9a-fA-F]+|[0-9]+", t) is None
           for t in tokens):
        raise ValueError(f"unsupported token in {name}")
    words = [int(token, 0) for token in tokens]
    if len(words) != stride * count or any(w < 0 or w > 0xffffffff
                                            for w in words):
        raise ValueError(f"unexpected frozen-table dimensions: {name}")
    entries = [words[i:i + stride] for i in range(0, len(words), stride)]
    if name in ("RTL8723BEPHY_REG_1TARRAY",
                "RTL8723BEAGCTAB_1TARRAY"):
        if any(reg >= 0x2000 or reg & 0xc0000000 for reg, _ in entries):
            raise ValueError(f"conditional/out-of-range BB/AGC table: {name}")
    return entries, hashlib.sha256(found.group(1).encode()).hexdigest()


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
    out = [
        "/* SPDX-License-Identifier: GPL-2.0",
        " * Copyright(c) 2009-2014 Realtek Corporation.",
        " * Generated from frozen Linux " + PIN + "; do not hand-edit.",
        " * Source: " + SOURCE,
        " * Radio-A conditional words are NOT executable register addresses.",
        " */",
        "#ifndef _RTWN8723BE_PHY_TABLES_H_",
        "#define _RTWN8723BE_PHY_TABLES_H_",
        "#include <sys/types.h>",
        "struct rtwn8723be_init_pair { uint32_t reg; uint32_t value; };",
        "struct rtwn8723be_pg_entry {",
        "    uint32_t band, path, txnum, reg, mask, value;",
        "};",
    ]
    for name, dest, stride, count in TABLES:
        entries, digest = extract(source, name, stride, count)
        out.extend([
            "/* Linux " + name + " SHA256: " + digest + " */",
            "static const struct " +
            ("rtwn8723be_pg_entry" if stride == 6 else "rtwn8723be_init_pair") +
            " " + dest + "[] = {",
        ])
        out.extend("    { " + ", ".join(f"0x{x:08x}U" for x in entry) + " },"
                   for entry in entries)
        out.extend([
            "};",
            "#define " + dest.upper() + "_COUNT \\",
            "    (sizeof(" + dest + ") / sizeof(" + dest + "[0]))",
        ])
    out.extend(["#endif /* _RTWN8723BE_PHY_TABLES_H_ */", ""])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(out))
    print("PHY_TABLES_OK " + " ".join(
        f"{name}={count}" for name, _, _, count in TABLES) + " HEAD=" + head)


if __name__ == "__main__":
    main()
