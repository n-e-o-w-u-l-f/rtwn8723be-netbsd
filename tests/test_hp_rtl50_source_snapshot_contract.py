#!/usr/bin/env python3
"""Source guard: HP RTL50 kernel consumes immutable copy-and-hash inputs.

This test does not prove a native HP build or a physical WLAN/RF result.
Actual byte digest validation occurs on HP before and after the kernel build.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
generator = (root / "tools/configure_hp_live_native_50.py").read_text()
verifier = (root / "tools/verify_hp_rtl50_source_snapshot.py").read_text()
builder = (root / "tools/build_hp_rtl50_next_candidate.sh").read_text()

start = generator.split("owned={p.name:p", 1)[1]
end = start.split('(out/"sys/dev/pci/files.pci").write_text(', 1)[0]

for token in (
    "owned_hashes={name:sha(path)",
    'shutil.copyfile(path,dst)',
    'not dst.is_file() or dst.is_symlink() or sha(dst)!=owned_hashes[name]',
    'state["source_snapshot_sha256"]=owned_hashes',
    'state["source_snapshot_files"]=len(owned_hashes)',
    'state["source_snapshot_private_copies_pass"]=True',
):
    assert token in start, token
assert ".symlink_to(path)" not in end
assert 'p.suffix in (".c",".h",".inc")' in start
assert "private RTL source snapshot changed during config" in generator
assert "Git source changed while taking RTL snapshot" in generator
assert "Git source HEAD changed during config" in generator
for token in (
    'status.get("source_commit") != args.source_commit',
    'status.get("kernel_ident") != expected_ident',
    'status.get("source_snapshot_private_copies_pass") is not True',
    'or len(sources) != 50',
    'or len(hashes) != status.get("source_snapshot_files")',
    'file.is_symlink() or digest(file) != expected_sha',
):
    assert token in verifier, token
assert builder.count("verify_hp_rtl50_source_snapshot.py") == 2, (
    "snapshot must be checked before and after HP kernel link")
assert builder.count("--source-commit") == 2
assert "git -C" not in verifier, "verifier must inspect frozen copy, not mutable Git worktree"
print("RTL50_PRIVATE_SOURCE_SNAPSHOT_CONTRACT_PASS")
