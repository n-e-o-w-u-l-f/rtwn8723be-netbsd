# RTL8723BE NetBSD 11 — atomic IRQ dispatch owner publication

**2026-10-29.** Native IRQ owner correction tested under portable
Linux-host C11/UBSan. Not a native NetBSD kernel build or live PCI
IRQ/softint/DMAR proof.

## Real issue

The former `rtwn8723be_netbsd_irq_set_dispatch()` copied
`sc_irq_dispatch`, set `sc_irq_arg`, and marked
`sc_irq_dispatch_ready` **without the IPL_NET IRQ mutex**.
`rtwn8723be_netbsd_intr`, `SOFTINT_NET` and
`rtwn8723be_netbsd_enable_interrupt` independently use the
same published callbacks. Another owner could enable IRQ while
the dispatch pointer table was partially updated, or replace/
clear callbacks while IRQ/softint handlers were still published.
Moreover, `dispatch_ready` only required two function pointers,
**not a valid callback argument**.

A void-returning dispatcher API also left its callers unable
to recover if this ownership transition had to be refused.

## Production change

`rtwn8723be_netbsd_irq_set_dispatch` now returns `int`.
Before publication, it requires an initialized NetBSD IRQ
mutex, a matching non-null callback argument for a valid
RX+TX-completion dispatch, or a fully null pair for unbind.
The entire callback-table/argument/ready publication and
revocation now occurs **under `sc_irq_lock` at IPL_NET**.
A still requested/enabled interrupt, hard IRQ, softint or
PCI interrupt handle causes `EBUSY`; **no partial callback
table write** takes place. Invalid callback arguments or
incomplete callback tables return `EINVAL`; a missing
initialized owner/lock returns `ENXIO`.

`rtwn8723be_datapath_prepare()` now checks that result.
When IRQ publication is refused, it restores the clean
datapath owner state, destroys its just-initialized TX mutex,
clears the unpublished datapath storage and returns the error.
It never exposes a prepared datapath with a missing IRQ
callback. `rtwn8723be_datapath_unprepare()` now also checks
revocation; if another IRQ owner was enabled after the
earlier teardown preflight, it retains all callback storage,
`sc_datapath` and the TX mutex and returns `EBUSY`
rather than releasing memory beneath a still-published
callback.

This does **not** call any network callback under the
IRQ mutex, block at IPL_NET, or replace the existing outer
lifecycle's duty to exclude new attach/ifnet entrants.

## Executed production-code regression

`tests/test_irq_dispatch_atomic_owner.py` extracts,
compiles and runs the actual production IRQ dispatcher,
datapath prepare and datapath unprepare C function bodies
with strict `-std=c11 -Wall -Wextra -Werror -pedantic`
and UBSan. Tests cover:

- Null dispatch argument, partial RX/TX callbacks and
  mismatched unbind rejected without publishing readiness.
- Already requested IRQ refuses datapath registration;
  native TX mutex and bridge are rolled back.
- Successful callback/argument publication under lock.
- Five independently active IRQ owners (requested,
  enabled, hard/soft IRQ handle and PCI handles) each
  refuse revocation and preserve the full dispatch.
- A deterministic race simulation enabling IRQ after
  unprepare's preflight but before final revocation:
  `EBUSY` retains the datapath and TX mutex; explicit
  later retry succeeds after ownership is removed.
- Fourteen unsafe source mutations rejected, including
  missing IRQ lock, missing owner conditions, unsafe
  callback readiness and missing attach/release rollback.

The older C11 callback/RX/TX/unprepare harnesses were
updated to use an error-returning mock dispatcher,
and the original source-contract mutation for final
unprepare teardown now correctly targets its *last*
release rather than the newly introduced prepare-failure
rollback. New test is included in portable CI.

## Open boundaries

A per-call IRQ mutex and fail-closed ownership checks do
not independently prove concurrent softint execution is
fully drained. The existing hard/soft IRQ disestablish
path and NetBSD attach/detach lifecycle still need a
real target build and HP physical verification. Automatic
deferred STOP retry, net80211 TX framing, pre-RUNNING
firmware C2H and four deliberately unbound Linux
lifecycle callbacks remain open: `register_ieee80211`,
`init_rfkill`, `bt_prepare`, `dm_init`.

No full native 48-C-unit NetBSD 11 kernel link, real
PCI IRQ/DMA or WLAN WPA2 association has been achieved.
No HP hardware command was executed and no experimental
kernel installed/booted. `main`, trusted F77 `/netbsd`,
`/boot.cfg`, i915 and PCI recovery assets are unchanged.
