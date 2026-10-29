# VERBINDLICHER AGENTENAUFTRAG – gemeinsamer HP-NetBSD-Kernel mit i915drmkms und rtwn8723be0

**Datum:** 2026-10-17. **Empfänger:** Agent des RTL8723BE-Projekts. **Typ:** Build-/Integrationsauftrag, ausdrücklich KEINE vorweggenommene i915-Freigabe.

## Ziel und Verantwortlichkeiten

Sobald der i915-Owner die vollständige NetBSD-i915drmkms-Portierung nachweislich freigegeben hat, führt der RTL-Agent beide Treiber in EINEM neuen NetBSD-11/amd64-Kernel für HP 17-x037ng / TPN-W121 zusammen. Der RTL-Agent ist Owner für Build-Konfiguration, vollständige native Kompilierung auf dem HP, echten Kernel-Link, Hashes, Logs und reproduzierbare Abnahme. Der i915-Agent bleibt Owner für DRM/KMS-/GPU-Runtime, physische Displayfunktion, Blackscreen-Korrektur und die i915-Freigabe. Kein Agent erfindet Beweise oder erteilt dem anderen ungeprüft eine Freigabe.

**Strikte Scopegrenze:** Build != Installation != Boot != funktionierendes KMS != funktionierendes WLAN. Dieser Auftrag autorisiert Vorbereitung und nach erfüllten Gates einen nichtinstallierenden Build. Boot-/Default-/Netzwerkänderungen brauchen gesonderte nachweislich sichere Bedingungen. **Build/Installation ausschließlich am HP.** Legion darf Referenz- und Quelltests sowie autorisierten SSH-Pivot ausführen. Keine kostenpflichtigen Runner, keine GitHub Actions.

## 1. Sofort zu ladende Quellen und Governance

1. Zentrale Governance: https://github.com/n-e-o-w-u-l-f/Agent-Governance ; zuerst AGENT_BOOTSTRAP.md, LAST_TASKS.md, governance/workflows/driver-completeness.md, governance/workflows/material-step-ledger.md, governance/tools/lan-ssh-relay.md, governance/workflows/failure-feedback.md sowie state/projects/HP-RTL8723BE.md und state/projects/HP-I915.md lesen.
2. RTL: https://github.com/n-e-o-w-u-l-f/rtwn8723be-netbsd – aktive Branch wip/hp-rtl-runtime-48-merge-20261010. Bei Vorbereitung HEAD fca8f1bd0991d96ac30c914fcb40c58abec2ad10; nach diesem Dokument zwingend neuen aktuellen HEAD prüfen. Config config/files.rtwn8723be_native enthält 50 native RTL-C-Units. Aktuelle RTL-Quelltests belegen keine bereits gebootete WLAN-Verbindung.
3. i915: https://github.com/n-e-o-w-u-l-f/i915-cherryview-braswell-netbsd – aktive Branch work/hp-native-drm-stage-replay-20261015. Bei Vorbereitung HEAD f536130b9ca049967ddf729954e3b32a69e33a96. Source-only IOSF- und NetBSD-Patchtests vorhanden; vollständiger nativer 323-C-Unit-/DRM-/TTM-Kernel-Link, physischer KMS-Erfolg und Blackscreen-Behebung sind bisher NICHT nachgewiesen.
4. Eingefrorene Referenzen: Linux torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab; NetBSD NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6. Hardware Intel 8086:22b1 rev35 subsystem 103c:8205 und Realtek 10ec:b723 subsystem 103c:81c1. PCI-Identitäten auf HP read-only prüfen.
5. RTL-Release-Gate: tools/check_i915_kernel_release.py, tests/test_i915_release_gate_source.py, docs/RTL_I915_WAIT_AND_NETBSD_AUTOPORT_20261017.md. i915-Unvollständigkeit darf NICHT anhand von Quelltest-PASS übergangen werden.

