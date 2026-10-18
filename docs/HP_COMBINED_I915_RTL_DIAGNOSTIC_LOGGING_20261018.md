# Combined i915/RTL NetBSD 11 — diagnostic kernel logging delta

**Owner:** HP-RTL8723BE combined kernel builder, consuming HP-I915 source.
**Status:** SOURCE-ONLY PASS; HP native compilation, full kernel ELF link,
installation and boot have NOT RUN. Date: 2026-10-18.

## Implemented in existing combined kernel configurator

`tools/configure_hp_combined_i915_rtl.py::render_config` now selects
exact diagnostic options in the generated private NetBSD-11 kernel config:

```conf
options DDB
options DDB_TEE_MSGBUF=1
options MSGBUFSIZE=262144
```

The renderer checks NetBSD inherited GENERIC for any existing matching
definition. Identical inherited options are not redefined; duplicates or
conflicting `DDB_TEE_MSGBUF` and `MSGBUFSIZE` values **refuse** the
candidate rather than silently overriding kernel policy. The existing
GPU `i915drmkms` PCI, `intelfb` and RTL `rtwn8723be` checks are
not weakened.

**Legion independent source tests, exact RTL WIP
`50f19bb56b4f4eda2811d2a3a3f7a6ba4214ab37`:**

- `python3 -B tests/test_hp_combined_source_contract.py` EXIT 0,
  `HP_COMBINED_SOURCE_CONTRACT_PASS`; includes synthetic positive/
  negative owner/source/PCI tests, duplicate/conflicting debug options.
- Loaded real, frozen `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`
  `sys/arch/amd64/conf/GENERIC` (45,488 bytes) and invoked the real
  `render_config`; PASS. In this exact Generic, DDB is already inherited;
  the generator adds `DDB_TEE_MSGBUF=1` and `MSGBUFSIZE=262144`.
- No source-only test is proof of executable kernel objects, the
  323 Linux i915 semantic mappings, physical KMS/PM or RTL WLAN.

## Kernel-internal and on-disk diagnostic separation

1. The kernel `printf`/DDB path reaches an in-RAM message buffer before
   userspace. The i915 owner still must instrument real driver G01–G09
   phase boundaries and verify NetBSD ABI correctness before full build.
2. When userspace starts, the NetBSD `syslogd` `kern.*` facility can
   persist kernel log messages into an **already created** file
   `/var/log/hp-kernel-boot.log`. The stage-only configuration and
   per-kernel XDM dispatcher are held by the i915 project in
   `tools/render_hp_netbsd11_four_boot_modes.py`. No such file or
   boot menu was installed on HP in this task.
3. On successful multi-user boot, `dmesg=YES` can write
   `/var/run/dmesg.boot`. Crash dump collection needs an actual dump
   device, `savecore`, space and correct kernel symbols. An early
   permanent freeze can still lose RAM messages; syslog is NOT a
   magic pre-filesystem disk logging facility.
4. The eventual boot menu item 4 must load a **separate, verified
   combined kernel ELF** `netbsd-11-i915-rtl-diag` and remain
   nondefault; 1–3 use byte-identical standard safe kernel copies.
   Preserve original F77/genfb and `/netbsd` until genuine readback
   and a physical recovery path have been confirmed.

## Full joint build still deliberately gated

The existing RTL
`tools/build_hp_combined_i915_rtl_candidate.sh` selects only HP NetBSD
and a clean, SHA-verified i915/RTL source pair, checks recovery and
native toolchain, and performs `nbconfig`, source/object owner proof
and *one full* `nbmake dependall` with a real link map; no install/boot.

The current production `tools/check_i915_kernel_release.py`
also requires an i915-owned signed-off full release manifest and six
genuine native/KMS/PM/recovery PASS signals; that file is absent on
the working i915 branch, and 300 i915 reference C units remain
semantically UNREVIEWED. **No real release was invented or installed.**
A separately reviewable **diagnostic compile-only authorization**
could be specified to break the cycle, but must be a *new*, tightly
scoped gate allowing native compile/link only (never kernel
installation or physical KMS boot), rather than falsifying
the production release. The current unmodified full release guard
still fails closed.

The direct HP RDC device is online but remote-command quota was
provider-confirmed exhausted; a native Tailscale command executor is
not exposed in the current chat; Legion-to-HP `andreas` SSH over
Tailnet independently returned an authentication error. None of these
statuses means the HP itself is offline, and none provides authorized
HP kernel-build execution in this turn.

## Source references

- https://man.netbsd.org/ddb.4
- https://man.netbsd.org/boot.cfg.5
- https://man.netbsd.org/syslog.conf.5
- https://www.netbsd.org/docs/guide/en/chap-kernel.html
