/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Host/NetBSD-kernel include boundary for source-shared RTL8723BE modules.
 * The kernel has kernel-specific sys/ headers and uses -nostdinc.
 * Portable host regression tests retain their standard C headers.
 */
#ifndef _RTWN8723BE_OS_COMPAT_H_
#define _RTWN8723BE_OS_COMPAT_H_
#ifdef _KERNEL
#include <sys/types.h>
#include <sys/stdbool.h>
#include <sys/stdint.h>
#include <sys/stddef.h>
#include <sys/errno.h>
#include <sys/systm.h>
#else
#include <sys/types.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
#endif
#endif
