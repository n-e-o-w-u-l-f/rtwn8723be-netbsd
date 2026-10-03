#include <errno.h>
#include <stddef.h>

#include "rtwn8723be_linux_state.h"

#define R23BE_REQUIRE(op) do { if ((op) == NULL) return ENOSYS; } while (0)
static int
rtwn8723be_probe_ops_ready(const struct rtwn8723be_linux_ops *ops)
{
    if (ops->pci_enable == NULL ||
        ops->dma_configure == NULL ||
        ops->pci_set_master == NULL ||
        ops->alloc_softc == NULL ||
        ops->map_bar == NULL ||
        ops->pci_prepare_d0 == NULL ||
        ops->find_adapter == NULL ||
        ops->init_io == NULL ||
        ops->read_eeprom_info == NULL ||
        ops->init_sw_vars == NULL ||
        ops->init_leds == NULL ||
        ops->init_aspm == NULL ||
        ops->init_core == NULL ||
        ops->init_pci_rings == NULL ||
        ops->register_ieee80211 == NULL ||
        ops->init_rfkill == NULL ||
        ops->establish_irq == NULL)
        return ENOSYS;
    return 0;
}

static int
rtwn8723be_hw_ops_ready(const struct rtwn8723be_linux_ops *ops)
{
    if (ops->disable_aspm == NULL ||
        ops->read_cr == NULL ||
        ops->check_pcie_dma_hang == NULL ||
        ops->reset_pcie_interface_dma == NULL ||
        ops->poweroff_adapter == NULL ||
        ops->init_mac == NULL ||
        ops->sys_cfg_clear_bit7 == NULL ||
        ops->download_firmware == NULL ||
        ops->phy_mac_config == NULL ||
        ops->rcr_postprocess == NULL ||
        ops->phy_bb_config == NULL ||
        ops->phy_rf_config == NULL ||
        ops->rf_channel_state_init == NULL ||
        ops->hw_configure == NULL ||
        ops->cam_reset_all == NULL ||
        ops->enable_hw_security == NULL ||
        ops->set_mac_address == NULL ||
        ops->enable_aspm_backdoor == NULL ||
        ops->enable_aspm == NULL ||
        ops->bt_hw_init == NULL ||
        ops->rf_calibration == NULL ||
        ops->set_nav_upper_235 == NULL ||
        ops->release_rx_dma == NULL ||
        ops->release_pcie_dma == NULL ||
        ops->dm_init == NULL)
        return ENOSYS;
    return 0;
}

static int
rtwn8723be_stop_ops_ready(const struct rtwn8723be_linux_ops *ops)
{
    /* No STOPPING transition until every required teardown step exists. */
    if (ops->bt_halt_deinit == NULL ||
        ops->mark_hal_stop == NULL ||
        ops->disable_interrupt == NULL ||
        ops->wait_rf_change_idle == NULL ||
        ops->hw_disable == NULL ||
        ops->enable_aspm == NULL)
        return ENOSYS;
    return 0;
}

static int
rtwn8723be_start_ops_ready(const struct rtwn8723be_linux_ops *ops)
{
    if (ops->reset_trx_ring == NULL ||
        ops->bt_prepare == NULL ||
        ops->set_retry_limit == NULL ||
        ops->enable_interrupt == NULL ||
        ops->init_rx_config == NULL ||
        ops->mark_hal_start == NULL)
        return ENOSYS;
    return rtwn8723be_hw_ops_ready(ops);
}

#define R23BE_CALL(stage_id, op, ...) do { \
    R23BE_REQUIRE(op); \
    state->stage = (stage_id); \
    error = (op)(__VA_ARGS__); \
    if (error != 0) \
        goto fail; \
} while (0)


