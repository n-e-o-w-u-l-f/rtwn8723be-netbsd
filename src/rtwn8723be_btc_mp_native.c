/* SPDX-License-Identifier: GPL-2.0 */
/* NetBSD owner of the frozen RTL8723BE Bluetooth MP firmware transaction. */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <sys/cpu.h>
#include <sys/intr.h>
#include <sys/time.h>
#include <sys/timevar.h>
#include <sys/condvar.h>

#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_btc_mp_native.h"

static bool
btc_mp_sleepable(void)
{
    return !cpu_intr_p() && !cpu_softintr_p();
}

int
rtwn8723be_btc_mp_native_init(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_btc_mp_native *mp;

    if (sc == NULL)
        return EINVAL;
    if (!btc_mp_sleepable())
        return EWOULDBLOCK;
    mp = &sc->sc_btc_mp;
    if (mp->initialized)
        return EALREADY;
    memset(mp, 0, sizeof(*mp));
    mutex_init(&mp->lock, MUTEX_DEFAULT, IPL_SOFTNET);
    cv_init(&mp->reply_cv, "btmreply");
    cv_init(&mp->drained_cv, "btmdrain");
    mp->initialized = true;
    return 0;
}

int
rtwn8723be_btc_mp_native_activate(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_btc_mp_native *mp;
    bool ready;
    uint64_t generation;

    if (sc == NULL || !sc->sc_btc_mp.initialized ||
        !sc->sc_h2c.initialized)
        return ENXIO;
    if (!btc_mp_sleepable())
        return EWOULDBLOCK;
    /* The owner also must have discarded old RX events after MCU reset. */
    if (!sc->sc_mapped || !sc->sc_linux.being_init_adapter ||
        !sc->sc_linux.fw_ready || sc->sc_linux.started ||
        sc->sc_irq_enabled || sc->sc_irq_pending[0] != 0 ||
        sc->sc_irq_pending[1] != 0)
        return EAGAIN;
    mutex_enter(&sc->sc_h2c.lock);
    ready = sc->sc_h2c.state.firmware_ready &&
        !sc->sc_h2c.state.faulted;
    generation = sc->sc_h2c.firmware_generation;
    mutex_exit(&sc->sc_h2c.lock);
    if (!ready || generation == 0)
        return EAGAIN;
    mp = &sc->sc_btc_mp;
    mutex_enter(&mp->lock);
    if (mp->busy || mp->active) {
        mutex_exit(&mp->lock);
        return EBUSY;
    }
    if (mp->firmware_generation == generation) {
        mutex_exit(&mp->lock);
        return EAGAIN; /* A retry is not a new MCU/RX lifetime. */
    }
    mp->firmware_generation = generation;
    mp->pending = false;
    mp->done = false;
    mp->cancelled = false;
    mp->faulted = false;
    memset(&mp->reply, 0, sizeof(mp->reply));
    mp->active = true;
    mutex_exit(&mp->lock);
    return 0;
}

int
rtwn8723be_btc_mp_native_request(struct rtwn8723be_softc *sc,
    uint8_t opcode, const uint8_t *command, size_t length, bool wait_reply,
    struct rtwn8723be_btc_mp_reply *out)
{
    struct rtwn8723be_btc_mp_native *mp;
    struct bintime remaining;
    uint8_t encoded[R23BE_H2C_MAX_PAYLOAD];
    int error;

    if (sc == NULL || !sc->sc_btc_mp.initialized)
        return ENXIO;
    if (!btc_mp_sleepable())
        return EWOULDBLOCK;
    if (command == NULL || length < 2U ||
        length > sizeof(encoded) || (wait_reply && out == NULL))
        return EINVAL;
    memcpy(encoded, command, length);
    error = rtwn8723be_btc_mp_prepare(opcode, encoded, length);
    if (error != 0)
        return error;
    mp = &sc->sc_btc_mp;
    mutex_enter(&mp->lock);
    if (mp->faulted || !mp->active) {
        mutex_exit(&mp->lock);
        return EAGAIN;
    }
    if (mp->busy) {
        mutex_exit(&mp->lock);
        return EBUSY;
    }
    /* Arm BEFORE submission: firmware can reply during the H2C call. */
    mp->busy = true;
    mp->pending = wait_reply;
    mp->done = false;
    mp->cancelled = false;
    mp->expected_sequence = encoded[0] >> 4;
    memset(&mp->reply, 0, sizeof(mp->reply));
    mutex_exit(&mp->lock);

