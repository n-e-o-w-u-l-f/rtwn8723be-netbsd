/* SPDX-License-Identifier: GPL-2.0 */
/* Frozen hw.c/led.c functions with test-only Linux ABI shims. */
#include "hw_disable_test_iface.h"
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
enum led_ctl_mode {
	LED_CTL_POWER_ON = 1,
	LED_CTL_LINK = 2,
	LED_CTL_NO_LINK = 3,
	LED_CTL_TX = 4,
	LED_CTL_RX = 5,
	LED_CTL_SITE_SURVEY = 6,
	LED_CTL_POWER_OFF = 7,
	LED_CTL_START_TO_LINK = 8,
	LED_CTL_START_WPS = 9,
	LED_CTL_STOP_WPS = 10,
};
enum rtl_led_pin {
	LED_PIN_GPIO0,
	LED_PIN_LED0,
	LED_PIN_LED1,
	LED_PIN_LED2
};
enum rtl_link_state {
	MAC80211_NOLINK = 0,
	MAC80211_LINKING = 1,
	MAC80211_LINKED = 2,
	MAC80211_LINKED_SCANNING = 3,
};
enum nl80211_iftype { NL80211_IFTYPE_UNSPECIFIED, NL80211_IFTYPE_ADHOC,
    NL80211_IFTYPE_STATION, NL80211_IFTYPE_AP,
    NL80211_IFTYPE_MESH_POINT = 7 };
#define BIT(n) (UINT32_C(1) << (n))
#define REG_FWHW_TXQ_CTRL 0x420
#define REG_TBTT_PROHIBIT 0x540
#define REG_BCN_CTRL 0x550
#define REG_BCNTCFG 0x510
#define REG_LEDCFG1 0x4d
#define REG_LEDCFG2 0x4e
#define REG_MAC_PINMUX_CFG 0x43
#define MSR 0x102
#define MSR_NOLINK 0
#define MSR_ADHOC 1
#define MSR_INFRA 2
#define MSR_AP 3
#define RF_CHANGE_BY_PS BIT(29)
#define RT_RF_OFF_LEVL_HALT_NIC BIT(3)
#define RT_SET_PS_LEVEL(ps, flag) ((ps)->cur_ps_level |= (flag))
struct ieee80211_hw;
struct rtl_ps_ctl { u32 rfoff_reason, cur_ps_level; };
struct rtl_mac { u8 link_state; };
struct rtl_pci { u8 reg_bcn_ctrl_val; };
struct rtl_hal_ops {
    void (*led_control)(struct ieee80211_hw *, enum led_ctl_mode);
    bool (*get_btc_status)(void);
};
struct rtl_hal_cfg { const struct rtl_hal_ops *ops; };
struct rtl_priv {
    void *backend;
    struct rtl_ps_ctl psc;
    struct rtl_mac mac80211;
    struct rtl_pci pci;
    struct { bool driver_is_goingto_unload; } rtlhal;
    struct { bool iqk_initialized; } phy;
    struct { bool led_opendrain; enum rtl_led_pin sw_led0; } ledctl;
    const struct rtl_hal_cfg *cfg;
};
struct ieee80211_hw { struct rtl_priv *priv; };
#define rtl_priv(hw) ((hw)->priv)
#define rtl_psc(priv) (&(priv)->psc)
#define rtl_mac(priv) (&(priv)->mac80211)
#define rtl_pcipriv(hw) (&(hw)->priv->pci)
#define rtl_pcidev(priv) (priv)
#define rtl_read_byte(priv, reg) disable_raw_read((priv)->backend, (reg))
#define rtl_write_byte(priv, reg, val) disable_raw_write((priv)->backend, (reg), (val))
#define rtl_dbg(...) ((void)0)
#define pr_err(...) ((void)0)
static void _rtl8723be_poweroff_adapter(struct ieee80211_hw *hw)
{ disable_raw_poweroff(hw->priv->backend); }

