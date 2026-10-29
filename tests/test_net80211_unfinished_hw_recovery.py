#!/usr/bin/env python3
"""Prove source-shared NetBSD recovery quarantine for all Linux hardware stages.

This does NOT run hardware STOP. It ensures net80211 cannot treat an
interrupted STOPPING, partial firmware init, or stale MAC flags as a
successful clean DOWN/media/ENETRESET. These need a separate journalled,
sleepable recovery owner instead of an unsafe generic RUNNING hw_stop.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
H = (ROOT / "src/rtwn8723be_net80211_state.h").read_text()
NET = (ROOT / "src/rtwn8723be_net80211.c").read_text()
name = "rtwn8723be_net80211_hw_recovery_required"
assert H.count(name + "(") == 1
tail = name + "(" + H.split(name + "(", 1)[1]
depth = 0
for i in range(tail.index("{"), len(tail)):
    if tail[i] == "{":
        depth += 1
    elif tail[i] == "}":
        depth -= 1
        if depth == 0:
            source = tail[:i + 1]
            break
else:
    raise AssertionError("unbalanced real recovery helper")

def contract(body: str) -> None:
    checks = (
        "if (state == NULL)", "return true;",
        "state->started", "state->fw_ready",
        "state->mac_func_enable", "state->being_init_adapter",
        "state->stage > R23BE_STAGE_PROBED",
        "state->stage != R23BE_STAGE_STOPPED",
    )
    for x in checks:
        assert x in body, x
    assert body.index("if (state == NULL)") < body.index("state->started")
    assert body.index("state->stage > R23BE_STAGE_PROBED") < body.index(
        "state->stage != R23BE_STAGE_STOPPED")
    assert NET.count(name + "(") == 4
    assert NET.count("rtwn8723be_net80211_running_hw_stop_needed(") == 1

contract(source)
mutants = (
    source.replace("if (state == NULL)", "if (false)", 1),
    source.replace("state->started ||", "false ||", 1),
    source.replace("state->fw_ready ||", "false ||", 1),
    source.replace("state->mac_func_enable ||", "false ||", 1),
    source.replace("state->being_init_adapter ||", "false ||", 1),
    source.replace("state->stage > R23BE_STAGE_PROBED", "false", 1),
    source.replace("state->stage != R23BE_STAGE_STOPPED", "false", 1),
)
for i, mutant in enumerate(mutants, 1):
    assert mutant != source, i
    try:
        contract(mutant)
    except (ValueError, AssertionError):
        continue
    raise AssertionError(f"unsafe cleanup-source mutation accepted: {i}")

harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include "rtwn8723be_net80211_state.h"

static void clean(enum rtwn8723be_linux_stage stage)
{
    struct rtwn8723be_linux_state state = {0};
    state.stage = stage;
    assert(!rtwn8723be_net80211_hw_recovery_required(&state));
}
static void dirty_flag(enum rtwn8723be_linux_stage stage, int mode)
{
    struct rtwn8723be_linux_state state = {0};
    state.stage = stage;
    if (mode == 1) state.started = true;
    else if (mode == 2) state.fw_ready = true;
    else if (mode == 3) state.mac_func_enable = true;
    else if (mode == 4) state.being_init_adapter = true;
    else assert(false);
    assert(rtwn8723be_net80211_hw_recovery_required(&state));
}
int main(void)
{
    assert(rtwn8723be_net80211_hw_recovery_required(NULL));
    clean(R23BE_STAGE_IDLE);
    clean(R23BE_STAGE_IEEE80211_REGISTER);
    clean(R23BE_STAGE_RFKILL);
    clean(R23BE_STAGE_IRQ_ESTABLISH);
    clean(R23BE_STAGE_PROBED);
    clean(R23BE_STAGE_STOPPED);
    struct rtwn8723be_linux_state state = {0};
    state.stage = R23BE_STAGE_FIRMWARE_DOWNLOAD;
    assert(rtwn8723be_net80211_hw_recovery_required(&state));
    state.stage = R23BE_STAGE_RUNNING;
    assert(rtwn8723be_net80211_hw_recovery_required(&state));
    state.stage = R23BE_STAGE_STOPPING;
    assert(rtwn8723be_net80211_hw_recovery_required(&state));
    for (int mode = 1; mode <= 4; mode++) {
        dirty_flag(R23BE_STAGE_PROBED, mode);
        dirty_flag(R23BE_STAGE_STOPPED, mode);
    }
    puts("RTL_UNFINISHED_STOPPING_FIRMWARE_QUARANTINE_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-hw-cleanup-quarantine-") as td:
    file = Path(td) / "test.c"
    exe = Path(td) / "test"
    file.write_text(harness)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all", "-I",
                    str(ROOT / "src"), str(file), "-o", str(exe)],
                   check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_UNFINISHED_HW_RECOVERY_MUTATIONS_OK negatives=7")
