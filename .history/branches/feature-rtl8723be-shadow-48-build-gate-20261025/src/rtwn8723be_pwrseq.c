#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/bus.h>
#include <sys/errno.h>

#include "rtwn8723be_pwrseq_plan.h"
#include "rtwn8723be_pwrseq_data.h"

#define RTWN8723BE_PWR_POLL_MAX 5000
#define RTWN8723BE_PWR_POLL_US  10

int
rtwn8723be_pwrseq_exec(bus_space_tag_t st, bus_space_handle_t sh,
    const struct rtwn8723be_pwr_step *steps, size_t nsteps,
    uint8_t cut, uint8_t fab, uint8_t intf)
{
    size_t i;
    uint32_t polling_count = 0;
    uint8_t v;

    for (i = 0; i < nsteps; i++) {
        const struct rtwn8723be_pwr_step *s = &steps[i];

        if ((s->fab_mask & fab) == 0 ||
            (s->cut_mask & cut) == 0 ||
            (s->intf_mask & intf) == 0)
            continue;

        switch (s->cmd) {
        case RTWN8723BE_PWR_READ:
            /*
             * Pinned Linux PWR_CMD_READ is intentionally a no-op apart
             * from tracing.  Do not invent a hardware read here.
             */
            break;
        case RTWN8723BE_PWR_WRITE:
            v = bus_space_read_1(st, sh, s->offset);
            v &= (uint8_t)~s->mask;
            v |= (uint8_t)(s->value & s->mask);
            bus_space_write_1(st, sh, s->offset, v);
            break;
        case RTWN8723BE_PWR_POLL:
            /*
             * Linux keeps polling_count across the complete parser run,
             * rather than resetting it for each polling command.
             */
            for (;;) {
                v = bus_space_read_1(st, sh, s->offset) & s->mask;
                if (v == (s->value & s->mask))
                    break;
                delay(RTWN8723BE_PWR_POLL_US);
                if (polling_count++ > RTWN8723BE_PWR_POLL_MAX)
                    return ETIMEDOUT;
            }
            break;
        case RTWN8723BE_PWR_DELAY:
            if (s->value == RTWN8723BE_PWR_DELAY_US)
                delay(s->offset);
            else
                delay((unsigned int)s->offset * 1000U);
            break;
        case RTWN8723BE_PWR_END:
            return 0;
        default:
            return EINVAL;
        }
    }

    return 0;
}

static int
rtwn8723be_pwrseq_transition(bus_space_tag_t st, bus_space_handle_t sh,
    const struct rtwn8723be_pwr_step *steps, size_t nsteps,
    uint8_t cut, uint8_t fab, uint8_t intf)
{
    return rtwn8723be_pwrseq_exec(st, sh, steps, nsteps,
        cut, fab, intf);
}

int
rtwn8723be_pwrseq_flow_exec(bus_space_tag_t st, bus_space_handle_t sh,
    enum rtwn8723be_pwr_flow flow, uint8_t cut, uint8_t fab, uint8_t intf)
{
    int error;

#define RUN_TRANSITION(array, count) do {                               \
    error = rtwn8723be_pwrseq_transition(st, sh, (array), (count),        \
        cut, fab, intf);                                                   \
    if (error != 0)                                                        \
        return error;                                                      \
} while (0)

    switch (flow) {
    case RTWN8723BE_PWR_FLOW_POWER_ON:
        RUN_TRANSITION(rtwn8723be_trans_cardemu_to_act,
            RTWN8723BE_TRANS_CARDEMU_TO_ACT_COUNT);
        break;
    case RTWN8723BE_PWR_FLOW_RADIO_OFF:
        RUN_TRANSITION(rtwn8723be_trans_act_to_cardemu,
            RTWN8723BE_TRANS_ACT_TO_CARDEMU_COUNT);
        break;
    case RTWN8723BE_PWR_FLOW_CARD_DISABLE:
        RUN_TRANSITION(rtwn8723be_trans_act_to_cardemu,
            RTWN8723BE_TRANS_ACT_TO_CARDEMU_COUNT);
        RUN_TRANSITION(rtwn8723be_trans_cardemu_to_carddis,
            RTWN8723BE_TRANS_CARDEMU_TO_CARDDIS_COUNT);
        break;
    case RTWN8723BE_PWR_FLOW_CARD_ENABLE:
        RUN_TRANSITION(rtwn8723be_trans_carddis_to_cardemu,
            RTWN8723BE_TRANS_CARDDIS_TO_CARDEMU_COUNT);
        RUN_TRANSITION(rtwn8723be_trans_cardemu_to_act,
            RTWN8723BE_TRANS_CARDEMU_TO_ACT_COUNT);
        break;
    case RTWN8723BE_PWR_FLOW_SUSPEND:
        RUN_TRANSITION(rtwn8723be_trans_act_to_cardemu,
            RTWN8723BE_TRANS_ACT_TO_CARDEMU_COUNT);
        RUN_TRANSITION(rtwn8723be_trans_cardemu_to_sus,
            RTWN8723BE_TRANS_CARDEMU_TO_SUS_COUNT);
        break;
    case RTWN8723BE_PWR_FLOW_RESUME:
        RUN_TRANSITION(rtwn8723be_trans_sus_to_cardemu,
            RTWN8723BE_TRANS_SUS_TO_CARDEMU_COUNT);
        RUN_TRANSITION(rtwn8723be_trans_cardemu_to_act,
            RTWN8723BE_TRANS_CARDEMU_TO_ACT_COUNT);
        break;
    case RTWN8723BE_PWR_FLOW_HWPDN:
        RUN_TRANSITION(rtwn8723be_trans_act_to_cardemu,
            RTWN8723BE_TRANS_ACT_TO_CARDEMU_COUNT);
        RUN_TRANSITION(rtwn8723be_trans_cardemu_to_pdn,
            RTWN8723BE_TRANS_CARDEMU_TO_PDN_COUNT);
        break;
    case RTWN8723BE_PWR_FLOW_ENTER_LPS:
        RUN_TRANSITION(rtwn8723be_trans_act_to_lps,
            RTWN8723BE_TRANS_ACT_TO_LPS_COUNT);
        break;
    case RTWN8723BE_PWR_FLOW_LEAVE_LPS:
        RUN_TRANSITION(rtwn8723be_trans_lps_to_act,
            RTWN8723BE_TRANS_LPS_TO_ACT_COUNT);
        break;
    default:
        return EINVAL;
    }

#undef RUN_TRANSITION
    return 0;
}
