#!/usr/bin/env python3
"""Read-only native NetBSD DRM/TTM/i915 + RTL source-owner collision audit.

The three filelists and i915 structural inventory MUST come from independently
verified source revisions. This does not compile a kernel, claim completed
Linux-to-NetBSD ABI equivalence, or release i915 for any HP build.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
import sys

RTL = re.compile(
    r"^\s*file\s+dev/pci/(rtwn8723be_\w+\.c)\s+rtwn8723be_native\s*(?:#.*)?$",
    re.M)
FILELISTS = {
    "i915": "external/bsd/drm2/i915drm/files.i915drmkms",
    "drm": "external/bsd/drm2/drm/files.drmkms",
    "ttm": "external/bsd/drm2/ttm/files.ttm",
}
FILE = re.compile(r"^\s*file\s+(\S+\.c)\s+([^\s#]+)(?:\s|$)")
HEADER = ("linux_source", "structural_class", "netbsd_evidence",
          "semantic_state")
KNOWN_CLASSES = {
    "EXACT_ACTIVE_DIST", "ACTIVE_OVERRIDE_OR_MOVED", "PRESENT_NOT_BUILT",
    "UNRESOLVED_NO_BASENAME",
}
EXPECTED = {"i915": 165, "drm": 79, "ttm": 10}


def valid_relative(path: str) -> bool:
    p = PurePosixPath(path)
    return bool(path and not path.startswith("/") and "\\" not in path
                and "\x00" not in path and ".." not in p.parts
                and "." not in p.parts and "//" not in path)


def source_entries(text: str, family: str) -> list[dict]:
    if family not in FILELISTS:
        raise ValueError("unexpected provider family")
    output = []
    for row, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        m = FILE.match(line)
        if not m:
            continue
        p, selector = m.groups()
        if not valid_relative(p) or not p.startswith("external/bsd/drm2/"):
            raise ValueError("unsafe/non DRM source at line " + str(row))
        output.append({"path": p, "owner": family,
                       "selector": selector, "line": row,
                       "object": PurePosixPath(p).stem + ".o"})
    return output


def read_structural(text: str) -> list[dict]:
    lines = text.splitlines()
    if not lines or tuple(lines[0].split("\t")) != HEADER:
        raise ValueError("i915 inventory schema mismatch")
    entries = []
    known = set()
    for row, line in enumerate(lines[1:], 2):
        cells = line.split("\t")
        if len(cells) != 4:
            raise ValueError("i915 inventory row wrong width " + str(row))
        src, cls, evidence, semantic = cells
        if (not valid_relative(src) or not src.endswith(".c")
                or cls not in KNOWN_CLASSES or src in known or not semantic):
            raise ValueError("i915 source/semantic class invalid " + str(row))
        known.add(src)
        entries.append({"linux": src, "class": cls, "evidence": evidence,
                        "semantic": semantic})
    if len(entries) != 323:
        raise ValueError("must cover all 323 frozen Linux active source rows")
    return entries


def audit(rtltext: str, netbsd: dict[str, str],
          structural: str) -> dict:
    rtl_units = RTL.findall(rtltext)
    if len(rtl_units) != 50 or len(set(rtl_units)) != 50:
        raise ValueError("exact 50 uniquely selected native RTL C units required")
    native = []
    if set(netbsd) != set(FILELISTS):
        raise ValueError("i915/DRM/TTM native provider group incomplete")
    for group in FILELISTS:
        source = netbsd[group]
        if group == "i915" and (not re.search(
                r"^\s*device\s+i915drmkms\s*:", source, re.M) or
                not re.search(r"^\s*attach\s+i915drmkms\s+at\s+pci", source, re.M)):
            raise ValueError("real i915 PCI device/attach owner missing")
        entries = source_entries(source, group)
        if len(entries) != EXPECTED[group]:
            raise ValueError(f"{group} provider drift: expected "
                             f"{EXPECTED[group]} selected C rows, got {len(entries)}")
        native.extend(entries)
    owners = [{"object": Path(src).stem + ".o", "path": "dev/pci/" + src,
               "owner": "rtl"} for src in rtl_units] + native
    for obj, count in Counter(e["object"] for e in owners).items():
        if count != 1:
            paths = [e["path"] for e in owners if e["object"] == obj]
            raise ValueError("ambiguous kernel object " + obj + ": " + str(paths))
    for src, count in Counter(e["path"] for e in owners).items():
        if count != 1:
            raise ValueError("duplicate selected C translation unit: " + src)
    reference = read_structural(structural)
    direct = {"external/bsd/drm2/dist/drm/i915/" + e["linux"]
              for e in reference if e["class"] == "EXACT_ACTIVE_DIST"}
    present = {e["path"] for e in native}
    missing_direct = direct - present
    if missing_direct:
        raise ValueError("declared exact i915 C owners absent: " +
                         ", ".join(sorted(missing_direct)[:6]))
    classes = dict(sorted(Counter(e["class"] for e in reference).items()))
    sem = dict(sorted(Counter(e["semantic"] for e in reference).items()))
    if classes != {"ACTIVE_OVERRIDE_OR_MOVED": 13,
                   "EXACT_ACTIVE_DIST": 136,
                   "PRESENT_NOT_BUILT": 7,
                   "UNRESOLVED_NO_BASENAME": 167}:
        raise ValueError("frozen i915 coverage source classes drift")
    if sem != {"REFERENCE_INAPPLICABLE_CHV_UC_PXP": 23, "UNREVIEWED": 300}:
        raise ValueError("frozen 323-unit semantic review counts drift")
    return {
        "status": "SOURCE_OWNER_INVENTORY_PASS_RUNTIME_ABI_NOT_VERIFIED",
        "filelists": dict(EXPECTED),
        "native_candidate_C_rows": len(native),
        "native_candidate_unique_basename_objects": len(native),
        "rtl_native_C_rows": 50,
        "combined_candidate_unique_objects": len(owners),
        "i915_linux_structural_rows": len(reference),
        "direct_active_dist_matches": len(direct),
        "structural_classes": classes,
        "semantic_review": sem,
        "notes": [
            "Native file entries may be predicate-conditional; NOT compiled OBJS",
            "323 Linux file identities are NOT semantic API/ABI equivalence",
            "i915 owner full native overlay + i915 release remain independent",
            "Native NetBSD kernel link, KMS display and WLAN traffic NOT_RUN",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rtl-manifest", type=Path, required=True)
    p.add_argument("--i915-filelist", type=Path, required=True)
    p.add_argument("--drm-filelist", type=Path, required=True)
    p.add_argument("--ttm-filelist", type=Path, required=True)
    p.add_argument("--i915-structural", type=Path, required=True)
    a = p.parse_args()
    try:
        data = audit(a.rtl_manifest.read_text(), {
            "i915": a.i915_filelist.read_text(),
            "drm": a.drm_filelist.read_text(),
            "ttm": a.ttm_filelist.read_text(),
        }, a.i915_structural.read_text())
        print(json.dumps(data, sort_keys=True, indent=2))
        return 0
    except (ValueError, OSError) as e:
        print("COMBINED_SOURCE_OWNER_AUDIT_REFUSED: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
