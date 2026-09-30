#ifndef _RTWN8723BE_NETBSD_H_
#define _RTWN8723BE_NETBSD_H_

#include <sys/types.h>
#include <sys/device.h>
#include <sys/bus.h>

#include <dev/pci/pcireg.h>
#include <dev/pci/pcivar.h>

#include "rtwn8723be_f16_1.h"
#include "rtwn8723be_linux_state.h"

#define RTWN8723BE_PCI_BAR_MMIO        0x18
#define RTWN8723BE_DMA_MAXADDR         0xffffffffULL

/*
 * Linux rtlwifi dispatches RX/TX work from the shared PCI interrupt after
 * rtl8723be_interrupt_recognized() has ACKed HISR/HISRE.  NetBSD keeps the
 * hard interrupt short and transfers the recognized vector to SOFTINT_NET.
 */
struct rtwn8723be_irq_dispatch {
    void (*rx)(void *);
    void (*tx_done)(void *, unsigned int);
    void (*power_event)(void *);
};

struct rtwn8723be_softc {
    device_t sc_dev;
    struct pci_attach_args sc_pa;
    pci_chipset_tag_t sc_pc;
    pcitag_t sc_tag;

    bus_space_tag_t sc_st;
    bus_space_handle_t sc_sh;
    bus_addr_t sc_base;
    bus_size_t sc_mapsize;
    bool sc_mapped;

    bus_dma_tag_t sc_dmat_parent;
    bus_dma_tag_t sc_dmat;
    bool sc_dmat_owned;
    bool sc_dma_32bit;

    int sc_pcie_cap_off;
    uint32_t sc_pcie_lcsr_initial;
    bool sc_pcie_cap_valid;

    struct rtwn8723be_tx_ring sc_tx_ring[RTWN8723BE_TX_QUEUE_COUNT];
    struct rtwn8723be_rx_ring sc_rx_ring[RTWN8723BE_RX_QUEUE_COUNT];
    bool sc_rings_allocated;

    pci_intr_handle_t *sc_pihp;
    void *sc_ih;
    void *sc_soft_ih;

    uint32_t sc_irq_mask[2];
    uint32_t sc_sys_irq_mask;
    volatile uint32_t sc_irq_pending[2];
    bool sc_irq_enabled;
    bool sc_irq_dispatch_ready;

    struct rtwn8723be_irq_dispatch sc_irq_dispatch;
    void *sc_irq_arg;

    struct rtwn8723be_linux_state sc_linux;

    uint32_t sc_receive_config;
    uint32_t sc_transmit_config;
    const char *sc_firmware_name;
    bool sc_btcoexist;
    bool sc_mac_func_enable;
};

void rtwn8723be_netbsd_context_init(struct rtwn8723be_softc *,
    device_t, const struct pci_attach_args *);

uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *, bus_size_t);
uint16_t rtwn8723be_read_2(struct rtwn8723be_softc *, bus_size_t);
uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *, bus_size_t);
void rtwn8723be_write_1(struct rtwn8723be_softc *, bus_size_t, uint8_t);
void rtwn8723be_write_2(struct rtwn8723be_softc *, bus_size_t, uint16_t);
void rtwn8723be_write_4(struct rtwn8723be_softc *, bus_size_t, uint32_t);

int rtwn8723be_netbsd_pci_enable(void *);
int rtwn8723be_netbsd_dma_configure(void *);
void rtwn8723be_netbsd_dma_release(struct rtwn8723be_softc *);
int rtwn8723be_netbsd_pci_set_master(void *);
int rtwn8723be_netbsd_alloc_softc(void *);
int rtwn8723be_netbsd_map_bar(void *);
int rtwn8723be_netbsd_pci_prepare_d0(void *);
int rtwn8723be_netbsd_find_adapter(void *);
int rtwn8723be_netbsd_init_io(void *);
int rtwn8723be_netbsd_init_sw_vars(void *);
int rtwn8723be_netbsd_init_pci_rings(void *);
int rtwn8723be_netbsd_reset_trx_ring(void *);
void rtwn8723be_netbsd_free_pci_rings(struct rtwn8723be_softc *);

int rtwn8723be_netbsd_init_aspm(void *);
int rtwn8723be_netbsd_disable_aspm(void *);
int rtwn8723be_netbsd_enable_aspm(void *);

int rtwn8723be_netbsd_read_cr(void *, uint8_t *);
int rtwn8723be_netbsd_check_pcie_dma_hang(void *, bool *);
int rtwn8723be_netbsd_reset_pcie_interface_dma(void *, bool);
int rtwn8723be_netbsd_poweroff_adapter(void *);

void rtwn8723be_netbsd_irq_set_dispatch(struct rtwn8723be_softc *,
    const struct rtwn8723be_irq_dispatch *, void *);
int rtwn8723be_netbsd_establish_irq(void *);
void rtwn8723be_netbsd_disestablish_irq(struct rtwn8723be_softc *);
int rtwn8723be_netbsd_enable_interrupt(void *);
int rtwn8723be_netbsd_disable_interrupt(void *);

extern const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops;

#endif /* _RTWN8723BE_NETBSD_H_ */