**Historischer Zustand ist keine Live-Freigabe.** Vor jedem Schritt Branch-HEAD, Git-Origin, Zielrechte, aktive Prozesse und tatsächlich laufenden NetBSD-Kernel neu prüfen; konkurrierende Commits per Git-SHA-Preflight berücksichtigen. Die Aussage des Auftraggebers „RTL soweit fertig“ ist die Koordinationsvorgabe, kein Ersatz für laufzeitgeprüftes PCI Attach/IRQ/RX/WPA2.

## 2. Verbindliches, nicht manipulierbares i915-Release-Gate

Vor jeglichem HP-Kernel-Build muss im sauberen kanonischen i915-Git-Checkout im committed HEAD die i915-eigene Datei governance/HP_I915DRMKMS_KERNEL_RELEASE.json vorhanden sein. Der offizielle RTL-Prüfer verlangt exakt:
- schema 1, target HP-TPN-W121-RTL8723BE-I915DRMKMS, decision APPROVED, scope HP_COMBINED_KERNEL_BUILD_ALLOWED;
- rtl_source_sha = *jetzt* exakter 40-hex Git-SHA des zu bauenden RTL-Branches, nicht das veraltete oben genannte Datum;
- validated_i915_source_sha = nachgewiesener i915-Commit, im ancestry des Release-HEAD;
- sechs ehrliche verification-Werte PASS: full_i915_drm_ttm_port, netbsd_native_i915_kernel_link, hp_physical_kms_display, f83_f84_black_screen_resolved, hp_recovery_boot_verified, i915_runtime_pm_verified;
- approval.owner HP-I915 und echte approval.release_id.
Der RTL-Agent darf weder eine fake/temporäre APPROVED-Datei noch synthetische PASS-Evidenz veröffentlichen.

**Vorprüfung** (erst nach Prüfung der lokal tatsächlich vorhandenen Pfade; auf einem Quellhost ohne Kernel-Build zulässig):
    
    python3 tools/check_i915_kernel_release.py --i915-repo /pfad/zum/sauberen/i915-checkout --rtl-head "$(git rev-parse HEAD)"

Exit 2 = WAIT_FOR_I915_RELEASE, **kein** HP-Build. Die Prüfung unmittelbar VOR Source-Staging und VOR vollständigem Kernel-Link wiederholen; HEAD/Releases dürfen zwischenzeitlich nicht driften.

**Abhängigkeitszyklus:** Der aktuelle Prüfer fordert physisch funktionierendes i915-KMS und einen fertigen i915-Kernel-Link schon VOR dem kombinierten Build. Ist dieses KMS nur durch den noch nicht gebauten Kombikernel prüfbar, STOP mit DEPENDENCY_CYCLE, statt selbst die sechs Gates abzuschalten. Der i915-Owner muss entweder unabhängig einen lauffähigen i915-only Kernel samt realen Prüfbelegen liefern oder eine vom Nutzer ausdrücklich genehmigte, formal getrennte, sicherheitsbewertete compile-only-Freigabe vorschlagen/implementieren. Eine neue Freigabe ersetzt alte Sicherheitsprüfungen nur nach legitimer Änderung und erneuter Regression; keine Umgehung.

## 3. Kritischer technischer Fehler bisheriger RTL-Buildpfade

Der RTL-WIP-Branch enthält tools/build_hp_rtl50_next_candidate.sh, tools/configure_hp_live_native_50.py und tools/build_hp_native.py. Diese konstruieren absichtlich RTL-only-/SAFE-GENFB-Kernel und setzen in ihrer Konfiguration **no i915drmkms***. Alle drei dürfen für einen vermeintlichen gemeinsamen Kernel **nicht unverändert** ausgeführt werden. Ein erfolgreiches früheres RTL50/Shadow-Image hat nachweislich **NULL** i915-Kernelobjekte und erfüllt diesen Auftrag nicht.

