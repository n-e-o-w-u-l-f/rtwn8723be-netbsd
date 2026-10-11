/* SPDX-License-Identifier: GPL-2.0 */
/* Inert per-device lifetime foundation for future RTL runtime owners. */
#ifndef _RTWN8723BE_RUNTIME_OWNER_H_
#define _RTWN8723BE_RUNTIME_OWNER_H_

#include <sys/types.h>
#include <sys/mutex.h>

struct rtwn8723be_softc;

/*
 * Lock order is lifecycle_lock -> io_lock.  This foundation owns no I/O,
 * callbacks or hardware state yet; it only makes the future lifetime
 * boundary explicit without importing the obsolete frozen runtime.
 */
struct rtwn8723be_runtime_owner {
    kmutex_t lifecycle_lock;
    kmutex_t io_lock;
    unsigned int io_depth;
    bool initialized;
    bool closing;
};

void rtwn8723be_runtime_owner_init(struct rtwn8723be_softc *);
void rtwn8723be_runtime_owner_fini(struct rtwn8723be_softc *);

#endif
