#!/usr/bin/env python3
"""Execute the actual native datapath start and TX-completion callbacks.

Inject STOPPING and owner loss AT mutex acquisition, after the former
unlocked admission check would have passed. The C11/UBSan harness also
ensures stopped or failed TX reclaim never wakes net80211. No NetBSD
softint/detach concurrency or actual DMA test is implied.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DP = (ROOT / "src/rtwn8723be_datapath.c").read_text()

def source_body(name: str, result_type: str) -> str:
    anchor = "\n" + name + "("
    assert DP.count(anchor) == 1, name
    fragment = name + "(" + DP.split(anchor, 1)[1]
    start, level = fragment.index("{"), 0
    for i in range(start, len(fragment)):
        if fragment[i] == "{":
            level += 1
        elif fragment[i] == "}":
            level -= 1
            if level == 0:
                return result_type + "\n" + fragment[:i+1]
    raise AssertionError("unbalanced " + name)

start = source_body("rtwn8723be_datapath_start", "int")
done = source_body("rtwn8723be_dp_tx_done", "static void")

def contract(start_body: str, done_body: str) -> None:
    lock = "mutex_enter(&dp->tx_lock);"
    unlock = "mutex_exit(&dp->tx_lock);"
    owner = "if (sc->sc_datapath != dp || sc->sc_irq_arg != dp)"
    state = "sc->sc_linux.stage != R23BE_STAGE_RUNNING"
    enable = "dp->tx_enabled = true;"
    assert start_body.index(lock) < start_body.index(owner)
    assert start_body.index(lock) < start_body.index(state)
    assert start_body.index(state) < start_body.index(enable)
    assert start_body.index(enable) < start_body.index(unlock)
    assert "return error;" in start_body

    entry = "if (!dp->tx_enabled || dp->sc == NULL ||"
    stop_stage = "dp->sc->sc_linux.stage != R23BE_STAGE_RUNNING"
    reclaim = "error = rtwn8723be_tx_native_reclaim("
    notify_capture = "if (error == 0 && reclaimed != 0 && dp->tx_complete != NULL)"
    callback = "notify(notify_arg, qid, reclaimed);"
    assert done_body.index(lock) < done_body.index(entry)
    for token in (
        "dp->sc->sc_datapath != dp", "dp->sc->sc_irq_arg != dp",
        "!dp->sc->sc_linux.started", "!dp->sc->sc_linux.fw_ready",
        stop_stage,
    ):
        assert token in done_body[done_body.index(entry):done_body.index(reclaim)]
    assert done_body.index(reclaim) < done_body.index(notify_capture)
    publish = done_body.index("dp->tx_callback_active++;")
    first_release = done_body.index(unlock, publish)
    assert done_body.index(notify_capture) < publish < first_release
    assert first_release < done_body.index(callback)
    assert done_body.index(callback) < done_body.index("dp->tx_callback_active--;")
    assert done_body.index("dp->tx_callback_active--;") < done_body.rindex(unlock)
    assert "if (notify != NULL)" in done_body

contract(start, done)

controls = (
    (start.replace("mutex_enter(&dp->tx_lock);\n    if (sc->sc_datapath",
                   "if (sc->sc_datapath", 1), done),
    (start.replace("sc->sc_linux.stage != R23BE_STAGE_RUNNING",
                   "false", 1), done),
    (start.replace("sc->sc_datapath != dp", "false", 1), done),
    (start.replace("sc->sc_irq_arg != dp", "false", 1), done),
    (done.replace("dp->sc->sc_linux.stage != R23BE_STAGE_RUNNING",
                  "false", 1), start),
    (done.replace("dp->sc->sc_datapath != dp", "false", 1), start),
    (done.replace("dp->sc->sc_irq_arg != dp", "false", 1), start),
    (done.replace("if (error == 0 && reclaimed != 0 && dp->tx_complete != NULL)",
                  "if (reclaimed != 0 && dp->tx_complete != NULL)", 1), start),
    (done.replace("if (notify != NULL) {\n        notify(",
                  "if (true) {\n        notify(", 1), start),
)
for i, (changed_a, changed_b) in enumerate(controls, 1):
    # the last seven controls target done; first four target start
    changed_start, changed_done = (changed_a, changed_b) if i <= 4 else (
        changed_b, changed_a)
    assert changed_start != start or changed_done != done, i
    try:
        contract(changed_start, changed_done)
    except (AssertionError, ValueError):
        continue
    raise AssertionError(f"unsafe TX completion mutation {i} accepted")

pre = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#include <errno.h>

#define R23BE_STAGE_RUNNING 43
#define R23BE_STAGE_STOPPING 44
#define RTWN8723BE_TX_QUEUE_COUNT 9
struct rtwn8723be_datapath;
struct rtwn8723be_softc {
    struct rtwn8723be_datapath *sc_datapath;
    void *sc_irq_arg, *sc_ih;
    struct { int stage; bool started, fw_ready; } sc_linux;
    bool sc_irq_dispatch_ready, sc_mapped, sc_rings_allocated;
};
#define KASSERT assert
typedef struct { bool held; } kmutex_t;
struct rtwn8723be_datapath {
    struct rtwn8723be_softc *sc;
    kmutex_t tx_lock;
    bool prepared, tx_enabled;
    unsigned int tx_callback_active;
    int rx_error, tx_error;
    uint64_t rx_delivered, tx_reclaimed;
    void (*tx_complete)(void *, unsigned int, size_t);
    void *tx_complete_arg;
};
static struct rtwn8723be_softc *active_sc;
static int inject_on_lock, enter_count, exit_count;
static void mutex_enter(kmutex_t *m)
{
    assert(m != NULL && !m->held);
    m->held = true;
    enter_count++;
    if (inject_on_lock == 1)
        active_sc->sc_linux.stage = R23BE_STAGE_STOPPING;
    if (inject_on_lock == 2)
        active_sc->sc_datapath = NULL;
    if (inject_on_lock == 3)
        active_sc->sc_irq_arg = NULL;
    inject_on_lock = 0;
}
static void mutex_exit(kmutex_t *m)
{ assert(m != NULL && m->held); m->held=false; exit_count++; }

static int reclaim_calls, reclaim_error, reclaim_count;
static int rtwn8723be_tx_native_reclaim(struct rtwn8723be_softc *sc,
    unsigned int qid, size_t *reclaimed)
{
    assert(sc && sc->sc_datapath && qid == 2);
    assert(sc->sc_datapath->tx_lock.held);
    reclaim_calls++;
    *reclaimed = (size_t)reclaim_count;
    return reclaim_error;
}
static int notify_calls;
static unsigned int last_qid;
static size_t last_reclaimed;
static void notify(void *arg, unsigned int qid, size_t reclaimed)
{
    struct rtwn8723be_datapath *dp = arg;
    assert(dp && !dp->tx_lock.held);
    assert(dp->tx_callback_active == 1);
    notify_calls++;
    last_qid = qid;
    last_reclaimed = reclaimed;
}
'''
post = r'''
static void reset(struct rtwn8723be_softc *sc,
    struct rtwn8723be_datapath *dp)
{
    *sc = (struct rtwn8723be_softc){0};
    *dp = (struct rtwn8723be_datapath){0};
    dp->sc = sc;
    dp->prepared = true;
    dp->tx_complete = notify;
    dp->tx_complete_arg = dp;
    sc->sc_datapath = dp;
    sc->sc_irq_arg = dp;
    sc->sc_linux.started = true;
    sc->sc_linux.fw_ready = true;
    sc->sc_linux.stage = R23BE_STAGE_RUNNING;
    sc->sc_irq_dispatch_ready = true;
    sc->sc_ih = sc;
    sc->sc_mapped = sc->sc_rings_allocated = true;
    active_sc = sc;
    reclaim_calls = reclaim_error = notify_calls = 0;
    reclaim_count = 2;
    enter_count = exit_count = 0;
    inject_on_lock = 0;
}
static void balanced(struct rtwn8723be_datapath *dp)
{ assert(!dp->tx_lock.held && enter_count == exit_count); }

int main(void)
{
    struct rtwn8723be_softc sc={0};
    struct rtwn8723be_datapath dp={0};

    /* This catches the actual stale-before-lock admission bug. */
    reset(&sc, &dp);
    inject_on_lock = 1;
    assert(rtwn8723be_datapath_start(&dp) == EAGAIN);
    assert(!dp.tx_enabled && sc.sc_linux.stage == R23BE_STAGE_STOPPING);
    balanced(&dp);

    reset(&sc, &dp);
    inject_on_lock = 2;
    assert(rtwn8723be_datapath_start(&dp) == EBUSY);
    assert(!dp.tx_enabled);
    balanced(&dp);

    reset(&sc, &dp);
    inject_on_lock = 3;
    assert(rtwn8723be_datapath_start(&dp) == EBUSY);
    assert(!dp.tx_enabled);
    balanced(&dp);

    reset(&sc, &dp);
    assert(rtwn8723be_datapath_start(&dp) == 0 && dp.tx_enabled);
    balanced(&dp);

    rtwn8723be_dp_tx_done(&dp, RTWN8723BE_TX_QUEUE_COUNT);
    assert(reclaim_calls == 0 && notify_calls == 0);

    rtwn8723be_dp_tx_done(&dp, 2);
    assert(reclaim_calls == 1 && notify_calls == 1);
    assert(last_qid == 2 && last_reclaimed == 2);
    assert(dp.tx_callback_active == 0);
    assert(dp.tx_reclaimed == 2);
    balanced(&dp);

    /* Success with zero reclaimed must not wake net80211. */
    reclaim_count = 0;
    rtwn8723be_dp_tx_done(&dp, 2);
    assert(reclaim_calls == 2 && notify_calls == 1);
    balanced(&dp);

    /* Partial reclaim with an error retains recoverable ownership. */
    reclaim_count = 1; reclaim_error = EIO;
    rtwn8723be_dp_tx_done(&dp, 2);
    assert(reclaim_calls == 3 && notify_calls == 1);
    assert(dp.tx_error == EIO && dp.tx_reclaimed == 3);
    balanced(&dp);

    /* Late softint must not touch ring or net80211 in STOPPING. */
    sc.sc_linux.stage = R23BE_STAGE_STOPPING;
    rtwn8723be_dp_tx_done(&dp, 2);
    assert(reclaim_calls == 3 && notify_calls == 1);
    balanced(&dp);

    /* Runtime STOP previously disabled tx_enabled without draining IRQ. */
    sc.sc_linux.stage = R23BE_STAGE_RUNNING;
    dp.tx_enabled = false;
    rtwn8723be_dp_tx_done(&dp, 2);
    assert(reclaim_calls == 3 && notify_calls == 1);

    dp.tx_enabled = true;
    sc.sc_datapath = NULL;
    rtwn8723be_dp_tx_done(&dp, 2);
    assert(reclaim_calls == 3 && notify_calls == 1);
    sc.sc_datapath = &dp;
    sc.sc_irq_arg = NULL;
    rtwn8723be_dp_tx_done(&dp, 2);
    assert(reclaim_calls == 3 && notify_calls == 1);
    sc.sc_irq_arg = &dp;

    sc.sc_linux.fw_ready = false;
    rtwn8723be_dp_tx_done(&dp, 2);
    assert(reclaim_calls == 3 && notify_calls == 1);
    sc.sc_linux.fw_ready = true;
    sc.sc_linux.started = false;
    rtwn8723be_dp_tx_done(&dp, 2);
    assert(reclaim_calls == 3 && notify_calls == 1);
    balanced(&dp);

    /* Also check late transition at lock acquisition itself. */
    reset(&sc, &dp);
    dp.tx_enabled = true;
    inject_on_lock = 1;
    rtwn8723be_dp_tx_done(&dp, 2);
    assert(reclaim_calls == 0 && notify_calls == 0);
    balanced(&dp);

    puts("RTL_DATAPATH_TX_START_COMPLETION_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-tx-complete-") as td:
    c = Path(td) / "test.c"
    exe = Path(td) / "test"
    c.write_text(pre + "\n" + start + "\n" + done + "\n" + post)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        str(c), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_DATAPATH_TX_COMPLETION_SOURCE_NEGATIVES_OK negatives=9")
