# 0088 RTL8723BE DMA allocator — optimization-safe source guard

Status: **POST_CLOSED_SOURCE_ONLY** / HP native compiler and actual DMA still **NOT_RUN**.
Target: HP TPN-W121, NetBSD 11 amd64, source branch `wip/hp-rtl-runtime-48-merge-20261010`.
Pinned C source: `src/rtwn8723be_f16_1_dma.c` Git blob `790e4c3cbd46cf6405b689023087d94e5b481050`.
Reviewed test: `tests/test_dma_alloc_rejection_c11.py` Git blob `3412c1495803adeb8513312aacb96c9239dbcbc0`.

## Why the test was changed

The previous `--source-only` validation relied on Python `assert`, which is removed by `python3 -O`; optimized runs could otherwise claim PASS without enforcing the DMA-unload requirement. Replace it with explicit exceptions against the extracted real `rtwn8723be_f16_1_dma_mem_alloc` and `rtwn8723be_f16_1_dma_mem_free` function bodies, stripped of C comments for checking. Enforce load-error/rejection/PRE-sync ordering, exactly one pre-cleanup unload on a rejected *loaded* map, guarded loaded-map free and reverse cleanup order.

Five independent source-text mutants must be refused: removal, duplicate, unreachable/reordered unload, premature DMA POST, and clearing EFBIG.

## Actual run and diagnosed failure

- First SentinelX/Legion source-only run: **FAILED**, self-test mutant 3 unchanged. The fixture assumed a bare `goto fail;\n`, whereas the actual C statement carries an inline comment. This was **a test-fixture anchor defect, not a DMA-driver runtime failure**.
- Test fixture corrected and published in commit `9d59716331938f23351636383edca0bb276223f3`.
- Second SentinelX/Legion run in isolated, automatically deleted temporary directories: **PASS**. Read-only C source and test bytes taken directly from the above GitHub blobs; 3 Python argument variants × normal + `-O` = **6/6 positive runs**, each `--self-test` refusing all **5/5** mutants.
- Independent negative check removed the unload from a temporary copy of the actual source; `python3 -O --source-only` returned exit 1 with the expected explicit source-invariant rejection.
- Calling the test with no arguments on Legion returned exit 2 `RTL_DMA_HP_NATIVE_COMPILER_ONLY` **before any compiler invocation**.
- Tool's result `ok=true`, process exit 0, and output `RTL_0088_SOURCE_ONLY_PASS positive=6 source_mutants=5 off_hp_refused=1 original_bad_refused=1 native=NOT_RUN`.

## What this does not establish

This was **not** an HP NetBSD C11/UBSan execution, a real bus_dma mapping/unmapping, a native kernel object/link, a WLAN TX/RX hardware acceptance, or working WPA2. No HP, SSH-to-HP, RTL runtime C, i915, boot, EFI, F77, stock kernel or config file was changed. SentinelX could directly execute only on Legion at the time; the HP had no operational direct SentinelX session. Previously provider-denied i915 0071/0081/0085 and RTL RX 0086 effects were not retried or rerouted.

## Next controlled gate

On a **legitimately available and authorized HP native executor**, first reconcile local Git worktree and pinned source identity; run `python3 tests/test_dma_alloc_rejection_c11.py --source-only --self-test` and then (only on the HP) `python3 tests/test_dma_alloc_rejection_c11.py` while retaining verbose compiler stdout/stderr and exit status. A successful model is not the parent driver acceptance. Real kernel DMA/IRQ/scan/WPA2 testing requires a separate built kernel and safe experimental boot controls.
