#!/usr/bin/env python3
"""RTL8723B management-frame RX filter source/reference and placement gate.

Reference: pinned Linux rtl8723be/reg.h (0x6A0/0x6A2/0x6A4);
RTL8723B rtw88 September 2026 v4 WLAN_RX_FILTER0/1/2 = ffff/0400/ffff.
F77 observed 0000/0000/ffff and 0 beacons; candidate not hardware proven.
"""
from pathlib import Path
import re

root=Path(__file__).resolve().parents[1]
h=(root/"src/rtwn8723be_f16_1.h").read_text()
source=(root/"src/rtwn8723be_netbsd.c").read_text()
for symbol,addr in (("R23BE_REG_RXFLTMAP0","0x06a0"),
                    ("R23BE_REG_RXFLTMAP1","0x06a2"),
                    ("R23BE_REG_RXFLTMAP2","0x06a4")):
    pattern=r"^#define\s+"+symbol+r"\s+"+addr+r"$"
    assert len(re.findall(pattern,h,re.M))==1,(symbol,addr)
start=source.split("rtwn8723be_netbsd_init_mac(void *arg)",1)
assert len(start)==2
mac=start[1].split("rtwn8723be_netbsd_rcr_postprocess(",1)[0]
sequence=(
"rtwn8723be_write_4(sc, R23BE_REG_RCR, sc->sc_receive_config);",
"rtwn8723be_write_2(sc, R23BE_REG_RXFLTMAP2, 0xffff);",
"rtwn8723be_write_2(sc, R23BE_REG_RXFLTMAP1, 0x0400);",
"rtwn8723be_write_2(sc, R23BE_REG_RXFLTMAP0, 0xffff);",
"rtwn8723be_write_4(sc, R23BE_REG_TCR, sc->sc_transmit_config);",
)
indexes=[mac.find(x) for x in sequence]
assert -1 not in indexes and indexes==sorted(indexes), indexes
for x in sequence[1:4]:
    assert mac.count(x)==1,x
assert mac.find("if (!sc->sc_mapped || !sc->sc_rings_allocated)") < indexes[0]
assert "return error;" in mac
print("RTL_MANAGEMENT_BEACON_RX_FILTER_SOURCE_ORDER_PASS")
