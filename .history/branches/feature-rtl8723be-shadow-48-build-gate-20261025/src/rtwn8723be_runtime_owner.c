/* SPDX-License-Identifier: GPL-2.0 */
/* Inert per-device lifetime foundation for future RTL runtime owners. */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/intr.h>
#include <sys/mutex.h>

#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_runtime_owner.h"

void
rtwn8723be_runtime_owner_init(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_owner *owner;

    KASSERT(sc != NULL);
    owner = &sc->sc_runtime_owner;
    KASSERT(!owner->initialized);
    mutex_init(&owner->lifecycle_lock, MUTEX_DEFAULT, IPL_NONE);
    mutex_init(&owner->io_lock, MUTEX_DEFAULT, IPL_NONE);
    owner->io_depth = 0;
    owner->closing = false;
    owner->initialized = true;
}

void
rtwn8723be_runtime_owner_fini(struct rtwn8723be_softc *sc)
{
    struct rtwn8723be_runtime_owner *owner;

    if (sc == NULL)
        return;
    owner = &sc->sc_runtime_owner;
    if (!owner->initialized)
        return;

    mutex_enter(&owner->lifecycle_lock);
    owner->closing = true;
    KASSERT(owner->io_depth == 0);
    mutex_exit(&owner->lifecycle_lock);
    mutex_destroy(&owner->io_lock);
    mutex_destroy(&owner->lifecycle_lock);
    owner->initialized = false;
    owner->closing = false;
}
