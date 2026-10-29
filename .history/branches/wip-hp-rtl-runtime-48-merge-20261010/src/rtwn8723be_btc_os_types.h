/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _R23BE_BTC_OS_TYPES_H_
#define _R23BE_BTC_OS_TYPES_H_
#include "rtwn8723be_os_compat.h"
#ifdef _KERNEL
#include <sys/stdarg.h>
#else
#include <stdarg.h>
#endif

/* Exact scalar widths and imported wifi/debug/register constants. */
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int8_t s8;
typedef int16_t s16;
typedef int32_t s32;
typedef int64_t s64;
#ifndef BIT
#define BIT(n) (UINT32_C(1) << (n))
#endif
#define BIT0 BIT(0)
#define BIT1 BIT(1)
#define BIT2 BIT(2)
#define BIT3 BIT(3)
#define BIT4 BIT(4)
#define BIT5 BIT(5)
#define BIT6 BIT(6)
#define BIT7 BIT(7)
#define BIT8 BIT(8)
#define BIT9 BIT(9)
#define BIT23 BIT(23)
#define BIT24 BIT(24)
#define MASKLWORD UINT32_C(0x0000ffff)
#define MASKHWORD UINT32_C(0xffff0000)
#define REG_SYS_FUNC_EN 0x0002U
#define COMP_BT_COEXIST BIT(30)
#define DBG_LOUD 4
enum radio_path { RF90_PATH_A=0, RF90_PATH_B=1, RF90_PATH_C=2, RF90_PATH_D=3 };
enum macphy_mode { SINGLEMAC_SINGLEPHY=0, DUALMAC_DUALPHY, DUALMAC_SINGLEPHY };
#include "rtwn8723be_btc_dm_types.h"

/* A diagnostic sink owns formatting, including Linux's %Nph byte dump.
 * It never owns or retains the algorithms' borrowed arguments.
 */
struct seq_file {
    void *arg;
    void (*vprintf)(void *, const char *, va_list);
};
static inline void seq_printf(struct seq_file *s, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    s->vprintf(s->arg, fmt, ap);
    va_end(ap);
}
static inline void seq_puts(struct seq_file *s, const char *text)
{
    seq_printf(s, "%s", text);
}
#endif
