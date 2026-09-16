#ifndef _RTWN8723BE_F16_1_H_
#define _RTWN8723BE_F16_1_H_

#include <sys/types.h>
#include <sys/bus.h>

/*
 * RTL8723BE hardware contract copied from the Linux rtl8723be reference
 * driver.  This header intentionally does not invent device offsets.
 */
#define RTWN8723BE_TX_DESC_SIZE        40
#define RTWN8723BE_RX_DESC_SIZE        32
#define RTWN8723BE_RX_DRV_INFO_UNIT    8
#define RTWN8723BE_TX_DESC_NEXT_OFFSET 40

/* System / firmware control. */
#define R23BE_REG_SYS_ISO_CTRL         0x0000
#define R23BE_REG_SYS_FUNC_EN          0x0002
#define R23BE_REG_APS_FSMCO            0x0004
#define R23BE_REG_SYS_CLKR             0x0008
#define R23BE_REG_9346CR               0x000a
#define R23BE_REG_RF_CTRL              0x001f
#define R23BE_REG_MAC_PHY_CTRL         0x002c
#define R23BE_REG_RSV_CTRL             0x001c
#define R23BE_REG_EFUSE_CTRL           0x0030
#define R23BE_REG_MCUFWDL              0x0080
#define R23BE_REG_MCUTSTCFG            0x0084
#define R23BE_REG_SYS_CFG              0x00f0
#define R23BE_REG_SYS_CFG1             0x00fc
#define R23BE_REG_ROM_VERSION          0x00fd

/* Host interrupt block. */
#define R23BE_REG_HIMR                 0x00b0
#define R23BE_REG_HISR                 0x00b4
#define R23BE_REG_HIMRE                0x00b8
#define R23BE_REG_HISRE                0x00bc

/* MAC/DMA control. */
#define R23BE_REG_CR                   0x0100
#define R23BE_REG_PBP                  0x0104
#define R23BE_REG_PKT_BUFF_ACCESS_CTRL 0x0106
#define R23BE_REG_TRXDMA_CTRL          0x010c
#define R23BE_REG_TRXFF_BNDY           0x0114
#define R23BE_REG_TRXFF_STATUS         0x0118
#define R23BE_REG_RXFF_PTR             0x011c
#define R23BE_REG_FWIMR                0x0130
#define R23BE_REG_FWISR                0x0134

/* Firmware H2C/C2H mailbox block. */
#define R23BE_REG_C2HEVT_MSG_NORMAL    0x01a0
#define R23BE_REG_C2HEVT_CLEAR         0x01af
#define R23BE_REG_HMEBOX_0             0x01d0
#define R23BE_REG_HMEBOX_1             0x01d4
#define R23BE_REG_HMEBOX_2             0x01d8
#define R23BE_REG_HMEBOX_3             0x01dc
#define R23BE_REG_HMEBOX_EXT_0         0x01f0
#define R23BE_REG_HMEBOX_EXT_1         0x01f4
#define R23BE_REG_HMEBOX_EXT_2         0x01f8
#define R23BE_REG_HMEBOX_EXT_3         0x01fc

/* TX/RX DMA queue and PCIe descriptor registers. */
#define R23BE_REG_RQPN                 0x0200
#define R23BE_REG_TXDMA_OFFSET_CHK     0x020c
#define R23BE_REG_TXDMA_STATUS         0x0210
#define R23BE_REG_RXDMA_AGG_PG_TH      0x0280
#define R23BE_REG_FW_UPD_RDPTR         0x0284
#define R23BE_REG_RXDMA_CONTROL        0x0286
#define R23BE_REG_RXPKT_NUM            0x0287
#define R23BE_REG_PCIE_CTRL_REG        0x0300
#define R23BE_REG_INT_MIG              0x0304
#define R23BE_REG_BCNQ_DESA            0x0308
#define R23BE_REG_HQ_DESA              0x0310
#define R23BE_REG_MGQ_DESA             0x0318
#define R23BE_REG_VOQ_DESA             0x0320
#define R23BE_REG_VIQ_DESA             0x0328
#define R23BE_REG_BEQ_DESA             0x0330
#define R23BE_REG_BKQ_DESA             0x0338
#define R23BE_REG_RX_DESA              0x0340

