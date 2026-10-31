# Keks Trace

Chargenrückverfolgung mit Rework und Behältern für die Keksproduktion, als App für ERPNext 16.

Dieser Stand ist der **Prototyp für das Go/No-Go** aus Phase 0 des Konzepts. Er bildet den
echten Ablauf ab und zeigt, dass Rework über mehrere Tage in ERPNext sauber gebucht,
geprüft und rückverfolgt werden kann.

## Abgebildeter Ablauf

```
Zuckersirup      Zucker aus dem Silo (+ Wasser)               → Charge, Tank
Grundteig        Silos + Säcke (+ Rework)                     → Charge, Teigbehälter
   ↓  (ein Grundteig kann auf mehrere Veredelungen und Tage aufgeteilt werden)
Teig veredelt    Grundteig + Zutaten (+ Rework)               → Charge, Teigbehälter
   ↓
Backware         gebacken                                     → Charge
   ↓
Ware lose        + Füllung / Glasur / Schokolade              → Charge, Kiste im Lager loser Ware
   ↓  (Wochen bis Monate)
Fertigware       + Folie                                      → Los mit MHD
   ↓
Lieferschein     an den Kunden
```

Füllungen werden gekauft (Chargenstufe **Rohstoff**) oder selbst hergestellt (Chargenstufe
**Halbfabrikat**, eigene Charge mit eigener Rückverfolgung).

## Was die App kann

- **Rework-Regeln (Rework-Matrix):** welches Rework in welchen Grundteig oder veredelten Teig,
  mit welchem Höchstanteil. Ohne Regel wird die Buchung abgelehnt.
- **Allergenprüfung:** Rework darf keine Allergene in einen Teig bringen, die dieser nicht hat,
  auch wenn versehentlich eine Regel existiert (z. B. Soja aus schokoliertem Bruch im Nussteig).
- **Ablaufprüfung aller Eingänge:** Grundteig über Standzeit, Rework über Höchstalter,
  Füllung über MHD werden gesperrt, mit klarer deutscher Meldung.
- **Rework-Alter:** zählt ab dem ältesten Tag der ganzen Kette. Damit sind Rework-Ketten
  automatisch auf das Höchstalter begrenzt.
- **FIFO-Hinweis:** Warnung, wenn ein älterer Rework-Behälter übersprungen wird (blockiert nicht).
- **MHD:** ab Backtag, nicht ab Verpackungstag, und nie länger als das kürzeste MHD der nach dem
  Backen aufgebrachten Füllungen, Glasuren und Schokolade.
- **Behälter mit Code:** Teigbehälter, Rework-Behälter, Kisten loser Ware. Jeder Behälter weiß,
  welche Charge und wie viel darin liegt. Befüllen eines belegten Behälters, falscher Behälter
  und Entnahme über den Inhalt werden blockiert. Leere Behälter werden automatisch frei.
- **Genealogie:** jede Fertigungs- und Umpackbuchung schreibt Kanten Input-Charge → Output-Charge
  mit Menge und Anteil.
- **Rückverfolgung** vorwärts (bis zum Kunden mit Lieferschein) und rückwärts (bis zur
  Lieferantencharge, inkl. Füllung und Packmittel), über beliebig viele Stufen und
  Rework-Generationen, mit Anteil je Charge. Als Bericht „Rueckverfolgung“ und per API.
- **Silos und Tanks:** jedes Silo hat einen Artikel (z. B. Weizenmehl 550, Dinkelmehl, Zucker;
  Tank Zuckersirup). Entnahmen ohne Charge teilt das System nach FIFO auf die Chargen im Silo auf.
  Wird nachgefüllt, bevor das Silo leer ist, gelten alte und neue Charge als vermischt: die alte
  wird zusätzlich zugeordnet (Kante „Silo“, Menge 0), bis die Nachlaufmenge des Silos entnommen
  ist. Eine **Leermeldung** trennt sofort sauber und bucht einen rechnerischen Rest als
  „Silo Differenz“ aus. Sackware desselben Artikels wird wie gewohnt mit gescannter Charge gebucht.
  Gesperrte Chargen im Silo blockieren die Entnahme. Rückdatierte Entnahmen teilen nie mehr zu,
  als heute noch vorhanden ist.
