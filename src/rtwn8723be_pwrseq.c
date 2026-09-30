#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>

#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_pwrseq_plan.h"
#include "rtwn8723be_pwrseq_data.h"

#define RTWN8723BE_PWR_POLL_MAX 5000

static int
rtwn8723be_pwrseq_steps(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_pwr_step *steps, size_t nsteps,
    uint32_t *polling_count)
{
    size_t i;

    for (i = 0; i < nsteps; i++) {
        const struct rtwn8723be_pwr_step *p = &steps[i];
        uint8_t value;

        if ((p->fab_mask & RTWN8723BE_PWR_FAB_ALL) == 0 ||
            (p->cut_mask & RTWN8723BE_PWR_CUT_ALL) == 0 ||
            (p->intf_mask & RTWN8723BE_PWR_INTF_PCI) == 0)
            continue;

        /*
         * Every command that survives the PCI interface filter in the
         * pinned 8723BE tables addresses MAC space.  Preserve the base
         * field and reject any future non-MAC PCI step rather than silently
         * applying it through the wrong NetBSD bus-space handle.
         */
        if (p->base != RTWN8723BE_PWR_BASE_MAC)
            return ENOTSUP;

        switch (p->cmd) {
        case RTWN8723BE_PWR_READ:
            /* Linux parser deliberately performs no action for READ. */
            break;

        case RTWN8723BE_PWR_WRITE:
            value = rtwn8723be_read_1(sc, p->offset);
            value &= (uint8_t)~p->mask;
            value |= p->value & p->mask;
            rtwn8723be_write_1(sc, p->offset, value);
            break;

        case RTWN8723BE_PWR_POLL:
            for (;;) {
                value = rtwn8723be_read_1(sc, p->offset);
                value &= p->mask;
                if (value == (p->value & p->mask))
                    break;

                delay(10);
                if ((*polling_count)++ >
                    RTWN8723BE_PWR_POLL_MAX)
                    return ETIMEDOUT;
            }
            break;

        case RTWN8723BE_PWR_DELAY:
            if (p->value == RTWN8723BE_PWR_DELAY_US)
                delay(p->offset);
            else
                delay((unsigned int)p->offset * 1000U);
            break;

        case RTWN8723BE_PWR_END:
            return 0;

        default:
            return EINVAL;
        }
    }

    return 0;
}

#define RUN_TRANSITION(name) do {                                           \
    error = rtwn8723be_pwrseq_steps(sc, rtwn8723be_trans_##name,            \
        RTWN8723BE_TRANS_##name##_COUNT, &polling_count);                    \
    if (error != 0)                                                          \
        return error;                                                        \
} while (0)

int
rtwn8723be_pwrseq_run(struct rtwn8723be_softc *sc,
    enum rtwn8723be_power_flow flow)
{
    uint32_t polling_count = 0;
    int error;

    if (!sc->sc_mapped)
        return ENXIO;

    switch (flow) {
    case RTWN8723BE_FLOW_POWER_ON:
        RUN_TRANSITION(cardemu_to_act);
        break;

    case RTWN8723BE_FLOW_RADIO_OFF:
        RUN_TRANSITION(act_to_cardemu);
        break;

    case RTWN8723BE_FLOW_CARD_DISABLE:
        RUN_TRANSITION(act_to_cardemu);
        RUN_TRANSITION(cardemu_to_carddis);
        break;

    case RTWN8723BE_FLOW_CARD_ENABLE:
        RUN_TRANSITION(carddis_to_cardemu);
        RUN_TRANSITION(cardemu_to_act);
        break;

    case RTWN8723BE_FLOW_SUSPEND:
        RUN_TRANSITION(act_to_cardemu);
        RUN_TRANSITION(cardemu_to_sus);
        break;

    case RTWN8723BE_FLOW_RESUME:
        RUN_TRANSITION(sus_to_cardemu);
        RUN_TRANSITION(cardemu_to_act);
        break;

    case RTWN8723BE_FLOW_HWPDN:
        RUN_TRANSITION(act_to_cardemu);
        RUN_TRANSITION(cardemu_to_pdn);
        break;

    case RTWN8723BE_FLOW_LPS_ENTER:
        RUN_TRANSITION(act_to_lps);
        break;

    case RTWN8723BE_FLOW_LPS_LEAVE:
        RUN_TRANSITION(lps_to_act);
        break;

    default:
        return EINVAL;
    }

    /*
     * Execute the canonical END command too.  This is intentionally
     * retained even though it has no hardware effect: it keeps the NetBSD
     * flow composition structurally identical to Linux pwrseq.c.
     */
    return rtwn8723be_pwrseq_steps(sc, rtwn8723be_trans_end,
        RTWN8723BE_TRANS_END_COUNT, &polling_count);
}

#undef RUN_TRANSITION
