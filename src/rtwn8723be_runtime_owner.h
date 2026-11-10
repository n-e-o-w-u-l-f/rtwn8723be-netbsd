/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _RTWN8723BE_RUNTIME_OWNER_H_
#define _RTWN8723BE_RUNTIME_OWNER_H_

#include <sys/types.h>
#include <sys/mutex.h>

struct lwp;
struct rtwn8723be_softc;
struct rtwn8723be_c2h_handlers;
struct rtwn8723be_runtime_context;

enum rtwn8723be_runtime_operation {
    R23BE_RUNTIME_NONE = 0,
    R23BE_RUNTIME_CONFIGURE,
    R23BE_RUNTIME_REGISTER,
    R23BE_RUNTIME_START,
    R23BE_RUNTIME_STOP,
    R23BE_RUNTIME_RETIRE
};

/*
 * lifecycle_lock protects only short admission/operation metadata. Never
 * hold it over allocation, module callbacks, MMIO, sleeping or IRQ drain.
 * io_depth is lifecycle_lock metadata for a future genuine provider lease;
 * io_lock is reserved for that provider's sleepable serialized I/O.
 * Lock order, when both are needed, is lifecycle_lock -> io_lock, with no
 * blocking I/O-lock acquisition while the IPL_NET lock is held.
 *
 * operation_lwp identifies the one accepted orchestration thread. Future
 * real providers must define same-operation nesting and exclude other
 * callers; this binding does not manufacture RF/DM/BTC provider leases.
 */
struct rtwn8723be_runtime_owner {
    kmutex_t lifecycle_lock; /* IPL_NET, short and non-sleeping */
    kmutex_t io_lock;        /* IPL_NONE, no fabricated provider use */
    unsigned int io_depth;
    bool initialized;
    bool closing;
    enum rtwn8723be_runtime_operation operation;
    struct lwp *operation_lwp;
    struct rtwn8723be_runtime_context *context;
};

void rtwn8723be_runtime_owner_init(struct rtwn8723be_softc *);
/*
 * Copy an immutable complete C2H table before publishing any device owner.
 * arg must be the owning softc. Real callback code and provider bindings
 * must outlive successful owner teardown; no production supplier is implied.
 */
int rtwn8723be_runtime_owner_configure(struct rtwn8723be_softc *,
    const struct rtwn8723be_c2h_handlers *);
/* Structural only: no provider acquire/ready call, PCI or MMIO effect. */
int rtwn8723be_runtime_probe_ready(struct rtwn8723be_softc *);
int rtwn8723be_netbsd_register_ieee80211(void *);
int rtwn8723be_runtime_hw_start(struct rtwn8723be_softc *);
int rtwn8723be_runtime_hw_stop(struct rtwn8723be_softc *);
/*
 * External detach excludes new entrants. Release-build EBUSY retains all
 * locks/storage if any resource or operation still owns the softc.
 */
int rtwn8723be_runtime_owner_fini(struct rtwn8723be_softc *);

#endif
