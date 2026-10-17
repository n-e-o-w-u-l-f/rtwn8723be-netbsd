#!/bin/sh
# Compile, link and identify the *next* RTL8723BE NetBSD 11 HP-only kernel.
# SAFE: no privileged actions, kernel install, firmware writes, radio tests,
# network changes, reboot, or modification of the verified F77 fallback.
set -eu
umask 077

if [ "$(uname -s)" != "NetBSD" ]; then
    echo "REFUSED: this candidate must be built on NetBSD" >&2
    exit 2
fi
case "$(uname -n)" in
    hp-tpnw121*) ;;
    *) echo "REFUSED: only the designated HP may build this candidate" >&2; exit 2 ;;
esac
if [ "$(id -u)" -eq 0 ]; then
    echo "REFUSED: build as unprivileged owner andreas, not root" >&2
    exit 2
fi
case "$(uname -v)" in
    *RTWN8723BE-F77-LINUX-EFUSE-MAP*) ;;
    *) echo "REFUSED: verify the safe F77 boot before another native candidate build" >&2; exit 2 ;;
esac

ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
WORK=$(dirname "$ROOT")
BRANCH=wip/hp-rtl-runtime-48-merge-20261010
GIT=$(command -v git)
PYTHON=/usr/pkg/bin/python3
test -x "$PYTHON" || { echo "REFUSED: HP python3 missing" >&2; exit 2; }
test -s "$WORK/rtl-kconfig-live-inc-20261011/obj/netbsd" || {
    echo "REFUSED: previously linked RTL50 base artifact not found" >&2
    exit 2
}
if [ "$("$GIT" -C "$ROOT" branch --show-current)" != "$BRANCH" ]; then
    echo "REFUSED: unexpected source branch" >&2
    exit 2
fi
if [ -n "$("$GIT" -C "$ROOT" status --porcelain=v1)" ]; then
    echo "REFUSED: source checkout has local/untracked modifications" >&2
    exit 2
fi
HEAD=$("$GIT" -C "$ROOT" rev-parse HEAD)
SHORT=$(printf '%s' "$HEAD" | cut -c1-12)
case "$SHORT" in
    *[!0-9a-f]*|"") echo "REFUSED: Git SHA invalid" >&2; exit 2 ;;
esac
# Must include the newer checked RX-filter patch and real lifetime fences.
grep -Fq 'R23BE_REG_RXFLTMAP0, 0xffff' "$ROOT/src/rtwn8723be_netbsd.c"
grep -Fq 'if (error != 0)' "$ROOT/src/rtwn8723be_runtime.c"
for testname in \
    test_irq_mutex_single_owner.py \
    test_hp_rtl50_source_snapshot_contract.py \
    test_hp_native_kernel_config_source.py \
    test_runtime_sw_owner_order.py \
    test_runtime_rf_publication_order.py \
    test_btc_byte_mask_linux_parity.py \
    test_net80211_mgmt_be_independent_source.py \
    test_net80211_fragment_slots_source.py \
    test_net80211_fragment_failclosed_source.py \
    test_tx_frame_prepare_source.py \
    test_tx_batch_source.py \
    test_datapath_batch_source.py \
    test_net80211_management_wake_source.py \
    test_hp_rtl50_panic_inventory_source.py \
    test_irq_shutdown_race_contract.py \
    test_net80211_deferred_start_source.py \
    test_net80211_rx_fcs_source.py \
    test_tx_descriptor_staging_source.py \
    test_net80211_unregister_sleep_ipl_source.py \
    test_linux_netbsd_driver_order_source.py \
    test_port_closure_inventory.py \
    test_btc_async_events_after_running.py \
    test_reserved_beacon_native_source.py \
    test_failed_probe_net80211_rollback.py \
    test_runtime_dma_reset_owner.py \
    test_runtime_start_shutdown_error_source.py \
    test_rf_calibration_pre_dm_source.py \
    test_calibration.py \
    test_calibration_native.py \
    test_full_runtime_callbacks_source.py \
    test_wip_reverse_owner_prestart.py \
    test_linux_lifecycle_stop.py \
    test_probe_unstarted_and_failed_shutdown_gates.py \
    test_rx_management_filter_native.py \
    test_wip_world_regdomain_glue.py
