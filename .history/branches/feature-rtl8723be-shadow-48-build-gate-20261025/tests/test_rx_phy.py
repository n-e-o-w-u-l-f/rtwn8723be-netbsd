#!/usr/bin/env python3
"""Execute real RTL8723BE CCK/OFDM PHY extraction with strict host C11/UBSan.

Isolated host regression only: never claim native NetBSD build or real RF.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r"""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "rtwn8723be_rx_phy.h"

static uint8_t d[32], b[64];
static int rssi;

static void setup(unsigned rate, unsigned lan, unsigned vga,
                  unsigned pwdb, unsigned shift, unsigned phy_units)
{
    memset(d, 0, sizeof(d));
    memset(b, 0, sizeof(b));
    d[0] = 16; /* Frame size, little endian. */
    d[2] = (uint8_t)phy_units; /* DWORD0 bits 16..19. */
    d[3] = (uint8_t)((1U << 2) | shift); /* PHYST bit26 and shift bits24..25. */
    d[12] = (uint8_t)rate;
    b[shift + 4] = (uint8_t)pwdb;
    b[shift + 5] = (uint8_t)((lan << 5) | vga);
    rssi = -120;
}
static int decode(void)
{
    return rtwn8723be_rx_phy_rssi(d, sizeof(d), b, sizeof(b), &rssi);
}
int main(void)
{
    unsigned lan, vga, cases = 0;
    const unsigned groups[] = {6, 4, 1, 0};
    const int bases[] = {-34, -14, 6, 16};
    for (lan = 0; lan < 4; ++lan) {
        for (vga = 0; vga <= 31; ++vga) {
            int expected = bases[lan] - 2 * (int)vga;
            setup(0, groups[lan], vga, 0, 0, 4);
            assert(decode() == 0);
            assert(rssi == (expected > 0 ? 0 : expected));
            cases++;
        }
    }
    setup(3, 6, 5, 0, 2, 4);
    assert(decode() == 0 && rssi == -44);
    setup(4, 0, 0, 80, 1, 4);
    assert(decode() == 0 && rssi == -70);
    setup(12, 0, 0, 0, 0, 4);
    assert(decode() == 0 && rssi == -110);
    setup(11, 0, 0, 254, 0, 4);
    assert(decode() == 0 && rssi == 0);

    setup(0, 2, 4, 0, 0, 4);
    assert(decode() == ENODATA && rssi == -120);
    setup(4, 0, 0, 80, 0, 4);
    d[3] &= (uint8_t)~4U; /* Missing PHYST. */
    assert(decode() == ENODATA && rssi == -120);
    setup(4, 0, 0, 80, 0, 4);
    d[3] |= 0x80; /* OWN bit31. */
    assert(decode() == EAGAIN && rssi == -120);
    setup(4, 0, 0, 80, 0, 4);
    d[11] |= 0x10; /* C2H report-selection DWORD2 bit28. */
    assert(decode() == EINVAL && rssi == -120);
    setup(4, 0, 0, 80, 0, 0);
    assert(decode() == EMSGSIZE && rssi == -120);
    setup(4, 0, 0, 80, 3, 4);
    assert(rtwn8723be_rx_phy_rssi(d, sizeof(d),
        b, 34, &rssi) == EMSGSIZE && rssi == -120);
    setup(4, 0, 0, 80, 0, 4);
    assert(rtwn8723be_rx_phy_rssi(d, 31, b, sizeof(b),
        &rssi) == EINVAL && rssi == -120);
    assert(rtwn8723be_rx_phy_rssi(d, sizeof(d),
        b, 9101, &rssi) == EINVAL && rssi == -120);
    assert(rtwn8723be_rx_phy_rssi(NULL, sizeof(d),
        b, sizeof(b), &rssi) == EINVAL);
    assert(rtwn8723be_rx_phy_rssi(d, sizeof(d),
        NULL, sizeof(b), &rssi) == EINVAL);
    assert(rtwn8723be_rx_phy_rssi(d, sizeof(d),
        b, sizeof(b), NULL) == EINVAL);
    printf("RTL_RX_PHY_C11_OK: %u exhaustive CCK AGC, OFDM, ownership and guards\n",
        cases);
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-rx-phy-") as temp:
    source = Path(temp) / "harness.c"
    target = Path(temp) / "harness"
    source.write_text(HARNESS)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
         "-pedantic", "-fsanitize=undefined", "-fno-sanitize-recover=all",
         "-I", str(ROOT / "src"),
         str(ROOT / "src/rtwn8723be_rx_phy.c"),
         str(source), "-o", str(target)],
        check=True,
    )
    subprocess.run([str(target)], check=True)
