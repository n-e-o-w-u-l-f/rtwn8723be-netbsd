#!/usr/bin/env python3
"""Synthetic source-only tests for a two-driver NetBSD kernel Kconfig builder.

Positive fixtures are NOT i915 approval, a native compile or an actual
Linux-323 semantic proof. Hardware and KMS evidence remain owner-gated.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from configure_hp_combined_i915_rtl import (
    FLAGS, I915_CLOSURE, I915_FILES, canonical_relative, effective_config,
    i915_closure, mirror, render_config, rtl_inventory, validate_i915_filelist,
    verify_make_objects,
)


def refused(fn, label):
    try:
        fn()
    except (ValueError, OSError):
        return
    raise AssertionError("expected denial of " + label)


rtl_units = rtl_inventory(ROOT)
assert len(rtl_units) == 50 and len(set(rtl_units)) == 50
fake_rtl_sha = "a" * 40
fake_gpu_sha = "b" * 40

generic = ('i915drmkms* at pci? dev ? function ?\n'
           'intelfb* at intelfbbus?\n'
           'genfb* at pci? dev ? function ?\n')
identity, config = render_config(generic, fake_rtl_sha[:12], fake_gpu_sha[:12])
assert identity == "HP-COMBINED-I915-" + "b" * 12 + "-RTL-" + "a" * 12
assert 'include "arch/amd64/conf/GENERIC"' in config
assert "rtwn8723be* at pci? dev ? function ?" in config
assert "no i915drmkms" not in config
effective_config(generic, config)
refused(lambda: effective_config("", config), "inherited i915drmkms")
refused(lambda: effective_config(generic, config + "no i915drmkms*\n"),
        "deliberate no i915drmkms")
refused(lambda: render_config("no i915drmkms*\n", "a"*12, "b"*12),
        "disabled i915 in GENERIC")
refused(lambda: render_config(generic, "bad", "b"*12),
        "invalid dual source identity")
for value in ("../x", "/absolute", "sys/../x", "x//y", "sys\\device"):
    refused(lambda p=value: canonical_relative(p), "unsafe path " + value)

gpu = [
    "sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c",
    "sys/external/bsd/drm2/dist/drm/i915/display/intel_display.c",
    "sys/external/bsd/drm2/dist/drm/drm_drv.c",
]
objects = " ".join([x[:-2]+".o" for x in rtl_units] +
                   [Path(x).stem + ".o" for x in gpu])
result = verify_make_objects(objects, rtl_units, gpu)
assert result["rtl_objects"] == 50
assert result["gpu_and_drm_objects"] == 3
refused(lambda: verify_make_objects(" ".join(x for x in objects.split()
                                       if x != "i915_pci_autoconf.o"),
                                    rtl_units, gpu), "missing i915 owner")
refused(lambda: verify_make_objects(objects + " i915_pci_autoconf.o",
                                    rtl_units, gpu), "duplicate symbol owner")
refused(lambda: verify_make_objects(" ".join(x for x in objects.split()
                                  if not x.startswith("rtwn8723be")),
                                  rtl_units, gpu), "RTL-only Kconfig")

native_lines = (
    "device i915drmkms: drmkms, drmkms_pci\n"
    "attach i915drmkms at pci\n"
    + "".join("file " + p[4:] + " i915drmkms\n" for p in gpu)
)
validate_i915_filelist(native_lines, gpu)
refused(lambda: validate_i915_filelist(native_lines.replace(
    "attach i915drmkms at pci", "attach i915drmkms at mainbus"), gpu),
    "wrong i915 PCI attachment")
refused(lambda: validate_i915_filelist(native_lines.replace(
    " i915drmkms\n", " drmkms\n", 1), gpu),
    "i915 missing selected native file")

with tempfile.TemporaryDirectory(prefix="rtl-combined-source-contract-") as tmp:
    root = Path(tmp)
    i915 = root / "i915"
    i915.mkdir()
    assert subprocess.run(["git", "init", "-q", str(i915)],
                          capture_output=True).returncode == 0
    (i915 / "README").write_text("synthetic closure test\n")
    subprocess.run(["git", "-C", str(i915), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(i915), "-c", "user.name=Test",
         "-c", "user.email=unit-test@example.invalid",
         "commit", "-qm", "baseline"], check=True)
    ancestor = subprocess.check_output(
        ["git", "-C", str(i915), "rev-parse", "HEAD"], text=True).strip()
    names = gpu
    rows = [{
        "linux_source":f"drivers/gpu/drm/i915/gt/synthetic{i:03d}.c",
        "native_sources":[names[i % len(names)]],
        "evidence":"Synthetic behavioral mapping only for policy testing.",
    } for i in range(323)]
    matrix = i915 / "docs/I915-STRUCTURAL-COVERAGE.tsv"
    matrix.parent.mkdir(parents=True, exist_ok=True)
    matrix.write_text("linux_source\tstructural_class\tnetbsd_evidence\tsemantic_state\n" +
                      "".join(row["linux_source"] +
                              "\tUNRESOLVED_NO_BASENAME\t\tUNREVIEWED\n"
                              for row in rows))
    overlay = []
    for name in names + [I915_FILES]:
        file = i915 / "native_overlay" / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(native_lines if name == I915_FILES
                        else "/* synthetic i915 source */\nint synthetic() {return 1;}\n")
        overlay.append({
            "source":"native_overlay/" + name,
            "destination":name,
            "sha256":hashlib.sha256(file.read_bytes()).hexdigest(),
        })
    contract = {
        "schema":1, "validated_i915_source_sha":ancestor,
        "verified_subsystems":{k:"PASS" for k in FLAGS},
        "linux_323_units":rows, "selected_i915_sources":names,
        "source_overlays":overlay,
    }
    cp = i915 / I915_CLOSURE
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(contract))
    validated = i915_closure(i915, ancestor)
    assert validated["linux_323_mapped"] == 323
    assert validated["source_owner_count"] == 3
    assert I915_FILES in validated["files"]
    contract["linux_323_units"] = rows[:-1]
    cp.write_text(json.dumps(contract))
    refused(lambda: i915_closure(i915, ancestor), "322-of-323 mapping")
    contract["linux_323_units"] = [dict(row) for row in rows]
    contract["linux_323_units"][0]["linux_source"] = "drivers/gpu/drm/i915/fake.c"
    cp.write_text(json.dumps(contract))
    refused(lambda: i915_closure(i915, ancestor),
            "323 counts correct but wrong frozen source identity")
    contract["linux_323_units"] = rows
    contract["verified_subsystems"]["symbol_provider_closure"] = "OPEN"
    cp.write_text(json.dumps(contract))
    refused(lambda: i915_closure(i915, ancestor), "GPU DRM symbol closure not PASS")
    contract["verified_subsystems"]["symbol_provider_closure"] = "PASS"
    contract["selected_i915_sources"] = names[:-1]
    cp.write_text(json.dumps(contract))
    refused(lambda: i915_closure(i915, ancestor), "unselected GPU DRM source")
    contract["selected_i915_sources"] = names
    cp.write_text(json.dumps(contract))

    # A source tree may contain older NetBSD dirs but not newer i915 modern
    # nested directories. The private mirror must create those dirs safely.
    base = root / "base-sys"
    (base / "dev/pci").mkdir(parents=True)
    (base / "dev/pci/files.pci").write_text("original pinned PCI config\n")
    (base / "unchanged").write_text("frozen NetBSD\n")
    dest = root / "shadow"
    mirror(base, dest, {
        "dev/pci/files.pci":b"combined PCI driver config\n",
        "external/bsd/drm2/dist/drm/i915/new/modern.c":b"/* modern */\n",
    })
    assert (dest / "dev/pci/files.pci").read_text() == "combined PCI driver config\n"
    assert (base / "dev/pci/files.pci").read_text() == "original pinned PCI config\n"
    assert (dest / "external/bsd/drm2/dist/drm/i915/new/modern.c").is_file()
    assert (dest / "unchanged").is_symlink()
    assert (dest / "unchanged").read_text() == "frozen NetBSD\n"

builder = (ROOT / "tools/build_hp_combined_i915_rtl_candidate.sh").read_text()
configurator = (ROOT / "tools/configure_hp_combined_i915_rtl.py").read_text()
verifier = (ROOT / "tools/verify_hp_combined_kernel.py").read_text()
assert 'no i915drmkms*' not in builder
assert "check_i915_kernel_release.py" in builder
assert builder.index("check_i915_kernel_release.py") < builder.index("configure_hp_combined_i915_rtl.py")
assert builder.index("verify_hp_combined_kernel.py") < builder.index("dependall")
assert "COMBINED_KERNEL_LINKED_NO_INSTALL" in verifier
assert "HP-RTL50-" in configurator  # guarded refusal of legacy identity
assert "WAIT_FOR_I915_RELEASE" in configurator

print("HP_COMBINED_SOURCE_CONTRACT_PASS: RTL50, GPU/DRM3 synthetic units, "
      "Linux323 mapping/negative gates, i915-on Kconfig, clean private "
      "symlink overlay, full-link only; NOT native-built")
