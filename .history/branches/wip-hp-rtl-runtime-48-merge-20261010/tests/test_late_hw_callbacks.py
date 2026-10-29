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
    "rtwn8723be_netbsd_init_rx_config",
    "rtwn8723be_netbsd_hw_configure",
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
struct rtwn8723be_softc { int sc_mapped; int sc_efuse_autoload_ok; int sc_core_initialized; uint32_t sc_receive_config; uint32_t sc_mac_rx_conf; uint8_t sc_retry_limit; uint8_t sc_bcn_ctrl_val; uint8_t sc_macaddr[6]; };
#define R23BE_REG_RCR 0x608
#define R23BE_REG_CAMCMD 0x670
#define R23BE_REG_MACID 0x610
#define R23BE_REG_RETRY_LIMIT 0x42a
#define R23BE_REG_NAV_UPPER 0x652
#define R23BE_REG_RXDMA_CONTROL 0x286
#define R23BE_REG_PCIE_CTRL_REG 0x300
#define R23BE_REG_FWHW_TXQ_CTRL 0x420
#define R23BE_REG_DARFRC 0x430
#define R23BE_REG_RARFRC 0x438
#define R23BE_REG_RRSR 0x440
#define R23BE_REG_ARFR0 0x444
#define R23BE_REG_ARFR1 0x44c
#define R23BE_REG_AMPDU_MAX_TIME 0x456
#define R23BE_REG_FAST_EDCA_CTRL 0x460
#define R23BE_REG_HT_SINGLE_AMPDU 0x4c7
#define R23BE_REG_MAX_AGGR_NUM 0x4ca
#define R23BE_REG_TBTT_PROHIBIT 0x540
#define R23BE_REG_NAV_PROT_LEN 0x546
#define R23BE_REG_BCN_CTRL 0x550
#define R23BE_REG_RX_PKT_LIMIT 0x60c
static uint32_t regmap[0x800];
static unsigned writes;
struct write_event { unsigned reg, width; uint32_t val; };
static struct write_event log_events[256];
static uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *s, unsigned r)
{ (void)s; return regmap[r]; }
static uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *s, unsigned r)
{ (void)s; return (uint8_t)regmap[r]; }
static void rtwn8723be_write_4(struct rtwn8723be_softc *s,
                              unsigned r, uint32_t v)
{ (void)s; regmap[r] = v; log_events[writes] = (struct write_event){ r, 4, v }; writes++; }
static void rtwn8723be_write_1(struct rtwn8723be_softc *s,
                              unsigned r, uint8_t v)
{ (void)s; regmap[r] = v; log_events[writes] = (struct write_event){ r, 1, v }; writes++; }
static void rtwn8723be_write_2(struct rtwn8723be_softc *s,
                              unsigned r, uint16_t v)
{ (void)s; regmap[r] = v; log_events[writes] = (struct write_event){ r, 2, v }; writes++; }
"""
MAIN = r"""
int main(void)
{
    struct rtwn8723be_softc sc = {0};
    assert(rtwn8723be_netbsd_phy_mac_config(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_rcr_postprocess(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_cam_reset_all(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_set_mac_address(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_init_rx_config(&sc) == ENXIO);
    assert(rtwn8723be_netbsd_hw_configure(&sc) == ENXIO);
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
    assert(rtwn8723be_netbsd_init_rx_config(&sc) == ENXIO);
    sc.sc_core_initialized = 1;
    assert(rtwn8723be_netbsd_init_rx_config(&sc) == 0);
    assert(sc.sc_mac_rx_conf == sc.sc_receive_config);
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
    const struct write_event expected[17] = {
        {0x440, 4, 0x00000fffU}, {0x448, 4, 0xfffff000U},
        {0x450, 4, 0x003ff000U}, {0x420, 2, 0x1f00U},
        {0x456, 1, 0x70U}, {0x42a, 2, 0x0707U},
        {0x430, 4, 0x01000000U}, {0x434, 4, 0x07060504U},
        {0x438, 4, 0x01000000U}, {0x43c, 4, 0x07060504U},
        {0x550, 1, 0x1dU}, {0x541, 1, 0xffU},
        {0x546, 2, 0x0040U}, {0x460, 4, 0x03086666U},
        {0x4c7, 1, 0x80U}, {0x60c, 1, 0x20U},
        {0x4ca, 1, 0x1fU}
    };
    unsigned before_hw = writes;
    assert(rtwn8723be_netbsd_hw_configure(&sc) == 0);
    assert(sc.sc_bcn_ctrl_val == 0x1d);
    assert(writes == before_hw + 17);
    for (unsigned i = 0; i < 17; i++) {
        assert(log_events[before_hw + i].reg == expected[i].reg);
        assert(log_events[before_hw + i].width == expected[i].width);
        assert(log_events[before_hw + i].val == expected[i].val);
    }
    assert(regmap[R23BE_REG_MAX_AGGR_NUM] == 0x1f);
    puts("CALLBACK_TESTS_OK: MAC RCR CAM MACADDR RXCONFIG HW17 NAV RXDMA PCIE RETRY");
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