/*
 * Linux's rtl8723be/trx.h descriptor field definitions.  The TX descriptor
 * has a 40-byte hardware header; the Linux helper also accesses the
 * following PCIe TX-buffer/next-descriptor words.  Keep those accesses out
 * of the C struct until the PCIe TXBD allocation model is ported verbatim.
 */
#define R23BE_TXD0_PKT_SIZE_MASK       0x0000ffffU
#define R23BE_TXD0_OFFSET_MASK         0x00ff0000U
#define R23BE_TXD0_BMC                0x01000000U
#define R23BE_TXD0_HTC                0x02000000U
#define R23BE_TXD0_LAST_SEG           0x04000000U
#define R23BE_TXD0_FIRST_SEG          0x08000000U
#define R23BE_TXD0_LINIP               0x10000000U
#define R23BE_TXD0_OWN                 0x80000000U

#define R23BE_TXD1_MACID_MASK          0x0000007fU
#define R23BE_TXD1_QUEUE_MASK          0x00001f00U
#define R23BE_TXD1_RATEID_MASK         0x001f0000U
#define R23BE_TXD1_SECTYPE_MASK        0x00c00000U
#define R23BE_TXD1_PKTOFFSET_MASK      0x1f000000U

#define R23BE_TXD2_AGG_ENABLE          0x00001000U
#define R23BE_TXD2_RDG_ENABLE          0x00002000U
#define R23BE_TXD2_MORE_FRAG            0x00020000U
#define R23BE_TXD2_AMPDU_DENSITY_MASK  0x00700000U

#define R23BE_TXD3_HWSEQ_SEL_MASK      0x000000c0U
#define R23BE_TXD3_USE_RATE            0x00000100U
#define R23BE_TXD3_DISABLE_FB          0x00000400U
#define R23BE_TXD3_CTS2SELF            0x00000800U
#define R23BE_TXD3_RTS_ENABLE          0x00001000U
#define R23BE_TXD3_HW_RTS_ENABLE       0x00002000U
#define R23BE_TXD3_NAV_USE_HDR         0x00008000U
#define R23BE_TXD3_MAX_AGG_NUM_MASK    0x003e0000U

#define R23BE_TXD4_TX_RATE_MASK        0x0000007fU
#define R23BE_TXD4_DATA_RATE_FB_MASK   0x00001f00U
#define R23BE_TXD4_RTS_RATE_FB_MASK    0x0001e000U
#define R23BE_TXD4_RTS_RATE_MASK       0x1f000000U

#define R23BE_TXD5_SUBCARRIER_MASK     0x0000000fU
#define R23BE_TXD5_SHORTGI              0x00000010U
#define R23BE_TXD5_BW_MASK              0x00000060U
#define R23BE_TXD5_RTS_SHORT            0x00001000U
#define R23BE_TXD5_RTS_SC_MASK          0x0001e000U

#define R23BE_TXD7_BUFSIZE_MASK         0x0000ffffU
#define R23BE_TXD8_HWSEQ_EN             0x00008000U
#define R23BE_TXD9_SEQ_MASK             0x00fff000U

/* RX descriptor DWORD 0. */
#define R23BE_RXD0_PKT_LEN_MASK         0x00003fffU
#define R23BE_RXD0_CRC32                0x00004000U
#define R23BE_RXD0_ICV                  0x00008000U
#define R23BE_RXD0_DRV_INFO_MASK        0x000f0000U
#define R23BE_RXD0_SHIFT_MASK           0x03000000U
#define R23BE_RXD0_PHYST                0x04000000U
#define R23BE_RXD0_SWDEC                0x08000000U
#define R23BE_RXD0_OWN                  0x80000000U

/* Linux RX descriptor is exactly 32 bytes. */
struct rtwn8723be_rx_desc {
    uint32_t d[8];
};

/* 40-byte Linux hardware descriptor header. */
struct rtwn8723be_tx_desc {
    uint32_t d[10];
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