**Erstelle einen neuen, eigenen Combined-Konfigurator/Builder** unter RTL-tools, etwa configure_hp_combined_i915_rtl.py und build_hp_combined_i915_rtl_candidate.sh, ohne RTL-only-Runner stillschweigend umzuschreiben. Er muss:
- echte i915-GPU-Source-Closure plus alle 50 RTL-Quellen aus demselben aktuellen RTL-Commit übernehmen;
- beide Geräte in der *neu erzeugten* NetBSD-Kernel-Config aktivieren;
- verbindlichen i915-Release-Check vor jeder Mutation und erneut vor Build/Link ausführen;
- auf i915-KMS-off, no i915drmkms*, null i915-Objekten im generierten Makefile, RTL-Quelllücken, fehlender Freigabe, schmutziger Quellbasis, falschem HP/OS/Owner oder fehlender Recovery-/Toolchain-Vorprüfung **fail closed** abbrechen;
- eine eindeutige neue Kernel-Identität aus i915-SHA12 und RTL-SHA12 einbetten; keine alte HP-RTL50-SAFE-GENFB-Identität wiederverwenden;
- Positiv- und Negativtests insbesondere für den alten no-i915-Fall, gefälschte Freigabe, falschen RTL-SHA und fehlenden i915-Objekt-Owner hinzufügen.

## 4. Vollständige Integrationsmatrix vor dem nativen Link

**i915:** 323 ausgewählte Linux-C-Units der eingefrorenen Referenz gegen reale NetBSD-native Einheiten oder begründete semantische Ersetzungen mappen (letzter struktureller Befund: 136 aktive exakte Pfade, 13 aktive gleichnamig verlegt, 7 gleichnamig vorhanden aber inaktiv, 167 ohne gleichnamiges NetBSD-Pendant). Dies sind Dateinamenkategorien, NICHT 167 automatisch fehlende Funktionen. Alle benötigten LinuxKPI, DRM, TTM, GEM/GTT, UVM, Memory, PCI, MMIO, DMA, IRQ, Firmware, VBT/OpRegion, eDP/AUX/CDCLK, power wells, modeset/framebuffer-handoff, panic-free cleanup/PM und init/unwind in NetBSD-APIs schließen. Moderne Parent-/Display-Callbacks (16 Schnittstellen), funktionale CHV IOSF get/put/read/write, korrekte PUNIT/locked_unit_mask-/DPIO_2-Sperrung, tatsächliche -EAGAIN/-ETIMEDOUT-Weitergabe prüfen. Der i915-Source-only-Patch für intel_sideband.c/.h ist noch KEIN nativer HP-Einbau. Vor einem Freigabe-PASS reale IRQ-/MMIO-Laufzeit und physisches Display nachweisen.

**RTL:** Exakt 50 aktuell ausgewählte native C-Units, PCI-Match RTL8723BE, NetBSD net80211/ifnet, bus_space/bus_dma, IRQ/IPL, Firmware und Firmware-Pfad, H2C/C2H, RF/Bluetooth-Coexistence, MAC/BB/RF, RFKill, Netzkanal, TX/RX-Descriptor/Rings, RX-Beacons und WPA2, Probe/Attach/Init/Stop/Detach sowie asymmetrische DMA-/Firmware-Fehlerpfade prüfen. Historische 47-/50-Objekt-/private-Kernel-Links ohne i915 und 35 Python-Quelltests sind nur Teilbelege.

**Kollisionen/Ablauf:** Beide PCI-Attachments haben eigene Lebenszyklen, IRQ, MMIO/BAR, DMA und PM; weder Gerät noch Interrupt-Owner doppelt registrieren. NetBSD-Kernel-Buildsystem, nicht Linux-Kconfig, ist ABI-Quelle. GPU probe -> Display init -> IRQ -> GEM -> DRM/KMS/Framebuffer entsprechend Referenz und realen NetBSD-Adaptern; WLAN PCI -> power -> firmware -> PHY/RF -> DMA/IRQ -> net80211 -> TX/RX entsprechend Referenz. Reverse-Unwind bei jedem Scheitern. Keine Dummy-Callbacks oder bloßes Unterdrücken unbekannter Symbole.