- **Storno:** stornierte Buchungen bleiben sichtbar, fließen aber nicht mehr in die
  Rückverfolgung ein; Behälterinhalt wird zurückgesetzt.

### IFS Food 8

| Anforderung | Umsetzung |
| --- | --- |
| 4.18.1 Rückverfolgung über alle Stufen, Rework, Verpackung, Auslieferung (KO) | Genealogie und Bericht „Rueckverfolgung“ (siehe oben) |
| 4.18.2 Test mit Mengenbilanz, mindestens jährlich | **Mengenbilanz** je Charge (Bericht „Mengenbilanz“, API `mengenbilanz`): Zugang, verbraucht, zu Rework umgefüllt, ausgeliefert, entsorgt, Bestand, Ausbeute, Abgleich Lager gegen Genealogie. **Rückverfolgungstest** (DocType `Rueckverfolgungstest`): führt beim Anlegen vorwärts, rückwärts und alle Mengenbilanzen aus, misst die Dauer, speichert Bericht und Rohdaten; nach dem Buchen unveränderbar |
| 2.1.2.1 Aufzeichnungen nicht nachträglich änderbar, nur Berechtigte | Genealogie, Behälterhistorie und Sperrprotokoll für niemanden änderbar oder löschbar; gebuchte und stornierte Belege nicht löschbar; Chargen mit Historie nicht löschbar; Herstell- und Verfallsdatum nur durch die QS, mit Änderungsprotokoll an Charge und Artikel |
| 5.11 Nicht konforme Ware | **Sperren/Freigeben** (`keks_trace.sperre.sperren`, `freigeben`, nur QS): Artikel mit „Freigabe vor Verwendung“ starten gesperrt (Wareneingang, lose Ware). Gesperrte Chargen können nicht verarbeitet, umgefüllt oder ausgeliefert werden; Umlagern ins Sperrlager und Ausbuchen bleiben möglich. **Rückrufsperre** (`rueckruf_sperre`): sperrt eine Charge und alle, in die sie eingeflossen ist, und liefert die betroffenen Kunden. Alles im Protokoll `Chargen Sperre` |
| Vollständigkeit (Auditor-Frage) | Fehlt bei einer Fertigung eine Zutat laut Stückliste, warnt oder blockiert die Buchung (Einstellung in `Keks Trace Einstellungen`) |

Gebucht wird ausschließlich mit ERPNext-Standardbelegen (Stock Entry „Manufacture“ und „Repack“,
Lieferschein). Der ERPNext-Kern wird nicht verändert.

## Aufbau