int
rtwn8723be_linux_probe(void *ctx, struct rtwn8723be_linux_state *state,
    const struct rtwn8723be_linux_ops *ops)
{
    int error = 0;

    if (state == NULL || ops == NULL)
        return EINVAL;

    error = rtwn8723be_probe_ops_ready(ops);
    if (error != 0)
        return error;

    state->stage = R23BE_STAGE_IDLE;
    state->started = false;
    state->fw_ready = false;
    state->mac_func_enable = false;

    R23BE_CALL(R23BE_STAGE_PCI_ENABLE, ops->pci_enable, ctx);
    R23BE_CALL(R23BE_STAGE_DMA_CONFIG, ops->dma_configure, ctx);
    R23BE_CALL(R23BE_STAGE_BUS_MASTER, ops->pci_set_master, ctx);
    R23BE_CALL(R23BE_STAGE_SOFTC_ALLOC, ops->alloc_softc, ctx);
    R23BE_CALL(R23BE_STAGE_BAR_MAP, ops->map_bar, ctx);
    R23BE_CALL(R23BE_STAGE_PCI_D0, ops->pci_prepare_d0, ctx);
    R23BE_CALL(R23BE_STAGE_ADAPTER_IDENTIFY, ops->find_adapter, ctx);
    R23BE_CALL(R23BE_STAGE_IO_INIT, ops->init_io, ctx);
    R23BE_CALL(R23BE_STAGE_EEPROM, ops->read_eeprom_info, ctx);
    R23BE_CALL(R23BE_STAGE_SW_VARS, ops->init_sw_vars, ctx);
    R23BE_CALL(R23BE_STAGE_LEDS, ops->init_leds, ctx);
    R23BE_CALL(R23BE_STAGE_ASPM_INIT, ops->init_aspm, ctx);
    R23BE_CALL(R23BE_STAGE_CORE_INIT, ops->init_core, ctx);

    /*
     * Linux rtl_pci_init() allocates and initializes all TX/RX rings before
     * rtl_pci_start() calls rtl8723be_hw_init().  This ordering is mandatory:
     * _rtl8723be_init_mac() programs the ring DMA addresses into hardware.
     */
    R23BE_CALL(R23BE_STAGE_PCI_RINGS, ops->init_pci_rings, ctx);

    R23BE_CALL(R23BE_STAGE_IEEE80211_REGISTER,
        ops->register_ieee80211, ctx);
    R23BE_CALL(R23BE_STAGE_RFKILL, ops->init_rfkill, ctx);
    R23BE_CALL(R23BE_STAGE_IRQ_ESTABLISH, ops->establish_irq, ctx);

    state->stage = R23BE_STAGE_PROBED;
    return 0;

fail:
    return error != 0 ? error : EIO;
}

int
rtwn8723be_linux_hw_init(void *ctx, struct rtwn8723be_linux_state *state,
    const struct rtwn8723be_linux_ops *ops)
{
    uint8_t cr;
    bool dma_hang;
    int error = 0;

    if (state == NULL || ops == NULL)
        return EINVAL;

    error = rtwn8723be_hw_ops_ready(ops);
    if (error != 0)
        return error;

    state->being_init_adapter = true;
    state->fw_ready = false;

    R23BE_CALL(R23BE_STAGE_DISABLE_ASPM, ops->disable_aspm, ctx);

    R23BE_REQUIRE(ops->read_cr);
    state->stage = R23BE_STAGE_DETECT_MAC_STATE;
    error = ops->read_cr(ctx, &cr);
    if (error != 0)
        goto fail;

    if (cr != 0 && cr != 0xea)
        state->mac_func_enable = true;
    else
        state->mac_func_enable = false;

    R23BE_REQUIRE(ops->check_pcie_dma_hang);
    dma_hang = false;
    error = ops->check_pcie_dma_hang(ctx, &dma_hang);
    if (error != 0)
        goto fail;

    if (dma_hang) {
        R23BE_CALL(R23BE_STAGE_PCIE_DMA_RECOVERY,
            ops->reset_pcie_interface_dma, ctx, state->mac_func_enable);
        state->mac_func_enable = false;
    }

    if (state->mac_func_enable) {
        R23BE_CALL(R23BE_STAGE_POWER_OFF_OLD_STATE,
            ops->poweroff_adapter, ctx);
        state->mac_func_enable = false;
    }

    R23BE_CALL(R23BE_STAGE_INIT_MAC, ops->init_mac, ctx);
    R23BE_CALL(R23BE_STAGE_INIT_MAC, ops->sys_cfg_clear_bit7, ctx);

    R23BE_CALL(R23BE_STAGE_FIRMWARE_DOWNLOAD,
        ops->download_firmware, ctx);
    state->fw_ready = true;

    R23BE_CALL(R23BE_STAGE_PHY_MAC, ops->phy_mac_config, ctx);
    R23BE_CALL(R23BE_STAGE_RCR_FIXUP, ops->rcr_postprocess, ctx);
    R23BE_CALL(R23BE_STAGE_PHY_BB, ops->phy_bb_config, ctx);
    R23BE_CALL(R23BE_STAGE_PHY_RF, ops->phy_rf_config, ctx);
    R23BE_CALL(R23BE_STAGE_RF_CHANNEL_STATE,
        ops->rf_channel_state_init, ctx);

    R23BE_CALL(R23BE_STAGE_HW_CONFIGURE, ops->hw_configure, ctx);
    state->mac_func_enable = true;

    R23BE_CALL(R23BE_STAGE_SECURITY, ops->cam_reset_all, ctx);
    R23BE_CALL(R23BE_STAGE_SECURITY, ops->enable_hw_security, ctx);
    R23BE_CALL(R23BE_STAGE_SECURITY, ops->set_mac_address, ctx);

    R23BE_CALL(R23BE_STAGE_ASPM_RESTORE,
        ops->enable_aspm_backdoor, ctx);
    R23BE_CALL(R23BE_STAGE_ASPM_RESTORE, ops->enable_aspm, ctx);

    R23BE_CALL(R23BE_STAGE_BT_HW, ops->bt_hw_init, ctx);
    R23BE_CALL(R23BE_STAGE_RF_CALIBRATION, ops->rf_calibration, ctx);

    /* Linux writes ((30000 + 127) / 128) == 235 to REG_NAV_UPPER. */
    R23BE_CALL(R23BE_STAGE_NAV_UPPER, ops->set_nav_upper_235, ctx);

    R23BE_CALL(R23BE_STAGE_DMA_RELEASE, ops->release_rx_dma, ctx);
    R23BE_CALL(R23BE_STAGE_DMA_RELEASE, ops->release_pcie_dma, ctx);

    R23BE_CALL(R23BE_STAGE_DM_INIT, ops->dm_init, ctx);

    state->being_init_adapter = false;
    return 0;

fail:
    state->being_init_adapter = false;
    return error != 0 ? error : EIO;
}

