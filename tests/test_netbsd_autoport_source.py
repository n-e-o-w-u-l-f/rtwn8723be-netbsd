#!/usr/bin/env python3
"""Safe RTL Linux-to-NetBSD autoport source test; no kernel/HP effects."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from rtl_netbsd_autoport import (  # noqa: E402
    HEADER_MAP, audit, classify_diagnostics, translate_includes,
)

source = ("#include <errno.h>\n#include <stdint.h>\n"
          "#if defined(USERSPACE)\n#include <string.h>\n#endif\n"
          "#include <linux/pci.h>\n")
updated, fixes, hazards = translate_includes(source)
assert updated.startswith("#include <sys/errno.h>\n#include <sys/stdint.h>\n")
assert len(fixes) == 2 and len(hazards) == 2
assert {x["type"] for x in hazards} == {
    "CONDITIONAL_INCLUDE", "LINUX_KERNEL_ABI"}
assert not translate_includes(updated)[1], "must be idempotent"
assert set(HEADER_MAP) == {
    "errno.h", "stdbool.h", "stddef.h", "stdint.h", "string.h"}

diagnostics = "\n".join([
    "foo.c:3: fatal error: errno.h: No such file",
    "foo.c:5: fatal error: linux/pci.h: No such file",
    "ld: undefined reference to rtl_firmware_init",
    "error: implicit declaration of function pci_set_master",
    "DMA IRQ panic: timeout",
    "i915 display black-screen after KMS",
])
issues = classify_diagnostics(diagnostics)
assert len(issues) == 6, issues
assert issues[0]["strategy"] == "APPLY_IF_UNCONDITIONAL"
assert all(x["strategy"] == "MANUAL" for x in issues[1:])
assert not classify_diagnostics("everything compiled normally")

def run(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True,
                          text=True, timeout=20)

with tempfile.TemporaryDirectory(prefix="rtl-autoport-policy-") as temp:
    root = Path(temp) / "git-wip"
    (root / "src").mkdir(parents=True)
    (root / "config").mkdir(parents=True)
    manifest = []
    for i in range(50):
        name = f"rtwn8723be_mock{i:02d}.c"
        manifest.append(f"file dev/pci/{name} rtwn8723be_native\n")
        (root / "src" / name).write_text(
            "#include <errno.h>\nint a = 1;\n" if i == 0
            else "#include <sys/systm.h>\nint a = 1;\n")
    (root / "config/files.rtwn8723be_native").write_text("".join(manifest))
    assert run(["git", "init", "--quiet", str(root)]).returncode == 0
    assert run(["git", "add", "-A"], cwd=root).returncode == 0
    c = run(["git", "-c", "user.name=Test", "-c",
             "user.email=test@example.invalid", "commit", "-qm",
             "test initial"], cwd=root)
    assert c.returncode == 0, c.stderr
    head = run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    assert len(head) == 40
    report, edits = audit(root)
    assert report["native_c_units"] == 50
    assert report["auto_fixable_files"] == 1 and len(edits) == 1
    assert not report["manual_review"]
    tool = ROOT / "tools/rtl_netbsd_autoport.py"
    cmd = [sys.executable, "-B", str(tool), "--root", str(root)]
    before = run(cmd)
    assert before.returncode == 0, before.stderr
    assert json.loads(before.stdout)["auto_fixable_files"] == 1
    wrong = run(cmd + ["--apply", "--expected-sha", "0" * 40])
    assert wrong.returncode == 2
    assert (root / "src/rtwn8723be_mock00.c").read_text().startswith(
        "#include <errno.h>"), "denied run must not write"
    approved = run(cmd + ["--apply", "--expected-sha", head])
    assert approved.returncode == 0, approved.stderr
    assert json.loads(approved.stdout)["applied_files"] == 1
    assert (root / "src/rtwn8723be_mock00.c").read_text().startswith(
        "#include <sys/errno.h>")
    again = run(cmd)
    assert again.returncode == 0
    assert json.loads(again.stdout)["auto_fixable_files"] == 0
    assert run(cmd + ["--apply", "--expected-sha", head]).returncode == 2
    (root / "src/rtwn8723be_mock01.c").write_text(
        "#include <linux/pci.h>\nint b = 2;\n")
    final, _ = audit(root)
    assert any(x["type"] == "LINUX_KERNEL_ABI"
               for x in final["manual_review"])

print("RTL_NETBSD_AUTOPORT_SOURCE_PASS: 50-source synthetic manifest; "
      "6 diagnostic classes; safe header translation; SHA/dirty refusal; "
      "unsafe PCI/DMA/IRQ/firmware remains manual")