    /* Never hold the MP lock while taking H2C's lock or submitting MMIO. */
    error = rtwn8723be_h2c_native_send(sc, R23BE_BT_MP_H2C_ID,
        encoded, length);
    mutex_enter(&mp->lock);
    remaining = ms2bintime(R23BE_BT_MP_WAIT_MS);
    while (error == 0 && wait_reply && !mp->done &&
        !mp->cancelled && mp->active) {
        error = cv_timedwaitbt(&mp->reply_cv, &mp->lock, &remaining,
            DEFAULT_TIMEOUT_EPSILON);
        /* Recheck completion even on the boundary/error wakeup. */
        if (mp->done && !mp->cancelled)
            error = 0;
    }
    if (mp->cancelled || !mp->active)
        error = ECANCELED;
    else if (error == EWOULDBLOCK)
        error = ETIMEDOUT;
    if (error != 0 || !wait_reply) {
        /* No wire nonce: a late same-opcode reply cannot be disambiguated. */
        mp->faulted = true;
        mp->active = false;
    }
    if (error == 0 && wait_reply)
        *out = mp->reply;
    mp->busy = false;
    mp->pending = false;
    mp->done = false;
    cv_broadcast(&mp->drained_cv);
    mutex_exit(&mp->lock);
    return error;
}

int
rtwn8723be_btc_mp_native_receive(struct rtwn8723be_softc *sc,
    const struct rtwn8723be_c2h_event *event)
{
    struct rtwn8723be_btc_mp_native *mp;
    struct rtwn8723be_btc_mp_reply reply;
    int error;

    if (sc == NULL || event == NULL)
        return EINVAL;
    if (!sc->sc_btc_mp.initialized)
        return ENXIO;
    if (cpu_intr_p())
        return EWOULDBLOCK;
    if (event->id != R23BE_C2H_BT_MP)
        return EINVAL;
    error = rtwn8723be_btc_mp_decode(event->payload,
        event->payload_length, &reply);
    if (error != 0 || !reply.from_bt_firmware || !reply.completes)
        return error;
    mp = &sc->sc_btc_mp;
    mutex_enter(&mp->lock);
    if (mp->active && !mp->faulted && mp->busy && mp->pending &&
        !mp->done && !mp->cancelled &&
        reply.sequence == mp->expected_sequence) {
        mp->reply = reply;
        mp->done = true;
        cv_signal(&mp->reply_cv);
    }
    mutex_exit(&mp->lock);
    return 0;
}

int
rtwn8723be_btc_mp_native_stop(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_btc_mp_native *mp;

    if (sc == NULL)
        return EINVAL;
    if (!btc_mp_sleepable())
        return EWOULDBLOCK;
    mp = &sc->sc_btc_mp;
    if (!mp->initialized)
        return 0;
    mutex_enter(&mp->lock);
    mp->active = false;
    mp->faulted = true;
    mp->cancelled = true;
    cv_broadcast(&mp->reply_cv);
    /* Includes the unlocked H2C submission, not only the CV waiter. */
    while (mp->busy)
        cv_wait(&mp->drained_cv, &mp->lock);
    mp->pending = false;
    mp->done = false;
    memset(&mp->reply, 0, sizeof(mp->reply));
    mutex_exit(&mp->lock);
    return 0;
}

int
rtwn8723be_btc_mp_native_fini(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_btc_mp_native *mp;
    int error;

    if (sc == NULL)
        return EINVAL;
    if (!btc_mp_sleepable())
        return EWOULDBLOCK;
    mp = &sc->sc_btc_mp;
    if (!mp->initialized)
        return 0;
    /* Owner has excluded new calls and quiesced all RX/IRQ callbacks. */
    error = rtwn8723be_btc_mp_native_stop(sc);
    if (error != 0)
        return error;
    mutex_enter(&mp->lock);
    KASSERT(!mp->busy && !mp->pending);
    mp->initialized = false;
    mutex_exit(&mp->lock);
    cv_destroy(&mp->drained_cv);
    cv_destroy(&mp->reply_cv);
    mutex_destroy(&mp->lock);
    return 0;
}
