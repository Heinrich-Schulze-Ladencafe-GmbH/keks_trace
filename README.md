# Keks Trace

Chargenrückverfolgung mit Rework für die Keksproduktion, als App für ERPNext 16.

Dieser Stand ist der **Rework-Prototyp** (Go/No-Go aus Phase 0 des Konzepts). Er zeigt,
dass Rework über mehrere Tage in ERPNext sauber gebucht, geprüft und rückverfolgt werden kann.

## Was die App kann

- **Rework-Regeln (Rework-Matrix):** Welches Rework in welchen Teig, mit welchem Höchstanteil.
  Ohne Regel wird die Buchung abgelehnt.
- **Allergenprüfung:** Rework darf keine Allergene in einen Teig bringen, die dieser nicht hat,
  auch wenn versehentlich eine Regel existiert.
- **Rework-Alter:** Das Alter zählt ab dem ältesten Backtag der ganzen Kette. Abgelaufenes Rework
  wird gesperrt. Damit sind Rework-Ketten automatisch auf das Höchstalter begrenzt.
- **FIFO-Hinweis:** Warnung, wenn ein älterer Rework-Behälter übersprungen wird (blockiert nicht).
- **MHD ab Backtag:** Wird lose Ware später verpackt, rechnet das MHD vom Backtag, nicht vom Verpackungstag.
- **Genealogie:** Jede Fertigungs- und Umpackbuchung schreibt Kanten Input-Charge → Output-Charge mit Menge und Anteil.
- **Rückverfolgung** vorwärts (bis zum Kunden mit Lieferschein) und rückwärts (bis zur Lieferantencharge),
  über beliebig viele Rework-Generationen, mit Anteil je Charge. Als Bericht „Rueckverfolgung“ und per API.
- **Storno:** Stornierte Buchungen bleiben sichtbar, fließen aber nicht mehr in die Rückverfolgung ein.

Gebucht wird ausschließlich mit ERPNext-Standardbelegen (Stock Entry „Manufacture“ und „Repack“,
Lieferschein). Der ERPNext-Kern wird nicht verändert.

## Aufbau

| Datei / Objekt | Zweck |
| --- | --- |
| `keks_trace/hooks.py` | Hängt die Prüfungen und die Genealogie an Lagerbuchungen |
| `keks_trace/install.py` | Zusatzfelder an Artikel und Charge, Chargenverwaltung aktivieren |
| `keks_trace/rework.py` | Rework-Prüfungen vor dem Buchen |
| `keks_trace/genealogie.py` | Genealogie-Kanten, Ursprungs- und Verfallsdaten nach dem Buchen |
| `keks_trace/trace.py` | Rekursive Rückverfolgung vorwärts/rückwärts, Kunden |
| `keks_trace/api.py` | `keks_trace.api.rueckverfolgung` für Scanner-Seiten und Terminals |
| DocType `Allergengruppe` | Allergengruppen der Teige und des Reworks |
| DocType `Rework Regel` | Rework-Matrix |
| DocType `Chargen Genealogie` | Kanten der Rückverfolgung (wird nur automatisch geschrieben) |
| Bericht `Rueckverfolgung` | Rückverfolgung in der Oberfläche |
| `keks_trace/demo.py` | Demo-Stammdaten und Drei-Tage-Kette |
| `keks_trace/tests/` | Abnahmetests |

Zusatzfelder: am Artikel **Chargenstufe** (Rohstoff, Packmittel, Teig, Rework, Backware lose,
Fertigware) und **Allergengruppe**; an der Charge **Chargenstufe** und **Ursprungsdatum**.
Haltbarkeit (Rework-Höchstalter, MHD) nutzt die ERPNext-Standardfelder „Has Expiry Date“ und „Shelf Life In Days“ am Artikel.

## Installation auf dem Testserver

Voraussetzung: ERPNext 16 läuft (siehe Anleitung im Chat bzw. im Konzept) und der
Einrichtungsassistent ist abgeschlossen (Firma angelegt).

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

## Demo: drei Produktionstage mit Rework

```bash
bench --site keks.localhost execute keks_trace.demo.run
```

Legt Demo-Artikel (Präfix `KT-`), Allergengruppen, Rework-Regeln, einen Demo-Lieferanten und
-Kunden an und bucht:

1. **Tag 1:** Wareneingang → Teig T1 → Backen B1 → Bruch wird Rework R1
2. **Tag 2:** Teig T2 mit 5 % Rework R1 → B2 → Rework R2
3. **Tag 3:** Teig T3 mit 5 % Rework R2 → B3; Backware B1 wird verpackt (Los L1) und an den Demo-Kunden geliefert

Danach gibt sie drei Rückverfolgungen aus: Rückruf der Mehlcharge (vorwärts bis zum Kunden),
Reklamation von Los L1 (rückwärts) und Teig T3 rückwärts über zwei Rework-Generationen.
Jeder Lauf erzeugt neue Chargen; die Rückverfolgung lässt sich danach auch im Bericht
**Rueckverfolgung** ansehen.

> Nur auf einem Testsystem ausführen. Die Demo bucht echte Lagerbewegungen.

## Tests

```bash
bench --site keks.localhost set-config allow_tests true
bench --site keks.localhost run-tests --module keks_trace.tests.test_rework_kette
```

| Test | Szenario aus dem Konzept |
| --- | --- |
| `test_t06_*` | Nuss-Rework in Butterteig blockiert; Allergenkonflikt trotz falscher Regel; Butter-Rework in Nussteig erlaubt |
| `test_t07_*` | Rework-Anteil über Maximum blockiert, mit zulässiger Restmenge |
| `test_t08_*` | Abgelaufenes Rework blockiert |
| `test_t09_*` | FIFO-Hinweis bei jüngerem Rework, Buchung läuft trotzdem |
| `test_t10_*` | MHD ab Backtag, nicht ab Verpackungstag |
| `test_rework_alter_*` | Rework-Alter zählt ab ältestem Backtag der Kette |
| `test_t13_*` | Rückruf Mehl vorwärts bis Kunde, inkl. Anteil über Rework |
| `test_t14_*` | Rückwärts über zwei Rework-Generationen, inkl. Packmittel |
| `test_t15_*` | Storno entfernt Kanten aus der Rückverfolgung, Historie bleibt |

Die Tests rollen ihre Daten am Ende zurück.

## Bewusst noch nicht enthalten

Silo-Zeitfenster, Produktträger und Trägerbelegung, Scanner-Oberflächen für Terminals und
Handscanner, Etikettendruck (QR), Waagenanbindung, Freigabe vor dem Verpacken,
Wareneingang über Bestellungen. Das folgt nach dem Go/No-Go.

## Offene fachliche Annahmen (von der QS zu bestätigen)

- Rework-Höchstalter in der Demo: 7 Tage, gezählt ab dem ältesten Backtag der Kette.
- Höchstanteil in der Demo: 10 % der Einwaage.
- Rework kommt zur Einwaage hinzu; die Demo reduziert dafür die Rohstoffe anteilig.
- Fertigware-MHD = ältester Backtag der eingesetzten losen Ware + Haltbarkeit des Fertigartikels.

## Lizenz

Interne Software der Heinrich Schulze Ladencafe GmbH. Alle Rechte vorbehalten.
