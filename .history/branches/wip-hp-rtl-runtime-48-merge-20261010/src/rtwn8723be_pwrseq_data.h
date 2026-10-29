/* Auto-derived numeric RTL8723B power transitions from pinned Linux pwrseq.h. */
/* Reference: fd179f8a05be3ccae366b9b96e176b51fbe54aab */
#ifndef _RTWN8723BE_PWRSEQ_DATA_H_
#define _RTWN8723BE_PWRSEQ_DATA_H_

#include "rtwn8723be_pwrseq_plan.h"

static const struct rtwn8723be_pwr_step rtwn8723be_trans_cardemu_to_act[] = {
    { 32, 255, 15, 3, 0, 1, 1, 1 },
    { 103, 255, 15, 3, 0, 1, 16, 0 },
    { 1, 255, 15, 3, 0, 3, 1, 1 },
    { 0, 255, 15, 3, 0, 1, 32, 0 },
    { 5, 255, 15, 15, 0, 1, 28, 0 },
    { 117, 255, 15, 4, 0, 1, 1, 1 },
    { 6, 255, 15, 15, 0, 2, 2, 2 },
    { 117, 255, 15, 4, 0, 1, 1, 0 },
    { 6, 255, 15, 15, 0, 1, 1, 1 },
    { 5, 255, 15, 15, 0, 1, 128, 0 },
    { 5, 255, 15, 15, 0, 1, 24, 0 },
    { 5, 255, 15, 15, 0, 1, 1, 1 },
    { 5, 255, 15, 15, 0, 2, 1, 0 },
    { 16, 255, 15, 15, 0, 1, 64, 64 },
    { 73, 255, 15, 15, 0, 1, 2, 2 },
    { 99, 255, 15, 15, 0, 1, 2, 2 },
    { 98, 255, 15, 15, 0, 1, 2, 0 },
    { 88, 255, 15, 15, 0, 1, 1, 1 },
    { 90, 255, 15, 15, 0, 1, 2, 2 },
    { 104, 1, 15, 15, 0, 1, 8, 8 },
    { 105, 255, 15, 15, 0, 1, 64, 64 },
};
#define RTWN8723BE_TRANS_CARDEMU_TO_ACT_COUNT (sizeof(rtwn8723be_trans_cardemu_to_act) / sizeof(rtwn8723be_trans_cardemu_to_act[0]))

static const struct rtwn8723be_pwr_step rtwn8723be_trans_act_to_cardemu[] = {
    { 31, 255, 15, 15, 0, 1, 255, 0 },
    { 79, 255, 15, 15, 0, 1, 1, 0 },
    { 73, 255, 15, 15, 0, 1, 2, 0 },
    { 5, 255, 15, 15, 0, 1, 2, 2 },
    { 5, 255, 15, 15, 0, 2, 2, 0 },
    { 16, 255, 15, 15, 0, 1, 64, 0 },
    { 0, 255, 15, 3, 0, 1, 32, 32 },
    { 32, 255, 15, 3, 0, 1, 1, 0 },
};
#define RTWN8723BE_TRANS_ACT_TO_CARDEMU_COUNT (sizeof(rtwn8723be_trans_act_to_cardemu) / sizeof(rtwn8723be_trans_act_to_cardemu[0]))

static const struct rtwn8723be_pwr_step rtwn8723be_trans_cardemu_to_sus[] = {
    { 5, 255, 15, 4, 0, 1, 24, 24 },
    { 5, 255, 15, 3, 0, 1, 24, 8 },
    { 35, 255, 15, 1, 0, 1, 16, 16 },
    { 7, 255, 15, 1, 0, 1, 255, 32 },
    { 5, 255, 15, 4, 0, 1, 24, 24 },
    { 134, 255, 15, 1, 3, 1, 1, 1 },
    { 134, 255, 15, 1, 3, 2, 2, 0 },
};
#define RTWN8723BE_TRANS_CARDEMU_TO_SUS_COUNT (sizeof(rtwn8723be_trans_cardemu_to_sus) / sizeof(rtwn8723be_trans_cardemu_to_sus[0]))

static const struct rtwn8723be_pwr_step rtwn8723be_trans_sus_to_cardemu[] = {
    { 5, 255, 15, 15, 0, 1, 136, 0 },
    { 134, 255, 15, 1, 3, 1, 1, 0 },
    { 134, 255, 15, 1, 3, 2, 2, 2 },
    { 35, 255, 15, 1, 0, 1, 16, 0 },
    { 5, 255, 15, 15, 0, 1, 24, 0 },
};
#define RTWN8723BE_TRANS_SUS_TO_CARDEMU_COUNT (sizeof(rtwn8723be_trans_sus_to_cardemu) / sizeof(rtwn8723be_trans_sus_to_cardemu[0]))

