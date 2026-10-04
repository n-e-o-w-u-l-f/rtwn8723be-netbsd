#ifndef _RTWN8723BE_F16_1_H_
#define _RTWN8723BE_F16_1_H_

#include <sys/types.h>
#include <sys/bus.h>

/* RTL8723BE hardware contract copied from the Linux rtl8723be reference. */
#define RTWN8723BE_TX_DESC_SIZE        40
#define RTWN8723BE_TX_DESC_STRIDE      64
#define RTWN8723BE_RX_DESC_SIZE        32
#define RTWN8723BE_RX_DRV_INFO_UNIT    8
#define RTWN8723BE_TX_DESC_NEXT_OFFSET 40
#define RTWN8723BE_TX_NEXT_DESC_DW     12
#define RTWN8723BE_RING_ALIGN          256
#define RTWN8723BE_RX_BUFFER_SIZE      9100

#define RTWN8723BE_RX_MPDU_QUEUE       0
#define RTWN8723BE_RX_CMD_QUEUE        1
#define RTWN8723BE_RX_QUEUE_COUNT      2
#define RTWN8723BE_RX_RING_COUNT       512

#define RTWN8723BE_BK_QUEUE            0
#define RTWN8723BE_BE_QUEUE            1
#define RTWN8723BE_VI_QUEUE            2
#define RTWN8723BE_VO_QUEUE            3
#define RTWN8723BE_BEACON_QUEUE        4
#define RTWN8723BE_TXCMD_QUEUE         5
#define RTWN8723BE_MGNT_QUEUE          6
#define RTWN8723BE_HIGH_QUEUE          7
#define RTWN8723BE_HCCA_QUEUE          8
#define RTWN8723BE_TX_QUEUE_COUNT      9

#define RTWN8723BE_TX_RING_COUNT       128
#define RTWN8723BE_TX_RING_BE_COUNT    256
#define RTWN8723BE_TX_RING_BCN_COUNT   2

#define RTWN8723BE_FIRMWARE_NAME       "rtlwifi/rtl8723befw_36.bin"
#define RTWN8723BE_FIRMWARE_DRIVER     "if_rtwn8723be"
#define RTWN8723BE_FIRMWARE_FILE       "rtl8723befw_36.bin"
#define RTWN8723BE_TCR_DEFAULT         0x03008200U
#define RTWN8723BE_RCR_DEFAULT         0xf0007a0eU

/* System / firmware control. */
#define R23BE_REG_SYS_ISO_CTRL         0x0000
#define R23BE_REG_SYS_FUNC_EN          0x0002
#define R23BE_REG_APS_FSMCO            0x0004
#define R23BE_REG_SYS_CLKR             0x0008
#define R23BE_REG_9346CR               0x000a
#define R23BE_REG_RF_CTRL              0x001f
#define R23BE_REG_MAC_PHY_CTRL         0x002c
#define R23BE_REG_RSV_CTRL             0x001c
#define R23BE_REG_PMC_DBG_CTRL2        0x00cc
#define R23BE_REG_EFUSE_CTRL           0x0030
#define R23BE_REG_EFUSE_TEST           0x0034
#define R23BE_REG_EFUSE_ACCESS         0x00cf

/* Pinned Linux rtl8723be EFUSE geometry and map contract. */
#define R23BE_EFUSE_REAL_CONTENT_LEN   256
#define R23BE_EFUSE_HWSET_MAX_SIZE     512
#define R23BE_EFUSE_MAX_SECTION        64
#define R23BE_EFUSE_MAX_WORD_UNIT      4
#define R23BE_EFUSE_FEN_ELDR           (1U << 12)
#define R23BE_EFUSE_LOADER_CLK_EN      (1U << 5)
#define R23BE_EFUSE_ANA8M              (1U << 1)

