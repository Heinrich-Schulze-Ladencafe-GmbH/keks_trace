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

## Flussschema (F1–F20)

Alle Warenflüsse stehen im Flussschema (Bestände und nummerierte Flüsse, je mit Buchungspunkt). Neu dazu:

- **F7 lose Ware im Karton:** Am Verpackungs-PC „Lose Ware buchen“, gezählt in Kartons (kg je Karton fest am
  Artikel, Einheit „Karton“), auf Palette mit NVE ins Lager. Lose Ware darf auf Paletten, umgelagert und
  geliefert werden (Kiloware).
- **F8/F9 Linienlager:** Kommt die Verpackung nicht nach, gehen Kartons ins Linienlager (Feld „Linienlager“ an
  der Linie). Der Verpackungs-PC zeigt, was dort wartet, und verpackt es zuerst („Lose Ware verpacken“).
  Wannen werden nicht gebucht und müssen am selben Tag leer sein.
- **F13 Herzen-Rohlinge:** normaler Auftrag der Backstraße (lose Ware im Karton), Herzenboden holt per Umlagern.
- **F18/F19 Rework:** nur die Backstube bucht Rework: Auftrag an der Linie, Sorte nach Entnahmepunkt (nach dem
  Ofen, nach dem Sprühen, am Ende; Feld am Rework-Artikel), Behälter, Gewicht von der Waage, Etikett. Der Teig
  der Linie wird dabei zu Rework (kein Linienrest). Am Kneter geht es zurück; der Filter lässt nur passende
  Sorten (Rework-Regel, Allergene) bis zum Höchstanteil zu, und es geht mit dem Teig in die Ware ein.
- **F20 Bruch/Biogas:** wird nicht gebucht; er ist der Linienrest beim Auftragsende.
- **Doppelbuchungen:** Jede Buchung vom Terminal trägt eine Anfrage-ID (`anfrage.py`). Geht eine Antwort im
  WLAN verloren und es wird nochmal getippt, liefert der Server das erste Ergebnis statt doppelt zu buchen.


Prüfstellen im Fluss (Scan, Schranke, Nachweis), QS und Behälter-Kreislauf: [docs/soll-prozess.html](docs/soll-prozess.html).

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
| Rezepturtreue (Einwaage) | Am Teigmacher wird die Einwaage je Zutat gegen das Soll geprüft, umgerechnet auf die Sollmenge (halbe Masse = halbe Sollmenge). Außerhalb der Toleranz (je Rezeptzeile oder Standard, mit Mindesttoleranz für kleine Mengen) braucht die Buchung einen Grund; er steht an der Buchung (`Rezept-Abweichung`) |
| Lagerumschlag (FEFO) | Rohstoff/Packmittel mit späterem MHD gescannt, obwohl ein früheres im Lager liegt: Hinweis beim Scan, Grund beim Buchen (Einstellung), gespeichert an der Buchung (`FEFO-Abweichung`). Bericht **MHD Rohstoffe**: was bald abläuft und was bei normalem Verbrauch voraussichtlich übrig bleibt |
| Rückverfolgung Lieferant | Die Charge ist die Lieferanten-Charge (keine Zweitnummer). Wareneingang per Scan des GS1-128-Etiketts; offensichtlich falsche Chargen („Präsentkarton“) werden abgewiesen |
| Durchsicht der Aufzeichnungen | Bericht **QS Tagesliste**: FEFO- und Einwaage-Abweichungen, Prüfungen außerhalb der Grenze und Sperren eines Tages an einer Stelle; offene Freigaben als Zahl. „Tag als durchgesehen bestätigen“ (nur QS) legt ein unveränderbares Protokoll **QS Durchsicht** an (wer, wann, wie viele Einträge) |
| Reinigung Behälter | Je Behälterart einstellbar: leerer Behälter geht auf „Reinigung“ und wird erst nach der Meldung „gereinigt“ (Info-Scan, mit Zeit und Station) wieder befüllt |

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
| `keks_trace/terminal/` | Schnittstelle der Terminals, nach Bereichen: `basis`, `bestand`, `stammdaten`, `scan`, `einwaage`, `zutaten`, `arbeitsliste`, `buchen`, `eingang`, `versand`, `palette`, `behaelter`, `linie`. Aufgerufen wird weiter `keks_trace.terminal.<funktion>` |
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
| `keks_trace/www/terminal.html` | Seite `/terminal` (Stil und Rahmen); das Skript liegt als ES-Module in `keks_trace/public/js/terminal/` (`main.js` lädt die Teile: `basis`, `tastatur`, `rahmen`, `station`, `linie`, `herstellen`, `rework`, `wareneingang`, `paletten`, `lieferung`, `lager`, `info`). Kein `bench build` nötig; `www/terminal.py` hängt einen Hash der Dateien an, damit Browser nach einem Update nichts Altes aus dem Cache nehmen |
| `tests/terminal/` | Rauchtest im Browser ohne Frappe (siehe unten) und strenge ESLint-Regeln für die Terminal-Module |

**Zusatzfelder:**
- am Artikel: **Chargenstufe** (Rohstoff, Packmittel, Halbfabrikat, Grundteig, Teig veredelt,
  Rework, Backware, Ware lose, Fertigware), **Allergengruppe**, **Freigabe vor Verwendung**;
- an der Charge: **Chargenstufe**, **Sperrstatus**, **Sperrgrund**, **Ursprungsdatum**, **Backtag**,
  **Kürzestes Komponenten-MHD**;
- am Buchungsposten: **Behälter / Träger**, **Silo / Tank** (gesetzt bei FIFO-Zuteilung).

Haltbarkeiten nutzen die ERPNext-Standardfelder „Has Expiry Date“ und „Shelf Life In Days“ am Artikel:
Standzeit bei Teigen, Höchstalter bei Rework, maximale Lagerdauer bei loser Ware, MHD bei Fertigware
und Füllungen.

