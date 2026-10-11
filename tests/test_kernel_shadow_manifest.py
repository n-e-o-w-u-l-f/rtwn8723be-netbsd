#!/usr/bin/env python3
"""Exercise the private PCI-manifest merge used by the HP shadow build.

This protects against a stale source tree that has zero or partial native
declarations.  The generated shadow must contain exactly the canonical
device, attach and 44 selected C declarations while retaining unrelated PCI
entries.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location(
    "configure_hp_native_kernel_shadow",
    ROOT / "tools" / "configure_hp_native_kernel_shadow.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

manifest = (ROOT / "config" / "files.rtwn8723be_native").read_text()
base = """\
device  unrelated: ifnet
attach  unrelated at pci
file dev/pci/unrelated.c unrelated
device  rtwn8723be_native: obsolete
attach  rtwn8723be_native at pci
file dev/pci/rtwn8723be_old.c rtwn8723be_native
"""

merged = MODULE.render_private_pci_manifest(base, manifest)
lines = merged.splitlines()
files = [line for line in lines if re.match(
    r"^file\s+dev/pci/rtwn8723be_\w+\.c\s+rtwn8723be_native$", line)]

assert "file dev/pci/unrelated.c unrelated" in lines
assert "device  rtwn8723be_native: obsolete" not in lines
assert "file dev/pci/rtwn8723be_old.c rtwn8723be_native" not in lines
assert sum(line.startswith("device  rtwn8723be_native:") for line in lines) == 1
assert sum(line.startswith("attach  rtwn8723be_native at pci") for line in lines) == 1
assert len(files) == 44
assert len(set(files)) == 44

inputs = MODULE.default_hp_shadow_inputs()
assert inputs["sys"] == Path("/usr/src/sys")
assert inputs["nbconfig"] == Path("/usr/tools/bin/nbconfig")
assert inputs["make"] == Path("/usr/tools/bin/nbmake-amd64")
paths = MODULE.hp_shadow_paths(inputs)
assert paths["pci_manifest"] == Path("/usr/src/sys/dev/pci/files.pci")
assert paths["baseline_config"] == Path("/usr/src/sys/arch/amd64/conf/GENERIC")
assert paths["common"] == Path("/usr/src/common")
assert MODULE.COMMON_REQUIRED_RELATIVE_PATHS == (
    "include/prop/proplib.h",
    "lib/libx86emu",
    "lib/libc/misc",
    "lib/libc/quad",
    "lib/libc/string",
    "lib/libc/arch/x86_64/string",
    "lib/libc/arch/x86_64/atomic",
    "lib/libc/hash/sha3",
)
shadow = Path("/private/sys")
dryrun = ("cc -I/private/sys/../common/include -c "
          "/private/sys/dev/pci/rtwn8723be_native.c "
          "-o rtwn8723be_native.o")
assert MODULE.private_dryrun_rule_present(
    dryrun, "rtwn8723be_native.c", "rtwn8723be_native.o", shadow)
assert not MODULE.private_dryrun_rule_present(
    dryrun + " /usr/src/sys/dev/pci/rtwn8723be_native.c",
    "rtwn8723be_native.c", "rtwn8723be_native.o", shadow)

print("RTL_PRIVATE_SHADOW_MANIFEST_MERGE_OK")
