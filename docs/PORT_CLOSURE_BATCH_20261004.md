# RTL8723BE — gemeinsame Portierungs- und Fehlerabschlussliste (2026-10-04)

**Status: IN_PROGRESS — gesamter Port NICHT geschlossen.** Dies ist die verifizierte
Callback-Inventur und der Arbeitsvertrag für das *zusammenhängende* Korrekturpaket.
Keine Einzelkorrektur gilt als vollständige Portierung. Änderungen werden im
isolierten Kandidaten zusammengeführt, dann gemeinsam getestet und erst bei
bestehenden Freigabekriterien als integriertes Paket veröffentlicht.

## Festgelegte Referenzen und Schutzgrenzen

- Eingefrorenes Linux: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`.
- NetBSD: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
- RTL-Snapshot bei der Erfassung: `main@5b3359d29acd1115faabec3a467ce436b722d71d`.
- Auf Legion dokumentiert: 23 RTL-C-Objekte kompiliert, nativer
  `NEOWULF_RTL_AUDIT/netbsd` erfolgreich gelinkt (29.651.360 Bytes).
  **Audit-Kernel weder installiert noch boot-/WLAN-validiert.**
- F77-Rettungskernel, originale NetBSD-Referenz, HP-Laufzeit und
  separater i915-Overlay mit sechs lokalen Änderungen bleiben unverändert.
- Bereits durch Werkzeugsicherheit verweigerte Quelländerungen dürfen nicht durch
  einen gleichwertigen Umweg wiederholt werden; fehlende Freigabe ist Blocker.

## Vollständige Callback-Inventur (Quelle: aktuelle Header/Initialisierung)

`src/rtwn8723be_linux_state.h` deklariert **53** Lifecycle-Callbacks.
`rtwn8723be_netbsd_ops` bindet **40**. Die folgenden **13** sind NULL:

| Phase | Fehlende Callbacks | Anzahl |
|---|---|---:|
| PCI/Probe | `register_ieee80211`, `init_rfkill` | 2 |
| Start, Firmware-/Hardwarelebenszyklus | `bt_prepare`, `phy_bb_config`, `rf_channel_state_init`, `enable_hw_security`, `enable_aspm_backdoor`, `bt_hw_init`, `rf_calibration`, `dm_init` | 8 |
| Stop/Teardown | `bt_halt_deinit`, `wait_rf_change_idle`, `hw_disable` | 3 |

Diese Zählung prüft die *Bindung*, nicht die Semantik vorhandener Funktionen.
Kein fehlender Callback darf durch einen Erfolg vortäuschenden Stub ersetzt
werden. `linux_state.c` prüft die notwendigen Callback-Gruppen vor
Probe/Start/Stop und verweigert unvollständige Übergänge mit `ENOSYS`.

## Weitere Portierungs- und Integrationslücken (nicht in den 13 enthalten)

1. **Probe, Identität und Rückbau:** vollständige EFUSE-/Chip-/Cut-/
   Board-/OEM-/RF-Identität einschließlich tatsächlich verifizierter HP-Werte;
   `net80211`-Registrierung und RFKill erst mit symmetrischem Unregister,
   IRQ-Quiescence, DMA-/BAR-/PCI-Rückbau und fehlertolerantem Detach aktivieren.
   `rtwn8723be_native.c` verweigert absichtlich den Post-Registration-Rückbau.
2. **Firmware, PHY und RF:** realer `firmware(9)`-Transfer mit Ready/
   Self-Reset/H2C und Fehlerrollback; BB/AGC/RF-Tabellen, PG-Konversion,
   Crystal-Cap, RFENV/Locks, Kanalauswahl, IQK/LC und Leistungsmanagement
   in nachgewiesener Linux-Reihenfolge. `rtwn8723be_txpwr_pg.c` ist
   gegenwärtig **nicht in den 23 nativen Build-Objekten** enthalten.
3. **Datenpfad und IRQ:** vollständige RX-/TX-Mapping-, Segment-/Span-,
   Descriptor-/OWN-, Beacon-, Queue-, Ring- und Interrupt-Lebensdauer;
   net80211-Frame-Eingabe, TX-Node/mbuf-Reclaim, Fehler-Unwind.
   `tx_native.c` gibt für Command/Beacon bewusst `EOPNOTSUPP`
   zurück; dies ist nicht mit einem funktionierenden Pfad gleichzusetzen.
4. **Firmwareereignisse/BT:** H2C/C2H-Mailboxen und alle für das Ziel
   erforderlichen Report-Handler und Bluetooth-Koexistenz-Zustände; die
   vorhandenen C2H-/RX-Bindungsfunktionen verweigern fehlende Handler.
5. **Sicherheit und Laufzeit:** Schlüssel/CAM, Media/QoS, Rate-Control,
   Kalibrierung/DM, ASPM, RFKill, Suspend/Resume, Recovery und Stop
   samt Rückbau und Fault-Injection.
6. **Validierung:** Linux-Quellpfad- und Abhängigkeitsabgleich aller
   `COV-RTL-000` bis `COV-RTL-017` (weiterhin offen/unvollständig),
   nativer Objekt-/Kernelbau des **vollständigen** Manifests,
   IRQ-/DMA-/Firmware-Fault-Injection und anschließend kontrollierte
   HP-Hardwaretests. Ein erfolgreicher Link des Audit-Kernels ist nur
   Build-Evidenz.
7. **Anderer Treiber, eigener Integrationszweig:** i915 muss ebenfalls
   vollständig gegen seinen eigenen Linux-/NetBSD-Dependency-Graph
   geprüft und als eigenes, gemeinsam getestetes Paket portiert werden.
   Die sechs lokalen i915-Änderungen dürfen nicht durch RTL-Arbeiten
   überlagert werden.

## Gemeinsame Ausführungsreihenfolge — keine Einzelfehler-Freigaben

1. **Erfassen:** alle 53 Callback-Verbindungen, 18 Coverage-Bereiche,
   abhängigen Quellmodule, Fehlerpfade und fehlenden NetBSD-Buildobjekte
   zu einem Gesamtgraphen zusammenführen; jede Lücke eindeutig zuordnen.
2. **Als Paket implementieren:** Probe/Teardown, PHY/Firmware, Datenpfad/
   IRQ, Security/BT/Runtime in Abhängigkeitsreihenfolge im getrennten
   RTL-Kandidaten bearbeiten. Nur notwendige, zulässige Quelländerungen,
   keine vorgetäuschten Geräteidentitäten oder Erfolg-Stubs.
3. **Gemeinsam testen:** Source-/Blob-Identität; Host-C/UBSan;
   deterministische negative Tests für DMA-/Firmware-/IRQ-Fehler und
   jeden Abbruchpunkt; **alle** nativen Objekte, Kernel-Link,
   reproduzierbarer CI-Lauf. Bei Fehlern Ursachen im gleichen Paket
   korrigieren und gesamte betroffene Testmatrix wiederholen.
4. **Erst nach funktionaler Closure** auf dem HP in einer separaten,
   wiederherstellbaren Testkonfiguration prüfen: PCI-Probe, Firmware-
   Ready, Interface, Association, RX/TX, BT und Power-/Recovery-Pfade.
   Kein automatisches Überschreiben von F77 oder des laufenden Kernels.

## Ausführbarer Inventur-/Gate-Test

`python3 tests/test_port_closure_inventory.py` prüft die exakt beobachtete
53/40/13-Basis, meldet alle fehlenden Namen und das fehlende PG-Buildobjekt;
`--require-closure` muss **vorerst mit Exit 1** scheitern. Wenn Callbacks
implementiert werden, wird die erwartete Inventur **im selben Paket**
aktualisiert; die normale Inventur darf nicht durch einen unbemerkten
Rückschritt verfälscht werden. Selbst ein bestandenes Callback/PG-Gate
ersetzt keine der obigen Laufzeit-/Hardware-Prüfungen.

**Verifizierter Basistest auf Legion:** normale Inventur Exit 0,
`--require-closure` Exit 1; 53 deklariert, 40 gebunden, 13 fehlen,
23 native C-Einheiten, TX-PG nicht im Manifest.

## 2026-10-04 ausgeführte Gesamtregression und isolierte TX-Korrektur

- Auf Legion wurden alle **25 vorhandenen** `tests/test_*.py` im
  überprüften `rtl-build-20261004`-Arbeitsbaum mit Einzeltest-Timeout
  ausgeführt: **24 PASS, 1 FAIL, 0 TIMEOUT**. Der einzige Fehler ist
  `test_phy_bb_sequence.py`: dessen veraltete Callback-Teststruktur
  kompiliert gegen die neue `reset_pwrgroup`-Schnittstelle nicht.
  `test_txpwr_pg.py` besteht **isoliert**, das PG-Modul ist jedoch
  weiterhin **nicht im nativen Manifest**. Vorher verweigerte Änderungen
  an BB-Test/PG/RX wurden nicht erneut versucht.
- Ausschließlich im **separaten lokalen RTL-Arbeitsbaum** wurde
  `src/rtwn8723be_tx_native.c` um vollständige 32-Bit-DMA-
  Adressintervall-, Segmentlängen- und Deskriptor-Ringprüfungen in
  Enqueue/Reclaim ergänzt. Neuer lokaler Regressionstest
  `tests/test_tx_dma_span.py`: **11 Grenzfälle PASS**, vier echte
  Produktionsprüfstellen, C11/`-Werror`/UBSan.
  Anschließend bestanden `test_tx_queue_lifetime.py` und
  `test_kernel_source_integrity.py` erneut, beide Exit 0.
- **LOCAL_ONLY; NICHT VERÖFFENTLICHT ODER NATIV GEBAUT:** Die versuchte
  Übertragung dieser aktualisierten TX-Datei in den separaten
  NetBSD-Kernel-Kandidaten wurde durch eine Plattform-Sicherheitsprüfung
  abgewiesen. Kein erneuter Kopierversuch über äquivalente Tools,
  keine heimliche GitHub-Veröffentlichung als Umweg. Der frühere
  23-Objekt-/Kernel-Link bleibt Evidenz für den *alten* Kandidaten,
  nicht für die neuen TX-Änderungen.
- **NEXT:** bei legitim geänderter Freigabe das zusammenhängende,
  bereits erfasste Callback-/PHY-/TX-/RX-/Firmware-/Rückbaupaket
  vervollständigen, die bekannte BB-Testinkonsistenz direkt beheben,
  den gesamten Prüfstand erneut ausführen und erst dann den neuen
  nativen Kernel-Kandidaten bauen. F77 und i915 unverändert.

## 2026-10-04 12:04 CEST: native H2C integration and 25-unit build checkpoint

**VERIFIED BUILD-ONLY; not runtime-, HP-, or full-driver-ready.** The H2C
binding batch `4cc6c3902b3e449ad2c95dbc83906082e3ac4fa5` adds the
native `bus_space`/adaptive-mutex adapter, lifecycle-owned init/reset/fini,
firmware-ready publication after the real download handshake, two extra
opt-in kernel units, updated source/closure inventories, tests and CI wiring.
The kernel remains fail-closed while other mandatory lifecycle callbacks
are missing; this is not proof of physical firmware/H2C traffic.

On Legion, strict C11/UBSan `test_h2c_mailbox.py` and
`test_h2c_native_binding.py`, plus `test_kernel_source_integrity.py`
(now 25 units and 53 reachable project files) and
`test_linux_lifecycle_stop.py`, each exited **0**. With frozen
`NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`, the
separate candidate `netbsd-rtl-h2c-4cc6c39` built and linked on
2026-10-04 at 12:01:39 CEST using the verified NetBSD amd64 toolchain.
Its 25 RTL objects include `rtwn8723be_h2c.o` (14,160 bytes) and
`rtwn8723be_h2c_native.o` (109,296 bytes). The link map references
both and `x86_64--netbsd-nm` confirms linked definitions of
`rtwn8723be_h2c_send`, `rtwn8723be_h2c_native_send`,
`rtwn8723be_h2c_native_init` and `rtwn8723be_h2c_native_fw_ready`.
The uninstalled/unbooted kernel is
`/opt/ChatGPT/hp-driver-port/netbsd-obj-rtl-h2c-4cc6c39/sys/arch/amd64/compile/RTWN8723BE_STAGE/netbsd`,
**29,652,288 bytes**, SHA256
`aee0343ade19f6af5da8493c903459c24b13429b1761ccd2eea060eaba69fdf1`,
different from the earlier e557 kernel
`f4f21f27b0a4359e9a12ac4adae1ad0631ca7499a739b0f20a590341124dd0fb`.
Own status was read back at 12:04:03 CEST:
`STATE=VERIFIED; PHASE=NATIVE_H2C_25_UNIT_KERNEL_LINKED_NOT_TESTREADY`.

**Verifier recovery:** the initial postbuild script incorrectly expected
the H2C object name literally inside the generated Makefile and reported
`H2C_BUILD_MANIFEST_MISSING` *after a successful native build*.
A separate actual source/Makefile, link-map and `nm` check proved
correct inclusion; the verifier was corrected and its status revalidated
without rebuilding or replacing either kernel. Do not repeat the
Makefile-object-name check.

**CI evidence:** GitHub Actions run `37193587946` reported failure with
**zero job steps**. Its job-log endpoint gave HTTP 404 `BlobNotFound`
(RequestId `895df45d-501e-0056-1fe6-535ffb000000`,
2026-10-04T09:58:51Z). Hosted C tests are therefore **not confirmed
executed**. This is an infrastructure/log failure, not an observed
biological safety classification. No new explicit external safety
denial was observed in this H2C workflow; ChatGPT app UI alerts are not
visible to the agent.

**Concurrent source update:** later GitHub commit
`30e8abce33fcf0940c4fdd4181a17b1d1cff6858` fixes the
`mark_hal_start` check to accept the actual `RX_CONFIG` lifecycle
phase and adds a strict C11/UBSan regression. The verified kernel above
is pinned to `4cc6c39` and **does not contain this later fix**; a
separate source-identical native build and tests are still required.

**Outstanding:** 53 lifecycle callbacks declared, 40 bound and **13
missing**; TX-power PG absent from the native manifest, complete
hardware cut/board/PA/LNA/RF identity, BB/PG/XTAL, calibration,
net80211, C2H/H2C end-to-end consumers, RX/TX/IRQ ownership and full
stop/recovery/detach remain OPEN. Previously externally safety-denied
TX/RX/PG operations were not rerouted. The frozen NetBSD reference,
F77 recovery, HP boot, and separate six-edit i915 overlay remain
unchanged. Neither driver is `FULL`/`PARITY`/`TESTREADY`.
