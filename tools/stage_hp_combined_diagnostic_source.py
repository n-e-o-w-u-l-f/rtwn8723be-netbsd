#!/usr/bin/env python3
"""Stage pinned NetBSD GENERIC i915 + RTL50 + G01-G09/G08 for COMPILE-ONLY.

This is deliberately NOT the production 323-Linux-unit/full-release builder.
No kernel is installed or booted; success never grants KMS/RTL release.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from configure_hp_combined_i915_rtl import (
    clean_git_head, effective_config, mirror, render_config, rtl_inventory,
)
from hp_i915_boot_trace_overlay import (
    I915_DRV_PATH, I915_DP_PATH, CHV_POWER_PATH,
    build_private_overlay, build_g08_private_overlay, build_chv_hardware_fixes,
    build_aux_irq_private_overlay,
)

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
SOURCE_SHA = "88c9e4c4ffb0669fdec14fd6a3589ab4aae43b2ef32ad5f6deb78b86ffd1d8e8"
I915_FILES = "sys/external/bsd/drm2/i915drm/files.i915drmkms"
REQUIRED_BUILTIN = (
    I915_DRV_PATH,
    "sys/external/bsd/drm2/i915drm/i915_module.c",
    "sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c",
)
MAGIC = "HP-DIAGNOSTIC-COMPILE-ONLY"
STATUS = "STAGED_DIAGNOSTIC_NONRELEASE_NO_KERNEL_BUILD"


def refuse(msg: str):
    raise ValueError("HP_DIAG_COMPILE_REFUSED: " + msg)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_file(src: Path, path: str) -> bytes:
    p = src / path
    if not p.is_file() or p.is_symlink():
        refuse("missing/linked NetBSD source: " + path)
    return p.read_bytes()


def checked_output(out: Path, src: Path, rtl: Path, i915: Path) -> Path:
    if not out.is_absolute() or out == Path("/") or out.exists() or out.is_symlink():
        refuse("new absolute output directory required")
    parent = out.parent.resolve(strict=True)
    if not parent.is_dir() or parent.is_symlink():
        refuse("untrusted output parent")
    for root in (src, rtl, i915):
        if out == root or root in out.parents or out in root.parents:
            refuse("output overlaps pinned source or driver checkout")
    return out


def prepare(src: Path, rtl: Path, i915: Path, out: Path,
            rtl_sha: str, gpu_sha: str) -> dict:
    """Purely source-only, writes a NEW private output folder; caller pins Git.

    No option in this function weakens the production i915 release gate.
    """
    src = src.resolve(strict=True)
    rtl = rtl.resolve(strict=True)
    i915 = i915.resolve(strict=True)
    out = checked_output(out, src, rtl, i915)
    if not re.fullmatch(r"[0-9a-f]{40}", rtl_sha) or not re.fullmatch(r"[0-9a-f]{40}", gpu_sha):
        refuse("invalid dual Git commit ID")
    generic = require_file(src, "sys/arch/amd64/conf/GENERIC").decode("utf-8")
    pci_file = require_file(src, "sys/dev/pci/files.pci").decode("utf-8")
    filelist = require_file(src, I915_FILES).decode("utf-8")
    require_file(src, "common/include/prop/proplib.h")
    native_drv = require_file(src, I915_DRV_PATH)
    if digest(native_drv) != SOURCE_SHA:
        refuse("not exact frozen NetBSD i915 driver source")
    if ("device\ti915drmkms:" not in filelist or
            not re.search(r"^\s*attach\s+i915drmkms\s+at\s+pci$", filelist, re.M)):
        refuse("missing native i915 PCI device owner")
    for unit in REQUIRED_BUILTIN:
        if unit[4:] not in filelist or not require_file(src, unit):
            refuse("missing native GENERIC i915 source owner " + unit)
    if (not re.search(r"^i915drmkms\*\s+at\s+pci\?", generic, re.M) or
            not re.search(r"^intelfb\*\s+at\s+intelfbbus\?", generic, re.M)):
        refuse("GENERIC does not select both built-in i915 and intelfb")
    if re.search(r"^\s*(?:device\s+rtwn8723be\s*:|attach\s+rtwn8723be\b)",
                 pci_file, re.M):
        refuse("preexisting RTL PCI symbol owner conflicts")
    rtl_units = rtl_inventory(rtl)
    identity, config = render_config(generic, rtl_sha[:12], gpu_sha[:12])
    effective_config(generic, config)
    expected = 'ident "' + identity + '"'
    if config.count(expected) != 1:
        refuse("generated combined Kconfig identity corrupted")
    diag_ident = f"{MAGIC}-I915-{gpu_sha[:12]}-RTL-{rtl_sha[:12]}"
    config = config.replace(expected, 'ident "' + diag_ident + '"') + (
        "# UNRELEASED SOURCE DIAGNOSTIC: pinned NetBSD native i915, NOT Linux323 parity\n"
    )
    replacements = {
        "sys/dev/pci/files.pci":
            (pci_file.rstrip("\n") + "\n# HP RTL50 diagnostics only\n" +
             (rtl / "config/files.rtwn8723be_native").read_text()).encode()
    }
    for unit in rtl_units:
        replacements["sys/dev/pci/" + unit] = (rtl / "src" / unit).read_bytes()
    for ext in ("*.h", "*.inc"):
        for file in (rtl / "src").glob("rtwn8723be" + ext):
            if file.is_symlink() or not file.is_file():
                refuse("linked RTL native include " + file.name)
            replacements["sys/dev/pci/" + file.name] = file.read_bytes()
    traced, trace_meta = build_private_overlay(i915, native_drv)
    native_dp = require_file(src, I915_DP_PATH)
    if I915_DP_PATH[4:] not in filelist:
        refuse("missing GENERIC-selected intel_dp.c display owner")
    traced_dp, dp_meta = build_g08_private_overlay(i915, native_dp)
    native_power = require_file(src, CHV_POWER_PATH)
    if CHV_POWER_PATH[4:] not in filelist:
        refuse("missing GENERIC-selected intel_display_power.c CHV owner")
    final_dp, final_power, chv_meta = build_chv_hardware_fixes(
        i915, native_dp, traced_dp, native_power)
    chv_meta["i915_chv_dp_preaux_sha256"] = chv_meta["i915_chv_dp_output_sha256"]
    final_dp, aux_meta = build_aux_irq_private_overlay(i915, final_dp)
    chv_meta["i915_chv_dp_output_sha256"] = digest(final_dp)
    dp_meta["i915_g08_trace_prechv_sha256"] = dp_meta["i915_g08_trace_output_sha256"]
    dp_meta["i915_g08_trace_output_sha256"] = digest(final_dp)
    replacements[I915_DRV_PATH] = traced
    replacements[I915_DP_PATH] = final_dp
    replacements[CHV_POWER_PATH] = final_power
    cfgpath = "sys/arch/amd64/conf/" + diag_ident
    replacements[cfgpath] = config.encode()
    snapshot = {
        "schema": 1, "status": STATUS, "identity": diag_ident,
        "target": "HP NetBSD 11 amd64 SOURCE/COMPILE DIAGNOSTIC ONLY",
        "native_i915_mode": "PINNED_NETBSD_GENERIC_NOT_FULL_LINUX323_PORT",
        "no_release_authorization": True,
        "eligible_for_install": False, "eligible_for_boot": False,
        "kernel_build": "NOT_RUN", "i915_full_323_semantic_closure": "NOT_VERIFIED",
        "RTL_SHA": rtl_sha, "I915_SHA": gpu_sha,
        "NETBSD_SHA": NETBSD_PIN,
        "config": "source/" + cfgpath, "rtl_native_units": rtl_units,
        "required_native_i915_sources": list(REQUIRED_BUILTIN),
        "source_sha256": {k:digest(v) for k,v in sorted(replacements.items())},
        **trace_meta, **dp_meta, **chv_meta, **aux_meta,
    }
    out.mkdir(mode=0o700)
    try:
        staged = out / "source"
        staged.mkdir(mode=0o700)
        mirror(src / "sys", staged / "sys", {
            k[4:]:v for k,v in replacements.items() if k.startswith("sys/")
        })
        (staged / "common").symlink_to(src / "common", target_is_directory=True)
        (out / "obj").mkdir(mode=0o700)
        (out / "diagnostic-source-manifest.json").write_text(
            json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    except BaseException:
        shutil.rmtree(out)
        raise
    return snapshot


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--i915-repo", required=True, type=Path)
    p.add_argument("--rtl-repo", type=Path, default=ROOT)
    p.add_argument("--netbsd-src", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    try:
        if (platform.system() != "NetBSD" or platform.machine() != "amd64" or
                not socket.gethostname().startswith("hp-tpnw121") or
                os.geteuid() == 0):
            refuse("HP_OWNER_NETBSD11_AMD64_NONROOT_ONLY")
        n, rtl, i915 = (x.resolve(strict=True) for x in
                         (args.netbsd_src, args.rtl_repo, args.i915_repo))
        if clean_git_head(n) != NETBSD_PIN:
            refuse("wrong NetBSD source revision")
        rtl_sha, gpu_sha = clean_git_head(rtl), clean_git_head(i915)
        result = prepare(n, rtl, i915, args.output, rtl_sha, gpu_sha)
        print(json.dumps({"status":STATUS,"identity":result["identity"],
                          "out":str(args.output),"native_kernel_built":False}))
        return 0
    except (OSError, RuntimeError, ValueError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