void rtl8723be_sw_led_on(struct ieee80211_hw *hw, enum rtl_led_pin pin)
{
	u8 ledcfg;
	struct rtl_priv *rtlpriv = rtl_priv(hw);

	rtl_dbg(rtlpriv, COMP_LED, DBG_LOUD,
		"LedAddr:%X ledpin=%d\n", REG_LEDCFG2, pin);

	switch (pin) {
	case LED_PIN_GPIO0:
		break;
	case LED_PIN_LED0:
		ledcfg = rtl_read_byte(rtlpriv, REG_LEDCFG2);
		ledcfg &= ~BIT(6);
		rtl_write_byte(rtlpriv, REG_LEDCFG2, (ledcfg & 0xf0) | BIT(5));
		break;
	case LED_PIN_LED1:
		ledcfg = rtl_read_byte(rtlpriv, REG_LEDCFG1);
		rtl_write_byte(rtlpriv, REG_LEDCFG1, ledcfg & 0x10);
		break;
	default:
		pr_err("switch case %#x not processed\n", pin);
		break;
	}
}

void rtl8723be_sw_led_off(struct ieee80211_hw *hw, enum rtl_led_pin pin)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u8 ledcfg;

	rtl_dbg(rtlpriv, COMP_LED, DBG_LOUD,
		"LedAddr:%X ledpin=%d\n", REG_LEDCFG2, pin);

	ledcfg = rtl_read_byte(rtlpriv, REG_LEDCFG2);

	switch (pin) {
	case LED_PIN_GPIO0:
		break;
	case LED_PIN_LED0:
		ledcfg &= 0xf0;
		if (rtlpriv->ledctl.led_opendrain) {
			ledcfg &= 0x90; /* Set to software control. */
			rtl_write_byte(rtlpriv, REG_LEDCFG2, (ledcfg|BIT(3)));
			ledcfg = rtl_read_byte(rtlpriv, REG_MAC_PINMUX_CFG);
			ledcfg &= 0xFE;
			rtl_write_byte(rtlpriv, REG_MAC_PINMUX_CFG, ledcfg);
		} else {
			ledcfg &= ~BIT(6);
			rtl_write_byte(rtlpriv, REG_LEDCFG2,
				       (ledcfg | BIT(3) | BIT(5)));
		}
		break;
	case LED_PIN_LED1:
		ledcfg = rtl_read_byte(rtlpriv, REG_LEDCFG1);
		ledcfg &= 0x10; /* Set to software control. */
		rtl_write_byte(rtlpriv, REG_LEDCFG1, ledcfg|BIT(3));

		break;
	default:
		pr_err("switch case %#x not processed\n", pin);
		break;
	}
}

static void _rtl8723be_sw_led_control(struct ieee80211_hw *hw,
				      enum led_ctl_mode ledaction)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	enum rtl_led_pin pin0 = rtlpriv->ledctl.sw_led0;

	switch (ledaction) {
	case LED_CTL_POWER_ON:
	case LED_CTL_LINK:
	case LED_CTL_NO_LINK:
		rtl8723be_sw_led_on(hw, pin0);
		break;
	case LED_CTL_POWER_OFF:
		rtl8723be_sw_led_off(hw, pin0);
		break;
	default:
		break;
	}
}

void rtl8723be_led_control(struct ieee80211_hw *hw,
			   enum led_ctl_mode ledaction)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rtl_ps_ctl *ppsc = rtl_psc(rtl_priv(hw));

	if ((ppsc->rfoff_reason > RF_CHANGE_BY_PS) &&
	    (ledaction == LED_CTL_TX ||
	     ledaction == LED_CTL_RX ||
	     ledaction == LED_CTL_SITE_SURVEY ||
	     ledaction == LED_CTL_LINK ||
	     ledaction == LED_CTL_NO_LINK ||
	     ledaction == LED_CTL_START_TO_LINK ||
	     ledaction == LED_CTL_POWER_ON)) {
		return;
	}
	rtl_dbg(rtlpriv, COMP_LED, DBG_LOUD, "ledaction %d,\n", ledaction);
	_rtl8723be_sw_led_control(hw, ledaction);
}

