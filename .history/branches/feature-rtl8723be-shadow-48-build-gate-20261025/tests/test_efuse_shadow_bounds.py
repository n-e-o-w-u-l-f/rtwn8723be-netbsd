#!/usr/bin/env python3
"""Exercise the actual NetBSD EFUSE-shadow parser body with simulated reads.

This is an isolated strict host-C/UBSan test, not NetBSD object compilation,
real MMIO, or an HP hardware test.  The malformed-section rule deliberately
fails closed where the frozen Linux decoder otherwise loses synchronization.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
HEADER = (ROOT / "src/rtwn8723be_f16_1.h").read_text()
BEGIN = "static int\nrtwn8723be_netbsd_efuse_shadow_read("
END = "\nint\nrtwn8723be_netbsd_read_eeprom_info("
assert SOURCE.count(BEGIN) == 1 and SOURCE.count(END) == 1
BODY = SOURCE[SOURCE.index(BEGIN):SOURCE.index(END)]
for define in (
    "#define R23BE_EFUSE_REAL_CONTENT_LEN   256",
    "#define R23BE_EFUSE_HWSET_MAX_SIZE     512",
    "#define R23BE_EFUSE_MAX_SECTION        64",
    "#define R23BE_EFUSE_MAX_WORD_UNIT      4",
):
    assert define in HEADER, "production EFUSE geometry changed: " + define
assert "if (offset >= R23BE_EFUSE_MAX_SECTION) {" in BODY
assert "error = EINVAL;\n            goto out;" in BODY

PREAMBLE = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define R23BE_EFUSE_REAL_CONTENT_LEN 256
#define R23BE_EFUSE_HWSET_MAX_SIZE 512
#define R23BE_EFUSE_MAX_SECTION 64
#define R23BE_EFUSE_MAX_WORD_UNIT 4
struct rtwn8723be_softc { uint8_t sc_efuse_map[512]; };
static uint8_t physical[256];
static unsigned int powered_on, powered_off;
static int fail_at = -1;
static void rtwn8723be_netbsd_efuse_power(
    struct rtwn8723be_softc *sc, bool on)
{
    (void)sc;
    if (on) powered_on++;
    else powered_off++;
}
static int rtwn8723be_netbsd_efuse_read_1(
    struct rtwn8723be_softc *sc, uint16_t address, uint8_t *value)
{
    (void)sc;
    if (address >= 256) return EINVAL;
    if ((int)address == fail_at) return EIO;
    *value = physical[address];
    return 0;
}
static void reset(void)
{
    memset(physical, 0xff, sizeof(physical));
    powered_on = powered_off = 0;
    fail_at = -1;
}
"""
CASES = r"""
int main(void)
{
    struct rtwn8723be_softc sc = {0};
    int result;

    reset();
    physical[0] = 0x0e; /* section 0, first word enabled */
    physical[1] = 0x29; physical[2] = 0x81;
    result = rtwn8723be_netbsd_efuse_shadow_read(&sc);
    assert(result == 0 && powered_on == 1 && powered_off == 1);
    assert(sc.sc_efuse_map[0] == 0x29 && sc.sc_efuse_map[1] == 0x81);
    assert(sc.sc_efuse_map[2] == 0xff);

    reset();
    physical[0] = 0x0f; /* extended section */
    physical[1] = 0x8e; /* section 64: outside the 0..63 map */
    physical[2] = 0x34; physical[3] = 0x12;
    result = rtwn8723be_netbsd_efuse_shadow_read(&sc);
    assert(result == EINVAL && powered_on == 1 && powered_off == 1);

    reset();
    physical[0] = 0x0e;
    physical[1] = 0x29; physical[2] = 0x81;
    physical[3] = 0x0f; physical[4] = 0x8e;
    physical[5] = 0x34; physical[6] = 0x12;
    result = rtwn8723be_netbsd_efuse_shadow_read(&sc);
    assert(result == EINVAL && powered_on == 1 && powered_off == 1);

    reset();
    physical[0] = 0x0e;
    fail_at = 1;
    result = rtwn8723be_netbsd_efuse_shadow_read(&sc);
    assert(result == EIO && powered_on == 1 && powered_off == 1);

    puts("RTL_EFUSE_SHADOW_HOST_C_OK: valid, invalid and failed reads");
    return 0;
}
"""

def execute(source: str, folder: Path, label: str, expect_success: bool) -> None:
    program = folder / (label + ".c")
    binary = folder / label
    program.write_text(PREAMBLE + source + CASES)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        str(program), "-o", str(binary),
    ], check=True)
    outcome = subprocess.run([str(binary)], capture_output=True, text=True)
    assert (outcome.returncode == 0) == expect_success, (
        label, outcome.returncode, outcome.stdout, outcome.stderr
    )
    if expect_success:
        print(outcome.stdout.strip())

def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        execute(BODY, directory, "fixed", True)
        original = BODY.replace(
            "if (offset >= R23BE_EFUSE_MAX_SECTION) {\n"
            "            error = EINVAL;\n"
            "            goto out;\n"
            "        }",
            "if (offset >= R23BE_EFUSE_MAX_SECTION)\n"
            "            continue;",
        )
        assert original != BODY
        execute(original, directory, "negative_control", False)
    print("RTL_EFUSE_NEGATIVE_CONTROL_OK: original decoder fails regression")
    print("LIMITATION: mock EFUSE reads, not native NetBSD or HP hardware")

if __name__ == "__main__":
    main()