| Datei / Objekt | Zweck |
| --- | --- |
| `keks_trace/hooks.py` | Hängt Prüfungen, Genealogie und Behälter an Lagerbuchungen |
| `keks_trace/install.py` | Chargenstufen, Zusatzfelder, Chargenverwaltung aktivieren |
| `keks_trace/pruefungen.py` | Einstieg für alle Prüfungen vor dem Buchen, Ablaufprüfung |
| `keks_trace/rework.py` | Rework-Matrix, Allergene, Höchstanteil, FIFO |
| `keks_trace/traeger.py` | Behälter befüllen, entnehmen, freigeben, Storno |
| `keks_trace/genealogie.py` | Genealogie-Kanten, Ursprung, Backtag, Komponenten-MHD, Verfall |
| `keks_trace/trace.py` | Rekursive Rückverfolgung vorwärts/rückwärts, Kunden |
| `keks_trace/api.py` | `rueckverfolgung`, `mengenbilanz`, `traeger_info` und `silo_info` für Scanner und Terminals |
| `keks_trace/sperre.py` | Sperren, Freigeben, Rückrufsperre, Prüfung bei Buchung und Lieferung |
| `keks_trace/schutz.py` | Unveränderbarkeit von Protokollen, Belegen und Chargendaten |
| `keks_trace/vollstaendigkeit.py` | Fehlende Rezeptzutaten erkennen |
| `keks_trace/bilanz.py` | Mengenbilanz je Charge |
| `keks_trace/silo.py` | Silo/Tank: FIFO-Zuteilung, Vermischung, Leermeldung (`leermeldung`), Silo-Info |
| DocType `Allergengruppe` | Allergene je Teig, Füllung, Rework |
| DocType `Rework Regel` | Rework-Matrix |
| DocType `Produkttraeger` | Behälter, Kiste oder Palette mit Code (QR) |
| DocType `Traeger Belegung` | Historie: welche Charge wann in welchem Behälter lag |
| DocType `Chargen Genealogie` | Kanten der Rückverfolgung (wird nur automatisch geschrieben) |
| DocType `Chargen Sperre` | Protokoll aller Sperren und Freigaben |
| DocType `Silo` | Silo oder Tank: Lagerort, Artikel, Nachlaufmenge |
| DocType `Silo Leermeldung` | Protokoll: Silo leer, rechnerischer Rest und Ausbuchung |
| DocType `Rueckverfolgungstest` | Testprotokoll mit Mengenbilanz als Audit-Nachweis |
| DocType `Keks Trace Einstellungen` | Vollständigkeitsprüfung, Toleranz der Mengenbilanz |
| Bericht `Rueckverfolgung` | Rückverfolgung in der Oberfläche |
| Bericht `Mengenbilanz` | Mengenbilanz einer Charge in der Oberfläche |
| `keks_trace/demo.py` | Demo-Stammdaten und drei Produktionstage |
| `keks_trace/tests/` | Abnahmetests |

**Zusatzfelder:**
- am Artikel: **Chargenstufe** (Rohstoff, Packmittel, Halbfabrikat, Grundteig, Teig veredelt,
  Rework, Backware, Ware lose, Fertigware), **Allergengruppe**, **Freigabe vor Verwendung**;
- an der Charge: **Chargenstufe**, **Sperrstatus**, **Sperrgrund**, **Ursprungsdatum**, **Backtag**,
  **Kürzestes Komponenten-MHD**;
- am Buchungsposten: **Behälter / Träger**, **Silo / Tank** (gesetzt bei FIFO-Zuteilung).

Haltbarkeiten nutzen die ERPNext-Standardfelder „Has Expiry Date“ und „Shelf Life In Days“ am Artikel:
Standzeit bei Teigen, Höchstalter bei Rework, maximale Lagerdauer bei loser Ware, MHD bei Fertigware
und Füllungen.

## Installation auf dem Testserver

Voraussetzung: ERPNext 16 läuft und der Einrichtungsassistent ist abgeschlossen (Firma angelegt).

```bash
cd ~/frappe-bench          # bzw. /workspace/development/frappe-bench im Container
bench get-app https://github.com/Heinrich-Schulze-Ladencafe-GmbH/keks_trace
bench --site keks.localhost install-app keks_trace
```

Für ein privates Repository fragt Git nach Zugangsdaten. Am einfachsten einen
GitHub-Token (nur Lesezugriff auf dieses Repository) als Passwort verwenden.

### Updates einspielen

```bash
cd ~/frappe-bench/apps/keks_trace && git pull
cd ~/frappe-bench && bench --site keks.localhost migrate
```

## Terminals

Die Scanner-Oberfläche läuft im Browser unter **`/terminal`** (z. B. `http://localhost:8000/terminal`).
Keine Mitarbeiter-Anmeldung: jedes Terminal meldet sich einmal mit einem Stations-Benutzer an und
wählt beim ersten Start seine Station. Jede Buchung trägt die Station (Feld „Station (Terminal)“
an Lagerbuchung und Lieferschein).

