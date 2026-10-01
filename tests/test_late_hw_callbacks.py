#!/usr/bin/env python3
"""Compile/test reference-derived NetBSD hw callbacks with mocked bus-space I/O.

This proves isolated C syntax and register/ordering behavior. It does not
claim NetBSD kernel integration or hardware/runtime parity.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
NAMES = (
    "rtwn8723be_netbsd_phy_mac_config",
    "rtwn8723be_netbsd_rcr_postprocess",
    "rtwn8723be_netbsd_cam_reset_all",
    "rtwn8723be_netbsd_set_mac_address",
    "rtwn8723be_netbsd_set_nav_upper_235",
    "rtwn8723be_netbsd_release_rx_dma",
    "rtwn8723be_netbsd_release_pcie_dma",
    "rtwn8723be_netbsd_set_retry_limit",
)

def extract(name):
    signature = "int\n" + name + "(void *arg)\n{"
    start = SOURCE.find(signature)
    if start == -1 or SOURCE.find(signature, start + 1) != -1:
        raise AssertionError("missing/non-unique callback: " + name)
    depth = 0
    for i in range(start + len(signature) - 1, len(SOURCE)):
        if SOURCE[i] == "{":
            depth += 1
        elif SOURCE[i] == "}":
            depth -= 1
            if depth == 0:
                return SOURCE[start : i + 1]
    raise AssertionError("unclosed callback: " + name)

PRELUDE = r"""
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#include <errno.h>
#include "rtwn8723be_mac_table.h"
struct rtwn8723be_softc { int sc_mapped; int sc_efuse_autoload_ok; uint32_t sc_receive_config; uint8_t sc_retry_limit; uint8_t sc_macaddr[6]; };
#define R23BE_REG_RCR 0x608
#define R23BE_REG_CAMCMD 0x670
#define R23BE_REG_MACID 0x610
#define R23BE_REG_RETRY_LIMIT 0x42a
#define R23BE_REG_NAV_UPPER 0x652
#define R23BE_REG_RXDMA_CONTROL 0x286
#define R23BE_REG_PCIE_CTRL_REG 0x300
static uint32_t regmap[0x800];
static unsigned writes;
static uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *s, unsigned r)
{ (void)s; return regmap[r]; }
static uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *s, unsigned r)
{ (void)s; return (uint8_t)regmap[r]; }
static void rtwn8723be_write_4(struct rtwn8723be_softc *s,
                              unsigned r, uint32_t v)
{ (void)s; regmap[r] = v; writes++; }
static void rtwn8723be_write_1(struct rtwn8723be_softc *s,
                              unsigned r, uint8_t v)
{ (void)s; regmap[r] = v; writes++; }
static void rtwn8723be_write_2(struct rtwn8723be_softc *s,
                              unsigned r, uint16_t v)
{ (void)s; regmap[r] = v; writes++; }
"""
MAIN = r"""
int main(void)
{
    struct rtwn8723be_softc sc = {0};
    assert(rtwn8723be_netbsd_phy_mac_config(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_rcr_postprocess(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_cam_reset_all(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_set_mac_address(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_set_nav_upper_235(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_release_rx_dma(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_release_pcie_dma(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_set_retry_limit(&sc) == ENXIO);
    assert(writes == 0);
    sc.sc_mapped = 1;
    assert(RTWN8723BE_MAC_TABLE_COUNT == 103);
    assert(rtwn8723be_netbsd_phy_mac_config(&sc) == 0);
    assert(writes == RTWN8723BE_MAC_TABLE_COUNT + 1);
    assert(regmap[0x02f] == 0x30);
    assert(regmap[0x76e] == 0x04);
    assert(regmap[0x04ca] == 0x0b);
    unsigned after_mac_table = writes;
    assert(rtwn8723be_netbsd_cam_reset_all(&sc) == 0);
    assert(regmap[R23BE_REG_CAMCMD] == 0xc0000000U);
    assert(writes == after_mac_table + 1);
    assert(rtwn8723be_netbsd_set_mac_address(&sc) == ENXIO);
    assert(writes == after_mac_table + 1);
    sc.sc_efuse_autoload_ok = 1;
    const uint8_t mac[] = { 0x02, 0x18, 0x7a, 0x23, 0xbe, 0x42 };
    for (unsigned i = 0; i < 6; i++) sc.sc_macaddr[i] = mac[i];
    assert(rtwn8723be_netbsd_set_mac_address(&sc) == 0);
    for (unsigned i = 0; i < 6; i++) assert(regmap[R23BE_REG_MACID + i] == mac[i]);
    assert(writes == after_mac_table + 7);
    regmap[R23BE_REG_RCR] = 0xffffffffU;
    assert(rtwn8723be_netbsd_rcr_postprocess(&sc) == 0);
    assert(sc.sc_receive_config == 0xfffffcffU);
    assert(regmap[R23BE_REG_RCR] == sc.sc_receive_config);
    assert(rtwn8723be_netbsd_set_nav_upper_235(&sc) == 0);
    assert(regmap[R23BE_REG_NAV_UPPER] == 235);
    regmap[R23BE_REG_RXDMA_CONTROL] = 0x84;
    assert(rtwn8723be_netbsd_release_rx_dma(&sc) == 0);
    assert(regmap[R23BE_REG_RXDMA_CONTROL] == 0x80);
    unsigned n = writes;
    assert(rtwn8723be_netbsd_release_rx_dma(&sc) == 0);
    assert(writes == n);
    regmap[R23BE_REG_PCIE_CTRL_REG + 1] = 0xff;
    assert(rtwn8723be_netbsd_release_pcie_dma(&sc) == 0);
    assert(regmap[R23BE_REG_PCIE_CTRL_REG + 1] == 0);
    assert(writes == n + 1);
    sc.sc_retry_limit = 7;
    assert(rtwn8723be_netbsd_set_retry_limit(&sc) == 0);
    assert(regmap[R23BE_REG_RETRY_LIMIT] == 0x0707);
    assert(writes == n + 2);
    puts("CALLBACK_TESTS_OK: MAC RCR CAM MACADDR NAV RXDMA PCIE RETRY");
    return 0;
}
"""

def main():
    body = PRELUDE + "\n\n".join(extract(name) for name in NAMES) + MAIN
    with tempfile.TemporaryDirectory() as directory:
        src, binary = Path(directory) / "test.c", Path(directory) / "test"
        src.write_text(body)
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "src"),
             "-pedantic", str(src), "-o", str(binary)],
            check=True,
        )
        subprocess.run([str(binary)], check=True)

if __name__ == "__main__":
    main()