static const struct rtwn8723be_pwr_step rtwn8723be_trans_cardemu_to_carddis[] = {
    { 7, 255, 15, 1, 0, 1, 255, 32 },
    { 5, 255, 15, 3, 0, 1, 24, 8 },
    { 5, 255, 15, 4, 0, 1, 4, 4 },
    { 74, 255, 15, 2, 0, 1, 1, 1 },
    { 35, 255, 15, 1, 0, 1, 16, 16 },
    { 134, 255, 15, 1, 3, 1, 1, 1 },
    { 134, 255, 15, 1, 3, 2, 2, 0 },
};
#define RTWN8723BE_TRANS_CARDEMU_TO_CARDDIS_COUNT (sizeof(rtwn8723be_trans_cardemu_to_carddis) / sizeof(rtwn8723be_trans_cardemu_to_carddis[0]))

static const struct rtwn8723be_pwr_step rtwn8723be_trans_carddis_to_cardemu[] = {
    { 5, 255, 15, 15, 0, 1, 136, 0 },
    { 134, 255, 15, 1, 3, 1, 1, 0 },
    { 134, 255, 15, 1, 3, 2, 2, 2 },
    { 74, 255, 15, 2, 0, 1, 1, 0 },
    { 5, 255, 15, 15, 0, 1, 24, 0 },
    { 35, 255, 15, 1, 0, 1, 16, 0 },
    { 769, 255, 15, 4, 0, 1, 255, 0 },
};
#define RTWN8723BE_TRANS_CARDDIS_TO_CARDEMU_COUNT (sizeof(rtwn8723be_trans_carddis_to_cardemu) / sizeof(rtwn8723be_trans_carddis_to_cardemu[0]))

static const struct rtwn8723be_pwr_step rtwn8723be_trans_cardemu_to_pdn[] = {
    { 35, 255, 15, 1, 0, 1, 16, 16 },
    { 7, 255, 15, 3, 0, 1, 255, 32 },
    { 6, 255, 15, 15, 0, 1, 1, 0 },
    { 5, 255, 15, 15, 0, 1, 128, 128 },
};
#define RTWN8723BE_TRANS_CARDEMU_TO_PDN_COUNT (sizeof(rtwn8723be_trans_cardemu_to_pdn) / sizeof(rtwn8723be_trans_cardemu_to_pdn[0]))

static const struct rtwn8723be_pwr_step rtwn8723be_trans_pdn_to_cardemu[] = {
    { 5, 255, 15, 15, 0, 1, 128, 0 },
};
#define RTWN8723BE_TRANS_PDN_TO_CARDEMU_COUNT (sizeof(rtwn8723be_trans_pdn_to_cardemu) / sizeof(rtwn8723be_trans_pdn_to_cardemu[0]))

static const struct rtwn8723be_pwr_step rtwn8723be_trans_act_to_lps[] = {
    { 769, 255, 15, 4, 0, 1, 255, 255 },
    { 1314, 255, 15, 15, 0, 1, 255, 255 },
    { 1528, 255, 15, 15, 0, 2, 255, 0 },
    { 1529, 255, 15, 15, 0, 2, 255, 0 },
    { 1530, 255, 15, 15, 0, 2, 255, 0 },
    { 1531, 255, 15, 15, 0, 2, 255, 0 },
    { 2, 255, 15, 15, 0, 1, 1, 0 },
    { 2, 255, 15, 15, 0, 3, 0, 0 },
    { 2, 255, 15, 15, 0, 1, 2, 0 },
    { 256, 255, 15, 15, 0, 1, 255, 3 },
    { 257, 255, 15, 15, 0, 1, 2, 0 },
    { 147, 255, 15, 1, 0, 1, 255, 0 },
    { 1363, 255, 15, 15, 0, 1, 32, 32 },
};
#define RTWN8723BE_TRANS_ACT_TO_LPS_COUNT (sizeof(rtwn8723be_trans_act_to_lps) / sizeof(rtwn8723be_trans_act_to_lps[0]))

static const struct rtwn8723be_pwr_step rtwn8723be_trans_lps_to_act[] = {
    { 128, 255, 15, 1, 3, 1, 255, 132 },
    { 65112, 255, 15, 2, 0, 1, 255, 132 },
    { 865, 255, 15, 4, 0, 1, 255, 132 },
    { 2, 255, 15, 15, 0, 3, 0, 1 },
    { 8, 255, 15, 15, 0, 1, 16, 0 },
    { 265, 255, 15, 15, 0, 2, 128, 0 },
    { 41, 255, 15, 15, 0, 1, 192, 0 },
    { 257, 255, 15, 15, 0, 1, 2, 2 },
    { 256, 255, 15, 15, 0, 1, 255, 255 },
    { 2, 255, 15, 15, 0, 1, 3, 3 },
    { 1314, 255, 15, 15, 0, 1, 255, 0 },
};
#define RTWN8723BE_TRANS_LPS_TO_ACT_COUNT (sizeof(rtwn8723be_trans_lps_to_act) / sizeof(rtwn8723be_trans_lps_to_act[0]))

static const struct rtwn8723be_pwr_step rtwn8723be_trans_end[] = {
    { 65535, 255, 15, 15, 0, 4, 0, 0 },
};
#define RTWN8723BE_TRANS_END_COUNT (sizeof(rtwn8723be_trans_end) / sizeof(rtwn8723be_trans_end[0]))

#endif
