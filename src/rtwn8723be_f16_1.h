#ifndef _RTWN8723BE_F16_1_H_
#define _RTWN8723BE_F16_1_H_

#include <sys/types.h>
#include <sys/bus.h>

/* Linux rtl8723be/trx.h hardware descriptor sizes. */
#define RTWN8723BE_TX_DESC_SIZE       40
#define RTWN8723BE_RX_DESC_SIZE       32
#define RTWN8723BE_RX_DRV_INFO_UNIT    8
#define RTWN8723BE_TX_DESC_NEXT_OFFSET 40

/* RTL8723BE PCI/MMIO register offsets used by the reference init path. */
#define R23BE_SYS_FUNC_EN             0x0002
#define R23BE_APSD_CTRL               0x0005
#define R23BE_PWR_STATUS              0x0006
#define R23BE_SYS_ISO_CTRL            0x0058
#define R23BE_SYS_CLKR                0x005a
#define R23BE_SYS_CFG                 0x00f0
#define R23BE_SYS_CFG1                0x00fc
#define R23BE_CR                      0x0100
#define R23BE_RXDMA_CONTROL           0x0284
#define R23BE_PCIE_CTRL               0x0300
#define R23BE_PCIE_DMA_DEBUG          0x0350
#define R23BE_MAC_PHY_CTRL_NORMAL     0x00f8
#define R23BE_RSV_CTRL                0x001c
#define R23BE_PMC_DBG_CTRL2          0x00cc

/* Linux rtl8723be PCIe DMA reset sequence: SYS_FUNC_EN+1 bit 0. */
#define R23BE_SYS_FUNC_EN1_PCIE_DMA  0x01
#define R23BE_RXDMA_PAUSE             0x04
#define R23BE_PMC_UNLOCK              0x04

/* TX descriptor DWORD 0. */
#define R23BE_TXD0_PKT_SIZE_MASK      0x0000ffffU
#define R23BE_TXD0_OFFSET_MASK        0x00ff0000U
#define R23BE_TXD0_BMC               0x01000000U
#define R23BE_TXD0_HTC               0x02000000U
#define R23BE_TXD0_LAST_SEG          0x04000000U
#define R23BE_TXD0_FIRST_SEG         0x08000000U
#define R23BE_TXD0_LINIP              0x10000000U
#define R23BE_TXD0_OWN                0x80000000U

/* TX descriptor DWORD 1. */
#define R23BE_TXD1_MACID_MASK         0x0000007fU
#define R23BE_TXD1_QUEUE_MASK         0x00001f00U
#define R23BE_TXD1_RATEID_MASK        0x001f0000U
#define R23BE_TXD1_SECTYPE_MASK       0x00c00000U
#define R23BE_TXD1_PKTOFFSET_MASK     0x1f000000U

/* TX descriptor DWORD 7/10/12. */
#define R23BE_TXD7_BUFSIZE_MASK       0x0000ffffU
#define R23BE_TXD8_HWSEQ_EN           0x00008000U
#define R23BE_TXD9_SEQ_MASK           0x00fff000U

/* RX descriptor DWORD 0. */
#define R23BE_RXD0_PKT_LEN_MASK       0x00003fffU
#define R23BE_RXD0_CRC32              0x00004000U
#define R23BE_RXD0_ICV                0x00008000U
#define R23BE_RXD0_DRV_INFO_MASK      0x000f0000U
#define R23BE_RXD0_SHIFT_MASK         0x03000000U
#define R23BE_RXD0_PHYST              0x04000000U
#define R23BE_RXD0_SWDEC              0x08000000U
#define R23BE_RXD0_EOR                0x40000000U
#define R23BE_RXD0_OWN                0x80000000U

/* RX descriptor DWORD 6 contains the DMA buffer address. */

struct rtwn8723be_tx_desc {
    uint32_t d[10];
    uint32_t tx_buf_addr;
    uint32_t reserved11;
    uint32_t next_desc_addr;
};

struct rtwn8723be_rx_desc {
    uint32_t d[6];
    uint32_t tsfl_or_status;
    uint32_t rx_buf_addr;
};

struct rtwn8723be_tx_ring {
    void *kva;
    bus_dmamap_t map;
    bus_addr_t paddr;
    uint32_t count;
    uint32_t producer;
    uint32_t consumer;
};

struct rtwn8723be_rx_ring {
    void *kva;
    bus_dmamap_t map;
    bus_addr_t paddr;
    uint32_t count;
    uint32_t consumer;
};

static inline uint32_t
r23be_get_own(const uint32_t v)
{
    return (v >> 31) & 1U;
}

static inline void
r23be_set_own(uint32_t *v)
{
    *v |= R23BE_TXD0_OWN;
}

static inline void
r23be_clear_own(uint32_t *v)
{
    *v &= ~R23BE_TXD0_OWN;
}

static inline uint32_t
r23be_rx_pkt_len(const struct rtwn8723be_rx_desc *d)
{
    return d->d[0] & R23BE_RXD0_PKT_LEN_MASK;
}

#endif /* _RTWN8723BE_F16_1_H_ */
