#!/usr/bin/env python3
"""Read-only HP RTL50 kernel configuration source contract.

Never execute the build script here: it parses CLI args, stages NetBSD
kernel sources and invokes native build tools. This test only parses AST.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "build_hp_native.py"

EXPECTED = [
    'include "arch/amd64/conf/GENERIC"',
    'ident "HP-RTL-NATIVE-20261005"',
    'no rtwn*',
    'no i915drmkms*',
    'rtwn8723be_native* at pci? dev ? function ?',
]


def extract_config(source):
    tree = ast.parse(source)
    writers = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "write_text"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "config"
    ]
    if len(writers) != 1 or not writers[0].args:
        raise AssertionError("expected one isolated HP kernel config writer")
    arg = writers[0].args[0]
    if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
        raise AssertionError("config contents must be statically inspectable")
    return arg.value


def contract_holds(contents):
    return contents.splitlines() == EXPECTED


original = SOURCE.read_text(encoding="utf-8")
rendered = extract_config(original)
assert contract_holds(rendered), "RTL HP kernel config must exclude i915drmkms"
assert original.count('len(units) != 50') == 1, "50-source closure guard changed"
assert 'platform.system() != "NetBSD"' in original, "HP-only OS guard removed"
assert 'socket.gethostname().startswith("hp-tpnw121")' in original, (
    "HP-only host guard removed"
)

# Negative controls: prove the contract detects the earlier unsafe config,
# and rejects duplicate or reordered kernel driver directives.
unsafe = rendered.replace("no i915drmkms*\n", "", 1)
assert unsafe != rendered and not contract_holds(unsafe)
duplicate = rendered.replace("no i915drmkms*\n", "no i915drmkms*\nno i915drmkms*\n", 1)
assert duplicate != rendered and not contract_holds(duplicate)
print("HP_RTL_KERNEL_CONFIG_I915_GUARD_SOURCE_PASS")
