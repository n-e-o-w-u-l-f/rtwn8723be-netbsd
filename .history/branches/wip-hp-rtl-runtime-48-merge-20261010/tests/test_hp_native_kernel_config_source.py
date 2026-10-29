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
    'rtwn8723be* at pci? dev ? function ?',
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
# NetBSD 11 device_xname includes the device-unit suffix and NUL byte.
# Keep the long C attachment symbol and 50-unit source naming unchanged.
manifest = (ROOT / "config/files.rtwn8723be_native").read_text(encoding="utf-8")
attach_source = (ROOT / "src/rtwn8723be_native.c").read_text(encoding="utf-8")
live_generator = (ROOT / "tools/configure_hp_live_native_50.py").read_text(encoding="utf-8")
driver_name, cfattach_name = "rtwn8723be", "rtwn8723be_native"
assert len(driver_name + "0") + 1 <= 16, "NetBSD DEVICE_XNAME_SIZE exceeded"
assert len(cfattach_name + "0") + 1 > 16, "bad previous name not captured"
assert manifest.count("device  rtwn8723be: ifnet, arp, wlan, firmload") == 1
assert manifest.count("attach  rtwn8723be at pci with rtwn8723be_native") == 1
assert "device  rtwn8723be_native:" not in manifest
assert "CFATTACH_DECL_NEW(rtwn8723be_native," in attach_source
assert live_generator.count("'rtwn8723be* at pci? dev ? function ?\\n'") == 1
assert "'rtwn8723be_native* at pci? dev ? function ?\\n'" not in live_generator
assert "rtwn8723be_native* at pci" not in original
print("HP_RTL_KERNEL_CONFIG_I915_GUARD_SOURCE_PASS")
