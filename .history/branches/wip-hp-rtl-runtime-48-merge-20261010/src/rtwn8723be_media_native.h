/* SPDX-License-Identifier: GPL-2.0 */
/* Legacy STA hardware helpers from frozen Linux RTL8723BE hw.c. */
#ifndef _RTWN8723BE_MEDIA_NATIVE_H_
#define _RTWN8723BE_MEDIA_NATIVE_H_
#include "rtwn8723be_os_compat.h"

struct rtwn8723be_media_state {
    uint32_t receive_config;
    uint64_t tsf;
    uint8_t bcn_ctrl;
    uint8_t bssid[6];
    uint16_t basic_rates;
    uint16_t aid;
    uint16_t beacon_interval;
    uint16_t sifs;
    uint8_t slot_time;
    bool linked;
    bool short_preamble;
    bool cache_valid;
    bool inprogress;
    bool quarantined;
};

/*
 * Every callback uses the actual sleepable runtime I/O/lifecycle owner.
 * ready proves running RF ON and excludes detach/stop/parallel RF, DM,
 * BTC and calibration. irq_restore MUST be callable for unwind even if
 * ready is revoked. edca_reset runs real rtl8723_dm_init_edca_turbo() state
 * reset once per AC; an EEPROM/software flag is not a DM owner.
 * LED actions use pinned enum values: LINK=2, NO_LINK=3.
 */
struct rtwn8723be_media_io {
    bool (*ready)(void *);
    int (*read8)(void *, uint32_t, uint8_t *);
    int (*read16)(void *, uint32_t, uint16_t *);
    int (*read32)(void *, uint32_t, uint32_t *);
    int (*write8)(void *, uint32_t, uint8_t);
    int (*write16)(void *, uint32_t, uint16_t);
    int (*write32)(void *, uint32_t, uint32_t);
    int (*edca_reset)(void *, unsigned int ac);
    int (*led_control)(void *, unsigned int action);
    int (*irq_disable)(void *, bool *was_enabled);
    int (*irq_restore)(void *, bool was_enabled);
};

/* Only real hardware initialization may reseed and clear quarantine. */
int rtwn8723be_media_state_seed(struct rtwn8723be_media_state *,
    uint8_t bcn_ctrl, uint32_t receive_config);
void rtwn8723be_media_state_invalidate(struct rtwn8723be_media_state *);

/* Each helper publishes cached state only after its whole sequence succeeds. */
int rtwn8723be_media_set_network(const struct rtwn8723be_media_io *, void *,
    struct rtwn8723be_media_state *, bool linked); /* legacy STA/NOLINK only */
int rtwn8723be_media_set_check_bssid(const struct rtwn8723be_media_io *, void *,
    struct rtwn8723be_media_state *, bool check);
int rtwn8723be_media_set_bssid(const struct rtwn8723be_media_io *, void *,
    struct rtwn8723be_media_state *, const uint8_t [6]);
int rtwn8723be_media_set_basic_rates(const struct rtwn8723be_media_io *, void *,
    struct rtwn8723be_media_state *, uint16_t descriptor_bitmap);
int rtwn8723be_media_basic_rate_bitmap(const uint8_t *net80211_rates,
    size_t count, uint16_t *descriptor_bitmap);
int rtwn8723be_media_set_aid(const struct rtwn8723be_media_io *, void *,
    struct rtwn8723be_media_state *, unsigned int aid); /* strip net80211 flags */
int rtwn8723be_media_set_preamble(const struct rtwn8723be_media_io *, void *,
    struct rtwn8723be_media_state *, bool short_preamble);
int rtwn8723be_media_set_sifs(const struct rtwn8723be_media_io *, void *,
    struct rtwn8723be_media_state *, uint16_t sifs, bool ht);
int rtwn8723be_media_set_slot(const struct rtwn8723be_media_io *, void *,
    struct rtwn8723be_media_state *, unsigned int slot_time,
    unsigned int acm_method, bool acm);
int rtwn8723be_media_channel_access(const struct rtwn8723be_media_io *, void *,
    struct rtwn8723be_media_state *, unsigned int slot_time,
    unsigned int acm_method, bool acm, bool ht);
int rtwn8723be_media_set_tsf(const struct rtwn8723be_media_io *, void *,
    struct rtwn8723be_media_state *, uint64_t tsf); /* STA; no IBSS beacon TX */
int rtwn8723be_media_set_beacon_interval(const struct rtwn8723be_media_io *,
    void *, struct rtwn8723be_media_state *, unsigned int interval);
#endif
