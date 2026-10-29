#!/usr/bin/env python3
"""Compile real portable RF channel-snapshot C with strict host C11/UBSan.

The serial bus protocol is covered separately by test_rf_serial.py.
No NetBSD bus_space, RF lock, firmware, or HP hardware is simulated here.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/rtwn8723be_rf_channel_state.c"
INCLUDE = ROOT / "src"
C = r"""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include "rtwn8723be_rf_channel_state.h"

static int calls, fail_at;
static unsigned int seen_path[2];
static uint32_t seen_reg[2];
static uint32_t response[2] = {0xfffffU, 0x54321U};

int
rtwn8723be_rf_serial_read(const struct rtwn8723be_rf_serial_ctx *ctx,
    unsigned int path, uint32_t reg, uint32_t *value)
{
    if (ctx->io == NULL)
        return ENXIO;
    assert(calls < 2 && value != NULL);
    seen_path[calls] = path;
    seen_reg[calls] = reg;
    calls++;
    if (calls == fail_at)
        return EIO;
    *value = response[path];
    return 0;
}

int main(void)
{
    const struct rtwn8723be_rf_serial_io io = {0};
    const struct rtwn8723be_rf_serial_ctx ctx = {&io, NULL};
    const struct rtwn8723be_rf_serial_ctx no_io = {NULL, NULL};
    uint32_t values[2] = {0x12345678U, 0x87654321U};

    assert(rtwn8723be_rf_channel_state_read(NULL, values) == EINVAL);
    assert(rtwn8723be_rf_channel_state_read(&ctx, NULL) == EINVAL);
    assert(rtwn8723be_rf_channel_state_read(&no_io, values) == ENXIO);
    assert(calls == 0 && values[0] == 0x12345678U);

    assert(rtwn8723be_rf_channel_state_read(&ctx, values) == 0);
    assert(calls == 2);
    assert(seen_path[0] == RTWN8723BE_RF_PATH_A &&
           seen_path[1] == RTWN8723BE_RF_PATH_B);
    assert(seen_reg[0] == 0x18U && seen_reg[1] == 0x18U);
    assert(values[0] == 0xf0fffU && values[1] == 0x54321U);

    calls = 0;
    fail_at = 1;
    assert(rtwn8723be_rf_channel_state_read(&ctx, values) == EIO);
    assert(calls == 1 && values[0] == 0xf0fffU &&
           values[1] == 0x54321U);

    calls = 0;
    fail_at = 2;
    assert(rtwn8723be_rf_channel_state_read(&ctx, values) == EIO);
    assert(calls == 2 && values[0] == 0xf0fffU &&
           values[1] == 0x54321U);

    calls = 0;
    fail_at = 0;
    response[0] = 0U;
    response[1] = 0xfffffU;
    assert(rtwn8723be_rf_channel_state_read(&ctx, values) == 0);
    assert(values[0] == 0xc00U && values[1] == 0xfffffU);
    puts("RTL_RF_CHANNEL_C11_UBSAN_OK order=A,B reg=0x18 "
         "A_mask=0xFFF03FF A_set=0xC00 failure_atomic");
    return 0;
}
"""

def main():
    with tempfile.TemporaryDirectory(prefix="rtl-rf-channel-") as tmp:
        check = Path(tmp) / "check.c"
        exe = Path(tmp) / "check"
        check.write_text(C)
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-fsanitize=undefined", "-fno-sanitize-recover=all",
            "-I", str(INCLUDE), str(SOURCE), str(check), "-o", str(exe)
        ], check=True)
        subprocess.run([str(exe)], check=True)

if __name__ == "__main__":
    main()
