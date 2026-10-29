#!/usr/bin/env python3
"""Execute the portable RTL8723BE world-regdomain policy.

This test is intentionally host-only.  It verifies the policy decision that
the future NetBSD net80211 glue consumes; it neither builds a kernel nor
touches hardware.
"""
from pathlib import Path
import os
import subprocess
import tempfile


ROOT = Path(os.environ.get("R23BE_ROOT", Path(__file__).resolve().parents[1]))
HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include "rtwn8723be_regdomain.h"

int
main(void)
{
    enum rtwn8723be_regdomain_channel_mode mode;

    mode = R23BE_REGDOMAIN_PASSIVE_CCK_ONLY;
    assert(rtwn8723be_regdomain_world_channel_mode(1, &mode) == 0);
    assert(mode == R23BE_REGDOMAIN_ACTIVE_CCK_OFDM);
    assert(rtwn8723be_regdomain_world_channel_mode(11, &mode) == 0);
    assert(mode == R23BE_REGDOMAIN_ACTIVE_CCK_OFDM);

    assert(rtwn8723be_regdomain_world_channel_mode(12, &mode) == 0);
    assert(mode == R23BE_REGDOMAIN_PASSIVE_CCK_OFDM);
    assert(rtwn8723be_regdomain_world_channel_mode(13, &mode) == 0);
    assert(mode == R23BE_REGDOMAIN_PASSIVE_CCK_OFDM);

    assert(rtwn8723be_regdomain_world_channel_mode(14, &mode) == 0);
    assert(mode == R23BE_REGDOMAIN_PASSIVE_CCK_ONLY);

    mode = R23BE_REGDOMAIN_ACTIVE_CCK_OFDM;
    assert(rtwn8723be_regdomain_world_channel_mode(0, &mode) == EINVAL);
    assert(mode == R23BE_REGDOMAIN_ACTIVE_CCK_OFDM);
    assert(rtwn8723be_regdomain_world_channel_mode(15, &mode) == EINVAL);
    assert(mode == R23BE_REGDOMAIN_ACTIVE_CCK_OFDM);
    assert(rtwn8723be_regdomain_world_channel_mode(1, NULL) == EINVAL);

    puts("RTL_REGDOMAIN_WORLD_BASELINE_C11_OK");
    return 0;
}
"""


with tempfile.TemporaryDirectory(prefix=".r23be-regdomain-") as name:
    directory = Path(name)
    source = directory / "test.c"
    binary = directory / "test"
    source.write_text(HARNESS)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=undefined", "-fno-sanitize-recover=all",
         "-I", str(ROOT / "src"),
         str(ROOT / "src" / "rtwn8723be_regdomain.c"),
         str(source), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