## Prüfen ohne Server

Die GitHub-Aktion **Prüfen** (`.github/workflows/pruefen.yml`) läuft bei jedem Push: `ruff` für Python,
ESLint für die Terminal-Module und der **Rauchtest** des Terminals. Der Rauchtest lädt `/terminal` in Chromium mit
nachgebildeten Server-Antworten (`tests/terminal/attrappen.mjs`), klickt sich je Stationstyp durch alle Knöpfe
und meldet jeden JavaScript-Fehler. Lokal (Node 22, Playwright mit Chromium):

```bash
node tests/terminal/rauchtest.mjs                          # Tiefe 3, alle Stationen
node tests/terminal/rauchtest.mjs --speichern /tmp/vorher  # vor einem Umbau alle Bildschirme festhalten
node tests/terminal/rauchtest.mjs --vergleich /tmp/vorher  # danach: Bildschirme und API-Aufrufe gleich?
```

Neue Masken oder Felder brauchen passende Antworten in `attrappen.mjs`, sonst baut der Test sie nur halb auf.
Die Integrationstests (`bench run-tests`) laufen weiter auf dem Testserver.

## Testserver auf Debian 13 in einem Lauf

Auf einer frischen VM mit Debian 13 (trixie). Zuerst die allgemeine Grundeinrichtung (sudo-Benutzer,
Rechnername, Zeitzone, feste IP, Proxmox-Agent) aus dem Repository
[server-werkzeuge](https://github.com/Heinrich-Schulze-Ladencafe-GmbH/server-werkzeuge):
`debian/grundeinrichtung.sh`, als root mit `su -` (mit Minus). Danach neu starten.

Dann keks_trace, als root:

```bash
curl -fsSLO https://raw.githubusercontent.com/Heinrich-Schulze-Ladencafe-GmbH/keks_trace/main/scripts/testserver-einrichten.sh
sudo bash testserver-einrichten.sh               # Testfirma „Keks Test GmbH“ mit Demo-Daten
sudo bash testserver-einrichten.sh --update      # später: neuesten Stand einspielen
```

Das Skript installiert MariaDB, Redis, nginx, supervisor, Chromium (für PDFs statt wkhtmltopdf),
Node 24 (offizielles Paket mit Prüfsumme), uv mit Python 3.14 und bench; dann Frappe/ERPNext 16,
E-Rechnung, DATEV und keks_trace, richtet die Seite auf Deutsch ein, spielt die Demos ein und stellt
auf Dauerbetrieb (startet nach Neustart von selbst). Am Ende stehen Adresse und Anmeldung da; die
Passwörter erzeugt es selbst und legt sie nur in `/root/keks-zugang.txt` ab. Bricht ein Lauf ab:
nochmal starten, Erledigtes wird übersprungen. Ist das Repository privat, fragt es nach einem
GitHub-Token (nur Lesezugriff) und lässt ihn nicht im Repository stehen; ohne Abfrage:
`KT_TOKEN=... sudo -E bash testserver-einrichten.sh`. Für Etikettendrucker muss die VM im selben
Netz wie die Drucker sein (Port 9100).

Ist das Repository privat, lässt sich das Skript selbst nicht per `curl` laden: dann aus GitHub
herunterladen und auf die VM kopieren.

## Installation auf einem bestehenden Server

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

**Einwaage wie bei FOBIS:** Die Zutatenliste beim Herstellen zeigt je Zutat **Bestellt** (Soll),
**Erledigt** (gescannt) und **ToDo**, darunter den Lagerort (Quelllager der Stückliste, sonst Standardlager des
Artikels, bei Silo-Zutaten das Silo). Steht am Artikel eine Maßeinheit-Umrechnung größer als die Lagereinheit
(z. B. 1 Sack = 25 kg), fragt das Terminal nach dem Scan in **Gebinden** („Wie viele Sack?“, darunter „= 50 kg“);
geht der Rest in ganzen Gebinden auf, ist das schon vorgewählt. Umschalten auf kg geht immer.

**Hinweis vom Büro:** Am Produktionsauftrag („Hinweis an Linie und Verpackung“) und am Kundenauftrag („Hinweis
an Produktion und Verpackung“) eine Zeile eintragen, z. B. „Mit Clip, neue Folie 2026“. Sie steht groß und gelb
über dem Auftrag an der Linie, am Verpackungs-PC, an der Packstation, beim Verpacken nach Kundenauftrag, in den
Auftragslisten und in der Tagesübersicht.

**Retour ins Lager:** „An die Linie“ → **Retour ins Lager**. Rohstoffe und Packmittel, die für den laufenden
Auftrag an die Linie gegeben, aber nicht verbraucht wurden (halber Sack, Folienrolle), gehen zurück in das Lager,
aus dem sie kamen. Sonst würden sie beim Auftragsende als Linienrest ausgebucht. Silo-Ware geht nicht zurück.
„Auftrag beenden“ erinnert daran, solange noch etwas auf der Linie liegt.

**Tagesübersicht** (an jeder Station): Aufträge des Tages je Linie mit Status, bestellt, gebucht (Balken) und
Hinweis, Zähler offen/fertig, blättern nach Vortag und Folgetag. Heute zeigt sie auch noch freigegebene oder
laufende Aufträge von früheren Tagen („vom …“).

**Datumsfelder** haben ein festes Format: nur Ziffern (TTMMJJ), die Punkte setzt das Terminal. Unter dem Feld
steht sofort das erkannte Datum mit Wochentag oder der Fehler (gibt es nicht, unvollständig, in der
Vergangenheit, über 10 Jahre in der Zukunft). Buchen geht erst mit gültigem Datum. Das MHD beim Wareneingang
ist Pflicht und darf nicht abgelaufen sein; der Server prüft das zusätzlich.

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

Eine Bildschirmtastatur schreibt in das angetippte Feld: Ziffern bei Mengen und Datum
(MHD als `300628` oder `30.06.28`), Buchstaben bei Text. OK springt ins nächste Feld.

**Ab 1000 px (Surface, Terminal) steht der Ziffernblock fest rechts**, wie bei FOBIS. Er wird nicht ein-
und ausgeblendet, der Inhalt springt nicht. Ohne aktives Feld gehen die Ziffern ins Scanfeld. Auch Scan- und
Suchfelder starten mit Ziffern (dort ist „,“ ein „-“); **ABC** schaltet auf Buchstaben, **123** zurück.
Reine Freitextfelder (Grund, Bemerkung) starten mit Buchstaben. Ohne Feld auf dem Bildschirm ist der Block
blass. Am Handy (unter 1000 px) erscheint die Tastatur wie bisher nur bei Bedarf, ▾ blendet sie aus. Der Scanner wird an der Tippgeschwindigkeit erkannt: ein Scan landet immer im Scanfeld,
auch wenn gerade ein Mengenfeld aktiv ist (dessen Inhalt bleibt). Echte Tastatur geht immer.

### Maske wie bei FOBIS (Einwaage und Verladung)

Ab 1000 px Breite sind **Einwaage** (Ansatz) und **Verladung** (Lieferung zu einem Kundenauftrag)
zweispaltig aufgebaut:

- **links** die Positionen als Tabelle (Pos, Artikel, Lager bzw. Einheit, Bestellt, Erledigt, ToDo,
  Status, Hinweis). Antippen wählt eine Position. Darunter steht die gewählte Position groß
  (Bestellt / Erledigt / ToDo) mit ihren Registrierungen; ✕ nimmt eine zurück.
- **rechts** die Gruppen **Herkunft** (Scan, Silo, Charge, Vorrat), **Eingabe** (Menge, Gebinde)
  und **Ziel** (Artikel, Kundenauftrag, Kunde). Darunter wird gebucht. Der Ziffernblock dockt
  rechts unten an.

Unter 1000 px (Handy) stehen die Spalten untereinander. Eine Lieferung ohne Kundenauftrag zeigt
weiter die einfache Ansicht.

### Wareneingang mit Scan

Zuerst das Etikett des Lieferanten scannen. **GS1-128** (oder GS1-DataMatrix/QR) mit (01) GTIN, (10) Charge,
(15)/(17) MHD und (310x) Gewicht füllt Artikel, Charge, MHD und Menge je Gebinde vor; eine **einfache EAN**
erkennt nur Artikel und Einheit. Die GTIN steht am Artikel unter **Barcodes** (ERPNext-Standard), mit Einheit
(z. B. Karton = 25 Stk) und Typ `EAN` (13 Stellen) bzw. `GTIN-14`. Unbekannte Codes: das Terminal sagt es, der
Artikel wird aus der Liste gewählt; eintragen im Büro. Alles Gelesene ist nur ein Vorschlag, gebucht wird erst
mit „Buchen“.

Trägt der Strichcode des Lieferanten die Charge, ist **kein eigenes Etikett** nötig: die Backstube scannt das
Lieferanten-Etikett und landet bei derselben Charge. Ohne Charge im Strichcode druckt das Terminal wie bisher
ein Etikett je Gebinde. Der Scanner muss das Trennzeichen FNC1 als ASCII 29 senden (Einstellung am Scanner),
sonst kann eine Charge mitten im Code die folgenden Felder verschlucken.

**Bestellung:** Gibt es offene Bestellungen (Einkauf) mit dem Artikel, steht unter dem Lieferanten eine Auswahl
mit offener Menge und Termin. Bei nur einer ist sie vorgewählt. Die Bestellung setzt den Lieferanten, ein
anderer Lieferant oder eine geschlossene Bestellung wird abgelehnt. Gespeichert wird sie an der Buchung
(`Bestellung (Einkauf)`), sie steht in der Akte und in der Belegliste des Netzbilds. Offen ist bestellt minus
Eingangsbelege minus Wareneingänge am Terminal zur Bestellung. Es bleibt ein Verweis: ERPNext zählt den
Eingang an der Bestellung nicht als geliefert. Ist alles da, die Bestellung im Büro schließen.

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
  wenn am Artikel ein Barcode (EAN) je Einheit hinterlegt ist. Auf dem Etikett und in (10) steht das
  **Los wie auf dem Karton** (z. B. `6447`), nicht der interne Chargenname.
- **Etikett aktuell halten:** Beim Druck merkt sich die Palette ihren Inhalt. Werden danach Kartons
  heruntergenommen (Lieferung, Umpacken, Umlagern, Verbrauch), meldet das Terminal „Etikett neu drucken“;
  die Palettenansicht zeigt es mit grünem Knopf. Kein Korrigieren von Hand mehr.

### Versandkarton mit eigener NVE

- **Versandkarton** ist eine dritte Art neben Lager- und Versandpalette (Paletten → „+ Neuer Versandkarton“). Er
  bekommt eine eigene NVE und dasselbe Etikett wie eine Palette (Layout nach der Rolle, A6). Alles, was für
  Paletten gilt, gilt für ihn: Inhalt je Los, Etikett mit Druckprotokoll, Akte, „Wo ist dieses Los?“,
  Rückverfolgung, Sperre. Nicht jeder Karton braucht eine NVE; lose Kartons werden weiter lose geliefert.
- **Auf eine Palette stellen** (eine Ebene): Versandkarton → „Auf eine Palette stellen“ oder an der Palette
  „+ Lose Kartons laden“ und die Karton-NVE scannen. Der Karton wird geschlossen, sein Inhalt bleibt seiner. Die
  Palette zeigt ihre Versandkartons, ihr Etikett zeigt alles zusammen. Ein Karton kommt nicht in einen anderen
  Karton. Jedes Auf- und Abnehmen steht im Protokoll **Versandkarton Zuordnung**.
- **Lieferung:** Ganze Palette = mit allen Versandkartons (gebucht wird je Karton, die Karton-NVE steht an der
  Position). Ein einzelner Versandkarton: seine NVE scannen; er wird von der Palette genommen, die Palette
  bleibt im Lager. Storno stellt alles wieder her, die Kartons stehen wieder auf der Palette.
- **DHL mit NVE:** Lieferung (DHL) → Auftrag → „Pakete als Versandkarton mit NVE“: je Paket Stück und Gewicht,
  „Paket packen“ (Versandkarton, älteste Lose zuerst, Etikett), danach ein Lieferschein für alle Pakete. Jede
  gescannte Sendungsnummer kommt an den nächsten Karton ohne Nummer.
- **NVE-Nummernkreis:** Liste mit dem Standard „Eigener“ (Basisnummer und Reserveziffer aus dem Kreis, leer =
  aus den Einstellungen; die Nummern laufen weiter). Die Arten „Bereich vom Kunden“ und „Etiketten vom Kunden“
  (Produktion für Dritte) sind angelegt, aber noch nicht freigeschaltet. Jede Palette merkt sich ihren Kreis.

## Etikettendrucker im Netz

Etiketten gehen direkt auf einen Drucker im Netz (ZPL über TCP, Port 9100), ohne Druckdialog.
Zebra-Drucker sprechen ZPL; Honeywell PM43 und PX6i über **ZSim** (Zebra-Emulation, eingebaut). Am
Drucker die Befehlssprache auf ZSim stellen, sonst druckt er den ZPL-Text als Klartext oder gar nicht.

1. **Etikettendrucker** anlegen: Name, Adresse (feste IP oder Rechnername), Port 9100, Auflösung und
   **Rollengröße** (ein Etikett, Breite x Höhe in mm). Die Layouts richten sich nach der Rolle: Kopf oben,
   Strichcodes unten am Rand, die Mitte wächst mit. Mindestens: Palette 100 x 120, Karton 90 x 50,
   Gebinde 95 x 60 mm; eine kleinere Rolle lässt sich dafür nicht zuordnen (auch nicht nachträglich).
   Knopf **Testdruck**: Rahmen 5 mm vom Rand nachmessen (Maß steht darauf; passt es nicht, stimmt die Auflösung nicht),
   **beide Strichcodes scannen**. Code 2 muss `(02)04032744000011(37)8(10)AB1234` ergeben; er wechselt
   die Code-128-Zeichensätze wie ein echtes Paletten-Etikett.
2. An der **Terminal Station**, Abschnitt „Etikettendrucker“, je Etikett einen Drucker eintragen:
   Palettenetikett (A6, 105 x 148 mm), Kartonlabel (100 x 60 mm), Gebinde-Etikett (100 x 70 mm).
   Die Druckermaske zeigt unter „Genutzt an“, welche Terminals ihn nutzen.
3. Leer gelassen oder Drucker nicht aktiv: das Terminal druckt wie bisher über den Browser.
   Antwortet der Drucker nicht, sagt das Terminal das und bietet „Im Browser drucken“ an.

**Logo:** in den Keks Trace Einstellungen „Logo für Etiketten“ hochladen; es steht auf Paletten- und
Kartonetikett (Drucker und Browser), nicht auf dem internen Gebinde-Etikett. Der Drucker kennt nur
Schwarz: Transparentes wird weiß, alles Dunkle und Farbige schwarz. Bei 10 mm Höhe und 203 dpi bleibt
das Wappen klar, feine Schrift im Logo („seit 1830“) ist nicht mehr lesbar.

**Interne Codes als Data Matrix:** Gebinde- und Behälter-Etikett tragen (wie die Kübel) einen Data Matrix
mit nur der Nummer; alles Weitere holt das System. Lesbar aus jedem Winkel, verträgt Schmutz, klein.
Braucht 2D-Scanner (Imager). Behälter-Codes deshalb nur aus Buchstaben, Ziffern und `- . /`.
Nach außen bleibt es linear: SSCC als GS1-128 auf der Palette, EAN auf dem Karton.

Inhalt wie die Browser-Etiketten (gleiche Datenquelle). Auf dem Paletten-Etikett steht der Inhalt
einer sortenreinen Palette in **zwei** GS1-128: (02)+(37) und (15)+(10). In einem Code wären die
Striche bei 203 dpi nur 0,25 mm breit, so sind es 0,5 mm. Ein Druck über die Anfrage-ID läuft
höchstens einmal, auch wenn nach Funkloch nochmal getippt wird. Kübel-Codes bleiben beim Laser.

Ausprobieren ohne Drucker: `bench execute keks_trace.etiketten.zpl_test --kwargs "{'drucker': {'name': 'X'}}"`
liefert das ZPL; ein Renderer wie Labelary zeigt es an. Achtung: der offline geprüfte Renderer
(zebrash) setzt den Wechsel nach Zeichensatz C (`>5`) falsch um; maßgeblich ist der Scan vom Drucker.

## Nachdruck, Akte und Audit-Ansicht

**Druckprotokoll.** Jeder Etikettendruck steht im Protokoll **Etikettendruck** (nicht änderbar, nicht löschbar):
Etikett, Grund, Drucker (oder „Browser“), Station, Person, bei Paletten der Inhalt zum Zeitpunkt des Drucks.
Den Grund bestimmt das System selbst, wo es ihn kennt: noch nie gedruckt = *Erstdruck*, Palette mit
geändertem Inhalt = *Inhalt geändert*, Druck als Teil einer Buchung = *Im Ablauf*. Ein Nachdruck per Knopf
ohne Anlass (gleicher Inhalt) fragt nach dem Grund: *Beschädigt / unleserlich* oder *Etikett fehlt*.
Kartonetiketten brauchen keinen Grund. Gebinde und Behälter, die vor dem Protokoll gedruckt wurden, gelten
beim nächsten Druck als Erstdruck.

**Etikett fehlt (Palette).** Info-Scan → Kartonetikett oder Los scannen → **Wo ist Los …?** zeigt alle
offenen Paletten, Behälter und lose Ware mit dem Los, je mit gepackt wann/wo/von wem, letzter Bewegung und
letztem Etikettendruck. Bei der gesuchten Palette **Etikett fehlt – nachdrucken**: Erst werden die anderen
Paletten mit dem Los gescannt (sie müssen ihr Etikett noch haben), sonst klebt eine NVE womöglich zweimal.
Wer sie nicht erreicht, druckt trotzdem; das Protokoll hält fest, welche gescannt wurden und welche nicht.
Das Los gilt je Tag und Artikel – mehrere Paletten mit demselben Los sind also der Normalfall.
NVE abtippen geht jetzt auch mit Leerzeichen und „(00)“.

**Akte.** Info-Scan einer Palette oder eines Behälters → **Akte**: Lebenslauf aus den vorhandenen Protokollen
(angelegt, gepackt, umgepackt, umgelagert, geliefert, Etiketten; beim Behälter: Befüllungen mit Charge,
geleert, gereinigt). Ein Los antippen → **Woraus besteht das?**: alle Rohstoffe und Packmittel mit Charge,
Wareneingang (Zeit, Station oder Eingangsbeleg, Lieferant, Lieferschein, direkt ins Silo), MHD und
QS-Freigabe; darunter der Herstellungsweg Stufe für Stufe mit Buchung, Station, Person und Prüfungen.
„Möglicherweise enthalten“ = nur über die Silo-Vermischung. Sehr lange Ketten (viel Rework) werden gekürzt,
vollständig bleibt die Rückverfolgung in ERPNext.

**Audit-Ansicht `/akte`** (Handy, Tablet, Surface): nur lesen, keine Station nötig, Anmeldung mit Leserecht
auf Chargen. Palette, Los oder Behälter scannen oder eintippen. Kamera-Scan über die im Browser eingebaute
Barcode-Erkennung: Chrome auf Android ja, Windows (Surface) nein – dort Handscanner (USB/Bluetooth) oder
Eintippen. Die Kamera braucht **HTTPS**; auf dem Testserver mit `http://` erscheint der Kamera-Knopf deshalb
nicht. Direktaufruf mit Code: `/akte?code=<NVE oder Los>`.

### Netzbild der Rückverfolgung (`/netz`)

Für Büro, QS und Audit am großen Bildschirm oder am Surface. Aufruf `/netz?code=<Los, Charge oder Palette>`
oder aus der Akte über „Netzbild: woher und wohin“. Nur lesen, Leserecht auf Chargen.

- Das gewählte Los steht in der Mitte. **Links** steht, woraus es besteht (bis zum Wareneingang), **rechts**,
  wohin es ging (bis zum Lieferschein beim Kunden). Die Spalten folgen der Stufe: Rohstoff, Zwischenstufe,
  Backware, Fertigware, Kunde.
- **Farbe hat Bedeutung:** Der Streifen links zeigt die Stufe. Rote Marke heißt gesperrt, orange heißt
  Prüfung mit Abweichung. Gestrichelt heißt „möglicherweise enthalten“ (Silo-Vermischung).
- **Anklicken** hebt den ganzen Weg hervor (woher und wohin), der Rest wird blass. An den Linien steht die
  Menge. Rechts stehen die Details: Wareneingang, Freigabe, Herstellung, Prüfungen und wo das Los jetzt liegt.
  „Von hier aus zeichnen“ macht den Knoten zur neuen Mitte.
- **Packmittel**, die nur in einen Schritt gehen, sind ab drei Stück zu einem Kasten gebündelt. Anklicken
  klappt ihn auf.
- **Belege in der Kette:** Einkauf (Wareneingang je Rohstoff und Packmittel) und Verkauf (Lieferschein mit
  Bestellnummer des Kunden). Ein Klick auf eine Zeile zeigt das Los im Bild. Ausgabe als CSV (Excel) oder Druck.
- Verschieben mit Maus oder Finger, Zoom mit −/+ oder Strg + Mausrad. Höchstens 300 Knoten; mehr steht
  gekürzt da, vollständig im Bericht „Rückverfolgung“.
- Eine Palette mit mehreren Losen fragt zuerst, welches Los gezeichnet wird. Bei einer schon versendeten
  Palette zählt, was je auf ihr stand.

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

## Produktionsplanung und Backstraße

Konzept für die QS: Dokument „Keks Trace – Produktionsplanung und Datenmodell“.

**Leistung hängt am Produkt.** Die Backstraße hat Abschnitte (**Linienabschnitt**): Formen, Backen,
Spicken, Hacken, Streichen, Füllen, Sprühen, Glasieren, Trocknen, Schoko 1, Kühlen 1, Streuseln,
Schoko 2, Kühlen 2 und die Verpackungsanlagen Manuelles Band, InoTec, Thürlings, Carina. Am Artikel
steht je Abschnitt die Geschwindigkeit (kg/h, Beutel/min oder Karton/h). Der langsamste Abschnitt
ist der Engpass; von den Verpackungsanlagen zählt die, die der Auftrag nutzt.

**Planung (Bericht „Produktionsplan“):**
- „Planung vorschlagen“ verteilt offene Kundenaufträge (Fertigware) nach Liefertermin in Stunden
  auf die Arbeitstage der **Linie** (Laufzeit pro Tag, Umrüstzeit bei Produktwechsel). Es entstehen
  **Produktionsaufträge** „Geplant“, in ganzen Kartons; kein Rest-Schnipsel unter 30 Minuten am Tagesende.
- „Tag freigeben“: erst freigegebene Aufträge erscheinen an den Terminals.
- Bericht „Teigbedarf“: veredelter Teig und Grundteig für die nächsten Tage gegen den Bestand;
  Grundteig nur für den veredelten Teig, der fehlt.

**An der Linie (Terminals mit Linie):**
- **Former / Nachfüllen** („An die Linie“): Auftrag wählen, Kübel, Gebinde oder Tank scannen. Das ist
  eine Umlagerung in den Lagerort der Linie mit dem Auftrag als Vermerk; der Kübel wird frei. Das
  Terminal schlägt die ältesten passenden Kübel vor; ein jüngerer gibt nur einen Hinweis.
- **Packstation** (nur Bildschirm): Artikel, Verpackungsanlage, Beutel je Karton, Los, MHD;
  Kartonlabel drucken (`/karton_etikett`).
- **Paletten-Terminal** („Palette fertig“): Anzahl Kartons → Fertigung. Verbraucht wird laut
  Linienrezept (Stückliste durch Backware und lose Ware aufgelöst) nur Ware dieses Auftrags, älteste
  zuerst; Ergebnis ist das Tages-Los auf der Palette, Backtag = heute. „Auftrag beenden“ bucht den
  Rest auf der Linie als „Linienrest“ aus.
- Lange Listen am Terminal haben ab 8 Einträgen ein Suchfeld.

**Metallcheck je Verpackungsanlage:** Jede Anlage (InoTec, Thürlings, Carina, Manuelles Band) hat
einen eigenen stündlichen CCP-Prüfplan („Prüfplan → Verpackungsanlage“). Er ist an Packstation und
Paletten-Terminal fällig, solange dort ein Auftrag auf dieser Anlage läuft; überfällig = keine
Palette. Abweichung sperrt die Lose, die seit dem letzten OK auf dieser Anlage verpackt wurden.

**Linien trennen:** Am Artikel steht, auf welcher Linie er hergestellt wird (Feld „Linie“). Stationen
einer Linie zeigen nur Artikel und Aufträge dieser Linie, Stationen ohne Linie nur Artikel ohne Linie;
der Versand sieht alle Aufträge. Die Planung plant je Linie nur ihre Artikel und meldet Artikel ohne Linie.

**Herzenboden** (`keks_trace.demo_herzen.anlegen`): Eigene Linie „Herzenboden“ mit den Stationen Herzen Garnieren und
Herzen Verpackung. Herzen in Stück, je Größe ein Artikel
(Platzhalter 12, 18, 25 cm). Rohling backen (Backstube, aus Grundteig) → Zuckerglasur nach eigener
Rezeptur (Halbfabrikat, max. 2 Tage; Haken „begrenzt das MHD des Endprodukts nicht“) → Garnieren
(Rohling + Glasur) → Verpacken auf der Kalfass (Herz + Folie + Etikett + Schleife, Metallcheck Fe 2,8 mm).

**Kübel:** Produktträger „Teigbehälter“ mit Nummer K-001 …; `/kuebel_code` erzeugt je Kübel
Data Matrix + Nummer als SVG zum Einlasern.

Demo: `bench --site keks.localhost execute keks_trace.demo_linie.anlegen` (Linie „Backstraße“,
Abschnitte mit Demo-Leistungen, Stationen Former, Nachfüllen …, Packstation, Paletten-Terminal,
40 Kübel, Großkunden A/B/C mit 120.000 / 80.000 / 50.000 Beuteln, Planung, erster Tag freigegeben).

## Bio und V-Label

Am Artikel gibt es die Haken **Bio (EU-Öko)**, **In Bio-Produkten erlaubt** (Salz, Wasser,
Backtriebmittel …), **Vegan** und **Vegetarisch**. Jede Charge trägt ein **Kennzeichen**
(z. B. „Bio, Vegan, Vegetarisch“ oder „keine“):

- **Wareneingang:** Bio-Ware nur von einem Lieferanten mit gültigem Öko-Zertifikat (am Lieferanten:
  Öko-Kontrollstelle, gültig bis, Datei). Das Terminal bietet bei Bio-Artikeln nur zertifizierte
  Lieferanten an; abgelaufene Zertifikate werden abgewiesen. Gleiches gilt für Eingangsrechnungen /
  Wareneingänge im Büro.
- **Herstellen:** Ist der Zielartikel Bio / vegan / vegetarisch, wird jede Zutat ohne dieses
  Kennzeichen schon beim Scannen rot abgewiesen (auch Silo-Chargen und Rework). Die neue Charge
  bekommt ein Kennzeichen nur, wenn alle Zutaten es tragen (Packmittel zählen nicht; für Bio muss
  mindestens eine echte Bio-Zutat dabei sein).
- **Umstellung:** Wurde an der Station zuletzt konventionell produziert, fragt das Terminal vor
  der ersten Bio-Charge die Prüfpläne „Bei Umstellung auf Bio“ ab (Demo: „Reinigung vor Bio“).
  Nicht in Ordnung → nicht gebucht, aber protokolliert.
- **Etikett:** Paletten, auf denen nur Bio-Ware steht, tragen „BIO“ und die eigene
  Öko-Kontrollnummer (Keks Trace Einstellungen). Die Vorschau am Packplatz zeigt sie mit Los und MHD.
- **Bericht „Bio Mengenabgleich“:** je Bio-Artikel und Zeitraum Anfang, Eingang, hergestellt,
  verbraucht, ausgeliefert, Lagerverkauf, entsorgt, Ende. Für die jährliche Öko-Kontrolle.

Demo: `KT Bio Mühle` (DE-ÖKO-006), Bio-Dinkelmehl, Bio-Rohrzucker, Speisesalz und
„Bio-Grundteig Dinkel (vegan)“.

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

### Demo-Tag und Drehbuch (`/demo`)

```bash
bench --site <site> execute keks_trace.demo_tag.vorbereiten   # oder auf /demo: „Für heute vorbereiten“
```

Legt jeden Morgen einen sauberen Demostand an, alle Daten relativ zu heute:

1. Zuckerguss-Tank leer melden und frisch anmischen (Haltbarkeit 2 Tage; alter Guss würde das Garnieren
   blockieren).
2. Herzen-Stammdaten, Kundenaufträge (mit Hinweis an die Produktion) und Vorrat auffüllen.
3. Eine offene Bestellung Puderzucker für heute: In der Demo wird der Wareneingang dazu live gebucht.
4. Ein Herz komplett bis zum Kunden. Daran zeigt die QS den Rückruf im Netzbild. Am selben Tag wird es
   nicht noch einmal angelegt („Neues Herz bis zum Kunden“ erzwingt es).

Die Seite **`/demo`** zeigt den Stand von heute und das **Drehbuch** für GL und QS (etwa 15 Minuten, sieben
Schritte mit Klicks, „Sagen:“-Sätzen und Direktlinks). Vorbereiten dürfen nur System Manager und nur auf
einem Demosystem: Marke der Testserver-Einrichtung (`private/.kt_demo_fertig`) oder `developer_mode`. Auf
dem Testserver läuft es zusätzlich jeden Morgen um 4:30 Uhr von selbst (Scheduler); auf anderen Systemen tut
der Job nichts.

Terminal-Direktlink: `/terminal?station=Lager` setzt die Station und öffnet sie.

### Herzen-Demo ohne viel Klicken

```bash
# Linie, Artikel, Behälter, drei Kundenaufträge in Stück (einer mit MHD höchstens 6 Monate)
# und Vorrat: Puderzucker, Eiweiß, Packmittel (je ein Karton angebrochen), Zuckerguss im Behälter,
# 200 Rohlinge und 200 garnierte Herzen je Größe. Füllt bei jedem Lauf nur auf, was fehlt.
bench --site keks.localhost execute keks_trace.demo_herzen.anlegen
# Ein Herz durch alle Abteilungen bis zum Lieferschein, mit Protokoll und Rückverfolgung
bench --site keks.localhost execute keks_trace.demo_herzen.durchlauf --kwargs "{'groesse': '9', 'stueck': 100}"
```

## Einkauf: Kontrakte und Reichweite

Eingekauft wird nach Auftragslage und Börse, nicht nach Bestellvorschlag. ERPNext-Standard deckt das ab:

- **Rahmenauftrag (Blanket Order, Typ Einkauf)** für Kontrakte: Menge und Preis fest, jede Bestellung
  zeigt auf den Rahmenauftrag (Häkchen „Gegen Rahmenauftrag“), ERPNext zählt den Abruf mit.
- **Mindestbestand** (Artikel → Nachbestellung) nur für Kleinkram wie Folie, Etiketten, Schleifen.
- Bericht **Reichweite Rohstoffe** (Workspace Keks Trace → Einkauf): Bestand, bestellt, Kontrakt offen,
  Verbrauch je Tag, reicht bis, Bedarf aus offenen Kundenaufträgen (über die Rezepte bis zum Rohstoff).

Demo: `bench --site keks.localhost execute keks_trace.demo_einkauf.anlegen` (50 t Zucker-Kontrakt, zwei Abrufe).

## E-Rechnung und DATEV

Mit den Apps `eu_einvoice` und `erpnext_datev` (ALYF, GPLv3): XRechnung und ZUGFeRD aus der Rechnung, Prüfung nach
EN 16931, Eingangsrechnungen einlesen, DATEV-Export. Testlauf, Pflichtfelder und Stolpersteine:
[docs/E-RECHNUNG.md](docs/E-RECHNUNG.md), Demo `keks_trace/demo_erechnung.py`.

## Lasttest (Datenflut)

Wie schnell bleibt das System, wenn Jahre an Daten drin sind? Auf dem Demo-Server:

```bash
# 2 Jahre Produktion als Chargen und Genealogie (Sekunden; faktor=3 = dreifache Tagesmenge)
bench --site keks.localhost execute keks_trace.lasttest.flut --kwargs "{'tage': 730}"
# echte Terminal-Buchungen (Wareneingang + Herstellen) ins Lagerbuch, misst die Buchungszeit
bench --site keks.localhost execute keks_trace.lasttest.buchungen --kwargs "{'anzahl': 300}"
# Antwortzeiten messen: Rückruf vorwärts, Reklamation rückwärts, Scan, Listen, Mengenbilanz
bench --site keks.localhost execute keks_trace.lasttest.messen
# Lasttest-Chargen wieder entfernen (Präfix LT-)
bench --site keks.localhost execute keks_trace.lasttest.aufraeumen
```

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
| `test_wareneingang_gs1` | GS1-128/EAN lesen (echte Etiketten, Prüfziffer, Datum mit Tag 00, Jahrhundert); Wareneingang per Scan ohne eigenes Etikett, Backstube findet die Charge über das Lieferanten-Etikett; „Präsentkarton“ als Charge abgewiesen; eigenes Karton-Etikett findet das Los |
| `test_fefo` | Ältere Charge im Lager (ohne gesperrte/abgelaufene); Grund Pflicht/Hinweis/Aus; Grund an der Buchung; Bericht MHD Rohstoffe |
| `test_rezepttreue` | Halbe Masse in Toleranz; Überdosis und fehlende Zutat brauchen Grund; Toleranz je Rezeptzeile und Mindesttoleranz; Grund an der Buchung |
| `test_fluesse` (Ergänzung) | FEFO auch beim Zuführen an der Linie; Paletten-Etikett: Los wie Karton, „neu drucken“ nach Entnahme |
| `test_qs_tagesliste` | Alle vier Arten eines Tages; Routinesperre „Freigabe vor Verwendung“ ist keine Abweichung; Durchsicht nur QS, je Tag einmal, nicht in der Zukunft, danach unveränderbar |
| `test_behaelter` | Behälter nach dem Leeren frei bzw. zur Reinigung (Einstellung); Meldung „gereinigt“ mit Zeit und Station; Anfrage-ID nur für geschützte Buchungen |
| `test_etiketten` | GS1-128 in ZPL (Zeichensätze, FNC1, zurückgelesen); Data Matrix (Größe, Zeichen, Behälter-Code); Layouts je Rollengröße, Mindestmaß beim Zuordnen und Ändern; Logo (transparent wird weiß, fehlt es: ohne Logo drucken); Drucker an der Station oder Browserdruck; inaktiv; nicht erreichbar mit klarer Meldung; Testdruck; Adresse geprüft; „Genutzt an“ |
| `test_akte` | Druckprotokoll: Erstdruck, Nachdruck nur mit Grund, Inhalt geändert, im Ablauf, Gebinde, Browserdruck, Testdruck, nicht änderbar; NVE mit Leerzeichen; Akte Palette und Behälter; Wo ist das Los; Etikett fehlt mit geprüften und nicht geprüften Paletten; Woraus besteht das bis zur Silo-Charge mit Wareneingang und QS-Freigabe |
| `test_einwaage` | Lagerort je Zutat (Quelllager der Stückliste vor Standardlager), Gebinde aus der Maßeinheit-Umrechnung |
| `test_retour_hinweis` | Retour von der Linie ins Herkunftslager (Menge geprüft, Rest beim Auftragsende als Linienrest); Hinweise von Produktions- und Kundenauftrag; Tagesübersicht mit Aufträgen vom Vortag |
| `test_versandkarton` | NVE aus dem Nummernkreis (fremde Kreise noch gesperrt); Versandkarton auf Palette mit Regeln und Protokoll, Etikett der Palette mit allem zusammen; ganze Palette liefern und Storno; einzelnen Karton von der Palette liefern; DHL-Pakete als Versandkartons mit Sendungsnummer je Karton |
| `test_netz` | Netzbild: rückwärts bis zum Wareneingang, vorwärts bis zum Lieferschein, Kanten mit Menge; Belegliste Einkauf/Verkauf; Palette als Einstieg (auch versendet); gesperrt sichtbar |
| `test_wareneingang_bestellung` | Wareneingang zu einer offenen Bestellung: Auswahl, offene Menge sinkt, Lieferant aus der Bestellung; falscher Lieferant, Artikel nicht bestellt, Bestellung geschlossen abgelehnt; Verweis in Akte und Belegliste |
| `test_demo_tag` | Demo-Tag: offene Bestellung, ein Herz bis zum Kunden, frischer Guss im Tank, Hinweis am Auftrag; zweiter Lauf am selben Tag nimmt den vorhandenen; ohne Marke tut der Morgenjob nichts |

Die Tests rollen ihre Daten am Ende zurück. Demo-Funktionen committen nur außerhalb von Tests
(`utils.demo_commit`); vorher schrieb ein Demo-Aufruf mitten in einem Test dessen Daten fest.

## Bewusst noch nicht enthalten

Waagenanbindung, Druckerstatus (Papier leer), Wareneingang als Eingangsbeleg zur Bestellung (am Terminal nur Verweis), eigene Kasse mit TSE und Kundendisplay,
Abweichungsmanagement/CAPA, SOPs und Schulungsnachweise.

## Offene fachliche Annahmen (von der QS zu bestätigen)

- Rework-Höchstalter in der Demo: 7 Tage, gezählt ab dem ältesten Tag der Kette.
- Höchstanteil in der Demo: 10 % der Einwaage.
- Nachlaufmenge Mehlsilos 100 kg, Zuckersilo 50 kg, Sirup-Tank 20 kg (abhängig von Silogeometrie, mit der Technik festlegen).
- Standzeit Grundteig 3 Tage, veredelter Teig 2 Tage, lose Ware 180 Tage ab Backtag.
- Schokolierter oder gefüllter Bruch hat keine Rework-Regel (geht nicht zurück in Teig).
- MHD Fertigware = früheres von Backtag + Haltbarkeit und kürzestem MHD der nach dem Backen
  aufgebrachten Füllungen, Glasuren und Schokolade.
- Lieferanten-Charge enthält mindestens eine Ziffer (2 bis 60 Zeichen). TODO(fachlich): gibt es Lieferanten
  mit rein alphabetischer Charge?
- FEFO bei Rohstoffen und Packmitteln: Standard „Grund Pflicht“.
- Einwaage: Standardtoleranz 5 % je Zutat, mindestens 0,01 kg. TODO(fachlich): Werte je Rezeptzeile mit der
  QS festlegen (Gewürze, Triebmittel enger).
- Einstellungen werden in Demos und Tests nur im Speicher überschrieben (`utils.einstellungen`), nie in der
  Datenbank. Nach `bench migrate` den Webserver neu starten bzw. `bench clear-cache`, sonst kennt er neue Felder nicht.
- Behälter nach dem Leeren zur Reinigung: Standard aus (wie bisher). TODO(fachlich): für welche Behälterarten
  einschalten (Teigkübel, Rework-Behälter, Kisten)?

## Lizenz

Interne Software der Heinrich Schulze Ladencafe GmbH. Alle Rechte vorbehalten.