| Station | Knöpfe (Vorlage) |
|---|---|
| Backstube | Herstellen (Grundteig, Veredelung, Backen, Füllen, Sirup), Rework/Bruch, Silo leer, Info-Scan |
| Verpackung | Verpacken (lose Ware + Folie → Los mit MHD), Packbruch, Paletten, Info-Scan |
| Herzen Garnieren | Herstellen (Veredelung, Füllen: Zuckerguss usw.), Rework/Bruch |
| Herzen Verpackung | Verpacken, Packbruch, Paletten |
| Lager | Wareneingang (Lieferantencharge, MHD, ins Silo, als Sackware oder Gebinde mit QR-Etikett), Silo leer, Paletten, Umlagern |
| Versand | Lieferung (Kunde/Auftrag wählen, Lose oder NVE scannen → Lieferschein), Paletten |
| Lagerverkauf | Umlagern ins Lager „Lagerverkauf“ (Scan von Los, Karton oder Palette) |

Die Knöpfe sind je Station einstellbar (**Terminal Station**: Haken je Funktion und erlaubte
Stufen); der Typ belegt sie nur vor. Der Server prüft bei jeder Buchung, ob die Station die
Funktion darf.

Eine Bildschirmtastatur unten schreibt in das angetippte Feld: Ziffern bei Mengen und Datum
(MHD als `300628` oder `30.06.28`), Buchstaben bei Text. OK springt ins nächste Feld, ▾ blendet
sie aus. Der Scanner wird an der Tippgeschwindigkeit erkannt: ein Scan landet immer im Scanfeld,
auch wenn gerade ein Mengenfeld aktiv ist (dessen Inhalt bleibt). Echte Tastatur geht immer.

Gescannt werden Behälter-Codes, Silo-Namen, Paletten (NVE) oder Chargennummern. Jede Zeile wird beim Scannen
geprüft (Rezept, Sperre, Verfall, Rework-Regel, Allergene, Bestand im Behälter/Silo). Stationen
werden unter **Terminal Station** gepflegt (Typ und Lagerorte); `keks_trace.demo.stammdaten`
legt die Demo-Stationen an.

## Kundenaufträge, Los und MHD

- **Kundenaufträge** (Sales Order) steuern das Verpacken: Das Terminal Verpackung zeigt offene
  Aufträge mit Restmenge und Termin; Verpackung, Palette und Lieferschein hängen am Auftrag,
  ERPNext führt „geliefert“ im Auftrag mit. Ohne Auftrag geht es weiterhin.
- **Paletten als Einheit**: am Artikel die Einheiten „Lage“ und „Palette“ mit kg je Palette
  (z. B. 42 Karton × 4 kg = 168 kg). Aufträge dürfen in Paletten stehen; das Terminal zeigt
  gemischt („offen 4 Paletten + 22 Karton“), gezählt wird weiter in Karton/Beutel. Die Palette
  zeigt ihre Füllung („35 von 42 Karton“) und meldet „voll“ bzw. „überladen“. Der Lieferschein
  steht in der Auftragseinheit (z. B. 0,48 Palette), die gezählten Kartons stehen daneben.
- **Los JWWT** (Einstellung „Los-Format“): Jahr, ISO-Kalenderwoche, Wochentag. Ein Los je
  Artikel und Tag; mehrere Verpackungen am Tag gehen in dieselbe Charge (`<Artikel>-<Jahr>-<Los>`).
  Ein gesperrtes Los wird nicht weiter befüllt. Vor dem Buchen zeigt das Terminal Los und MHD
  zum Einstellen des Beuteldruckers; sinkt das MHD durch ältere Ware, gibt es eine Warnung.
- **MHD**: am Artikel „Haltbarkeit in Monaten“ und „MHD zählt ab“ (Backtag/Verpackungstag).
  Beim Tages-Los gilt immer der älteste Backtag und das früheste Komponenten-MHD.
- **Gebinde** (Sack, Fass, IBC, ...): Wareneingang mit Anzahl und Menge je Gebinde, jedes Gebinde
  bekommt einen eigenen Code und ein QR-Etikett (`/gebinde_etikett?codes=…`). Die Backstube
  scannt den Gebinde-Code; der Rest im Gebinde wird mitgeführt.

## Pilot Honig Lebkuchen

```bash
bench --site keks.localhost execute keks_trace.pilot.anlegen       # Stammdaten
bench --site keks.localhost execute keks_trace.pilot.durchspielen  # ein Tag komplett
```

