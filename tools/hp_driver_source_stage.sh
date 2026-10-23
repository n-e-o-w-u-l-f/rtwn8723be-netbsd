#!/bin/sh
# HP driver source reconciliation: audit, isolated GitHub stage, HP-native test.
# No existing worktree, /usr/src, /netbsd, boot.cfg or EFI changes.
set -eu
umask 077

fail() { printf 'HP_DRIVER_STAGE_BLOCKED: %s\n' "$*" >&2; exit 2; }
info() { printf 'HP_DRIVER_STAGE: %s\n' "$*"; }

mode=${1:---audit}
if [ "$#" -gt 0 ]; then shift; fi
case "$mode" in
    --audit|--stage|--native-test) ;;
    *) fail 'Usage: sh hp_driver_source_stage.sh --audit [CHECKOUT ...] | --stage | --native-test' ;;
esac

# The compiler, source stage and inventory are specifically owned by the HP.
[ "$(uname -s)" = "NetBSD" ] || fail 'NetBSD-only: no Arch/Debian/Windows substitute'
[ "$(uname -m)" = "amd64" ] || fail 'target must be amd64'
case "$(hostname)" in
    hp-tpnw121|hp-tpnw121.*) ;;
    *) fail 'host identity is not the verified hp-tpnw121; no action' ;;
esac
command -v git >/dev/null 2>&1 || fail 'git missing on HP'
[ -n "${HOME:-}" ] || fail 'HOME must be defined'
ROOT=${HP_DRIVER_STAGE_ROOT:-"$HOME/hp-driver-source-stage"}
case "$ROOT" in /*) ;; *) fail 'stage root must be absolute' ;; esac
[ ! -L "$ROOT" ] || fail 'stage root is a symlink'
[ ! -e "$ROOT" ] || [ -d "$ROOT" ] || fail 'stage root is not a directory'

I915_REPO='i915-cherryview-braswell-netbsd'
RTL_REPO='rtwn8723be-netbsd'
I915_BRANCH='work/hp-native-drm-stage-replay-20261015'
RTL_BRANCH='wip/hp-rtl-runtime-48-merge-20261010'
GITHUB_PREFIX='https://github.com/n-e-o-w-u-l-f'

remote_sha() {
    repo=$1 branch=$2
    ref="refs/heads/$branch"
    # Fail closed on missing, moved or malformed refs; never guess a branch.
    line=$(git ls-remote --exit-code "$GITHUB_PREFIX/$repo.git" "$ref") ||
        fail "GitHub ref unavailable: $repo $ref"
    set -- $line
    [ "$#" -eq 2 ] || fail "unexpected ls-remote output for $repo"
    [ "$2" = "$ref" ] || fail "ref mismatch for $repo"
    [ "${#1}" -eq 40 ] || fail "malformed 40-character Git SHA for $repo"
    case "$1" in *[!0123456789abcdef]*) fail "non-hex Git SHA for $repo";; esac
    printf '%s\n' "$1"
}

audit_checkout() {
    d=$1
    [ -d "$d" ] || return 0
    git -C "$d" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
    origin=$(git -C "$d" remote get-url origin 2>/dev/null || :)
    case "$origin" in
       *n-e-o-w-u-l-f/i915-cherryview-braswell-netbsd*)
           project=I915 expected=$I915_SHA ;;
       *n-e-o-w-u-l-f/rtwn8723be-netbsd*)
           project=RTL expected=$RTL_SHA ;;
       *) return 0 ;;
    esac
    current_branch=$(git -C "$d" symbolic-ref --quiet --short HEAD 2>/dev/null || printf DETACHED)
    current_head=$(git -C "$d" rev-parse --verify HEAD) || fail "invalid HEAD at $d"
    # Do not expose remote URL: it may contain an embedded credential.
    if [ -n "$(git -C "$d" status --porcelain=v1 --untracked-files=normal)" ]; then
        cleanliness=DIRTY_OR_UNTRACKED
    else
        cleanliness=CLEAN
    fi
    if [ "$current_head" = "$expected" ]; then
        relation=MATCH
    elif git -C "$d" cat-file -e "$expected^{commit}" 2>/dev/null; then
        if git -C "$d" merge-base --is-ancestor "$current_head" "$expected"; then
            relation=REMOTE_AHEAD
        elif git -C "$d" merge-base --is-ancestor "$expected" "$current_head"; then
            relation=LOCAL_AHEAD
        else
            relation=DIVERGED
        fi
    else
        relation=ANCESTRY_UNKNOWN_REMOTE_OBJECT_NOT_FETCHED
    fi
    info "LOCAL_REPO=$d PROJECT=$project BRANCH=$current_branch HEAD=$current_head STATE=$cleanliness GITHUB_HEAD=$expected RELATION=$relation"
    info 'Audit does not fetch or alter refs; unknown ancestry requires reviewed fetch later'
}

audit_known() {
    info "HOST=$(hostname) OS=$(uname -srm) STAGE_ROOT=$ROOT"
    audit_checkout "$ROOT/i915"
    audit_checkout "$ROOT/rtl"
    # Bounded two-level candidate discovery under known developer homes only.
    # This is not an all-filesystem scan; callers may supply extra paths.
    for d in /root/* /root/*/* /home/andreas/* /home/andreas/*/*; do
        [ -e "$d/.git" ] || continue
        audit_checkout "$d"
    done
}

