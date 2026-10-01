#!/usr/bin/env python3
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
H = ROOT / "src" / "rtwn8723be_linux_state.h"
C = ROOT / "src" / "rtwn8723be_netbsd.c"

h = H.read_text()
c = C.read_text()

m = re.search(r"struct rtwn8723be_linux_ops \{(.*?)\n\};", h, re.S)
if not m:
    raise SystemExit("linux ops struct not found")

ops = re.findall(r"\(\*(\w+)\)\s*\(", m.group(1))
init = re.search(
    r"const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops = \{(.*?)\n\};",
    c, re.S,
)
if not init:
    raise SystemExit("NetBSD ops initializer not found")
bound = set(re.findall(r"\.(\w+)\s*=", init.group(1)))
missing = [op for op in ops if op not in bound]
extra = sorted(bound - set(ops))

report = {
    "total_callbacks": len(ops),
    "bound_callbacks": len(ops) - len(missing),
    "missing_callbacks": missing,
    "extra_bindings": extra,
}
print(json.dumps(report, indent=2))
raise SystemExit(1 if missing or extra else 0)