## 5. Nur HP: read-only Preflight für einen gemeinsamen Build

HP NetBSD 11 amd64 ist der einzige Native-Build-/Installationshost. Historischer, *nicht automatisch heute bestätigter* read-only SSH-Pivot: SentinelX Legion -> bestehende legitimierte SSH-Identität -> 10.1.0.44. Bei neuer Sitzung erst Quellidentität, bestehendes SSH-Schlüsselangebot, strikte Hostkey-Verifikation mit StrictHostKeyChecking=yes und BatchMode=yes, Zielkonto, Berechtigungen, OS, aktuelles Netzwerk testen. Bei providerseitiger Ausführungsablehnung keine alternative Shell/Host/Konto zur Umgehung.

Read-only auf HP prüfen: uname -srmv; id; NetBSD sysctl machdep.booted_kernel falls verfügbar; aktive bootbare Recovery samt tatsächlichem Default (historisches F77 ist nur ein dokumentierter Rückfallstand); freien Speicher/Platz; Prozesse/andere Builds; clean RTL/i915 Checkout; /usr/src/sys; /usr/tools/bin/nbconfig, /usr/tools/bin/nbmake-amd64; NetBSD-Compiler/Linker samt benötigtem PATH; /usr/pkg/bin/git, Python und Firmware. F16.0 darf nicht gebootet werden. F83/F84 zeigten schwarzes Panel mit Backlight; deren Ursache ist nicht geklärt. Für eine spätere Bootprobe muss ein unabhängiger funktionierender G01–G09-Frühkonsolen-/Rettungsweg nachgewiesen werden.

## 6. Genaue Combined-Kernel-Konfiguration und EIN Build

Lege für die beiden geprüften Git-SHAs einen **neuen privaten, unveränderlichen Source-/Objekt-Snapshot** außerhalb /usr/src und außerhalb /netbsd an; Base-NetBSD und gültige generierte Boot-/Kernel-Konfiguration nicht verändern. Original-SHA aller relevanten C/H/INC, NetBSD-Source-Hash, Freigabe und Konfigurationsfingerprint protokollieren.

Konfigurationsziel aus NetBSD GENERIC und tatsächlichen Dateien files.i915drmkms, files.pci sowie RTL config/files.rtwn8723be_native:
- i915drmkms* at pci? dev ? function ? (mit der tatsächlich benötigten NetBSD DRM/KMS- und intelfb-/intelfbbus-/drmfb-/wsdisplay-Auswahl).
- rtwn8723be* at pci? dev ? function ? (mit allen 50 ausgewählten RTL-Quellen).
- Keine wirksame no i915drmkms*-Zeile; keine reine genfb-Displayauswahl als Ersatz. Generische rtwn- oder nouveau-Match-Konflikte nur bei bewiesener Ursache gezielt ausschließen, nie pauschal.
- In der nach nbconfig erzeugten obj/Makefile tatsächlich i915-/DRM-Objektliste UND die 50 RTL-Objekte prüfen, doppelte Symbol-Owner und fehlende ABI-Provider verhindern. Keine drei-only-Objekt-Partial-Links als fertigen Kernel melden.

Nach vollständig bestandenem Preflight *nur auf HP* die tatsächlich vorhandenen nativen Tools verwenden, schematisch:

    /usr/tools/bin/nbconfig -s "$NETBSD_SRC/sys" -b "$OBJDIR" "$CONFIG"
    /usr/tools/bin/nbmake-amd64 -C "$OBJDIR" -j2 dependall

Ggf. den **bewiesenen** RTL-Linker-/PATH-Fix aus dem Owner-Wrapper übernehmen, nicht unüberprüft neue Compileroptionen erfinden. Vor dem großen Build die gesammelten Source-/Include-/Objekt-/ABI-/Symbolprobleme einmal erfassen und koordinieren. Ein kontrollierter vollständiger Build mit persistentem Status und Log; bei Fehlern Ursachen gruppiert beheben, nicht pro Kleinigkeit neu anstoßen.

