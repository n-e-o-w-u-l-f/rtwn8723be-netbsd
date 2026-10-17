#!/usr/bin/env python3
"""HP combined i915drmkms + RTL8723BE NetBSD 11 source/configurator.

No HP build, install, boot or GPU/WLAN activation is performed here.
--audit-only is read-only and requires no release.
--configure requires i915-owner release, clean Git inputs and HP ownership.
i915 release and full 323-unit native source-closure remain distinct gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_i915_kernel_release import check as release_check

SHA = re.compile(r"^[0-9a-f]{40}$")
RTL_UNIT = re.compile(
    r"^\s*file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native\s*$", re.M)
KERNEL_DEVICE = re.compile(r"^\s*(?:i915drmkms|rtwn8723be)\*\s+at\s+pci\?", re.M)
I915_FILES = "sys/external/bsd/drm2/i915drm/files.i915drmkms"
I915_CLOSURE = "governance/HP_I915DRMKMS_COMBINED_SOURCE_CLOSURE.json"
FLAGS = (
    "linux_323_semantic_mapping",
    "drm_ttm_gem_gtt_uvm",
    "linuxkpi_netbsd_abi",
    "pci_mmio_bus_dma_irq",
    "firmware_vbt_opregion",
    "chv_iosf_punit_dpio",
    "edp_aux_cdclk_pll",
    "fbdev_wsdisplay_handoff",
    "init_unwind_pm_lifetime",
    "symbol_provider_closure",
)
STOP = "WAIT_FOR_I915_RELEASE"


def refuse(message: str) -> None:
    raise ValueError(message)


def canonical_relative(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        refuse("unsafe or missing relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or "." in p.parts or str(p) != value:
        refuse("unsafe path " + repr(value))
    return value


def exact_sha(value: str) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        refuse("invalid Git SHA " + repr(value))
    return value


def run_git(repo: Path, *args: str) -> str:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=20,
    )
    if p.returncode:
        refuse("Git verification failed: " + " ".join(args))
    return p.stdout.strip()


def clean_git_head(repo: Path) -> str:
    if run_git(repo, "rev-parse", "--show-toplevel") != str(repo):
        refuse("not an exact standalone Git checkout")
    if run_git(repo, "status", "--porcelain=v1"):
        refuse("dirty source checkout: " + str(repo))
    return exact_sha(run_git(repo, "rev-parse", "HEAD"))


def rtl_inventory(repo: Path) -> list[str]:
    m = (repo / "config/files.rtwn8723be_native").read_text()
    units = RTL_UNIT.findall(m)
    if len(units) != 50 or len(set(units)) != 50:
        refuse("RTL_NATIVE_50_UNITS_INCOMPLETE")
    for unit in units:
        p = repo / "src" / unit
        if not p.is_file() or p.is_symlink():
            refuse("missing/nonregular RTL native source " + unit)
    if re.search(r"^\s*no\s+i915drmkms", m, re.M):
        refuse("RTL files manifest disables i915")
    return units


def i915_closure(repo: Path, i915_sha: str) -> dict:
    path = repo / I915_CLOSURE
    if not path.is_file() or path.is_symlink():
        refuse("I915_323_NATIVE_SOURCE_CLOSURE_MISSING")
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("schema") != 1:
        refuse("i915 source-closure manifest schema invalid")
    validated = exact_sha(data.get("validated_i915_source_sha"))
    ok = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", validated, i915_sha],
        capture_output=True, timeout=20,
    )
    if ok.returncode:
        refuse("i915 closure validated source SHA outside current Git history")
    phases = data.get("verified_subsystems")
    if not isinstance(phases, dict) or any(phases.get(k) != "PASS" for k in FLAGS):
        refuse("missing full i915 DRM/PCI/KMS/PM/source-owner verification")
    rows = data.get("linux_323_units")
    if not isinstance(rows, list) or len(rows) != 323:
        refuse("exactly 323 Linux active semantic mappings are required")
    # Bind all 323 row identities to the i915-owner's *actual* frozen
    # Linux reference inventory. Count-only synthetic names are not proof.
    inventory = repo / "docs/I915-STRUCTURAL-COVERAGE.tsv"
    if not inventory.is_file() or inventory.is_symlink():
        refuse("pinned i915 Linux-323 inventory missing")
    matrix = inventory.read_text().splitlines()
    if not matrix or matrix[0].split("\t")[:2] != [
            "linux_source", "structural_class"]:
        refuse("i915 pinned structural inventory header invalid")
    exact_linux = [line.split("\t")[0] for line in matrix[1:]]
    if len(exact_linux) != 323 or len(set(exact_linux)) != 323:
        refuse("i915 frozen 323 Linux source identity list corrupt")
    source_map, mapped = set(), set()
    for row in rows:
        if not isinstance(row, dict):
            refuse("invalid i915 semantic source entry")
        key = canonical_relative(row.get("linux_source"))
        if not key.endswith(".c") or key in source_map:
            refuse("duplicate/non-C Linux i915 semantic owner")
        source_map.add(key)
        assigned = row.get("native_sources")
        if not isinstance(assigned, list) or not assigned:
            refuse("unmapped original i915 Linux source: " + key)
        for native in assigned:
            native = canonical_relative(native)
            if not native.startswith("sys/") or not native.endswith(".c"):
                refuse("invalid target native source: " + native)
            mapped.add(native)
        if not isinstance(row.get("evidence"), str) or len(row["evidence"].strip()) < 12:
            refuse("missing per-unit behavioral evidence " + key)
    if source_map != set(exact_linux):
        refuse("i915 closure does not map exact 323 frozen Linux sources")
    selected = data.get("selected_i915_sources")
    if not isinstance(selected, list) or len(selected) < 3 or len(set(selected)) != len(selected):
        refuse("missing selected native i915/DRM/TTM source closure")
    selected = [canonical_relative(p) for p in selected]
    if any(not p.startswith("sys/") or not p.endswith(".c") for p in selected):
        refuse("invalid selected native source")
    if not mapped.issubset(set(selected)):
        refuse("i915 semantic mapping not included in selected kernel owner graph")
    if not any("/i915/" in p or "/i915drm/" in p for p in selected):
        refuse("no real native i915 C owner")
    for p in ("sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c",):
        if p not in selected:
            refuse("missing PCI i915 auto-configuration C owner: " + p)
    overlays = data.get("source_overlays")
    if not isinstance(overlays, list) or not overlays:
        refuse("i915 owner provided no modern NetBSD source overlays")
    files = {}
    for ent in overlays:
        if not isinstance(ent, dict):
            refuse("invalid i915 native overlay record")
        dest = canonical_relative(ent.get("destination"))
        src = canonical_relative(ent.get("source"))
        digest = ent.get("sha256")
        if not dest.startswith("sys/") or not src.startswith("native_overlay/"):
            refuse("i915 overlays must target private NetBSD sys/ tree")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            refuse("i915 overlay missing sha256")
        if dest in files:
            refuse("duplicate i915 overlay destination " + dest)
        file = repo / src
        if not file.is_file() or file.is_symlink():
            refuse("i915 overlay missing: " + src)
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            refuse("i915 source overlay SHA256 mismatch: " + src)
        files[dest] = (file, digest)
    if I915_FILES not in files:
        refuse("no i915-owned files.i915drmkms in source snapshot")
    if not any(name.endswith(".c") for name in files):
        refuse("i915 overlay has no native implementation")
    return {"sha":i915_sha, "source_owner_count":len(selected),
            "linux_323_mapped":len(rows), "selected":selected,
            "files":files, "raw":data}


def selected_i915_objects(selected: list[str]) -> set[str]:
    obj = [PurePosixPath(x).stem + ".o" for x in selected]
    if len(set(obj)) != len(obj):
        refuse("duplicate i915/DRM basename object owners")
    return set(obj)


def validate_i915_filelist(text: str, expected: list[str]) -> None:
    if re.search(r"^\s*no\s+i915drmkms", text, re.M):
        refuse("i915 provider filelist disables i915drmkms")
    if not re.search(r"^\s*device\s+i915drmkms\s*:", text, re.M):
        refuse("native i915drmkms device owner not declared")
    if not re.search(r"^\s*attach\s+i915drmkms\s+at\s+pci", text, re.M):
        refuse("native i915drmkms PCI attachment absent")
    active = set()
    for line in text.splitlines():
        match = re.match(r"^\s*file\s+(\S+)\s+(\S+)", line)
        if match and "i915drmkms" in match.group(2):
            active.add("sys/" + match.group(1))
    if not set(expected).issubset(active):
        refuse("i915 selected filelist omits DRM/native source owners: " +
               str(len(set(expected) - active)))


def render_config(generic: str, rtl_short: str, i915_short: str) -> tuple[str, str]:
    if re.search(r"^\s*no\s+(?:i915drmkms|intelfb|drmfb|rtwn8723be)\b", generic, re.M):
        refuse("GENERIC base disables required combined devices")
    if re.search(r"^\s*no\s+i915drmkms", generic, re.M):
        refuse("i915 KMS disabled")
    identity = "HP-COMBINED-I915-" + i915_short + "-RTL-" + rtl_short
    if not re.fullmatch(r"[0-9a-f]{12}", rtl_short) or not re.fullmatch(r"[0-9a-f]{12}", i915_short):
        refuse("invalid source commit identity")
    lines = ['include "arch/amd64/conf/GENERIC"', 'ident "' + identity + '"']
    for device, bus in (
        ("i915drmkms", "pci"),
        ("intelfb", "intelfbbus"),
        ("rtwn8723be", "pci"),
    ):
        if not re.search(r"^\s*" + device + r"\*\s+at\s+" + bus + r"\?", generic, re.M):
            if device == "intelfb":
                lines.append("intelfb* at intelfbbus?")
            else:
                lines.append(device + "* at pci? dev ? function ?")
    output = "\n".join(lines) + "\n"
    if re.search(r"^\s*no\s+i915drmkms", output, re.M):
        refuse("unacceptable RTL-only kernel configuration")
    return identity, output


def effective_config(generic: str, config: str) -> None:
    if re.search(r"^\s*no\s+i915drmkms", config, re.M | re.I):
        refuse("NO_I915DRMKMS - combined kernel must have KMS")
    combined = generic + "\n" + config
    for dev in ("i915drmkms", "intelfb", "rtwn8723be"):
        if not re.search(r"^\s*" + dev + r"\*\s+at\s+", combined, re.M):
            refuse("missing effective NetBSD kernel device: " + dev)
    if "HP-RTL50-" in config or "SAFE-GENFB" in config:
        refuse("legacy RTL-only kernel identity in combined configuration")


def verify_make_objects(obj_text: str, rtl: list[str], i915: list[str]) -> dict:
    objects = re.findall(r"[\w.-]+\.o\b", obj_text)
    actual = set(objects)
    rtl_names = {PurePosixPath(x).stem + ".o" for x in rtl}
    gpu_names = selected_i915_objects(i915)
    if rtl_names & gpu_names:
        refuse("duplicate GPU/WLAN object owner")
    if len(objects) != len(actual):
        refuse("duplicate selected object in expanded NetBSD OBJS")
    miss_rtl = rtl_names - actual
    miss_gpu = gpu_names - actual
    if miss_rtl or miss_gpu:
        refuse("incomplete combined NetBSD OBJS: RTL=" +
               str(len(miss_rtl)) + ", i915=" + str(len(miss_gpu)))
    if not any(n.startswith("i915") or n.startswith("intel") for n in gpu_names):
        refuse("missing actual i915 display/PCI object")
    return {"object_count":len(actual), "rtl_objects":len(rtl_names),
            "gpu_and_drm_objects":len(gpu_names)}


def mirror(base: Path, target: Path, replacements: dict[str, bytes], rel: str = "") -> None:
    """Copy only changed files; symlink untouched pinned NetBSD references.

    Permit genuinely NEW intermediate directories supplied by the i915
    owner, but never follow/overwrite a symlink on a replacement path.
    """
    if rel in replacements:
        if base.exists() and (base.is_dir() or base.is_symlink()):
            refuse("replacement collides with source directory/symlink " + rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(replacements[rel])
        return
    active = [key for key in replacements if not rel or key.startswith(rel + "/")]
    if base.is_symlink() or (base.exists() and not base.is_dir()):
        refuse("unsafe source-tree ancestor: " + rel)
    if base.is_dir():
        names = {p.name for p in base.iterdir()}
    elif active:
        names = set()  # A new native directory supplied by i915 overlays.
    else:
        refuse("missing source-tree path: " + rel)
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    for key in active:
        remaining = key[len(rel) + 1:] if rel else key
        if remaining:
            names.add(remaining.split("/", 1)[0])
    for name in sorted(names):
        sub = (rel + "/" if rel else "") + name
        original = base / name
        child = target / name
        if sub in replacements or any(k.startswith(sub + "/") for k in replacements):
            mirror(original, child, replacements, sub)
        else:
            if not original.exists() and not original.is_symlink():
                refuse("missing unchanged pinned source file " + sub)
            child.symlink_to(original)

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--i915-repo", required=True, type=Path)
    p.add_argument("--rtl-repo", type=Path, default=ROOT)
    p.add_argument("--netbsd-src", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--audit-only", action="store_true")
    args = p.parse_args()
    try:
        rtl = args.rtl_repo.resolve(strict=True)
        i915 = args.i915_repo.resolve(strict=True)
        rtl_sha = clean_git_head(rtl)
        gpu_sha = clean_git_head(i915)
        rtl_units = rtl_inventory(rtl)
        result = {"RTL_SHA":rtl_sha, "I915_SHA":gpu_sha,
                  "RTL_NATIVE_UNITS":len(rtl_units), "mode":
                  "AUDIT_ONLY" if args.audit_only else "CONFIGURE",
                  "kernel_build":"NOT_RUN"}
        permit, reason = release_check(i915, rtl_sha)
        result["i915_release"] = "VERIFIED" if permit else "WAIT_FOR_I915_RELEASE"
        result["release_reason"] = reason
        if args.audit_only:
            try:
                closure = i915_closure(i915, gpu_sha)
                result["i915_semantic_units"] = closure["linux_323_mapped"]
                result["i915_selected_native"] = closure["source_owner_count"]
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                result["closure"] = str(exc)
            print(json.dumps(result, indent=2))
            return 0
        if not permit:
            refuse("WAIT_FOR_I915_RELEASE: " + reason)
        if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
            refuse("ONLY_HP_NETBSD11_AMD64")
        if platform.machine() != "amd64" or os.geteuid() == 0:
            refuse("HP_OWNER_AMD64_NONROOT_REQUIRED")
        closure = i915_closure(i915, gpu_sha)
        if args.netbsd_src is None or args.output is None:
            refuse("--netbsd-src and --output required for combined configuration")
        src = args.netbsd_src.resolve(strict=True)
        if not (src / "sys/arch/amd64/conf/GENERIC").is_file():
            refuse("NetBSD/amd64 GENERIC missing")
        if not (src / "common/include/prop/proplib.h").is_file():
            refuse("NetBSD common/include native ABI dependency missing")
        out = args.output.resolve()
        if out.exists() or out.is_symlink() or out == src or src in out.parents:
            refuse("private output must not exist or be inside NetBSD reference")
        generic = (src / "sys/arch/amd64/conf/GENERIC").read_text()
        identity, cfg = render_config(generic, rtl_sha[:12], gpu_sha[:12])
        effective_config(generic, cfg)
        rtl_text = (rtl / "config/files.rtwn8723be_native").read_text()
        files_pci = (src / "sys/dev/pci/files.pci").read_text()
        if "device  rtwn8723be:" in files_pci or re.search(
                r"^\s*attach\s+rtwn8723be\b", files_pci, re.M):
            refuse("existing NetBSD RTL owner collision; no double registration")
        replacements = {"sys/dev/pci/files.pci": (files_pci.rstrip("\n") +
             "\n# HP combined RTL native selection\n" + rtl_text).encode()}
        for unit in rtl_units:
            replacements["sys/dev/pci/" + unit] = (rtl / "src" / unit).read_bytes()
        for path in (rtl / "src").glob("rtwn8723be*.h"):
            replacements["sys/dev/pci/" + path.name] = path.read_bytes()
        for path in (rtl / "src").glob("rtwn8723be*.inc"):
            replacements["sys/dev/pci/" + path.name] = path.read_bytes()
        for dest,(file,_) in closure["files"].items():
            replacements[dest] = file.read_bytes()
        for selected in closure["selected"]:
            if selected not in replacements and not (src / selected).is_file():
                refuse("missing native GPU/DRM/TTM source: " + selected)
        filelist = replacements[I915_FILES].decode()
        validate_i915_filelist(filelist, closure["selected"])
        cfgpath = "sys/arch/amd64/conf/" + identity
        replacements[cfgpath] = cfg.encode()
        # All validation above is read-only. The first mutation is a new,
        # private output folder. Never write through an original symlink.
        out.mkdir(mode=0o700, parents=False)
        try:
            staged = out / "source"
            staged.mkdir(mode=0o700)
            mirror(src / "sys", staged / "sys", {
                k[4:]:v for k,v in replacements.items()
                if k.startswith("sys/")})
            (staged / "common").symlink_to(src / "common", target_is_directory=True)
            (out / "obj").mkdir(mode=0o700)
            snapshot = {
                **result, "identity":identity,
                "config":"source/" + cfgpath,
                "rtl_native_units":rtl_units,
                "i915_selected_native":closure["selected"],
                "source_sha256":{k:hashlib.sha256(v).hexdigest()
                                 for k,v in sorted(replacements.items())},
                "status":"CONFIGURED_SOURCE_ONLY_NO_KERNEL_BUILD",
            }
            (out / "combined-source-manifest.json").write_text(
                json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
        except BaseException:
            shutil.rmtree(out)
            raise
        print(json.dumps({"status":"CONFIGURED_SOURCE_ONLY_NO_KERNEL_BUILD",
                          "identity":identity, "output":str(out),
                          "rtl":len(rtl_units), "i915":len(closure["selected"])}))
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as e:
        print("REFUSED_COMBINED_CONFIG: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
