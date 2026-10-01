#!/usr/bin/env python3
"""Materialize the complete pinned Linux rtl8723be dependency set."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"

RTL_ROOT = Path("drivers/net/wireless/realtek/rtlwifi")
SELECTED_DIRS = (
    RTL_ROOT / "rtl8723be",
    RTL_ROOT / "rtl8723com",
    RTL_ROOT / "btcoexist",
)

# Linux RTLWIFI common module + PCI transport selected by Kconfig.
COMMON_OBJECTS = (
    "base.c", "cam.c", "core.c", "debug.c", "efuse.c",
    "ps.c", "rc.c", "regd.c", "stats.c", "pci.c",
)

TOP_LEVEL_ALWAYS = (
    "Makefile", "Kconfig",
)

ACTIVE_MAKE_VARS = (
    (RTL_ROOT / "Makefile", "rtlwifi-objs", RTL_ROOT),
    (RTL_ROOT / "Makefile", "rtl_pci-objs", RTL_ROOT),
    (RTL_ROOT / "rtl8723be" / "Makefile", "rtl8723be-objs",
     RTL_ROOT / "rtl8723be"),
    (RTL_ROOT / "rtl8723com" / "Makefile", "rtl8723-common-objs",
     RTL_ROOT / "rtl8723com"),
    (RTL_ROOT / "btcoexist" / "Makefile", "btcoexist-objs",
     RTL_ROOT / "btcoexist"),
)


def makefile_object_sources(src_root: Path, rel_makefile: Path,
                            variable: str, prefix: Path) -> list[str]:
    text = (src_root / rel_makefile).read_text()
    logical = []
    pending = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        pending += (" " if pending else "") + line.strip()
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        logical.append(pending)
        pending = ""

    sources = []
    for line in logical:
        if ":=" in line:
            name, rhs = line.split(":=", 1)
        elif "+=" in line:
            name, rhs = line.split("+=", 1)
        else:
            continue
        if name.strip() != variable:
            continue
        for token in rhs.split():
            if token.endswith(".o"):
                sources.append(str(prefix / (token[:-2] + ".c")))
    if not sources:
        raise RuntimeError(f"no objects found for {variable} in {rel_makefile}")
    return sources


def git_head(tree: Path) -> str | None:
    try:
        p = subprocess.run(
            ["git", "-C", str(tree), "rev-parse", "HEAD"],
            check=True, text=True, capture_output=True
        )
        return p.stdout.strip()
    except Exception:
        return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_file(src_root: Path, dst_root: Path, rel: Path) -> None:
    src = src_root / rel
    if not src.is_file():
        raise FileNotFoundError(str(rel))
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--linux-tree", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--allow-unverified-linux-head", action="store_true")
    args = ap.parse_args()

    linux = args.linux_tree.resolve()
    out = args.out.resolve()
    head = git_head(linux)

    if head and head != LINUX_PIN and not args.allow_unverified_linux_head:
        raise SystemExit(
            f"refusing Linux HEAD {head}; expected pinned {LINUX_PIN}"
        )

    rtl = linux / RTL_ROOT
    if not rtl.is_dir():
        raise SystemExit(f"missing {rtl}")

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for rel in SELECTED_DIRS:
        src = linux / rel
        if not src.is_dir():
            raise SystemExit(f"missing {src}")
        shutil.copytree(src, out / rel, dirs_exist_ok=True)

    # Copy all top-level rtlwifi headers: the common objects and selected
    # chip modules share these structures/contracts.
    for hdr in rtl.glob("*.h"):
        rel = RTL_ROOT / hdr.name
        copy_file(linux, out, rel)

    for name in COMMON_OBJECTS + TOP_LEVEL_ALWAYS:
        copy_file(linux, out, RTL_ROOT / name)

    files = []
    materialized_c = []
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        rel = str(path.relative_to(out))
        files.append({
            "path": rel,
            "size": path.stat().st_size,
            "sha256": sha256(path),
        })
        if path.suffix == ".c":
            materialized_c.append(rel)

    active_c = []
    for rel_makefile, variable, prefix in ACTIVE_MAKE_VARS:
        active_c.extend(
            makefile_object_sources(linux, rel_makefile, variable, prefix)
        )
    active_c = sorted(set(active_c))

    missing_active = [
        rel for rel in active_c
        if not (out / rel).is_file()
    ]
    if missing_active:
        raise RuntimeError(
            "active source files missing from materialized tree: " +
            ", ".join(missing_active)
        )

    manifest = {
        "linux_pin": LINUX_PIN,
        "linux_head_observed": head,
        "selected_kconfig": [
            "RTL8723BE", "RTLWIFI", "RTLWIFI_PCI",
            "RTL8723_COMMON", "RTLBTCOEXIST",
        ],
        "common_objects": list(COMMON_OBJECTS),
        "active_c_file_count": len(active_c),
        "active_c_files": active_c,
        "materialized_c_file_count": len(materialized_c),
        "materialized_c_files": materialized_c,
        "total_file_count": len(files),
        "files": files,
    }

    (out / "PORT-MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )

    print(json.dumps({
        "linux_pin": LINUX_PIN,
        "active_c_file_count": len(active_c),
        "total_file_count": len(files),
        "manifest": str(out / "PORT-MANIFEST.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
