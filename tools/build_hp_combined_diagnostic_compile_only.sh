#!/bin/sh
# HP NetBSD11 ONLY: native GENERIC i915drmkms + RTL50 diagnostic compile.
# Non-release source-only diagnostic path. NO install, NO copy /netbsd, NO boot.
set -eu
umask 077
export LC_ALL=C
ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
if [ "$#" -ne 3 ]; then
  echo "usage: sh $0 <clean-i915-checkout> <clean-frozen-NetBSD-git> <NEW-absolute-private-output>" >&2
  exit 2
fi
I915=$1
NETBSD=$2
OUTPUT=$3
NBCONFIG=/usr/tools/bin/nbconfig
NBMAKE=/usr/tools/bin/nbmake-amd64
PYTHON=$(command -v python3) || { echo "REFUSED: Python3 unavailable" >&2; exit 2; }
[ "$(uname -s)" = NetBSD ] && [ "$(uname -m)" = amd64 ] || {
  echo "REFUSED: NetBSD amd64 HP only" >&2; exit 2; }
case "$(hostname)" in hp-tpnw121*) : ;; *)
  echo "REFUSED: physical HP target only" >&2; exit 2;; esac
[ "$(id -u)" -ne 0 ] || { echo "REFUSED: owner non-root only" >&2; exit 2; }
[ -x "$NBCONFIG" ] && [ -x "$NBMAKE" ] || {
  echo "REFUSED: HP native tools not verified" >&2; exit 2; }
[ -r /netbsd ] || { echo "REFUSED: current HP kernel path unreadable" >&2; exit 2; }
RUNNING=$(sysctl -n machdep.booted_kernel 2>/dev/null) || {
  echo "REFUSED: current kernel identity not established" >&2; exit 2; }
[ -n "$RUNNING" ] || { echo "REFUSED: empty kernel identity" >&2; exit 2; }
case "$RUNNING" in *F83*|*F84*|*F16.0*)
  echo "REFUSED: known blackscreen/panic candidate running" >&2; exit 2;; esac
