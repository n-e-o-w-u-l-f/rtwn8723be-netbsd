#!/usr/bin/env python3
"""Appended RX FCS must be advertised to NetBSD before crypto/decap.

Source contract with mutation controls; no C compiler or hardware involved.
Linux fd179f8 rtl8723be/reg.h: RCR_APPFCS=BIT(31).
NetBSD 03d918f sys/net80211/ieee80211_input.c: M_HASFCS trims CRC.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def contract(source, header):
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    match = re.search(
        r"\nrtwn8723be_net80211_input\([^;]+?\n\{(.*?)\n\}",
        source, re.S)
    if match is None:
        return False
    body = match[1]
    flag = re.search(
        r"if\s*\(\(n->sc->sc_receive_config\s*&\s*"
        r"\(1U\s*<<\s*31\)\)\s*!=\s*0\)\s*"
        r"m->m_flags\s*\|=\s*M_HASFCS;", body)
    if flag is None or body.count("M_HASFCS") != 1:
        return False
    allocation = body.find("m = m_devget(")
    failure = body.find("if (m == NULL)\n        return ENOBUFS;")
    node = body.find("ni = ieee80211_find_rxnode(")
    dispatch = body.find("ieee80211_input(ic, m, ni,")
    if not 0 <= allocation < failure < flag.start() < node < dispatch:
        return False
    # The stack owns trimming. Do not strip twice or modify borrowed DMA data.
    if "m_adj(" in body or "length -" in body:
        return False
    default = re.search(r"#define\s+RTWN8723BE_RCR_DEFAULT\s+(0x[0-9a-fA-F]+)U", header)
    return default is not None and bool(int(default[1], 16) & (1 << 31))


source = (ROOT / "src/rtwn8723be_net80211.c").read_text(encoding="utf-8")
header = (ROOT / "src/rtwn8723be_f16_1.h").read_text(encoding="utf-8")
assert contract(source, header), "appended FCS missing conditional M_HASFCS before net80211"
flag = "if ((n->sc->sc_receive_config & (1U << 31)) != 0)\n        m->m_flags |= M_HASFCS;"
assert source.count(flag) == 1
mutations = [
    source.replace(flag, "", 1),
    source.replace(flag, "m->m_flags |= M_HASFCS;", 1),
    source.replace(flag, flag.replace("<< 31", "<< 30"), 1),
    source.replace(flag, flag.replace("!= 0", "== 0"), 1),
    source.replace(flag, "", 1).replace(
        "ieee80211_free_node(ni);", flag + "\n    ieee80211_free_node(ni);", 1),
    source.replace(flag, flag + "\n    m_adj(m, -4);", 1),
    source.replace(flag, "/* " + flag + " */", 1),
]
for index, mutation in enumerate(mutations):
    assert mutation != source and not contract(mutation, header), index
print("RTL_NET80211_RX_FCS_SOURCE_PASS: appended-FCS contract; 7 rejected mutations")
