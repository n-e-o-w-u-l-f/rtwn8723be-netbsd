# Shadow I candidate: 48-unit build-only gate (2026-10-25)

## IST

The last **verified** native full kernel link is Shadow H at
`66fed5c6e732a373e4faa16f96b5742725c99d3b`, with 47 selected objects.
The current RTL manifest selects 48 native C translation units; the extra
`rtwn8723be_btc_context.c` has host/source tests, but **no verified matching
48-object HP link**. Do not extrapolate Shadow H's kernel hashes.

The live HP `/netbsd` must continue to be the F77 recovery image with SHA-256
`9b65629c0527bbd40f7ffa0d4ef0c59a32b5edceb597a5df8c86d1e7be1c8fde`.
F16.0 is forbidden; F83/F84 have unresolved black-screen outcomes. Neither
i915 nor the experimental RTL lifecycle is authorized for hardware activation.

## ÄNDERUNGEN

`tools/build_hp_kernel_shadow.py` is a build-only continuation after the
existing `tools/configure_hp_native_kernel_shadow.py` has completed and
verified **all 48** generated rules. It refuses non-HP hosts, root,
non-sibling/symlink shadows, dirty or changed source heads, stale manifests,
incomplete rules, noncanonical source symlinks, a changed original PCI manifest,
a changed F77 `/netbsd`, and any i915 input in the rendered kernel Makefile.
The private configuration must match the canonical `no i915drmkms*` form.

It runs `depend`, all 48 objects, then a **private `netbsd` link**. The
historically necessary `/usr/tools/bin` linker PATH is supplied to those
commands only. It records stage exit codes and SHA-256 logs; every nonempty
object; a deterministic ordered object digest; private kernel bytes, SHA-256
and embedded identity count. Original PCI manifest, live kernel, boot config
and selected sources are checked for mutation between stages. All results and
logs remain under the private shadow output. Failures are reported as
`FAILED` and are never treated as a partial passing kernel.

The older `tools/build_hp_native.py --target kernel` entrypoint now refuses
execution; its object-only configuration also explicitly excludes i915.
`tests/test_shadow_48_link_preflight.py` checks the positive plan and
fail-closed cases; the portable CI selects the new test.

## NEXT: guarded HP procedure, **not executed by this checkpoint**

Run only as the unprivileged account on HP NetBSD 11.0, after pulling a clean
checkout at the exact intended branch/head. The output directory must **not**
already exist. Example from the repository root:

```sh
git status --porcelain
python3 tests/test_shadow_48_link_preflight.py

python3 tools/configure_hp_native_kernel_shadow.py \
    --output ../rtl-kconfig-shadow-i-20261025

python3 tools/build_hp_kernel_shadow.py \
    --shadow ../rtl-kconfig-shadow-i-20261025
```

The first command must print nothing. The private configurator must report
`CONFIGURED_48_RULES_DRYRUN_PASS` in its `status.json` before the build gate
may proceed. Do not reuse a failed output directory; retain logs and create a
fresh shadow for another attempt.

Only a `BUILD_ONLY_PASSED` report with 48 nonempty objects, a successful
private link, one private kernel identity and unchanged original hashes can
close the **48-object compile/link gate**. The command intentionally never
copies to `/netbsd`, edits boot entries, reboots, loads hardware, or tests
i915. If any prerequisite or tool access is unavailable, keep the gate **OPEN**.

After this gate, the **real** `register_ieee80211`, `init_rfkill`,
`bt_prepare` and `dm_init` ownership and reverse teardown remain separate
runtime development tasks. PCI/IRQ attach, scan, association, suspend/recovery
and reliable traffic are NOT proven by this build.
