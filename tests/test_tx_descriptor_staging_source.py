#!/usr/bin/env python3
"""Native descriptor preparation boundary; source/mutation checks only."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def contract(source):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    source = source.split("\nrtwn8723be_tx_native_enqueue_owned(", 1)[1].split(
        "\nint\nrtwn8723be_tx_native_reclaim(", 1)[0]
    if source.count("(uint8_t *)&prepared_desc, sizeof(prepared_desc)") != 2:
        return False
    if "(uint8_t *)desc" in source:
        return False
    tokens = ["saved_desc = *desc;", "prepared_desc = saved_desc;",
              "error = rtwn8723be_tx_encode_command(",
              "error = rtwn8723be_tx_encode(&p,",
              "if (error == 0 &&",
              "(le32toh(prepared_desc.d[0]) & R23BE_TXD0_OWN) != 0)",
              "error = EINVAL;", "if (error != 0)", "goto unload_map;",
              "*desc = prepared_desc;", "BUS_DMASYNC_PREWRITE);",
              "slot->tx_owner = owner;", "slot->m = m;", "membar_producer();",
              "desc->d[0] = htole32(le32toh(desc->d[0]) | R23BE_TXD0_OWN);",
              "rtwn8723be_write_2(", "unload_map:", "bus_dmamap_unload(",
              "restore_desc:", "*desc = saved_desc;"]
    end = 0
    for token in tokens:
        pos = source.find(token, end)
        if pos < 0:
            return False
        end = pos + len(token)
    return source.count("*desc = prepared_desc;") == 1


source = (ROOT / "src/rtwn8723be_tx_native.c").read_text()
assert contract(source), "encode must succeed privately with OWN clear before ring copy"
target = "(uint8_t *)&prepared_desc, sizeof(prepared_desc)"
mutations = [source.replace(target, "(uint8_t *)desc, sizeof(*desc)", 1),
             source.replace(target, "(uint8_t *)desc, sizeof(*desc)"),
             source.replace("*desc = prepared_desc;", "", 1),
             source.replace("*desc = prepared_desc;", "/* *desc = prepared_desc; */", 1),
             source.replace("prepared_desc.d[0]) & R23BE_TXD0_OWN) != 0", "prepared_desc.d[0]) & R23BE_TXD0_OWN) == 0", 1),
             source.replace("*desc = saved_desc;", "", 1),
             source.replace("*desc = prepared_desc;", "", 1).replace("p = *input;", "*desc = prepared_desc;\n    p = *input;", 1)]
for i, mutation in enumerate(mutations):
    assert mutation != source and not contract(mutation), i
print("TX_DESCRIPTOR_STAGING_SOURCE_PASS: private encoders/OWN/rollback; 7 rejected mutations")