int
rtwn8723be_linux_adapter_start(void *ctx,
    struct rtwn8723be_linux_state *state,
    const struct rtwn8723be_linux_ops *ops)
{
    int error;

    if (state == NULL || ops == NULL)
        return EINVAL;
    if (state->started || state->stage == R23BE_STAGE_RUNNING)
        return EALREADY;
    if (state->stage != R23BE_STAGE_PROBED &&
        state->stage != R23BE_STAGE_STOPPED)
        return EAGAIN;

    error = rtwn8723be_start_ops_ready(ops);
    if (error != 0)
        return error;

    R23BE_CALL(R23BE_STAGE_RESET_RINGS, ops->reset_trx_ring, ctx);
    R23BE_CALL(R23BE_STAGE_BT_PREPARE, ops->bt_prepare, ctx);

    error = rtwn8723be_linux_hw_init(ctx, state, ops);
    if (error != 0)
        return error;

    R23BE_CALL(R23BE_STAGE_RETRY_LIMIT, ops->set_retry_limit, ctx);
    R23BE_CALL(R23BE_STAGE_IRQ_ENABLE, ops->enable_interrupt, ctx);
    R23BE_CALL(R23BE_STAGE_RX_CONFIG, ops->init_rx_config, ctx);
    R23BE_CALL(R23BE_STAGE_RUNNING, ops->mark_hal_start, ctx);

    state->started = true;
    return 0;

fail:
    return error != 0 ? error : EIO;
}

int
rtwn8723be_linux_adapter_stop(void *ctx,
    struct rtwn8723be_linux_state *state,
    const struct rtwn8723be_linux_ops *ops)
{
    int error = 0;

    if (state == NULL || ops == NULL)
        return EINVAL;
    if (!state->started || state->stage != R23BE_STAGE_RUNNING)
        return EAGAIN;
    error = rtwn8723be_stop_ops_ready(ops);
    if (error != 0)
        return error;

    state->stage = R23BE_STAGE_STOPPING;

    R23BE_CALL(R23BE_STAGE_STOPPING, ops->bt_halt_deinit, ctx);
    R23BE_CALL(R23BE_STAGE_STOPPING, ops->mark_hal_stop, ctx);
    R23BE_CALL(R23BE_STAGE_STOPPING, ops->disable_interrupt, ctx);
    R23BE_CALL(R23BE_STAGE_STOPPING, ops->wait_rf_change_idle, ctx);
    R23BE_CALL(R23BE_STAGE_STOPPING, ops->hw_disable, ctx);
    R23BE_CALL(R23BE_STAGE_STOPPING, ops->enable_aspm, ctx);

    state->started = false;
    state->mac_func_enable = false;
    state->fw_ready = false;
    state->stage = R23BE_STAGE_STOPPED;
    return 0;

fail:
    return error != 0 ? error : EIO;
}
