#!/usr/bin/env python3
"""Host-independent regression for the read-only NetBSD RTL50 panic inventory.

This checks the collector's Python syntax and security/filename contracts,
not a NetBSD execution, panic cause, or compiled kernel.
"""
import ast
import hashlib
import importlib.util
from pathlib import Path
import re
import tempfile

SCRIPT = Path(__file__).resolve().parents[1] / "tools/inspect_hp_rtl50_panic.py"
source = SCRIPT.read_text(encoding="utf-8")
tree = ast.parse(source, filename=str(SCRIPT))
assert "2e5a2cc97b9bbae3e55aa984e1477e7c29858bce" in source
assert "2eecc4e188c247514d5bc5b639c2773f3d8a823e4f84cc3a65e7e4960471a423" in source
assert "CRASH = Path(\"/var/crash\")" in source
assert "BOOTCFG = Path(\"/boot.cfg\")" in source
assert "if platform.system() != \"NetBSD\"" in source
# Inspect exact committed Python regex constants to guard against erroneous
# double-escaped patterns introduced by serialized remote file writes.
matches = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and (
            isinstance(node.func.value, ast.Name) and
            node.func.value.id == "re" and node.func.attr == "match" and
            node.args and isinstance(node.args[0], ast.Constant)):
        matches.append(node.args[0].value)
assert r"^\s*(savecore|savecore_flags|savecore_dir)=" in matches
assert r"^(netbsd\.|bounds$|minfree$|info\.)" in matches
assert re.match(r"^(netbsd\.|bounds$|minfree$|info\.)", "netbsd.0.core.gz")
assert re.match(r"^\s*(savecore|savecore_flags|savecore_dir)=",
                " savecore=yes")
assert not re.match(r"^(netbsd\.|bounds$|minfree$|info\.)", "private_key")
# Bounded read-only inventory: no writing a file, automatic uploader,
# kernel boot, or privilege escalation is reachable in the collector AST.
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        assert node.func.attr not in (
            "write_text", "write_bytes", "unlink", "mkdir", "rmdir",
            "rename", "replace", "chmod", "chown", "system", "Popen",
        ), node.func.attr
assert "shutdown" not in source
assert "reboot" not in source
assert "savecore -c" not in source
spec = importlib.util.spec_from_file_location("panic_inspector", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as directory:
    f = Path(directory) / "sample"
    f.write_bytes(b"kernel")
    assert module.stat_only(f)["status"] == "REGULAR"
    assert module.sha256(f) == hashlib.sha256(b"kernel").hexdigest()
    symbolic = Path(directory) / "symlink"
    symbolic.symlink_to(f)
    assert module.stat_only(symbolic)["status"] == "SYMLINK_REFUSED"
    assert module.stat_only(Path(directory) / "missing")["status"] == (
        "NOT_REGULAR_OR_MISSING")
print("HP_RTL50_PANIC_INVENTORY_READ_ONLY_SOURCE_CONTRACT_OK")
