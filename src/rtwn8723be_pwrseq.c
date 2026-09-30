#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/bus.h>
#include <sys/errno.h>

#include "rtwn8723be_pwrseq_plan.h"

#define RTWN8723BE_PWR_POLL_MAX 5000
#define RTWN8723BE_PWR_POLL_US  10

int
rtwn8723be_pwrseq_exec(bus_space_tag_t st, bus_space_handle_t sh,
    const struct rtwn8723be_pwr_step *steps, size_t nsteps,
    uint8_t cut, uint8_t fab, uint8_t intf)
{
    size_t i;
    uint32_t poll;
    uint8_t v;

    for (i = 0; i < nsteps; i++) {
        const struct rtwn8723be_pwr_step *s = &steps[i];

        if ((s->fab_mask & fab) == 0 ||
            (s->cut_mask & cut) == 0 ||
            (s->intf_mask & intf) == 0)
            continue;

        switch (s->cmd) {
        case RTWN8723BE_PWR_READ:
            (void)bus_space_read_1(st, sh, s->offset);
            break;
        case RTWN8723BE_PWR_WRITE:
            v = bus_space_read_1(st, sh, s->offset);
            v &= (uint8_t)~s->mask;
            v |= (uint8_t)(s->value & s->mask);
            bus_space_write_1(st, sh, s->offset, v);
            break;
        case RTWN8723BE_PWR_POLL:
            for (poll = 0; poll <= RTWN8723BE_PWR_POLL_MAX; poll++) {
                v = bus_space_read_1(st, sh, s->offset) & s->mask;
                if (v == (s->value & s->mask))
                    break;
                delay(RTWN8723BE_PWR_POLL_US);
            }
            if (poll > RTWN8723BE_PWR_POLL_MAX)
                return ETIMEDOUT;
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