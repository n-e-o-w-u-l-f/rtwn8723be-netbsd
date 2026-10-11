#!/usr/bin/env python3
"""A registered but unstarted interface must admit probe rollback only."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(os.environ.get("R23BE_ROOT", Path(__file__).resolve().parents[1]))
SOURCE = (ROOT / "src" / "rtwn8723be_net80211.c").read_text()


def function(src: str, name: str) -> str:
    marker = "\n" + name + "(struct rtwn8723be_net80211 *n)\n{"
    begin = src.index(marker)
    return src[begin:src.index("\n}\n", begin) + 3]


stop = function(SOURCE, "rtwn8723be_n80211_ifstop")
assert "rtwn8723be_net80211_unstarted_detach_allowed(" in stop, (
    "ifstop does not use the bounded unstarted rollback admission policy")

HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include "rtwn8723be_net80211_state.h"

static void
allowed(enum rtwn8723be_linux_stage stage)
{
    struct rtwn8723be_linux_state state = {0};

    state.stage = stage;
    assert(rtwn8723be_net80211_unstarted_detach_allowed(&state));
}

static void
blocked(enum rtwn8723be_linux_stage stage)
{
    struct rtwn8723be_linux_state state = {0};

    state.stage = stage;
    assert(!rtwn8723be_net80211_unstarted_detach_allowed(&state));
}

int
main(void)
{
    struct rtwn8723be_linux_state state = {0};

    allowed(R23BE_STAGE_IEEE80211_REGISTER);
    allowed(R23BE_STAGE_RFKILL);
    allowed(R23BE_STAGE_IRQ_ESTABLISH);
    allowed(R23BE_STAGE_PROBED);
    allowed(R23BE_STAGE_STOPPED);

    blocked(R23BE_STAGE_IDLE);
    blocked(R23BE_STAGE_PCI_RINGS);
    blocked(R23BE_STAGE_RESET_RINGS);
    blocked(R23BE_STAGE_RUNNING);
    blocked(R23BE_STAGE_STOPPING);

    state.stage = R23BE_STAGE_PROBED;
    state.started = true;
    assert(!rtwn8723be_net80211_unstarted_detach_allowed(&state));
    assert(!rtwn8723be_net80211_unstarted_detach_allowed(NULL));
    puts("RTL_NET80211_UNSTARTED_ROLLBACK_C11_OK");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix="rtl-net80211-rollback-") as name:
    directory = Path(name)
    source = directory / "test.c"
    binary = directory / "test"
    source.write_text(HARNESS)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-I", str(ROOT / "src"), str(source), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
