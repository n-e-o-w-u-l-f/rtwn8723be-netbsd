#!/usr/bin/env python3
"""Verify full combined native object coverage in actual-link MAP gate.

All tests are synthetic map text only. These tests neither compile nor
link a kernel and do not imply that the i915 ownership closure is complete.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from configure_hp_combined_i915_rtl import rtl_inventory
from verify_hp_combined_kernel import verify_link_map_owners


def refused(fn, label):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("missing-map object wrongly accepted: " + label)


rtl = rtl_inventory(ROOT)
gpu = [
    "sys/external/bsd/drm2/i915drm/i915_module.c",
    "sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c",
    "sys/external/bsd/drm2/dist/drm/i915/display/intel_display.c",
    "sys/external/bsd/drm2/dist/drm/drm_drv.c",
]
rtl_names = [Path(x).stem + ".o" for x in rtl]
gpu_names = [Path(x).stem + ".o" for x in gpu]
all_names = rtl_names + gpu_names
assert len(rtl) == 50 and len(set(all_names)) == 54
full_map = "Linker script and Map\n" + "".join(
    f" /private/stage/obj/{name}\n" for name in all_names)
result = verify_link_map_owners(full_map, rtl, gpu)
assert result["map_rtl_objects_verified"] == 50
assert result["map_gpu_drm_objects_verified"] == 4

# Every one of 50 RTL units and all GPU/DRM units is mandatory.
# A successful partial link or the first RTL/GPU only must never pass.
cases = 0
for name in all_names:
    without = full_map.replace(f" /private/stage/obj/{name}\n", "", 1)
    refused(lambda text=without: verify_link_map_owners(text, rtl, gpu),
            "removed-" + name)
    cases += 1

refused(lambda: verify_link_map_owners(
    " /stage/rtl/" + rtl_names[0] + "\n" +
    " /stage/gpu/" + gpu_names[0] + "\n", rtl, gpu), "weak-first-rtl-first-gpu")
cases += 1
refused(lambda: verify_link_map_owners("", rtl, gpu), "empty-map")
cases += 1
refused(lambda: verify_link_map_owners(
    full_map.replace(
        f" /private/stage/obj/{rtl_names[3]}\n",
        f" /private/stage/obj/{rtl_names[3]}.old\n"),
    rtl, gpu), "false-extension-substring")
cases += 1
refused(lambda: verify_link_map_owners(
    full_map.replace(
        f" /private/stage/obj/{gpu_names[1]}\n",
        f" /private/stage/obj/{gpu_names[1]}2\n"),
    rtl, gpu), "false-gpu-object-substring")
cases += 1
refused(lambda: verify_link_map_owners(
    full_map.replace(
        f" /private/stage/obj/{rtl_names[4]}\n",
        " /private/stage/obj/completely_different.o\n"),
    rtl, gpu), "unrelated-object-substitution")
cases += 1

print("HP_COMBINED_LINK_MAP_SOURCE_PASS: 50 RTL + 4 synthetic i915/DRM; "
      f"{cases} negative object/linker-map cases; native ELF NOT_RUN")
