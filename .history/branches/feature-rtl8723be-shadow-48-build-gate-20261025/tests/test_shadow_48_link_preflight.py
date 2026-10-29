#!/usr/bin/env python3
"""Portable negative/positive preflight checks for the private 48-object link.

No NetBSD tools or hardware are needed: main() is intentionally not called.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_hp_kernel_shadow as gate  # noqa: E402

manifest = (ROOT / "config/files.rtwn8723be_native").read_text()
units = gate.setup.SELECTED.findall(manifest)
assert len(units) == 48 and len(set(units)) == 48
head = "a" * 40
config = gate.setup.render_private_config("arch/amd64/conf/GENERIC")
makefile = "RTL native targets: rtwn8723be_btc_context.o\n"
status = {
    "state": "CONFIGURED_48_RULES_DRYRUN_PASS",
    "source_head": head,
    "selected_sources": units,
    "manifest_sha256": "nonempty",
    "unchanged_original_pci": True,
    "rules": [
        {"name": name, "exit": 0, "rule_present": True} for name in units
    ],
}
gate.validate_plan(status, units, head, config, makefile)


def must_reject(data, names=units, source_head=head, conf=config, mk=makefile):
    try:
        gate.validate_plan(data, names, source_head, conf, mk)
    except RuntimeError:
        return
    raise AssertionError("unsafe or stale private kernel build was accepted")


must_reject(status, conf=config.replace("no i915drmkms*\n", ""))
must_reject(status, conf=config.replace("no i915drmkms*\n", "i915drmkms* at pci?\n"))
must_reject(status, mk=makefile + "i915drmkms.o: i915drmkms.c\n")
must_reject(status, mk=makefile + "# accidental i915 build include\n")
must_reject(status, source_head="b" * 40)
must_reject({**status, "state": "RUNNING"})
must_reject({**status, "selected_sources": units[:-1]})
must_reject({**status, "unchanged_original_pci": False})
must_reject({**status, "rules": status["rules"][:-1]})
must_reject({**status, "rules": [
    *status["rules"][:-1],
    {"name": units[-1], "exit": 0, "rule_present": False},
]})
must_reject({**status, "rules": [
    *status["rules"][:-1],
    {"name": units[-1], "exit": 1, "rule_present": True},
]})
must_reject(status, names=units[:-1])
must_reject(status, names=[*units[:-1], units[0]])
# The older tree-staging entrypoint must never become an alternate
# full-kernel or i915-enabled path around the isolated shadow gate.
legacy = (ROOT / "tools/build_hp_native.py").read_text()
assert 'if args.target == "kernel":' in legacy
assert 'sys.exit("REFUSED: legacy kernel target disabled;' in legacy
assert "'no i915drmkms*\\n'" in legacy

print("RTL_PRIVATE_48_LINK_PREFLIGHT_OK")
