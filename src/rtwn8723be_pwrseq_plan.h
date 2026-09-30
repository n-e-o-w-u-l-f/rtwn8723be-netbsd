/*
 * RTL8723BE power-state machine contract.
 *
 * Hardware transition data is generated from pinned Linux
 * rtlwifi/rtl8723be/pwrseq.h at:
 * fd179f8a05be3ccae366b9b96e176b51fbe54aab
 *
 * The target device is PCIe, but all reference transition entries are kept
 * in rtwn8723be_pwrseq_data.h.  The parser applies the Linux interface mask
 * at runtime rather than deleting USB/SDIO entries by hand.
 */
#ifndef _RTWN8723BE_PWRSEQ_PLAN_H_
#define _RTWN8723BE_PWRSEQ_PLAN_H_

#include <sys/types.h>

#define RTWN8723BE_PWR_INTF_SDIO       0x01
#define RTWN8723BE_PWR_INTF_USB        0x02
#define RTWN8723BE_PWR_INTF_PCI        0x04
#define RTWN8723BE_PWR_INTF_ALL        0x0f

#define RTWN8723BE_PWR_FAB_ALL         0x0f
#define RTWN8723BE_PWR_CUT_TESTCHIP    0x01
#define RTWN8723BE_PWR_CUT_ALL         0xff

#define RTWN8723BE_PWR_READ            0
#define RTWN8723BE_PWR_WRITE           1
#define RTWN8723BE_PWR_POLL            2
#define RTWN8723BE_PWR_DELAY           3
#define RTWN8723BE_PWR_END             4

#define RTWN8723BE_PWR_DELAY_US        0
#define RTWN8723BE_PWR_DELAY_MS        1

#define RTWN8723BE_PWR_BASE_MAC        0
#define RTWN8723BE_PWR_BASE_USB        1
#define RTWN8723BE_PWR_BASE_PCIE       2
#define RTWN8723BE_PWR_BASE_SDIO       3

struct rtwn8723be_softc;

struct rtwn8723be_pwr_step {
    uint16_t offset;
    uint8_t cut_mask;
    uint8_t fab_mask;
    uint8_t intf_mask;
    uint8_t base;
    uint8_t cmd;
    uint8_t mask;
    uint8_t value;
};

enum rtwn8723be_power_flow {
    RTWN8723BE_FLOW_POWER_ON = 0,
    RTWN8723BE_FLOW_RADIO_OFF,
    RTWN8723BE_FLOW_CARD_DISABLE,
    RTWN8723BE_FLOW_CARD_ENABLE,
    RTWN8723BE_FLOW_SUSPEND,
    RTWN8723BE_FLOW_RESUME,
    RTWN8723BE_FLOW_HWPDN,
    RTWN8723BE_FLOW_LPS_ENTER,
    RTWN8723BE_FLOW_LPS_LEAVE,
};

int rtwn8723be_pwrseq_run(struct rtwn8723be_softc *,
    enum rtwn8723be_power_flow);

#endif /* _RTWN8723BE_PWRSEQ_PLAN_H_ */
