#!/bin/sh
# Combined HP-only NetBSD i915drmkms + RTL8723BE: full kernel, NEVER install.
set -eu
umask 077
export LC_ALL=C
ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
if [ "$#" -ne 3 ]; then
 echo "usage: sh $0 <i915-clean-git> <netbsd-source-root> <new-private-output>" >&2
 exit 2
fi
I915=$1
NETBSD=$2
OUTPUT=$3
PYTHON=$(command -v python3)
NBCONFIG=/usr/tools/bin/nbconfig
NBMAKE=/usr/tools/bin/nbmake-amd64

# Zero writes until i915-owning KMS approval + current HP/recovery pass.
[ "$(uname -s)" = NetBSD ] && [ "$(uname -m)" = amd64 ] || {
 echo "REFUSED: HP NetBSD11/amd64 kernel build only" >&2; exit 2; }
case "$(hostname)" in hp-tpnw121*) ;; *)
 echo "REFUSED: not HP TPN-W121" >&2; exit 2;; esac
[ "$(id -u)" -ne 0 ] || { echo "REFUSED: owner-only nonroot" >&2; exit 2; }
[ -x "$NBCONFIG" ] && [ -x "$NBMAKE" ] || {
 echo "REFUSED: HP native tools missing" >&2; exit 2; }
RTL_SHA=$(git -C "$ROOT" rev-parse HEAD)
I915_SHA=$(git -C "$I915" rev-parse HEAD)
[ -z "$(git -C "$ROOT" status --porcelain=v1)" ] &&
[ -z "$(git -C "$I915" status --porcelain=v1)" ] || {
 echo "REFUSED: dirty driver Git inputs" >&2; exit 2; }
"$PYTHON" -B "$ROOT/tools/check_i915_kernel_release.py" \
 --i915-repo "$I915" --rtl-head "$RTL_SHA" || {
 echo "WAIT_FOR_I915_RELEASE: no verified i915 KMS release" >&2; exit 2; }

# Recovery SHA, running boot identity and boot menu: all read-only.
RECOVERY=$(printenv HP_RECOVERY_KERNEL 2>/dev/null || :)
EXPECTED=$(printenv HP_RECOVERY_SHA256 2>/dev/null || :)
[ -n "$RECOVERY" ] && [ -n "$EXPECTED" ] &&
[ -r "$RECOVERY" ] && [ -r /netbsd ] && [ -r /boot.cfg ] || {
 echo "REFUSED: current HP kernel/boot/recovery not verified" >&2; exit 2; }
case "$EXPECTED" in *[!0-9a-f]*|"")
 echo "REFUSED: recovery digest not hex" >&2; exit 2;; esac
DIGESTLEN=$(printf %s "$EXPECTED" | wc -c | tr -d ' ')
[ "$DIGESTLEN" = 64 ] || {
 echo "REFUSED: recovery digest not SHA256" >&2; exit 2; }
ACTUAL=$("$PYTHON" -B -c \
 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' \
 "$RECOVERY")
[ "$ACTUAL" = "$EXPECTED" ] || {
 echo "REFUSED: recovered kernel SHA256 changed" >&2; exit 2; }
ACTIVE=$(sysctl -n machdep.booted_kernel 2>/dev/null) || {
 echo "REFUSED: current HP boot identity unavailable" >&2; exit 2; }
[ -n "$ACTIVE" ] || { echo "REFUSED: empty kernel identity" >&2; exit 2; }
case "$ACTIVE" in *F16.0*|*F83*|*F84*)
 echo "REFUSED: known bad kernel active" >&2; exit 2;; esac
