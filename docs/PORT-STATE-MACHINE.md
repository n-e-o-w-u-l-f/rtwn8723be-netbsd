# Linux -> NetBSD hardware-state port contract

Every phase below preserves Linux hardware-visible ordering.  NetBSD may
replace kernel APIs, but it must not reorder register, firmware, DMA, IRQ,
PHY/RF, or power transitions.

| Phase | RTL8723BE Linux anchor | NetBSD port target |
|---|---|---|
| P00 identify | PCI ID / chip version / efuse | pci attach + chip/ROM state |
| P01 power/reset | ASPM off, DMA-hang check/reset, NIC power flow | PCI/PM adapter + power-sequence executor |
| P02 MMIO | MAC register access | bus_space BAR + sideband adapters |
| P03 DMA allocate | LLT, queue/ring layout, descriptor bases | bus_dma rings with Linux descriptor layout |
| P04 firmware validate | rtl8723befw_36.bin, 0x5300 signature | firmware(9) validation |
| P05 firmware transfer | rtl8723_download_fw + mailbox reset | page upload + self-reset + ready handshake |
| P06 MAC | _rtl8723be_init_mac + MAC table | exact register/state translation |
| P07 BB/RF | phy_mac/bb/rf_config | PHY tables + RF state |
| P08 HW policy | _rtl8723be_hw_configure | RRSR/ARFR/retry/TBTT/NAV/aggregation |
| P09 security | CAM reset + HW security | NetBSD net80211 key adapter |
| P10 coexist/cal | BT init, IQK, TX tracking, LC | exact coexist/calibration state |
| P11 DMA release | RXDMA control then PCIE_CTRL_REG+1=0 | release only after P01-P10 succeed |
| P12 IRQ | HIMR/HIMRE/HSIMR | pci interrupt establishment + exact masks |
| P13 datapath | 40-byte TX / 32-byte RX descriptors | rtwn TX/RX adapter preserving OWN semantics |
| P14 firmware protocol | H2C/C2H mailboxes | fw command/event adapter |
| P15 runtime PM | RF/LPS/IPS, channel/BW, suspend/resume | NetBSD PM lifecycle adapter |
| P16 recovery | DMA/MAC reset and re-init | same phase rollback/re-entry order |

## Gate

A phase is COMPLETE only when its Linux call path, register/DMA effects,
ordering dependencies, NetBSD adapter, and error/rollback path are all
implemented and reviewed.  Compiling alone does not close a phase.