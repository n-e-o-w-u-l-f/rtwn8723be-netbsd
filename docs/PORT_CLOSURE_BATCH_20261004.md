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
