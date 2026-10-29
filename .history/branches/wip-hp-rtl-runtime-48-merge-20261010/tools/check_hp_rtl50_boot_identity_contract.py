#!/usr/bin/env python3
"""Pure-Python, host-independent bootfile inventory regression; no kernel build.

Does not call inspector.main(), subprocess, PCI/MMIO, sysctl or any network.
For NetBSD hardware identity acceptance the collector must still run on HP.
"""
import ast
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).with_name("inspect_hp_rtl50_panic.py")
code = SCRIPT.read_text(encoding="utf-8")
ast.parse(code, filename=str(SCRIPT))

spec = importlib.util.spec_from_file_location("rtl50_panic_inventory", SCRIPT)
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)

def selection(bootfile):
    return inspector.selected_kernel_artifacts(bootfile)

empty = selection({"exit": 1, "stdout": "/netbsd.GENERIC"})
assert Path("/netbsd") in empty, "current /netbsd must always be checked"
assert Path("/netbsd.GENERIC") not in empty, "failed sysctl is untrusted"
assert inspector.ARTIFACTS[0] in empty, "retain original failed RTL50 artifact"
assert selection({"exit": 0, "stdout": "/netbsd"}).count(Path("/netbsd")) == 1
assert Path("/netbsd.GENERIC") in selection(
    {"exit": 0, "stdout": "/netbsd.GENERIC"})
assert Path("/netbsd.rtl50") in selection(
    {"exit": 0, "stdout": "/netbsd.rtl50"})

for unsafe in (
    "/etc/passwd", "../../netbsd.GENERIC", "/root/netbsd",
    "/netbsd.GENERIC/subdir", "/netbsd.GENERIC\n/etc/passwd",
    "/netbsd.GENERIC\r",
):
    assert Path(unsafe) not in selection({"exit": 0, "stdout": unsafe}), (
        "untrusted bootfile path selected", unsafe
    )
assert selection({"exit": 0, "stdout": "/etc/passwd"}) == empty
assert selection({"exit": 0, "stdout": "/netbsd.GENERIC/subdir"}) == empty
assert "SYMLINK_REFUSED" in code and "path.is_symlink()" in code
assert "for f in selected_kernel_artifacts(report[\"bootfile\"])" in code

for node in ast.walk(ast.parse(code)):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        assert node.func.attr not in (
            "write_text", "write_bytes", "unlink", "mkdir", "rmdir",
            "rename", "replace", "chmod", "chown", "Popen",
        ), "collector must stay read-only"

print("HP_RTL50_BOOT_KERNEL_IDENTITY_SOURCE_OK")
