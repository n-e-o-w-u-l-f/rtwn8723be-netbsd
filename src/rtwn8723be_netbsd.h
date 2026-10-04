#ifndef _RTWN8723BE_NETBSD_H_
#define _RTWN8723BE_NETBSD_H_

#include <sys/types.h>
#include <sys/device.h>
#include <sys/bus.h>

#include <dev/pci/pcireg.h>
#include <dev/pci/pcivar.h>

#include <net/if.h>
#include <net/if_ether.h>
#include <net80211/ieee80211_var.h>

#include "rtwn8723be_f16_1.h"
#include "rtwn8723be_linux_state.h"
#include "rtwn8723be_phy_exec.h"

#define RTWN8723BE_PCI_BAR_MMIO        0x18
#define RTWN8723BE_DMA_MAXADDR         0xffffffffULL
#define RTWN8723BE_ANT_MAIN            0
#define RTWN8723BE_ANT_AUX             1
/* Linux enum bt_ant_num: ANT_X2=0, ANT_X1=1. */
#define RTWN8723BE_ANT_X2              0
#define RTWN8723BE_ANT_X1              1
#define RTWN8723BE_LED_PIN_GPIO0       0
#define RTWN8723BE_LED_PIN_LED0        1
#define RTWN8723BE_LED_PIN_LED1        2

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
    struct ethercom sc_ec;
    struct ieee80211com sc_ic;
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

    /*
     * Native attach snapshots the pre-probe PCI configuration before any
     * enable/D0/ASPM mutation. Failed probe restores exactly these values.
     */
    pcireg_t sc_pci_command_initial;
    uint8_t sc_pci_clockreg_initial;
    uint8_t sc_pci_pmreg_initial;
    pcireg_t sc_pci_powerstate_initial;
    bool sc_initial_pci_saved;

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
    uint32_t sc_mac_rx_conf;
    uint8_t sc_retry_limit;
    uint8_t sc_bcn_ctrl_val;
    uint32_t sc_transmit_config;
    const char *sc_firmware_name;

    uint8_t sc_efuse_map[R23BE_EFUSE_HWSET_MAX_SIZE];
    uint16_t sc_eeprom_id;
    uint16_t sc_eeprom_vid;
    uint16_t sc_eeprom_did;
    uint16_t sc_eeprom_svid;
    uint16_t sc_eeprom_smid;
    uint8_t sc_macaddr[6];
    uint8_t sc_package_type;
    bool sc_package_valid;

    /* Invalid until the hardware/EFUSE cut, board and RF paths are proved. */
    struct rtwn8723be_phy_identity sc_phy_identity;
    uint8_t sc_rf_path_count;
    bool sc_phy_identity_valid;
    bool sc_rf_path_count_valid;
    bool sc_efuse_autoload_ok;
    bool sc_boot_from_efuse;
    bool sc_btcoexist;
    uint8_t sc_btdm_ant_num;
    uint8_t sc_single_ant_path;
    uint8_t sc_btdm_ant_pos;
    uint8_t sc_ant_pos_registry_ctrl;
    bool sc_bt_ant_valid;
    bool sc_bt_stop_coex_dm;

    bool sc_up_first_time;
    bool sc_led_opendrain;
    uint8_t sc_sw_led0;
    uint8_t sc_sw_led1;
    bool sc_core_initialized;
    bool sc_hal_started; /* pinned Linux rtl_hal.state START/STOP */
    uint32_t sc_rfoff_reason;
};

void rtwn8723be_netbsd_context_init(struct rtwn8723be_softc *,
    device_t, const struct pci_attach_args *);

uint8_t rtwn8723be_read_1(struct rtwn8723be_softc *, bus_size_t);
uint16_t rtwn8723be_read_2(struct rtwn8723be_softc *, bus_size_t);
uint32_t rtwn8723be_read_4(struct rtwn8723be_softc *, bus_size_t);
void rtwn8723be_write_1(struct rtwn8723be_softc *, bus_size_t, uint8_t);
void rtwn8723be_write_2(struct rtwn8723be_softc *, bus_size_t, uint16_t);
void rtwn8723be_write_4(struct rtwn8723be_softc *, bus_size_t, uint32_t);
uint32_t rtwn8723be_netbsd_get_bbreg(struct rtwn8723be_softc *,
    bus_size_t, uint32_t);
void rtwn8723be_netbsd_set_bbreg(struct rtwn8723be_softc *,
    bus_size_t, uint32_t, uint32_t);
int rtwn8723be_netbsd_phy_bb_write(void *, uint32_t, uint32_t);
int rtwn8723be_netbsd_phy_agc_write(void *, uint32_t, uint32_t);

int rtwn8723be_netbsd_pci_enable(void *);
int rtwn8723be_netbsd_dma_configure(void *);
void rtwn8723be_netbsd_dma_release(struct rtwn8723be_softc *);
int rtwn8723be_netbsd_pci_set_master(void *);
int rtwn8723be_netbsd_alloc_softc(void *);
int rtwn8723be_netbsd_map_bar(void *);
int rtwn8723be_netbsd_pci_prepare_d0(void *);
int rtwn8723be_netbsd_find_adapter(void *);
int rtwn8723be_netbsd_init_io(void *);
int rtwn8723be_netbsd_read_eeprom_info(void *);
int rtwn8723be_netbsd_init_sw_vars(void *);
int rtwn8723be_netbsd_init_leds(void *);
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
int rtwn8723be_netbsd_bt_power_on_setting(struct rtwn8723be_softc *);
int rtwn8723be_netbsd_bt_preload_firmware(struct rtwn8723be_softc *);
int rtwn8723be_netbsd_init_mac(void *);
int rtwn8723be_netbsd_sys_cfg_clear_bit7(void *);
int rtwn8723be_netbsd_download_firmware(void *);
int rtwn8723be_netbsd_phy_mac_config(void *);
int rtwn8723be_netbsd_rcr_postprocess(void *);
int rtwn8723be_netbsd_cam_reset_all(void *);
int rtwn8723be_netbsd_set_mac_address(void *);
int rtwn8723be_netbsd_set_nav_upper_235(void *);
int rtwn8723be_netbsd_release_rx_dma(void *);
int rtwn8723be_netbsd_release_pcie_dma(void *);
int rtwn8723be_netbsd_set_retry_limit(void *);
int rtwn8723be_netbsd_init_rx_config(void *);
int rtwn8723be_netbsd_hw_configure(void *);
int rtwn8723be_netbsd_mark_hal_start(void *);
int rtwn8723be_netbsd_mark_hal_stop(void *);

void rtwn8723be_netbsd_irq_set_dispatch(struct rtwn8723be_softc *,
    const struct rtwn8723be_irq_dispatch *, void *);
int rtwn8723be_netbsd_establish_irq(void *);
void rtwn8723be_netbsd_disestablish_irq(struct rtwn8723be_softc *);
int rtwn8723be_netbsd_enable_interrupt(void *);
int rtwn8723be_netbsd_disable_interrupt(void *);

extern const struct rtwn8723be_linux_ops rtwn8723be_netbsd_ops;

#endif /* _RTWN8723BE_NETBSD_H_ */