Echte Rezepturen 5812 (Grundteig Honig) und 5888 (Honig Moppen), Artikel 17846/17670 mit EANs,
MHD 32 Monate. Ausgedachte Werte (Beutelgrößen, Gebinde, Ruhezeit, Packmittel) stehen in
`keks_trace/pilot.py` unter `PLATZHALTER`.

## Paletten (NVE / SSCC)

- **Verpacken** zählt in Karton oder Beutel (Umrechnung in kg steht am Artikel unter „Einheiten“).
  Fertigware bekommt eine kurze Los-Nummer (`L261030-01`). Beim Buchen eine Palette scannen
  oder „Neue Palette“ tippen: NVE wird vergeben, das GS1-Etikett (A6) öffnet sich zum Drucken.
- Paletten dürfen **gemischt** sein. Der Inhalt ergibt sich nur aus den unveränderbaren
  **Paletten-Bewegungen** (Zugang/Abgang je Los, Einheit, Station, Beleg).
- **Anbrechen/Kommissionieren:** Palette scannen, Position antippen, Anzahl, Zielpalette scannen
  oder neue Versandpalette anlegen.
- **Lieferung:** ganze Palette, einzelne Kartons von einer Palette oder lose Kartons. Ein
  Lieferschein kann nichts liefern, was auf einer Palette steht, ohne diese Palette anzugeben.
  Storno des Lieferscheins stellt die Paletten wieder her; eine Fertigung, deren Los auf einer
  Palette steht, kann nicht storniert werden.
- Rückverfolgung, Rückverfolgungstest und Rückrufsperre zeigen die betroffenen NVEs.
- Etikett: `/nve_etikett?nve=…`. NVE = Reserveziffer + **GS1-Basisnummer** + laufende Nummer +
  Prüfziffer. Basisnummer unter **Keks Trace Einstellungen** eintragen; ohne sie werden
  Test-NVEs (Nummernkreis 02) mit Aufdruck „TEST-NVE“ erzeugt, die nicht an Kunden gehen dürfen.
  Sortenreine Paletten bekommen einen zweiten Strichcode mit GTIN, MHD, Anzahl und Los,
  wenn am Artikel ein Barcode (EAN) je Einheit hinterlegt ist.

## Prüfungen (CP/CCP)

Unter **Prüfplan** werden Kontrollen gepflegt: Lenkung (CCP, CP, GHP), Auslöser (Intervall in
Minuten, je Buchung oder je Wareneingang), Stationen und/oder Artikel, Art (Messwert mit Min/Max
und Einheit, Prüfkörper wie Fe/NE/VA beim Metalldetektor, Ja/Nein), Korrekturmaßnahme und
Verweis auf das HACCP-Dokument.

- Am Terminal erscheint eine Leiste mit fälligen Prüfungen, sortiert nach sperrend, CCP, CP.
  Mit „sperrt wenn fällig“ (z. B. Metalldetektor stündlich) bucht die Station erst wieder,
  wenn die Prüfung erfasst ist.
- Prüfungen je Buchung oder Wareneingang (Brix am Sirup, Temperatur Kühlware) werden direkt im
  Buchungsdialog abgefragt. Ein Wert außerhalb der Grenze verweigert z. B. die Annahme und zeigt
  die Korrekturmaßnahme.
- Abweichung bei einer Intervallprüfung: Bemerkung ist Pflicht, alle Lose der Station seit der
  letzten OK-Prüfung werden gesperrt, die Prüfung ist sofort wieder fällig.
- Jede Erfassung ist ein unveränderbares Protokoll **Prüfung** (PR-JJJJ-…).

Die Demo-Stammdaten legen an: Metalldetektor Verpackung und Herzenboden (CCP, stündlich,
sperrend), Etikettencheck, Gewichtskontrolle, Brix Invertzuckersirup 80–84, Temperatur Butter
≤ 6 °C. **Die Verpackungsstationen buchen daher erst nach der Metalldetektor-Prüfung.**

## Lagerverkauf

