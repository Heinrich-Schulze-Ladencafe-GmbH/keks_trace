# Keks Trace

Chargenrückverfolgung mit Rework und Behältern für die Keksproduktion, als App für ERPNext 16.

Dieser Stand ist der **Prototyp für das Go/No-Go** aus Phase 0 des Konzepts. Er bildet den
echten Ablauf ab und zeigt, dass Rework über mehrere Tage in ERPNext sauber gebucht,
geprüft und rückverfolgt werden kann.

## Abgebildeter Ablauf

```
Grundteig        Silo + Säcke (+ Rework)                      → Charge, Teigbehälter
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
- **Storno:** stornierte Buchungen bleiben sichtbar, fließen aber nicht mehr in die
  Rückverfolgung ein; Behälterinhalt wird zurückgesetzt.

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
| `keks_trace/api.py` | `rueckverfolgung` und `traeger_info` für Scanner und Terminals |
| DocType `Allergengruppe` | Allergene je Teig, Füllung, Rework |
| DocType `Rework Regel` | Rework-Matrix |
| DocType `Produkttraeger` | Behälter, Kiste oder Palette mit Code (QR) |
| DocType `Traeger Belegung` | Historie: welche Charge wann in welchem Behälter lag |
| DocType `Chargen Genealogie` | Kanten der Rückverfolgung (wird nur automatisch geschrieben) |
| Bericht `Rueckverfolgung` | Rückverfolgung in der Oberfläche |
| `keks_trace/demo.py` | Demo-Stammdaten und drei Produktionstage |
| `keks_trace/tests/` | Abnahmetests |

**Zusatzfelder:**
- am Artikel: **Chargenstufe** (Rohstoff, Packmittel, Halbfabrikat, Grundteig, Teig veredelt,
  Rework, Backware, Ware lose, Fertigware) und **Allergengruppe**;
- an der Charge: **Chargenstufe**, **Ursprungsdatum**, **Backtag**, **Kürzestes Komponenten-MHD**;
- am Buchungsposten: **Behälter / Träger**.

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

## Demo: drei Produktionstage

```bash
bench --site keks.localhost execute keks_trace.demo.run
```

Legt Demo-Artikel (Präfix `KT-`), Allergengruppen, Rework-Regeln, Behälter, einen Demo-Lieferanten
und -Kunden an und bucht:

1. **Tag 1:** Wareneingang; Grundteig GT1 in Behälter TB1; Nougatfüllung selbst hergestellt;
   halber GT1 wird zu Nussteig V1; Backen; Schokoboden mit gekaufter Kuvertüre → lose Ware in
   Kiste KL1; Bruch → Rework R1 in Rework-Behälter RB1.
2. **Tag 2:** zweite Hälfte von GT1 + Rework R1 → Nussteig V2 (TB1 und RB1 werden frei); Backen,
   Schokolieren → KL2. Grundteig GT2 → Kakaoteig V3, Teigrest → Rework R2; Backen; Füllen mit
   Nougat → lose Ware in Kiste KL3.
3. **Tag 3:** Grundteig GT3 mit 5 % Rework R2; Verpacken aus KL1 (Rest bleibt in der Kiste) und
   KL3; Lieferung beider Lose an den Demo-Kunden.

Danach gibt sie Rückverfolgungen und den Behälterstand aus. Das Kakao-Nougat-Los zeigt die
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

Die Tests rollen ihre Daten am Ende zurück.

## Bewusst noch nicht enthalten

Silo-Zeitfenster (Mehl ist im Prototyp eine normale Charge), Scanner-Oberflächen für Terminals
und Handscanner, Etikettendruck (QR), Waagenanbindung, Freigabe vor dem Verpacken,
Paletten mit SSCC, Wareneingang über Bestellungen. Das folgt nach dem Go/No-Go.

## Offene fachliche Annahmen (von der QS zu bestätigen)

- Rework-Höchstalter in der Demo: 7 Tage, gezählt ab dem ältesten Tag der Kette.
- Höchstanteil in der Demo: 10 % der Einwaage.
- Standzeit Grundteig 3 Tage, veredelter Teig 2 Tage, lose Ware 180 Tage ab Backtag.
- Schokolierter oder gefüllter Bruch hat keine Rework-Regel (geht nicht zurück in Teig).
- MHD Fertigware = früheres von Backtag + Haltbarkeit und kürzestem MHD der nach dem Backen
  aufgebrachten Füllungen, Glasuren und Schokolade.

## Lizenz

Interne Software der Heinrich Schulze Ladencafe GmbH. Alle Rechte vorbehalten.
