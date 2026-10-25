#!/usr/bin/env python3
"""Build and link the 48-unit RTL8723BE kernel in an existing PRIVATE HP shadow.

This is a build-only gate, never an installation or boot procedure. The
canonical configure_hp_native_kernel_shadow.py must first complete with all
48 generated rules passing. This script does not write /usr/src, /netbsd, or
/boot.cfg, and refuses any build tree that could select i915drmkms.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess

import configure_hp_native_kernel_shadow as setup

ROOT = Path(__file__).resolve().parents[1]
F77_SHA256 = "9b65629c0527bbd40f7ffa0d4ef0c59a32b5edceb597a5df8c86d1e7be1c8fde"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_plan(status: dict, units: list[str], head: str,
                  config_text: str, makefile_text: str) -> None:
    """Pure preflight: reject stale rules, missing i915 exclusion and drift."""
    if (status.get("state") != "CONFIGURED_48_RULES_DRYRUN_PASS" or
            status.get("source_head") != head or
            status.get("selected_sources") != units or
            status.get("manifest_sha256") is None or
            not status.get("unchanged_original_pci")):
        raise RuntimeError("shadow configuration evidence is missing or stale")
    if len(units) != setup.NATIVE_C_UNIT_COUNT or len(set(units)) != len(units):
        raise RuntimeError("expected exactly 48 unique native C units")
    checked = status.get("rules")
    if (not isinstance(checked, list) or len(checked) != len(units) or
            [x.get("name") for x in checked] != units or
            any(x.get("exit") != 0 or x.get("rule_present") is not True
                for x in checked)):
        raise RuntimeError("generated native object rules are incomplete")
    expected = setup.render_private_config("arch/amd64/conf/GENERIC")
    if config_text != expected or config_text.count("no i915drmkms*\n") != 1:
        raise RuntimeError("private kernel config is not the i915-free baseline")
    if "i915" in makefile_text.lower():
        raise RuntimeError("i915 input detected in generated private Makefile")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", type=Path, required=True,
                        help="fresh rtl-kconfig-* output of the private configurator")
    args = parser.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        parser.error("REFUSED: build-only gate may run solely on the target HP/NetBSD")
    if os.geteuid() == 0:
        parser.error("REFUSED: build as unprivileged owner, never root")
    if args.shadow.is_symlink():
        parser.error("REFUSED: shadow directory must not be a symlink")
    output = args.shadow.resolve(strict=True)
    if (not output.is_dir() or output.parent != ROOT.parent.resolve() or
            not output.name.startswith("rtl-kconfig-")):
        parser.error("REFUSED: only a configured private sibling shadow is allowed")

    shadow = output / "sys"
    obj = output / "obj"
    status_path = output / "status.json"
    report_path = output / "build-48-status.json"
    if report_path.exists() or not status_path.is_file():
        parser.error("REFUSED: use an unused, fully configured private shadow")
    if (shadow.is_symlink() or obj.is_symlink() or
            not shadow.is_dir() or not obj.is_dir()):
        parser.error("REFUSED: private source/object directories are invalid")
    status = json.loads(status_path.read_text())
    if (status.get("owner_shadow") != str(shadow) or
            status.get("owner_objdir") != str(obj)):
        parser.error("REFUSED: configuration belongs to a different shadow")
    if subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"],
                               text=True).strip():
        parser.error("REFUSED: clean current source checkout required")
    head = subprocess.check_output(["git", "-C", str(ROOT),
                                    "rev-parse", "HEAD"], text=True).strip()

    manifest = ROOT / "config/files.rtwn8723be_native"
    units = setup.SELECTED.findall(manifest.read_text())
    config = output / setup.PRIVATE_CONFIG_NAME
    makefile = obj / "Makefile"
    source_manifest = Path("/usr/src/sys/dev/pci/files.pci")
    live_kernel = Path("/netbsd")
    bootcfg = Path("/boot.cfg")
    tools = setup.default_hp_shadow_inputs()
    if not (config.is_file() and makefile.is_file() and
            tools["make"].is_file() and source_manifest.is_file() and
            live_kernel.is_file()):
        parser.error("REFUSED: required immutable or private inputs missing")
    validate_plan(status, units, head, config.read_text(), makefile.read_text())
    if sha256(manifest) != status["manifest_sha256"]:
        parser.error("REFUSED: manifest changed after shadow configuration")
    if sha256(source_manifest) != status["baseline_stage_sha256"]:
        parser.error("REFUSED: original PCI manifest differs from shadow baseline")
    if sha256(live_kernel) != F77_SHA256:
        parser.error("REFUSED: live recovery /netbsd is not the verified F77")
    for name in units:
        project = ROOT / "src" / name
        staged = shadow / "dev/pci" / name
        if not (project.is_file() and staged.is_symlink() and
                staged.resolve() == project.resolve()):
            parser.error("REFUSED: missing or noncanonical shadow source: " + name)

    originals = {"pci": sha256(source_manifest), "kernel": sha256(live_kernel)}
    if bootcfg.exists():
        originals["bootcfg"] = sha256(bootcfg)
    sources = {name: sha256(ROOT / "src" / name) for name in units}
    report = {
        "state": "RUNNING", "source_head": head,
        "selected_sources": units, "manifest_sha256": sha256(manifest),
        "shadow": str(output), "originals_before": originals,
        "sources_before": sources,
        "started": datetime.now(timezone.utc).isoformat(), "commands": [],
    }

    def save() -> None:
        temp = output / "build-48-status.tmp"
        temp.write_text(json.dumps(report, indent=2) + "\n")
        temp.replace(report_path)

    def enforce_unchanged() -> None:
        if sha256(source_manifest) != originals["pci"] or sha256(live_kernel) != originals["kernel"]:
            raise RuntimeError("immutable PCI manifest or F77 kernel changed")
        if "bootcfg" in originals and sha256(bootcfg) != originals["bootcfg"]:
            raise RuntimeError("boot configuration changed")
        if any(sha256(ROOT / "src" / name) != digest
               for name, digest in sources.items()):
            raise RuntimeError("driver sources changed during build")
        if "i915" in makefile.read_text().lower():
            raise RuntimeError("i915 appeared in generated Makefile")

    # /usr/tools/bin is required by NetBSD's noninteractive link step.
    # Apply this PATH only to subprocesses, never to system profiles.
    env = os.environ.copy()
    env["PATH"] = "/usr/tools/bin:" + env.get("PATH", "/usr/bin:/bin")

    def build(stage: str, targets: list[str], timeout: int) -> None:
        cmd = [str(tools["make"]), "-C", str(obj), "-j2", *targets]
        log = output / ("build-48-" + stage + ".log")
        with log.open("w") as stream:
            result = subprocess.run(cmd, cwd=output, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        report["commands"].append({
            "stage": stage, "argv": cmd, "exit": result.returncode,
            "log_sha256": sha256(log),
        })
        save()
        if result.returncode != 0:
            raise RuntimeError(stage + " failed; see retained private log")
        enforce_unchanged()

    save()
    try:
        enforce_unchanged()
        build("depend", ["depend"], 3600)
        objects = [name[:-2] + ".o" for name in units]
        build("objects", objects, 7200)
        report["objects"] = {}
        hashes = []
        for name, objname in zip(units, objects):
            path = obj / objname
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError("missing/empty private object " + objname)
            digest = sha256(path)
            report["objects"][name] = {"bytes": path.stat().st_size, "sha256": digest}
            hashes.append(name + " " + digest)
        report["ordered_objects_sha256"] = hashlib.sha256(
            ("\n".join(hashes) + "\n").encode()).hexdigest()
        save()
        build("kernel", ["netbsd"], 7200)
        kernel = obj / "netbsd"
        if not kernel.is_file() or kernel.stat().st_size == 0:
            raise RuntimeError("private kernel link did not produce netbsd")
        with kernel.open("rb") as stream:
            count = stream.read().count(b"(RTWN8723BE-NATIVE-SHADOW)")
        if count != 1:
            raise RuntimeError("private kernel has unexpected identity count")
        enforce_unchanged()
        report["kernel"] = {"bytes": kernel.stat().st_size, "sha256": sha256(kernel),
                            "identity_occurrences": count}
        report["originals_after"] = {
            "pci": sha256(source_manifest), "kernel": sha256(live_kernel),
            **({"bootcfg": sha256(bootcfg)} if "bootcfg" in originals else {}),
        }
        report["state"] = "BUILD_ONLY_PASSED"
        report["limitation"] = ("48 private objects and kernel linked; NO install, "
                                "boot, PCI/IRQ admission, WLAN or i915 acceptance")
    except Exception as exc:
        report["state"] = "FAILED"
        report["error"] = str(exc)
        raise
    finally:
        report["finished"] = datetime.now(timezone.utc).isoformat()
        save()
    print("RTL_PRIVATE_48_KERNEL_LINK_BUILD_ONLY_PASS", report_path)


if __name__ == "__main__":
    main()