Der Lagerverkauf ist ein eigener Lagerort. Ware kommt per Scan über „Umlagern“ dorthin (Los,
Karton oder ganze Palette), auch 2. Wahl. Verkauft wird weiter über die vorhandene Kasse (TSE
bleibt dort).

Tagesabschluss: **Lagerverkauf Abschluss** anlegen, den Export der Kasse (CSV oder Excel mit
Spalten für Artikelname und Anzahl) anhängen, „Datei einlesen“. Da die Kasse nur Namen kennt,
ordnet **Kassenartikel** jedem Kassennamen Artikel und Einheit (Beutel, Eimer …) zu. Unbekannte
Namen bekommen einen Vorschlag und werden einmal von Hand zugeordnet; beim Buchen merkt sich
das System die Zuordnung. Gebucht wird als „Abverkauf Lagerverkauf“ nach FEFO (frühestes MHD
zuerst, gesperrte Lose nie). Rückverfolgung, Mengenbilanz und Rückruf zeigen den Lagerverkauf
als Abnehmer „Endverbraucher“ mit verkaufter Menge und Restbestand.

## Demo: drei Produktionstage

```bash
bench --site keks.localhost execute keks_trace.demo.run
```

Legt Demo-Artikel (Präfix `KT-`) mit Rezepten (Stücklisten), Allergengruppen, Rework-Regeln,
Behälter, einen Demo-Lieferanten und -Kunden an. Butter und lose Ware sind freigabepflichtig.
Die Demo bucht:

Jeder Lauf legt eigene Silos mit seinem Kürzel an (Weizenmehl 550, Dinkelmehl 630, Zucker,
Tank Zuckersirup), damit sich Läufe nicht vermischen.

1. **Tag 1:** Wareneingang (Mehl, Zucker, Dinkel ins Silo), Freigabe der Butter durch die QS;
   Zuckersirup aus Silozucker in den Tank; Grundteig GT1 in Behälter TB1; Nougatfüllung selbst hergestellt;
   halber GT1 wird zu Nussteig V1; Backen; Schokoboden mit gekaufter Kuvertüre → lose Ware in
   Kiste KL1; Bruch → Rework R1 in Rework-Behälter RB1.
2. **Tag 2:** Nachfüllen von Mehl- und Zuckersilo, bevor sie leer sind (Vermischung); zweite Hälfte von GT1 + Rework R1 → Nussteig V2 (TB1 und RB1 werden frei); Backen,
   Schokolieren → KL2. Grundteig GT2 (Zucker nach FIFO: Rest alte + neue Charge) → Kakaoteig V3
   mit Dinkelmehl und Zuckersirup, Teigrest → Rework R2; Backen; Füllen mit
   Nougat → lose Ware in Kiste KL3.
3. **Freigabe** der losen Ware in KL1 und KL3 (KL2 bleibt gesperrt).
4. **Tag 3:** Leermeldung Dinkelsilo (1 kg Rest wird ausgebucht), neue Dinkellieferung; Grundteig GT3 mit 5 % Rework R2; Verpacken aus KL1 (Rest bleibt in der Kiste) und
   KL3; Lieferung beider Lose an den Demo-Kunden.
5. **Rückverfolgungstest** für die Mehlcharge, gebucht als Protokoll.

Danach gibt sie Rückverfolgungen, den Behälterstand und den Testbericht mit allen Mengenbilanzen aus. Das Kakao-Nougat-Los zeigt die
MHD-Begrenzung durch die Füllung (MHD = MHD des Nougats statt Backtag + 270 Tage).

> Nur auf einem Testsystem ausführen. Die Demo bucht echte Lagerbewegungen.

## Tests

```bash
bench --site keks.localhost set-config allow_tests true
bench --site keks.localhost run-tests --module keks_trace.tests.test_rework_kette
```