stage_one() {
    repo=$1 branch=$2 dest=$3 expected=$4
    [ ! -e "$dest" ] && [ ! -L "$dest" ] ||
        fail "destination already exists; inspect with --audit, do not overwrite: $dest"
    info "CLONE_START repo=$repo branch=$branch expected=$expected"
    git clone --verbose --no-tags --single-branch --branch "$branch" \
        "$GITHUB_PREFIX/$repo.git" "$dest" ||
        fail "clone failed; preserve any partial directory for manual inspection: $dest"
    actual=$(git -C "$dest" rev-parse --verify HEAD) ||
        fail "no staged HEAD at $dest"
    [ "$actual" = "$expected" ] ||
        fail "remote moved during clone; staged $actual expected $expected (no rewrite)"
    [ -z "$(git -C "$dest" status --porcelain=v1)" ] ||
        fail "new checkout unexpectedly dirty: $dest"
    info "STAGED repo=$repo branch=$branch verified_head=$actual"
}

case "$mode" in
    --audit)
        I915_SHA=$(remote_sha "$I915_REPO" "$I915_BRANCH")
        RTL_SHA=$(remote_sha "$RTL_REPO" "$RTL_BRANCH")
        info "GITHUB_I915_HEAD=$I915_SHA BRANCH=$I915_BRANCH"
        info "GITHUB_RTL_HEAD=$RTL_SHA BRANCH=$RTL_BRANCH"
        audit_known
        for extra in "$@"; do audit_checkout "$extra"; done
        info 'AUDIT_ONLY; no fetch, pull, merge, kernel build or host deployment'
        ;;
    --stage)
        [ "$#" -eq 0 ] || fail '--stage accepts no extra paths'
        I915_SHA=$(remote_sha "$I915_REPO" "$I915_BRANCH")
        RTL_SHA=$(remote_sha "$RTL_REPO" "$RTL_BRANCH")
        audit_known
        [ ! -e "$ROOT/i915" ] && [ ! -L "$ROOT/i915" ] ||
            fail 'existing i915 stage; review it first'
        [ ! -e "$ROOT/rtl" ] && [ ! -L "$ROOT/rtl" ] ||
            fail 'existing RTL stage; review it first'
        mkdir -p "$ROOT"
        stage_one "$I915_REPO" "$I915_BRANCH" "$ROOT/i915" "$I915_SHA"
        stage_one "$RTL_REPO" "$RTL_BRANCH" "$ROOT/rtl" "$RTL_SHA"
        info 'SOURCE_STAGED; old HP worktrees, /usr/src and boot configuration untouched'
        info "NEXT: sh $0 --native-test (on HP only; userland DMA fixture)"
        ;;
    --native-test)
        [ "$#" -eq 0 ] || fail '--native-test accepts no extra paths'
        d="$ROOT/rtl"
        [ -d "$d/.git" ] || fail 'RTL stage absent; perform --stage first'
        branch=$(git -C "$d" symbolic-ref --quiet --short HEAD 2>/dev/null || :)
        [ "$branch" = "$RTL_BRANCH" ] || fail "unexpected RTL branch: $branch"
        head=$(git -C "$d" rev-parse --verify HEAD)
        expected=$(remote_sha "$RTL_REPO" "$RTL_BRANCH")
        [ "$head" = "$expected" ] || fail 'RTL stage is stale/divergent; preserve; do not auto-merge'
        [ -z "$(git -C "$d" status --porcelain=v1)" ] ||
            fail 'RTL stage has local changes; preserve; no automatic execution'
        [ -f "$d/tests/test_dma_alloc_rejection_c11.py" ] ||
            fail 'native test missing in staged checkout'
        command -v python3 >/dev/null 2>&1 || fail 'python3 missing on HP'
        command -v cc >/dev/null 2>&1 || fail 'C compiler missing on HP'
        logfile=$(mktemp "$ROOT/rtl-native-test.XXXXXXXX") ||
            fail 'cannot allocate persistent native test log'
        info "NATIVE_LOG=$logfile"
        set +e
        (cd "$d" && python3 tests/test_dma_alloc_rejection_c11.py --source-only --self-test &&
            python3 tests/test_dma_alloc_rejection_c11.py) >"$logfile" 2>&1
        rc=$?
        set -e
        cat "$logfile"
        [ "$rc" -eq 0 ] || fail "HP C11+UBSan test exit=$rc; preserve $logfile"
        info "HP_NATIVE_FIXTURE_PASS; log=$logfile; KERNEL_BUILD=NOT_RUN; WLAN=NOT_RUN"
        ;;
esac