#define R23BE_EEPROM_ID                0x8129
#define R23BE_EEPROM_MAC_ADDR          0x00d0
#define R23BE_EEPROM_VID               0x00d6
#define R23BE_EEPROM_DID               0x00d8
#define R23BE_EEPROM_SVID              0x00da
#define R23BE_EEPROM_SMID              0x00dc
/* Pinned Linux rtl8723be/reg.h: EEPROM_XTAL_8723BE. */
#define R23BE_EEPROM_XTAL_8723BE       0x00b9
#define R23BE_EEPROM_RF_BT_SETTING     0x00c3
#define R23BE_REG_MCUFWDL              0x0080
#define R23BE_REG_FW_START_ADDR        0x1000
#define R23BE_REG_MCUTSTCFG            0x0084
#define R23BE_REG_MAC_PHY_CTRL_NORMAL  0x00f8
#define R23BE_REG_SYS_CFG              0x00f0
#define R23BE_REG_SYS_CFG1             0x00fc
#define R23BE_REG_ROM_VERSION          0x00fd
#define R23BE_REG_GPIO_MUXCFG          0x0040
#define R23BE_REG_MAC_PINMUX_CFG       0x0043
#define R23BE_REG_LEDCFG1              0x004d
#define R23BE_REG_LEDCFG2              0x004e
#define R23BE_REG_XCK_OUT_CTRL         0x007c
#define R23BE_REG_MULTI_FUNC_CTRL      0x0068

/* Host interrupt block. */
#define R23BE_REG_HSIMR                0x0058
#define R23BE_REG_HSISR                0x005c
#define R23BE_REG_HIMR                 0x00b0
#define R23BE_REG_HISR                 0x00b4
#define R23BE_REG_HIMRE                0x00b8
#define R23BE_REG_HISRE                0x00bc

/* DW0 interrupt bits. */
#define R23BE_IMR_ROK                  (1U << 0)
#define R23BE_IMR_RDU                  (1U << 1)
#define R23BE_IMR_VODOK                (1U << 2)
#define R23BE_IMR_VIDOK                (1U << 3)
#define R23BE_IMR_BEDOK                (1U << 4)
#define R23BE_IMR_BKDOK                (1U << 5)
#define R23BE_IMR_MGNTDOK              (1U << 6)
#define R23BE_IMR_HIGHDOK              (1U << 7)
#define R23BE_IMR_CPWM                 (1U << 8)
#define R23BE_IMR_CPWM2                (1U << 9)
#define R23BE_IMR_C2HCMD               (1U << 10)
#define R23BE_IMR_HISR1_IND_INT        (1U << 11)
#define R23BE_IMR_ATIMEND              (1U << 12)
#define R23BE_IMR_HSISR_IND_ON_INT     (1U << 15)
#define R23BE_IMR_BCNDOK0              (1U << 16)
#define R23BE_IMR_BCNDMAINT0           (1U << 20)
#define R23BE_IMR_TBDOK                (1U << 25)
#define R23BE_IMR_TBDER                (1U << 26)
#define R23BE_IMR_GTINT3               (1U << 27)
#define R23BE_IMR_GTINT4               (1U << 28)
#define R23BE_IMR_PSTIMEOUT            (1U << 29)
#define R23BE_IMR_TXCCK                (1U << 30)

/* DW1 interrupt bits at HIMR+4/HISR+4. */
#define R23BE_IMR_RXFOVW               (1U << 8)
#define R23BE_IMR_TXFOVW               (1U << 9)
#define R23BE_IMR_RXERR                (1U << 10)
#define R23BE_IMR_TXERR                (1U << 11)

/* Linux 8723BE default interrupt contract. */
#define R23BE_IMR0_DEFAULT (R23BE_IMR_PSTIMEOUT | \
    R23BE_IMR_HSISR_IND_ON_INT | R23BE_IMR_C2HCMD | \
    R23BE_IMR_HIGHDOK | R23BE_IMR_MGNTDOK | R23BE_IMR_BKDOK | \
    R23BE_IMR_BEDOK | R23BE_IMR_VIDOK | R23BE_IMR_VODOK | \
    R23BE_IMR_RDU | R23BE_IMR_ROK)
#define R23BE_IMR1_DEFAULT R23BE_IMR_RXFOVW