static void _rtl8723be_set_bcn_ctrl_reg(struct ieee80211_hw *hw,
					u8 set_bits, u8 clear_bits)
{
	struct rtl_pci *rtlpci = rtl_pcidev(rtl_pcipriv(hw));
	struct rtl_priv *rtlpriv = rtl_priv(hw);

	rtlpci->reg_bcn_ctrl_val |= set_bits;
	rtlpci->reg_bcn_ctrl_val &= ~clear_bits;

	rtl_write_byte(rtlpriv, REG_BCN_CTRL, (u8)rtlpci->reg_bcn_ctrl_val);
}

static void _rtl8723be_stop_tx_beacon(struct ieee80211_hw *hw)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u8 tmp1byte;

	tmp1byte = rtl_read_byte(rtlpriv, REG_FWHW_TXQ_CTRL + 2);
	rtl_write_byte(rtlpriv, REG_FWHW_TXQ_CTRL + 2, tmp1byte & (~BIT(6)));
	rtl_write_byte(rtlpriv, REG_TBTT_PROHIBIT + 1, 0x64);
	tmp1byte = rtl_read_byte(rtlpriv, REG_TBTT_PROHIBIT + 2);
	tmp1byte &= ~(BIT(0));
	rtl_write_byte(rtlpriv, REG_TBTT_PROHIBIT + 2, tmp1byte);
}

static void _rtl8723be_resume_tx_beacon(struct ieee80211_hw *hw)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u8 tmp1byte;

	tmp1byte = rtl_read_byte(rtlpriv, REG_FWHW_TXQ_CTRL + 2);
	rtl_write_byte(rtlpriv, REG_FWHW_TXQ_CTRL + 2, tmp1byte | BIT(6));
	rtl_write_byte(rtlpriv, REG_TBTT_PROHIBIT + 1, 0xff);
	tmp1byte = rtl_read_byte(rtlpriv, REG_TBTT_PROHIBIT + 2);
	tmp1byte |= BIT(1);
	rtl_write_byte(rtlpriv, REG_TBTT_PROHIBIT + 2, tmp1byte);
}

static void _rtl8723be_enable_bcn_sub_func(struct ieee80211_hw *hw)
{
	_rtl8723be_set_bcn_ctrl_reg(hw, 0, BIT(1));
}

static void _rtl8723be_disable_bcn_sub_func(struct ieee80211_hw *hw)
{
	_rtl8723be_set_bcn_ctrl_reg(hw, BIT(1), 0);
}

static int _rtl8723be_set_media_status(struct ieee80211_hw *hw,
				       enum nl80211_iftype type)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u8 bt_msr = rtl_read_byte(rtlpriv, MSR) & 0xfc;
	enum led_ctl_mode ledaction = LED_CTL_NO_LINK;
	u8 mode = MSR_NOLINK;

	switch (type) {
	case NL80211_IFTYPE_UNSPECIFIED:
		mode = MSR_NOLINK;
		rtl_dbg(rtlpriv, COMP_INIT, DBG_TRACE,
			"Set Network type to NO LINK!\n");
		break;
	case NL80211_IFTYPE_ADHOC:
	case NL80211_IFTYPE_MESH_POINT:
		mode = MSR_ADHOC;
		rtl_dbg(rtlpriv, COMP_INIT, DBG_TRACE,
			"Set Network type to Ad Hoc!\n");
		break;
	case NL80211_IFTYPE_STATION:
		mode = MSR_INFRA;
		ledaction = LED_CTL_LINK;
		rtl_dbg(rtlpriv, COMP_INIT, DBG_TRACE,
			"Set Network type to STA!\n");
		break;
	case NL80211_IFTYPE_AP:
		mode = MSR_AP;
		ledaction = LED_CTL_LINK;
		rtl_dbg(rtlpriv, COMP_INIT, DBG_TRACE,
			"Set Network type to AP!\n");
		break;
	default:
		pr_err("Network type %d not support!\n", type);
		return 1;
	}

	/* MSR_INFRA == Link in infrastructure network;
	 * MSR_ADHOC == Link in ad hoc network;
	 * Therefore, check link state is necessary.
	 *
	 * MSR_AP == AP mode; link state is not cared here.
	 */
	if (mode != MSR_AP && rtlpriv->mac80211.link_state < MAC80211_LINKED) {
		mode = MSR_NOLINK;
		ledaction = LED_CTL_NO_LINK;
	}

	if (mode == MSR_NOLINK || mode == MSR_INFRA) {
		_rtl8723be_stop_tx_beacon(hw);
		_rtl8723be_enable_bcn_sub_func(hw);
	} else if (mode == MSR_ADHOC || mode == MSR_AP) {
		_rtl8723be_resume_tx_beacon(hw);
		_rtl8723be_disable_bcn_sub_func(hw);
	} else {
		rtl_dbg(rtlpriv, COMP_ERR, DBG_WARNING,
			"Set HW_VAR_MEDIA_STATUS: No such media status(%x).\n",
			mode);
	}

	rtl_write_byte(rtlpriv, MSR, bt_msr | mode);
	rtlpriv->cfg->ops->led_control(hw, ledaction);
	if (mode == MSR_AP)
		rtl_write_byte(rtlpriv, REG_BCNTCFG + 1, 0x00);
	else
		rtl_write_byte(rtlpriv, REG_BCNTCFG + 1, 0x66);
	return 0;
}

