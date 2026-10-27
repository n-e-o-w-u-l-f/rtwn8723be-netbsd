# RTL8723BE NetBSD 11 — explicit net80211 DOWN retry after EBUSY

2026-10-27. **Native-source change plus Linux-host C11/UBSan tests**, not
a native NetBSD 11 full kernel build or physical RTL8723BE WLAN test.

## Root cause

Since the guarded RX/TX hardware STOP implemented in stacked PR #15,
`rtwn8723be_datapath_begin_stop` intentionally returns `EBUSY` when
borrowed RX DMA or a TX completion callback remains active. It sets
`dp->stop_pending = true`, closes further descriptor admission, and
retains the real Linux runtime in `RUNNING` until an explicit retry
can safely transition to `STOPPING`.

However, the net80211 `rtwn8723be_n80211_ifstop` already cleared
`IFF_RUNNING` and `IFF_OACTIVE` before calling `hw_stop`.
After that `EBUSY`, a later explicit `ifconfig ... down`
issued `SIOCSIFFLAGS` with both `IFF_UP` and `IFF_RUNNING`
**clear**. The existing ioctl handler only called `ifstop` if
`IFF_RUNNING` was still set. Therefore the deferred STOP could
not be retried by another ordinary DOWN ioctl; hardware resources
remained live behind a logically down interface.

## Actual production correction

- `rtwn8723be_datapath_stop_retry_ready` obtains the existing
  **IPL_NET `dp->tx_lock`**, then samples the latched STOP together
  with disabled TX, matching published device/IRQ owner, valid
  dispatch, `sc_linux.started`, and actual
  `sc_linux.stage == R23BE_STAGE_RUNNING`. An unowned, absent or
  retired datapath does **not** authorize a stop retry.
- `rtwn8723be_n80211_ioctl`, after `ifioctl_common` succeeds,
  recognizes an **explicit DOWN state with both IFF_UP and
  IFF_RUNNING clear** and a locked ready pending-stop snapshot.
  It calls the existing `rtwn8723be_n80211_ifstop` again.
- That function rechecks the true Linux lifecycle and invokes the
  native `hw_stop` method. The hardware's real
  `begin_stop` still serializes and revalidates all RX/TX leases
  under the same TX mutex: a stale eligibility snapshot is **not**
  permission to bypass the owner.
- No `IFF_RUNNING` flag is fabricated. Net80211 remains DOWN
  throughout the failed STOP and the retry, so its old TX dequeue
  gate stays shut. A completed stop clears `stop_pending` and
  retires the Linux runtime. Later DOWN requests become no-ops.
- The ioctl entry also checks `n->sc != NULL` before taking
  `&n->sc->sc_ic`; a corrupted/stale registered bridge now
  fails with `ENXIO`, not a NULL dereference.

## Host-executed regression

`tests/test_net80211_deferred_down_retry.py` compiles **the
production** `n80211_ifstop`, `n80211_ioctl`, native
`datapath_begin_stop`, and locked
`datapath_stop_retry_ready` function bodies with strict C11
and UBSan. Its simulated Linux hardware method delegates to
the production begin-stop function; only the later actual
hardware side effects are stubbed.

Scenarios include:

- first explicit DOWN while RX DMA callback active: `EBUSY`,
  DOWN ifnet flags, Linux still RUNNING, `stop_pending` latched;
- repeated DOWN before callback return: another safe `EBUSY`,
  without falsely marking STOPPED;
- requested UP with STOP pending: start refuses and drops IFF_UP;
- subsequent DOWN after RX callback release: begin-stop enters
  STOPPING and hardware mock reaches STOPPED;
- further DOWN after success: no repeated hardware stop;
- foreign IRQ owner: predicate refuses a spurious stop retry;
- NULL native softc: ioctl returns `ENXIO`.

Eleven unsafe source mutations must be rejected. The test is wired
into `.github/workflows/portable-c-regressions.yml`.

## Still unfinished

This implements **only reissue-driven retries**. No wakeup,
callout, worker, sleepable drain, or automatic retry is installed;
external software must actually issue a new DOWN ioctl or provide
a complete serialized lifecycle owner.

The temporary EBUSY still leaves an adapter logically DOWN while
its internal Linux state is RUNNING, with new TX/RX admission
disabled. The outer runtime controller must eventually finish
the drain or explicitly quarantine/recover the hardware; users
must not treat a successful ioctl retry test as a guarantee of
unattended shutdown.

IRQ and softint drain, media-change restart during EBUSY,
firmware C2H during early start, RFKill/BTC/DM ownership, real
net80211 frame TX, native NetBSD 48-object kernel link and HP
WLAN association remain **open**. Four Linux callbacks
`register_ieee80211`, `init_rfkill`, `bt_prepare`, and
`dm_init` remain unbound.

No kernel installation or boot was performed. `main`,
trusted F77 `/netbsd`, `/boot.cfg`, i915 and recovery
assets remain unchanged.
