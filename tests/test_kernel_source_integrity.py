#!/usr/bin/env python3
"""Fail on copied tool transcripts or libc headers in native RTL source closure."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BAD = re.compile(
    r"^(?:\[executed on device:|\[Reading \d+ lines|"
    r"Process started with PID|(?:✅|⏳) Process )",
    re.M,
)
LIBC = re.compile(
    r"^#\s*include\s*<(?:errno|stdbool|stddef|stdint|string)\.h>",
    re.M,
)
INCLUDE = re.compile(r'^#\s*include\s*"([^"]+)"', re.M)
manifest = (ROOT / "config/files.rtwn8723be_native").read_text()
native = set(re.findall(
    r"^file\s+dev/pci/(rtwn8723be\w+\.c)\s+rtwn8723be_native\s*$",
    manifest, re.M,
))
assert len(native) == 28
assert {"rtwn8723be_bb_native.c", "rtwn8723be_txpwr_pg.c",
        "rtwn8723be_rf_channel_state.c"} <= native
all_source = list(SRC.glob("*.c")) + list(SRC.glob("*.h"))
for path in all_source:
    assert not BAD.search(path.read_text()), "tool transcript: " + str(path)
seen, pending = set(), list(native)
while pending:
    name = pending.pop()
    if name in seen:
        continue
    seen.add(name)
    src = SRC / name
    assert src.is_file(), "missing native dependency: " + name
    text = src.read_text()
    if name != "rtwn8723be_os_compat.h":
        assert not LIBC.search(text), "userspace libc include: " + name
    for dep in INCLUDE.findall(text):
        if dep.startswith("rtwn8723be"):
            assert (SRC / dep).is_file(), "unresolved project header: " + dep
            pending.append(dep)
compat = (SRC / "rtwn8723be_os_compat.h").read_text()
for required in ("#ifdef _KERNEL", "#include <sys/types.h>",
                 "#include <sys/stdbool.h>", "#include <sys/stdint.h>",
                 "#include <sys/stddef.h>", "#include <sys/errno.h>",
                 "#include <sys/systm.h>"):
    assert required in compat, "missing NetBSD API: " + required
assert "rtwn8723be_os_compat.h" in seen
assert "#include <net/if_media.h>" in (
    SRC / "rtwn8723be_netbsd.h").read_text()
assert "#define IEEE80211_NO_HT" in (
    SRC / "rtwn8723be_netbsd.h").read_text()
print(f"RTL_KERNEL_SOURCE_INTEGRITY_OK native_units={len(native)} "
      f"reachable_project_files={len(seen)} scanned_files={len(all_source)}")