void rtl8723be_card_disable(struct ieee80211_hw *hw)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rtl_ps_ctl *ppsc = rtl_psc(rtl_priv(hw));
	struct rtl_mac *mac = rtl_mac(rtl_priv(hw));
	enum nl80211_iftype opmode;

	mac->link_state = MAC80211_NOLINK;
	opmode = NL80211_IFTYPE_UNSPECIFIED;
	_rtl8723be_set_media_status(hw, opmode);
	if (rtlpriv->rtlhal.driver_is_goingto_unload ||
	    ppsc->rfoff_reason > RF_CHANGE_BY_PS)
		rtlpriv->cfg->ops->led_control(hw, LED_CTL_POWER_OFF);
	RT_SET_PS_LEVEL(ppsc, RT_RF_OFF_LEVL_HALT_NIC);
	_rtl8723be_poweroff_adapter(hw);

	/* after power off we should do iqk again */
	if (!rtlpriv->cfg->ops->get_btc_status())
		rtlpriv->phy.iqk_initialized = false;
}

static bool rtl8723be_get_btc_status(void)
{
	return true;
}

void disable_oracle(void *backend, struct rtwn8723be_hw_disable_state *state,
    const struct rtwn8723be_hw_disable_inputs *input, bool *iqk_initialized)
{
    static const struct rtl_hal_ops ops = {
        rtl8723be_led_control, rtl8723be_get_btc_status
    };
    static const struct rtl_hal_cfg cfg = { &ops };
    struct rtl_priv priv;
    struct ieee80211_hw hw = { &priv };
    memset(&priv, 0, sizeof(priv));
    priv.backend = backend;
    priv.cfg = &cfg;
    priv.psc.rfoff_reason = input->rfoff_reason;
    priv.psc.cur_ps_level = state->cur_ps_level;
    priv.mac80211.link_state = state->mac_link_state;
    priv.pci.reg_bcn_ctrl_val = state->bcn_ctrl;
    priv.rtlhal.driver_is_goingto_unload = input->driver_is_goingto_unload;
    priv.phy.iqk_initialized = *iqk_initialized;
    priv.ledctl.led_opendrain = input->led_opendrain;
    priv.ledctl.sw_led0 = (enum rtl_led_pin)input->led_pin;
    rtl8723be_card_disable(&hw);
    state->bcn_ctrl = priv.pci.reg_bcn_ctrl_val;
    state->mac_link_state = priv.mac80211.link_state;
    state->cur_ps_level = priv.psc.cur_ps_level;
    state->poweroff_attempted = state->powered_off = true;
    *iqk_initialized = priv.phy.iqk_initialized;
}
