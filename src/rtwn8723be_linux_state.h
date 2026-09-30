#ifndef _RTWN8723BE_LINUX_STATE_H_
#define _RTWN8723BE_LINUX_STATE_H_

#include <stdbool.h>
#include <stdint.h>

enum rtwn8723be_linux_stage {
    R23BE_STAGE_IDLE = 0,
    R23BE_STAGE_RESET_RINGS,
    R23BE_STAGE_BT_PREPARE,
    R23BE_STAGE_DISABLE_ASPM,
    R23BE_STAGE_DETECT_MAC_STATE,
    R23BE_STAGE_PCIE_DMA_RECOVERY,
    R23BE_STAGE_POWER_OFF_OLD_STATE,
    R23BE_STAGE_INIT_MAC,
    R23BE_STAGE_FIRMWARE_DOWNLOAD,
    R23BE_STAGE_PHY_MAC,
    R23BE_STAGE_RCR_FIXUP,
    R23BE_STAGE_PHY_BB,
    R23BE_STAGE_PHY_RF,
    R23BE_STAGE_RF_CHANNEL_STATE,
    R23BE_STAGE_HW_CONFIGURE,
    R23BE_STAGE_SECURITY,
    R23BE_STAGE_ASPM_RESTORE,
    R23BE_STAGE_BT_HW,
    R23BE_STAGE_RF_CALIBRATION,
    R23BE_STAGE_NAV_UPPER,
    R23BE_STAGE_DMA_RELEASE,
    R23BE_STAGE_DM_INIT,
    R23BE_STAGE_RETRY_LIMIT,
    R23BE_STAGE_IRQ_ENABLE,
    R23BE_STAGE_RX_CONFIG,
    R23BE_STAGE_RUNNING,
    R23BE_STAGE_STOPPING,
    R23BE_STAGE_STOPPED
};

struct rtwn8723be_linux_state {
    enum rtwn8723be_linux_stage stage;
    bool being_init_adapter;
    bool mac_func_enable;
    bool fw_ready;
    bool started;
};

struct rtwn8723be_linux_ops {
    int (*reset_trx_ring)(void *);
    int (*bt_prepare)(void *);

    int (*disable_aspm)(void *);
    int (*read_cr)(void *, uint8_t *);
    int (*check_pcie_dma_hang)(void *, bool *);
    int (*reset_pcie_interface_dma)(void *, bool);
    int (*poweroff_adapter)(void *);
    int (*init_mac)(void *);

    int (*sys_cfg_clear_bit7)(void *);
    int (*download_firmware)(void *);
    int (*phy_mac_config)(void *);
    int (*rcr_postprocess)(void *);
    int (*phy_bb_config)(void *);
    int (*phy_rf_config)(void *);
    int (*rf_channel_state_init)(void *);
    int (*hw_configure)(void *);
    int (*cam_reset_all)(void *);
    int (*enable_hw_security)(void *);
    int (*set_mac_address)(void *);

    int (*enable_aspm_backdoor)(void *);
    int (*enable_aspm)(void *);
    int (*bt_hw_init)(void *);
    int (*rf_calibration)(void *);
    int (*set_nav_upper_235)(void *);

    int (*release_rx_dma)(void *);
    int (*release_pcie_dma)(void *);
    int (*dm_init)(void *);

    int (*set_retry_limit)(void *);
    int (*enable_interrupt)(void *);
    int (*init_rx_config)(void *);
    int (*mark_hal_start)(void *);

    int (*bt_halt_deinit)(void *);
    int (*mark_hal_stop)(void *);
    int (*disable_interrupt)(void *);
    int (*wait_rf_change_idle)(void *);
    int (*hw_disable)(void *);
};

int rtwn8723be_linux_hw_init(void *, struct rtwn8723be_linux_state *,
    const struct rtwn8723be_linux_ops *);
int rtwn8723be_linux_adapter_start(void *, struct rtwn8723be_linux_state *,
    const struct rtwn8723be_linux_ops *);
int rtwn8723be_linux_adapter_stop(void *, struct rtwn8723be_linux_state *,
    const struct rtwn8723be_linux_ops *);

#endif