POST erst bei realem Exit 0: vollständigen LD-Link in Log/Map nachweisen (nicht nur ld -r), nichtleeres ELF obj/netbsd, file, what-Identität mit beiden Source-SHAs, SHA-256, alle RTL- und i915-Objekte im echten Link, Kernel-Konfig, Symbolauflösung, PCI-Attachments und reproducible artifact log. Status COMBINED_KERNEL_LINKED_NO_INSTALL; **kein** Default-Eintrag/Install/Boot, kein Überschreiben /netbsd.

## 7. Danach erst: getrennt genehmigte Laufzeitabnahme

GPU: i915 bindet an 8086:22b1, echte native DRM/KMS-Übernahme, eDP-Panel/Connector, sichtbarer Modeset/Framebuffer, keine Panic/kein beleuchteter Blackscreen; G01–G09-Frühkonsole und PM/Suspend-Resume gegen Linux-/NetBSD-Lifecycle. Ein /dev/dri oder genfb zählt nicht als KMS-Erfolg.

WLAN: rtwn8723be0 bindet an 10ec:b723, Firmware geladen, physisch empfangene Beacons/Scan, WPA2-Assoziation/4-Way-Handshake, DHCP/IP/DNS und echte TX-/RX-Pakete, Recovery/Detach/Reinit/PM. Eine Interface-Anzeige allein zählt nicht als funktionierendes WLAN.

Rettungsfähigkeit: Verifizierter Rückfallkernel unverändert verfügbar und aus Boot-Menü auswählbar; keine Unterbrechung des vorhandenen Remote-Zugangs ohne unabhängigen Konsolenweg.

## 8. Reporting-/Handoff-Vertrag für zwei Agenten

i915-Owner liefert: exakter neuer i915-HEAD, validierter i915-Commit und vollständige DRM/TTM/GEM/323-Unit-Closure, native i915 Kernel-Link-/KMS-/Runtime-PM-/F83/F84-Fix-/Recovery-Belege, dann erst authentische i915-Release-Datei. Ein bloßer Git-Commit der IOSF-Patches ist **KEINE** i915-Freigabe.

RTL-Owner liefert: jetzt gültigen RTL-HEAD; Combined-Builder/Config samt Negativtests; GitSHA-/Quell-Owner-Matrix, beide PCI-Geräte/alle Kernel-Objekte in echter Konfiguration, Host-/Toolchain-/Recovery-Preflight, Build-Log/Exit-/LD-map, Kernel-SHA/what/file, klare Kennzeichnung kein Install/Boot, gesonderte KMS-/WLAN-Runtime-Ergebnisse und nachvollziehbaren Fehlerzustand.

Benutze Status in genau dieser Trennung: WAIT_FOR_I915_RELEASE / DEPENDENCY_CYCLE / INTEGRATION_READY / NATIVE_PREFLIGHT_PASS / COMBINED_KERNEL_LINKED_NO_INSTALL / TESTREADY / BOOTED / KMS_OK / WLAN_OK / FULLY_ACCEPTED. Jede Abweichung benötigt Fehlerfingerprint, tatsächliche Ursache, zulässige Reparatur, Regression, Commit-SHA, unabhängigen POST-Readback und NEXT. Vermeide OpenAI-Plattformablehnung mit GitHub-HTTP-Fehler gleichzusetzen.

**HANDLUNGSBEFEHL:** Starte sofort mit den unabhängigen GitHub-/Source-Only-Integrationsarbeiten für einen wirklichen Combined-Builder. Sobald die authentische i915-Freigabe und die unabhängigen HP-/Recovery-/Permissions-Gates nachgewiesen sind, starte den **einen** nativen Kernel-Build mit beiden Treibern. Bei fehlender Freigabe KEIN Kernel-Build und KEIN vorgetäuschter Erfolg.
