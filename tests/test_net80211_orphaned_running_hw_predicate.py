#!/usr/bin/env python3
"""Exercise real Linux RUNNING-owner predicate independently of ifnet flags.

Portable C11/UBSan verifies the source-shared net80211 state helper: only
a genuinely started RUNNING hardware owner can be retried via normal
hw_stop; STOPPING and partially failed firmware startup must never be
misclassified as safe RUNNING reentry.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "src/rtwn8723be_net80211_state.h").read_text()
NET = (ROOT / "src/rtwn8723be_net80211.c").read_text()

NAME = "rtwn8723be_net80211_running_hw_stop_needed"
assert HEADER.count(NAME + "(") == 1
fragment = NAME + "(" + HEADER.split(NAME + "(", 1)[1]
start = fragment.index("{")
depth = 0
for i in range(start, len(fragment)):
    if fragment[i] == "{":
        depth += 1
    elif fragment[i] == "}":
        depth -= 1
        if depth == 0:
            body = fragment[:i + 1]
            break
else:
    raise AssertionError("missing real RUNNING predicate body")
assert "state != NULL && state->started &&" in body
assert "state->stage == R23BE_STAGE_RUNNING" in body

for token in (
    "rtwn8723be_net80211_running_hw_stop_needed(",
    "&n->sc->sc_linux",
):
    assert token in NET
# Only the explicit DOWN-to-hardware-STOP admission uses the narrow
# RUNNING predicate. All media/reset paths use the broader quarantine.
assert NET.count("rtwn8723be_net80211_running_hw_stop_needed(") == 1
assert NET.count("rtwn8723be_net80211_hw_recovery_required(") == 4

mutants = (
    body.replace("state != NULL &&", "true &&", 1),
    body.replace("state->started &&", "true &&", 1),
    body.replace("state->stage == R23BE_STAGE_RUNNING",
                 "state->stage != R23BE_STAGE_RUNNING", 1),
    body.replace("state->stage == R23BE_STAGE_RUNNING",
                 "true", 1),
)
for i, mutant in enumerate(mutants, 1):
    assert mutant != body, i
    try:
        assert "state != NULL && state->started &&" in mutant
        assert "state->stage == R23BE_STAGE_RUNNING" in mutant
    except AssertionError:
        continue
    raise AssertionError(f"unsafe running hardware source mutant {i} accepted")

harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include "rtwn8723be_net80211_state.h"

int main(void)
{
    struct rtwn8723be_linux_state s = {0};
    assert(!rtwn8723be_net80211_running_hw_stop_needed(NULL));
    s.stage = R23BE_STAGE_PROBED;
    assert(!rtwn8723be_net80211_running_hw_stop_needed(&s));
    s.stage = R23BE_STAGE_STOPPED;
    assert(!rtwn8723be_net80211_running_hw_stop_needed(&s));
    s.stage = R23BE_STAGE_RUNNING;
    assert(!rtwn8723be_net80211_running_hw_stop_needed(&s));
    s.started = true;
    assert(rtwn8723be_net80211_running_hw_stop_needed(&s));
    s.stage = R23BE_STAGE_STOPPING;
    assert(!rtwn8723be_net80211_running_hw_stop_needed(&s));
    s.stage = R23BE_STAGE_FIRMWARE_DOWNLOAD;
    assert(!rtwn8723be_net80211_running_hw_stop_needed(&s));
    s.stage = R23BE_STAGE_STOPPED;
    assert(!rtwn8723be_net80211_running_hw_stop_needed(&s));
    s.started = false;
    s.stage = R23BE_STAGE_RUNNING;
    s.fw_ready = true;
    assert(!rtwn8723be_net80211_running_hw_stop_needed(&s));
    puts("RTL_ORPHANED_RUNNING_HW_PREDICATE_C11_UBSAN_OK");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="r23be-orphan-hw-owner-") as td:
    src = Path(td) / "test.c"
    exe = Path(td) / "test"
    src.write_text(harness)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-pedantic", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all",
                    "-I", str(ROOT / "src"), str(src), "-o", str(exe)],
                   check=True)
    subprocess.run([str(exe)], check=True)
print("RTL_ORPHANED_RUNNING_HW_SOURCE_MUTATIONS_OK negatives=4")
