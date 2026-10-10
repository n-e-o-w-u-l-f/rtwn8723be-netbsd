#!/usr/bin/env python3
"""Source-anchored guards for reserved-page PCI beacon DMA integration.

Reference: Linux torvalds/linux@fd179f8a rtlwifi/pci.c and
rtl8723be/reg.h (REG_BCN_PSR_RPT = 0x06a8).
This is a source gate, NOT PCIe or firmware hardware acceptance.
"""
from pathlib import Path

S = Path(__file__).resolve().parents[1] / "src"
reg = (S / "rtwn8723be_f16_1.h").read_text()
dma = (S / "rtwn8723be_f16_1_dma.c").read_text()
tx = (S / "rtwn8723be_tx_native.c").read_text()
txh = (S / "rtwn8723be_tx_native.h").read_text()
reserved = (S / "rtwn8723be_reserved_native.c").read_text()
assert "#define R23BE_REG_BCN_PSR_RPT          0x06a8" in reg
assert "#define RTWN8723BE_TX_RING_BCN_COUNT   2" in reg
assert "RTWN8723BE_BEACON_QUEUE" in dma and "ring->count" in dma
for owner in ("rtwn8723be_tx_native_enqueue_reserved",
              "rtwn8723be_tx_native_reclaim_reserved"):
    assert tx.count(owner + "(") == 1, owner
    assert txh.count(owner + "(") == 1, owner
    assert owner + "(" in reserved
assert "qid != RTWN8723BE_BEACON_QUEUE" in tx
assert "return command && fwq == RTWN8723BE_TX_FW_BEACON ? 0 : EINVAL;" in tx
assert "idx = qid == RTWN8723BE_BEACON_QUEUE ? 0U : ring->producer;" in tx
assert "ring->producer = qid == RTWN8723BE_BEACON_QUEUE ?" in tx
assert "ring->consumer = qid == RTWN8723BE_BEACON_QUEUE ?" in tx
assert "rtwn8723be_tx_encode_command(p.packet_len," in tx
assert "rtwn8723be_tx_native_enqueue_owned(sc," in tx
assert "RTWN8723BE_BEACON_QUEUE, m, p, true, owner, release" in tx
assert "RTWN8723BE_BEACON_QUEUE, reclaimed" in tx
assert "BUS_DMASYNC_POSTWRITE" in tx and "bus_dmamap_unload" in tx
assert "rtwn8723be_f16_1_tx_slot_release(slot, true)" in tx
assert "mutex_enter(&rsvd->dp->tx_lock);" in reserved
assert "mutex_exit(&rsvd->dp->tx_lock);" in reserved
print("RTL_BEACON_RESERVED_NATIVE_SOURCE_PASS")