/* Host-system interrupt bits. */
#define R23BE_HSIMR_PDN_INT_EN         (1U << 7)
#define R23BE_HSIMR_RON_INT_EN         (1U << 6)

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
#define R23BE_REG_FWHW_TXQ_CTRL        0x0420
#define R23BE_REG_RETRY_LIMIT          0x042a
/* Frozen Linux rtl8723be/reg.h HW configuration register block. */
#define R23BE_REG_DARFRC               0x0430
#define R23BE_REG_RARFRC               0x0438
#define R23BE_REG_RRSR                 0x0440
#define R23BE_REG_ARFR0                0x0444
#define R23BE_REG_ARFR1                0x044c
#define R23BE_REG_AMPDU_MAX_TIME       0x0456
#define R23BE_REG_FAST_EDCA_CTRL       0x0460
#define R23BE_REG_HT_SINGLE_AMPDU      0x04c7
#define R23BE_REG_MAX_AGGR_NUM         0x04ca
#define R23BE_REG_TBTT_PROHIBIT        0x0540
#define R23BE_REG_NAV_PROT_LEN         0x0546
#define R23BE_REG_BCN_CTRL             0x0550
#define R23BE_REG_RX_PKT_LIMIT         0x060c
#define R23BE_REG_HWSEQ_CTRL           0x0423
#define R23BE_REG_TCR                  0x0604
#define R23BE_REG_RCR                  0x0608
/* Pinned Linux rtl8723be/reg.h: REG_MACID/REG_CAMCMD. */
#define R23BE_REG_MACID                0x0610
#define R23BE_REG_CAMCMD               0x0670
#define R23BE_REG_RXFLTMAP2            0x06a4
#define R23BE_REG_MCUTST_1             0x01c0
#define R23BE_REG_SECONDARY_CCA_CTRL   0x0577

/* Firmware H2C/C2H mailbox block. */
#define R23BE_REG_C2HEVT_MSG_NORMAL    0x01a0
#define R23BE_REG_C2HEVT_CLEAR         0x01af
#define R23BE_REG_HMETFR               0x01cc
#define R23BE_REG_HMEBOX_0             0x01d0
#define R23BE_REG_HMEBOX_1             0x01d4
#define R23BE_REG_HMEBOX_2             0x01d8
#define R23BE_REG_HMEBOX_3             0x01dc
#define R23BE_REG_HMEBOX_EXT_0         0x01f0
#define R23BE_REG_HMEBOX_EXT_1         0x01f4
#define R23BE_REG_HMEBOX_EXT_2         0x01f8
#define R23BE_REG_HMEBOX_EXT_3         0x01fc

/* Linked-list table / TX packet-buffer setup from pinned Linux 8723BE. */
#define R23BE_REG_LLT_INIT             0x01e0
#define R23BE_REG_TDECTRL              0x0208
#define R23BE_REG_RQPN_NPQ             0x0214
#define R23BE_REG_TXPKTBUF_BCNQ_BDNY   0x0424
#define R23BE_REG_TXPKTBUF_MGQ_BDNY    0x0425
#define R23BE_REG_TXPKTBUF_WMAC_LBK_BF_HD 0x045d
#define R23BE_REG_RX_DRVINFO_SZ         0x060f
#define R23BE_LLT_POLL_MAX              20
#define R23BE_LLT_WRITE_ACCESS          1U
#define R23BE_LLT_NO_ACTIVE             0U

