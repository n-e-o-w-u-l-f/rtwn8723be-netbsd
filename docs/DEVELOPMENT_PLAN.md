# RTL8723BE NetBSD development plan

## Verified boundary

F12.2 is the current safe hardware-programming boundary on the HP TPN-W121.
F11 verified firmware transfer and firmware-ready handshake. F12.1 allocates
RX/TX DMA rings. F12.2 programs descriptor bases and queue/page configuration,
while PCI bus mastering, DMA engines and interrupts remain disabled.

## Next stages

### F13 — LLT only

Initialize the TX-page linked list using the Linux/NetBSD RTL8723BE semantics.
Do not enable PCI bus mastering, CR DMA bits, MAC TX/RX, or interrupts.

### F14 — interrupt path

Establish the PCI interrupt handler and verify interrupt establishment without
starting DMA traffic. Keep bus mastering and DMA engines disabled during this
validation stage.

### F15 — DMA activation

Only after LLT and interrupt infrastructure are verified, enable PCI bus
mastering and the required HCI/TX/RX DMA control bits. RX/TX descriptor
ownership and ring state must be initialized before traffic is permitted.

### F16 — interface registration

Register the network/wireless interface and connect the operational lifecycle:
reset/init, start, stop, watchdog and interrupt-driven RX/TX completion.

## Safety invariants

- Never overwrite production `/netbsd`.
- Experimental boots use `userconf disable i915drmkms*`.
- Preserve F12.2 as the immediate rollback kernel.
- Never repeat F7/F7a blind MMIO probes.
- Validate every DMA map/address before any hardware write that depends on it.
- Keep Linux RTL8723BE semantics as the primary reference; do not substitute
  unrelated Realtek generations.

## Current experimental F13 warning

The existing uninstalled F13 build is intentionally **not** a boot candidate.
Its activation routine enables bus mastering and DMA/MAC control before the
interrupt and interface lifecycle are established. It must be refactored into
F13/F14/F15 boundaries before installation or boot testing.
