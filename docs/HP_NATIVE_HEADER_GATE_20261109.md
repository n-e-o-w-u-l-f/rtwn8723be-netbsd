# Native NetBSD include repair — 2026-11-09

Project: HP-RTL8723BE / `n-e-o-w-u-l-f/rtwn8723be-netbsd`.
Execution: `hp-tpnw121.lan`, NetBSD 11 amd64, unprivileged owner workspace.
Baseline: `d916b778a4794c3aed2bbb8e88d551cef1730312`; development branch: `debug`.

## Reproduced failure and repair

The unchanged private shadow configured successfully and verified all 48 native
compiler rules. All 48 dependency targets succeeded. The object build then failed
in `rtwn8723be_f16_1_dma.c`: `ieee80211_var.h` needs the complete
`struct ifmedia` and the `ifm_change_cb_t` / `ifm_stat_cb_t` types.

The actual target `net/if_media.h` supplies those definitions; the net80211
header does not include it. The same missing dependency exists in
`rtwn8723be_tx_native.c`. Each file now includes `net/if_media.h`
immediately before `net80211/ieee80211_var.h`. The production change is
exactly two include lines, independently reviewed against the actual HP headers.

## Verification

- All 48 manifest-selected driver objects built using the generated private
  NetBSD kernel rules with the normal warning/error flags.
- All 48 object hashes independently read back and checked.
- Existing `test_dma_mem_unwind.py`, `test_native_tx_node_dma_lifetime.py`,
  and `test_tx_queue_lifetime.py` succeeded on HP.
- `git diff --check` passed; all other 996 baseline tracked files were unchanged
  before this report was added.
- F77 `/netbsd`, `/boot.cfg`, and installed `files.pci` hashes were unchanged.
- Initial failure evidence and successful repair evidence are both retained.
  [Machine-readable result](evidence/HP_NATIVE_HEADER_GATE_20261109.json).

## Scope and next gate

This proves native object compilation and the named mock/source regressions.
Full kernel link, installation, boot, real PCI DMA/IRQ/STOP races, scan,
association and WPA2 traffic were NOT_RUN by this step. No i915, boot,
radio or installed-source change occurred.

Next: private native full-kernel build/link with this exact source identity,
then the remaining net80211 TX consumer and callback/lifetime work. Physical
testing still requires independently verified recovery and console evidence.

Historical Legion runtime commit `cda48e590ae4e65db4aca3ecb3bb116a27c5cbbe`
is kept separately rather than activating its superseded implementation.
