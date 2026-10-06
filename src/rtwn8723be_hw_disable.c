/* SPDX-License-Identifier: GPL-2.0 */
/* Copyright(c) 2009-2014 Realtek Corporation. */
/* Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab rtl8723be/{hw,led}.c. */
#include "rtwn8723be_hw_disable.h"

#define R23HD_REG_FWHW_TXQ_CTRL 0x420U
#define R23HD_REG_TBTT_PROHIBIT 0x540U
#define R23HD_REG_BCN_CTRL 0x550U
#define R23HD_REG_BCNTCFG 0x510U
#define R23HD_MSR 0x102U
#define R23HD_REG_LEDCFG1 0x4dU
#define R23HD_REG_LEDCFG2 0x4eU
#define R23HD_REG_MAC_PINMUX_CFG 0x43U
#define R23HD_RF_CHANGE_BY_PS (UINT32_C(1) << 29)
#define R23HD_HALT_NIC (UINT32_C(1) << 3)
#define R23HD_MAC_NOLINK 0U
#define R23HD_LED_GPIO0 0U
#define R23HD_LED_LED0 1U
#define R23HD_LED_LED1 2U

struct disable_work {
    const struct rtwn8723be_hw_disable_io *io;
    void *arg;
    int error;
};
static bool
disable_ready(struct disable_work *hw)
{
    if (hw->error != 0)
        return false;
    if (!hw->io->ready(hw->arg)) {
        hw->error = ENXIO;
        return false;
    }
    return true;
}
static uint8_t
disable_read(struct disable_work *hw, uint32_t reg)
{
    uint8_t value = 0;
    if (disable_ready(hw))
        hw->error = hw->io->read_1(hw->arg, reg, &value);
    return value;
}
static void
disable_write(struct disable_work *hw, uint32_t reg, uint8_t value)
{
    if (disable_ready(hw))
        hw->error = hw->io->write_1(hw->arg, reg, value);
}
static void
disable_led_on(struct disable_work *hw, uint8_t pin)
{
    uint8_t value;
    if (pin == R23HD_LED_LED0) {
        value = disable_read(hw, R23HD_REG_LEDCFG2);
        value &= (uint8_t)~(1U << 6);
        disable_write(hw, R23HD_REG_LEDCFG2,
            (uint8_t)((value & 0xf0U) | (1U << 5)));
    } else if (pin == R23HD_LED_LED1) {
        value = disable_read(hw, R23HD_REG_LEDCFG1);
        disable_write(hw, R23HD_REG_LEDCFG1, value & 0x10U);
    }
}
static void
disable_led_off(struct disable_work *hw, uint8_t pin, bool opendrain)
{
    uint8_t value = disable_read(hw, R23HD_REG_LEDCFG2);
    if (pin == R23HD_LED_LED0) {
        value &= 0xf0U;
        if (opendrain) {
            value &= 0x90U;
            disable_write(hw, R23HD_REG_LEDCFG2, value | (1U << 3));
            value = disable_read(hw, R23HD_REG_MAC_PINMUX_CFG);
            disable_write(hw, R23HD_REG_MAC_PINMUX_CFG, value & 0xfeU);
        } else {
            value &= (uint8_t)~(1U << 6);
            disable_write(hw, R23HD_REG_LEDCFG2,
                (uint8_t)(value | (1U << 3) | (1U << 5)));
        }
    } else if (pin == R23HD_LED_LED1) {
        value = disable_read(hw, R23HD_REG_LEDCFG1);
        disable_write(hw, R23HD_REG_LEDCFG1,
            (uint8_t)((value & 0x10U) | (1U << 3)));
    }
}
static void
disable_media(struct disable_work *hw, struct rtwn8723be_hw_disable_state *state,
    const struct rtwn8723be_hw_disable_inputs *input)
{
    uint8_t msr, value, bcn;
    msr = disable_read(hw, R23HD_MSR) & 0xfcU;
    value = disable_read(hw, R23HD_REG_FWHW_TXQ_CTRL + 2U);
    disable_write(hw, R23HD_REG_FWHW_TXQ_CTRL + 2U,
        value & (uint8_t)~(1U << 6));
    disable_write(hw, R23HD_REG_TBTT_PROHIBIT + 1U, 0x64U);
    value = disable_read(hw, R23HD_REG_TBTT_PROHIBIT + 2U);
    disable_write(hw, R23HD_REG_TBTT_PROHIBIT + 2U,
        value & (uint8_t)~1U);
    bcn = state->bcn_ctrl & (uint8_t)~(1U << 1);
    disable_write(hw, R23HD_REG_BCN_CTRL, bcn);
    if (hw->error == 0)
        state->bcn_ctrl = bcn;
    disable_write(hw, R23HD_MSR, msr);
    /* LED_CTL_NO_LINK calls sw_led_on; high RF-off reasons suppress it. */
    if (input->rfoff_reason <= R23HD_RF_CHANGE_BY_PS)
        disable_led_on(hw, input->led_pin);
    disable_write(hw, R23HD_REG_BCNTCFG + 1U, 0x66U);
}
int
rtwn8723be_hw_disable(const struct rtwn8723be_hw_disable_io *io, void *arg,
    struct rtwn8723be_hw_disable_state *state,
    const struct rtwn8723be_hw_disable_inputs *input)
{
    struct disable_work hw;
    int first;
    if (io == NULL || state == NULL || input == NULL)
        return EINVAL;
    if (io->ready == NULL || io->read_1 == NULL || io->write_1 == NULL ||
        io->poweroff == NULL || !input->state_valid)
        return ENXIO;
    if (!input->rf_idle)
        return EBUSY;
    if (input->led_pin > R23HD_LED_LED1)
        return EINVAL;
    hw.io = io;
    hw.arg = arg;
    hw.error = 0;
    if (!disable_ready(&hw))
        return hw.error;
    state->poweroff_attempted = state->powered_off = false;
    state->last_error = state->poweroff_error = 0;
    state->mac_link_state = R23HD_MAC_NOLINK;
    disable_media(&hw, state, input);
    first = hw.error;
    if (input->driver_is_goingto_unload ||
        input->rfoff_reason > R23HD_RF_CHANGE_BY_PS) {
        /* Independent shutdown action after a failed fallible media step. */
        hw.error = 0;
        disable_led_off(&hw, input->led_pin, input->led_opendrain);
        if (first == 0)
            first = hw.error;
    }
    state->cur_ps_level |= R23HD_HALT_NIC;
    if (io->ready(arg)) {
        state->poweroff_attempted = true;
        state->poweroff_error = io->poweroff(arg);
        state->powered_off = state->poweroff_error == 0;
    } else {
        state->poweroff_error = ENXIO;
    }
    if (first == 0)
        first = state->poweroff_error;
    state->last_error = first;
    /* get_btc_status is the frozen true HAL capability, not EFUSE BT presence. */
    return first;
}
