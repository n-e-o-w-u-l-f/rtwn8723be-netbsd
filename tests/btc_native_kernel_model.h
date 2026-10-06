/* SPDX-License-Identifier: GPL-2.0 */
#ifndef BTC_NATIVE_KERNEL_MODEL_H
#define BTC_NATIVE_KERNEL_MODEL_H
#include <sys/types.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <assert.h>
#include <string.h>
#include <pthread.h>
#define KASSERT(x) assert(x)
#define MUTEX_DEFAULT 0
#define IPL_NONE 0
#define IPL_SOFTNET 4
#define PRI_NONE -1
#define WQ_MPSAFE 1
typedef struct kmutex {pthread_mutex_t p;} kmutex_t;
typedef struct kcondvar {pthread_cond_t p;} kcondvar_t;
struct lwp {int unused;};
extern _Thread_local struct lwp btc_test_lwp;
#define curlwp (&btc_test_lwp)
struct work {void *wk_dummy;};
struct workqueue;
bool cpu_intr_p(void);
bool cpu_softintr_p(void);
bool mutex_owned(kmutex_t *);
void mutex_init(kmutex_t *,int,int);
void mutex_destroy(kmutex_t *);
void mutex_enter(kmutex_t *);
void mutex_exit(kmutex_t *);
void cv_init(kcondvar_t *,const char *);
void cv_destroy(kcondvar_t *);
void cv_wait(kcondvar_t *,kmutex_t *);
void cv_broadcast(kcondvar_t *);
int workqueue_create(struct workqueue **,const char *,void (*)(struct work *,void *),void *,int,int,int);
void workqueue_enqueue(struct workqueue *,struct work *,void *);
void workqueue_wait(struct workqueue *,struct work *);
void workqueue_destroy(struct workqueue *);
#endif