case "$OUTPUT" in /*) ;; *)
 echo "REFUSED: output must be absolute and private" >&2; exit 2;; esac
[ ! -e "$OUTPUT" ] && [ ! -L "$OUTPUT" ] || {
 echo "REFUSED: cannot overwrite output" >&2; exit 2; }

# All 38 RTL source/native regressions plus combined Kconfig and final
# linker-map tests are mandatory. Never run the RTL-only builder itself.
"$PYTHON" -B "$ROOT/tools/run_hp_combined_preflight_tests.py" \
 --run --i915-repo "$I915" --netbsd-src "$NETBSD" || {
 echo "REFUSED: combined native/source regression gate failed" >&2; exit 2; }
# Revalidate the i915 owner decision after a potentially lengthy test run.
"$PYTHON" -B "$ROOT/tools/check_i915_kernel_release.py" \
 --i915-repo "$I915" --rtl-head "$RTL_SHA" || {
 echo "WAIT_FOR_I915_RELEASE: i915 authorization changed during preflight" >&2
 exit 2
}
# First permanent output mutation is a NEW private source/object snapshot.
"$PYTHON" -B "$ROOT/tools/configure_hp_combined_i915_rtl.py" \
 --rtl-repo "$ROOT" --i915-repo "$I915" \
 --netbsd-src "$NETBSD" --output "$OUTPUT" || exit 2
STATUS="$OUTPUT/combined-build-status.txt"
LOG="$OUTPUT/combined-build.log"
{
 printf 'phase=CONFIGURED_SOURCE_ONLY\n'
 printf 'rtl_sha=%s\ni915_sha=%s\n' "$RTL_SHA" "$I915_SHA"
 printf 'booted_kernel=%s\nrecovery_sha256=%s\n' "$ACTIVE" "$EXPECTED"
 printf 'installed=false\nbooted=false\n'
} > "$STATUS"

verify_inputs() {
 [ "$(git -C "$ROOT" rev-parse HEAD)" = "$RTL_SHA" ] &&
 [ "$(git -C "$I915" rev-parse HEAD)" = "$I915_SHA" ] &&
 [ -z "$(git -C "$ROOT" status --porcelain=v1)" ] &&
 [ -z "$(git -C "$I915" status --porcelain=v1)" ] &&
 "$PYTHON" -B "$ROOT/tools/check_i915_kernel_release.py" \
 --i915-repo "$I915" --rtl-head "$RTL_SHA"
}
verify_inputs || { echo "phase=REFUSED_RELEASE_OR_SOURCE_DRIFT" >> "$STATUS"; exit 2; }
CONFIG=$("$PYTHON" -B -c \
 'import json,sys; print(json.load(open(sys.argv[1]))["config"])' \
 "$OUTPUT/combined-source-manifest.json")
echo "phase=RUN_NBCONFIG" >> "$STATUS"
"$NBCONFIG" -s "$OUTPUT/source/sys" -b "$OUTPUT/obj" \
 "$OUTPUT/$CONFIG" > "$LOG" 2>&1 || {
 echo "phase=FAILED_NBCONFIG" >> "$STATUS"; exit 2; }
# Validate actual NetBSD bmake OBJS from the generated native Kconfig.
"$PYTHON" -B "$ROOT/tools/verify_hp_combined_kernel.py" \
 --output "$OUTPUT" --make "$NBMAKE" >> "$LOG" 2>&1 || {
 echo "phase=FAILED_NATIVE_OBJECT_GRAPH" >> "$STATUS"; exit 2; }
verify_inputs || { echo "phase=REFUSED_RELEASE_CHANGED" >> "$STATUS"; exit 2; }
echo "phase=FULL_KERNEL_DEPENDALL" >> "$STATUS"
# The sole build command, only HP; there is NO install or boot step.
"$NBMAKE" -C "$OUTPUT/obj" -j2 dependall >> "$LOG" 2>&1 || {
 echo "phase=FAILED_FULL_KERNEL_LINK" >> "$STATUS"; exit 2; }
"$PYTHON" -B "$ROOT/tools/verify_hp_combined_kernel.py" \
 --output "$OUTPUT" --make "$NBMAKE" --postlink >> "$LOG" 2>&1 || {
 echo "phase=FAILED_ELF_LINK_OR_OBJECT_PROOF" >> "$STATUS"; exit 2; }
echo "phase=COMBINED_KERNEL_LINKED_NO_INSTALL" >> "$STATUS"
echo "COMBINED_KERNEL_LINKED_NO_INSTALL: $OUTPUT/obj/netbsd"
echo "NOT installed, NOT booted; fallback kernel/default UNCHANGED."