do
    "$PYTHON" -B "$ROOT/tests/$testname"
done

OUT="$WORK/rtl-kconfig-live-$SHORT"
if [ -e "$OUT" ] || [ -L "$OUT" ]; then
    echo "REFUSED: immutable owner output already exists: $OUT" >&2
    exit 2
fi
"$PYTHON" -B "$ROOT/tools/configure_hp_live_native_50.py" --output "$OUT"
test -s "$OUT/status.json"
"$PYTHON" -B "$ROOT/tools/verify_hp_rtl50_source_snapshot.py" \
    --output "$OUT" --source-commit "$HEAD"
echo "RUNNING source=$HEAD" >"$OUT/full-link.state"
# A failed post-link identity/snapshot check, a missing utility or an
# interrupted owner shell must not leave an indefinite false RUNNING token.
# A SIGKILL cannot be trapped: inspect the actual ps/log evidence in that
# exceptional case rather than inferring liveness from this status file.
trap 'rc=$?; if [ "$rc" -ne 0 ] && grep -q "^RUNNING " "$OUT/full-link.state" 2>/dev/null; then printf "FAILED_INCOMPLETE_EXIT:%s source=%s\\n" "$rc" "$HEAD" >"$OUT/full-link.state"; fi' 0
echo "HP_RTL50_NEXT_KERNEL_BUILD_START commit=$HEAD"
if "$OUT/nbmake-owner" -C "$OUT/obj" -j2 dependall >"$OUT/full-link.log" 2>&1; then
    :
else
    rc=$?
    echo "FAILED_BUILD:$rc source=$HEAD" >"$OUT/full-link.state"
    echo "HP_RTL50_NEXT_KERNEL_BUILD_FAILED exit=$rc log=$OUT/full-link.log" >&2
    grep -E 'error:|fatal error:|undefined reference|Failed target' "$OUT/full-link.log" | tail -n 15 >&2 || :
    exit "$rc"
fi

# The kernel must still consume the exact immutable source snapshot
# after the full dependall process; no live-worktree pointer is accepted.
if "$PYTHON" -B "$ROOT/tools/verify_hp_rtl50_source_snapshot.py" \
    --output "$OUT" --source-commit "$HEAD"; then
    :
else
    rc=$?
    echo "FAILED_SOURCE_SNAPSHOT:$rc source=$HEAD" >"$OUT/full-link.state"
    echo "REFUSED: owner C/H/INC snapshot changed during kernel link" >&2
    exit "$rc"
fi
EXPECTED="HP-RTL50-$SHORT-SAFE-GENFB"
if [ ! -s "$OUT/obj/netbsd" ] || ! /usr/bin/what "$OUT/obj/netbsd" | grep -F "$EXPECTED" >/dev/null; then
    echo "FAILED_IDENTITY source=$HEAD" >"$OUT/full-link.state"
    echo "REFUSED: linked ELF missing or source identity mismatch" >&2
    exit 1
fi
if [ "$("$GIT" -C "$ROOT" rev-parse HEAD)" != "$HEAD" ] || \
   [ -n "$("$GIT" -C "$ROOT" status --porcelain=v1)" ]; then
    echo "FAILED_SOURCE_CHANGED source=$HEAD" >"$OUT/full-link.state"
    echo "REFUSED: source changed while compiling; cannot certify artifact" >&2
    exit 1
fi
echo "LINKED source=$HEAD ident=$EXPECTED" >"$OUT/full-link.state"
echo "HP_RTL50_NEXT_KERNEL_LINK_PASS_NO_INSTALL"
echo "SOURCE=$HEAD"
echo "ARTIFACT=$OUT/obj/netbsd"
/usr/bin/file "$OUT/obj/netbsd"
/usr/bin/sha256 "$OUT/obj/netbsd"
/usr/bin/what "$OUT/obj/netbsd" | grep -F "$EXPECTED"
echo "SAFE_F77_PRESERVED=YES"
echo "HARDWARE_WIFI_AND_WPA2=NOT_TESTED"