case "$OUTPUT" in /*) : ;; *)
  echo "REFUSED: output must be absolute" >&2; exit 2;; esac
[ ! -e "$OUTPUT" ] && [ ! -L "$OUTPUT" ] || {
  echo "REFUSED: existing output cannot be replaced" >&2; exit 2; }
# Uses checked Git source identity and private-only ELF tracing snapshots.
# DOES NOT call the production check_i915_kernel_release.py:
# that gate applies to deployment/full Linux-323 parity, NOT compile-only.
"$PYTHON" -B "$ROOT/tools/stage_hp_combined_diagnostic_source.py" \
  --i915-repo "$I915" --rtl-repo "$ROOT" \
  --netbsd-src "$NETBSD" --output "$OUTPUT" || exit 2
LOG="$OUTPUT/diagnostic-build.log"
STATUS="$OUTPUT/diagnostic-build-status.txt"
{
  printf 'mode=DIAGNOSTIC_COMPILE_ONLY_NONRELEASE\n'
  printf 'running_kernel=%s\n' "$RUNNING"
  printf 'release=false\ninstall=false\nboot=false\n'
  printf 'phase=PRIVATE_SOURCE_STAGED\n'
} > "$STATUS"
phase() { printf 'phase=%s\n' "$1" >> "$STATUS"; }
CONFIG=$("$PYTHON" -B -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["config"])' \
  "$OUTPUT/diagnostic-source-manifest.json")
phase NBCONFIG
"$NBCONFIG" -s "$OUTPUT/source/sys" -b "$OUTPUT/obj" \
  "$OUTPUT/$CONFIG" > "$LOG" 2>&1 || {
    phase FAILED_NBCONFIG
    echo "DIAGNOSTIC_NBCONFIG_FAILED: inspect private $LOG" >&2
    exit 2
  }
phase VERIFY_NATIVE_OBJS
"$NBMAKE" -C "$OUTPUT/obj" -V OBJS > "$OUTPUT/native-objects.txt" 2>>"$LOG" || {
  phase FAILED_OBJECT_QUERY
  exit 2
}
"$PYTHON" -B - "$ROOT" "$OUTPUT" >>"$LOG" 2>&1 <<'PY'
import json,pathlib,sys
root,out=map(pathlib.Path,sys.argv[1:])
sys.path.insert(0,str(root/"tools"))
from configure_hp_combined_i915_rtl import verify_make_objects
from stage_hp_combined_diagnostic_source import REQUIRED_BUILTIN, REQUIRED_DRM_VBLANK, STATUS
data=json.loads((out/"diagnostic-source-manifest.json").read_text())
if data["status"] != STATUS or data["eligible_for_install"] or data["eligible_for_boot"]:
    raise RuntimeError("diagnostic-only status no longer valid")
obj=(out/"native-objects.txt").read_text()
required=list(REQUIRED_BUILTIN)+list(REQUIRED_DRM_VBLANK)
if data["required_native_i915_sources"] != required:
    raise RuntimeError("staged i915/DRM VBlank owner list differs from native gate")
result=verify_make_objects(obj,data["rtl_native_units"],required)
if result["rtl_objects"] != 50 or result["gpu_and_drm_objects"] != 5:
    raise RuntimeError("missing i915, VBlank core/worker or RTL50 native objects")
print("DIAGNOSTIC_GENERATED_NATIVE_OBJECT_GRAPH_PASS",result)
PY
# Don't treat preprocessor/compilation faults as permission to install.
phase FULL_KERNEL_DIAGNOSTIC_COMPILE
"$NBMAKE" -C "$OUTPUT/obj" -j2 dependall >>"$LOG" 2>&1 || {
  phase FAILED_NATIVE_DEPENDALL_OR_LINK
  echo "DIAGNOSTIC_COMPILE_OR_LINK_FAILED: inspect $LOG" >&2
  exit 2
}
phase CHECK_PRIVATE_ELF_AND_SOURCE
"$PYTHON" -B - "$ROOT" "$OUTPUT" >>"$LOG" 2>&1 <<'PY'
import hashlib,json,pathlib,struct,sys
root,out=map(pathlib.Path,sys.argv[1:])
sys.path.insert(0,str(root/"tools"))
from verify_hp_combined_kernel import verify_link_map_owners
manifest=json.loads((out/"diagnostic-source-manifest.json").read_text())
if manifest["eligible_for_boot"] or manifest["eligible_for_install"] or not manifest["no_release_authorization"]:
    raise RuntimeError("diagnostic output was mislabeled as release")
for name, digest in manifest["source_sha256"].items():
    file=out/"source"/name
    if not file.is_file() or file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest()!=digest:
        raise RuntimeError("private source SHA mismatch: "+name)
elf=out/"obj/netbsd"
if not elf.is_file() or elf.is_symlink():
    raise RuntimeError("no private linked ELF")
with elf.open("rb") as f: header=f.read(64)
if len(header)<64 or header[:5]!=b"\x7fELF\x02" or header[5]!=1 or struct.unpack("<H",header[18:20])[0]!=62:
    raise RuntimeError("not amd64 ELF64 kernel")
linkmap=out/"obj/netbsd.map"
if not linkmap.is_file() or linkmap.is_symlink() or linkmap.stat().st_size<200:
    raise RuntimeError("final ELF map missing, diagnostic link not verified")
map_proof=verify_link_map_owners(
    linkmap.read_text(errors="replace"),
    manifest["rtl_native_units"], manifest["required_native_i915_sources"])
print("DIAGNOSTIC_FINAL_MAP_PROOF",map_proof)
print("DIAGNOSTIC_UNRELEASED_ELF_SHA256",hashlib.sha256(elf.read_bytes()).hexdigest())
PY
phase DIAGNOSTIC_KERNEL_LINKED_NOT_RELEASED_NOT_INSTALLED
echo "DIAGNOSTIC_KERNEL_LINKED_NOT_RELEASED_NOT_INSTALLED: $OUTPUT/obj/netbsd"
echo "Production release absent; physical KMS/WPA2 and recovery NOT VERIFIED."