| Test | Szenario |
| --- | --- |
| `test_t06*` | Nuss-Rework in Grundteig ohne Regel blockiert; Allergenkonflikt trotz falscher Regel; schokolierter Bruch bringt Soja in Nussteig; Teigrest-Rework in veredelten Teig erlaubt |
| `test_t07` | Rework-Anteil über Maximum blockiert, mit zulässiger Restmenge |
| `test_t08`, `test_t08b` | Abgelaufenes Rework und Grundteig über Standzeit blockiert |
| `test_t09` | FIFO-Hinweis bei jüngerem Rework, Buchung läuft trotzdem |
| `test_rework_alter_*` | Rework-Alter zählt ab ältestem Tag der Kette |
| `test_t10`, `test_t10b` | MHD ab Backtag; MHD durch selbst gemachte Füllung begrenzt |
| `test_t11` | Ein Grundteig auf zwei Veredelungen an zwei Tagen |
| `test_t13` | Rückruf Mehl vorwärts bis zu beiden Kunden-Losen, inkl. Anteil über Rework |
| `test_t14` | Rückwärts bis Füllung, Lieferant und Packmittel; über Rework bis zum Grundteig vom Vortag |
| `test_t15` | Storno entfernt Kanten und leert den Behälter, Historie bleibt |
| `test_t16*` | Belegter Behälter, falscher Behälter, zu viel entnommen, Teilentnahme, Behälter in Reinigung |
| `test_t12`, `test_t17` | Nicht freigegebene lose Ware und gesperrter Wareneingang blockiert, nach Freigabe möglich |
| `test_t18`, `test_t18b` | Rückrufsperre sperrt alle betroffenen Chargen; gesperrtes Los kann nicht ausgeliefert werden |
| `test_t19` | Lagerbenutzer darf nicht freigeben und kein MHD ändern |
| `test_t20`–`test_t22` | Protokolle nicht änderbar/löschbar; stornierte Belege und Chargen mit Historie nicht löschbar; Sperrstatus nicht von Hand |
| `test_t23` | Fehlende Rezeptzutat: Warnung bzw. Blockade |
| `test_t24`, `test_t25` | Mengenbilanz Rohstoff inkl. Entsorgung und Ausbeute; erkennt eine Lücke zwischen Lager und Genealogie |
| `test_t26` | Rückverfolgungstest als unveränderbarer Nachweis |
| `test_t27` | Silo: FIFO-Zuteilung auf alte und neue Charge |
| `test_t28`, `test_t28b` | Vermischung beim Nachfüllen; Nachlauf endet nach genug Entnahme |
| `test_t29` | Leermeldung bucht den Rest aus und trennt alte und neue Charge sauber |
| `test_t30` | Zuckersirup: rückwärts bis zur Zuckercharge, Ausbeute mit Wasser |
| `test_t31`, `test_t32` | Gesperrte Charge im Silo blockiert; zu wenig im Tank |
| `test_t33` | Sackmehl neben Silomehl: genau die gescannte Charge |

Die Tests rollen ihre Daten am Ende zurück.

## Bewusst noch nicht enthalten

Waagenanbindung, Wareneingang über Bestellungen, eigene Kasse mit TSE und Kundendisplay,
Bio/V-Label-Kennzeichnung, Abweichungsmanagement/CAPA, SOPs und Schulungsnachweise.

## Offene fachliche Annahmen (von der QS zu bestätigen)

- Rework-Höchstalter in der Demo: 7 Tage, gezählt ab dem ältesten Tag der Kette.
- Höchstanteil in der Demo: 10 % der Einwaage.
- Nachlaufmenge Mehlsilos 100 kg, Zuckersilo 50 kg, Sirup-Tank 20 kg (abhängig von Silogeometrie, mit der Technik festlegen).
- Standzeit Grundteig 3 Tage, veredelter Teig 2 Tage, lose Ware 180 Tage ab Backtag.
- Schokolierter oder gefüllter Bruch hat keine Rework-Regel (geht nicht zurück in Teig).
- MHD Fertigware = früheres von Backtag + Haltbarkeit und kürzestem MHD der nach dem Backen
  aufgebrachten Füllungen, Glasuren und Schokolade.

## Lizenz

Interne Software der Heinrich Schulze Ladencafe GmbH. Alle Rechte vorbehalten.