/* TX/RX DMA queue and PCIe descriptor registers. */
#define R23BE_REG_RQPN                 0x0200
#define R23BE_REG_TXDMA_OFFSET_CHK     0x020c
#define R23BE_REG_TXDMA_STATUS         0x0210
#define R23BE_REG_RXDMA_AGG_PG_TH      0x0280
#define R23BE_REG_FW_UPD_RDPTR         0x0284
#define R23BE_REG_RXDMA_CONTROL        0x0286
#define R23BE_REG_RXPKT_NUM            0x0287
#define R23BE_REG_PCIE_CTRL_REG        0x0300
#define R23BE_REG_DBI_CTRL             0x0350
#define R23BE_REG_INT_MIG              0x0304
#define R23BE_REG_BCNQ_DESA            0x0308
#define R23BE_REG_HQ_DESA              0x0310
#define R23BE_REG_MGQ_DESA             0x0318
#define R23BE_REG_VOQ_DESA             0x0320
#define R23BE_REG_VIQ_DESA             0x0328
#define R23BE_REG_BEQ_DESA             0x0330
#define R23BE_REG_BKQ_DESA             0x0338
#define R23BE_REG_RX_DESA              0x0340
#define R23BE_REG_NAV_UPPER            0x0652

/* PCIe DMA control bits used by the Linux init/reset path. */
#define R23BE_PCIE_CTRL_DMA_HANG_RST   (1U << 0)
#define R23BE_RXDMA_PAUSE              (1U << 2)

/* TX descriptor fields. */
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
#define R23BE_RXD0_EOR                  0x40000000U
#define R23BE_RXD0_OWN                  0x80000000U

struct mbuf;

struct rtwn8723be_rx_desc { uint32_t d[8]; };
/*
 * Linux struct rtl_tx_desc is 16 DWORDs (64-byte coherent ring stride).
 * RTL8723BE actively fills the first 40 bytes; DWORD 10 carries the TX
 * buffer address and DWORD 12 carries the linked next-descriptor address.
 */
struct rtwn8723be_tx_desc { uint32_t d[16]; };

struct rtwn8723be_dma_mem {
    bus_dmamap_t map;
    bus_dma_segment_t seg;
    int nsegs;
    void *kva;
    bus_addr_t paddr;
    bus_size_t size;
};

struct rtwn8723be_dma_slot {
    bus_dmamap_t map;
    struct mbuf *m;
};

struct rtwn8723be_tx_ring {
    struct rtwn8723be_dma_mem desc_dma;
    struct rtwn8723be_dma_slot *slot;
    uint32_t count;
    uint32_t producer;
    uint32_t consumer;
};

struct rtwn8723be_rx_ring {
    struct rtwn8723be_dma_mem desc_dma;
    struct rtwn8723be_dma_slot *slot;
    uint32_t count;
    uint32_t consumer;
};

int rtwn8723be_f16_1_dma_mem_alloc(bus_dma_tag_t,
    struct rtwn8723be_dma_mem *, bus_size_t, bus_size_t);
void rtwn8723be_f16_1_dma_mem_free(bus_dma_tag_t,
    struct rtwn8723be_dma_mem *);
void rtwn8723be_f16_1_dma_sync_for_device(bus_dma_tag_t,
    struct rtwn8723be_dma_mem *, bus_addr_t, bus_size_t);
void rtwn8723be_f16_1_dma_sync_for_cpu(bus_dma_tag_t,
    struct rtwn8723be_dma_mem *, bus_addr_t, bus_size_t);
int rtwn8723be_f16_1_tx_ring_alloc(bus_dma_tag_t,
    struct rtwn8723be_tx_ring *, uint32_t);
void rtwn8723be_f16_1_tx_ring_free(bus_dma_tag_t,
    struct rtwn8723be_tx_ring *);
int rtwn8723be_f16_1_rx_ring_alloc(bus_dma_tag_t,
    struct rtwn8723be_rx_ring *, uint32_t);
void rtwn8723be_f16_1_rx_ring_free(bus_dma_tag_t,
    struct rtwn8723be_rx_ring *);

static inline uint32_t r23be_get_own(const uint32_t v) { return (v >> 31) & 1U; }
static inline void r23be_set_own(uint32_t *v) { *v |= R23BE_TXD0_OWN; }
static inline void r23be_clear_own(uint32_t *v) { *v &= ~R23BE_TXD0_OWN; }
static inline uint32_t r23be_rx_pkt_len(const struct rtwn8723be_rx_desc *d) { return d->d[0] & R23BE_RXD0_PKT_LEN_MASK; }

#endif /* _RTWN8723BE_F16_1_H_ */
