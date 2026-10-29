#!/usr/bin/env python3
"""Source-level guard: Linux-order NetBSD ring reset must return TX owner once.

Runtime cannot accept the new MCU generation until IRQ/softint is halted
and every selected RX/TX ring descriptor has been restored.
"""
from pathlib import Path
S=Path(__file__).resolve().parents[1]/"src"
net=(S/"rtwn8723be_netbsd.c").read_text()
dma=(S/"rtwn8723be_f16_1_dma.c").read_text()
runtime=(S/"rtwn8723be_runtime.c").read_text()
linux=(S/"rtwn8723be_linux_state.c").read_text()
a=net.index("rtwn8723be_netbsd_reset_trx_ring(void *arg)")
z=net.index("rtwn8723be_netbsd_irq_set_dispatch(",a)
fn=net[a:z]
assert fn.index("sc->sc_irq_enabled") < fn.index("for (q = 0;")
assert "sc->sc_ih != NULL" in fn and "sc->sc_soft_ih != NULL" in fn
assert "rtwn8723be_f16_1_tx_slot_release(&ring->slot[i], false)" in fn
assert "m_freem(ring->slot[i].m)" not in fn
assert fn.index("BUS_DMASYNC_POSTWRITE") < fn.index(
    "rtwn8723be_f16_1_tx_slot_release(&ring->slot[i], false)")
assert fn.index("bus_dmamap_unload(") < fn.index(
    "rtwn8723be_f16_1_tx_slot_release(&ring->slot[i], false)")
assert fn.index("ring->consumer = 0;") < fn.index(
    "sc->sc_runtime->mcu_rx_drained = true;")
assert "rtwn8723be_f16_1_tx_slot_release(struct rtwn8723be_dma_slot *slot" in dma
assert "slot->tx_owner = NULL;" in dma and "slot->tx_release = NULL;" in dma
assert "r->mcu_rx_drained = false;" in runtime
assert "!r->mcu_rx_drained" in runtime
assert "R23BE_CALL(R23BE_STAGE_RESET_RINGS, ops->reset_trx_ring, ctx)" in linux
assert "R23BE_CALL(R23BE_STAGE_BT_PREPARE, ops->bt_prepare, ctx)" in linux
assert linux.index("R23BE_CALL(R23BE_STAGE_RESET_RINGS, ops->reset_trx_ring, ctx)") < (
    linux.index("R23BE_CALL(R23BE_STAGE_BT_PREPARE, ops->bt_prepare, ctx)"))
print("RTL_DMA_RESET_OWNER_GENERATION_SOURCE_PASS")
