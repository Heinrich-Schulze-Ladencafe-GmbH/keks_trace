# Schnittstelle Messgeräte → keks_trace (Version 1)

Für Brücken (z. B. ESP32), die Messwerte von Waagen und Feuchtebestimmern per WLAN an ERPNext/keks_trace
schicken. Dieses Dokument ist der Vertrag: die Server-Seite wird genau so gebaut. Änderungen nur mit neuer
Version (`"schnittstelle": 2`); Version 1 bleibt dann gültig.

Erste Geräte: Feuchtebestimmer **PCE-MA 110TS-ICA** (RS-232) und eine Kranwaage (RS-232 oder Funk).

## Grundsätze

1. **Die Brücke meldet nur, was das Gerät sagt.** Sie weiß nicht, zu welcher Charge oder welchem Auftrag
   eine Messung gehört, und rät es nicht. Die Zuordnung macht der Mitarbeiter am Terminal.
2. **Nichts geht verloren, nichts wird doppelt gespeichert.** Jede Messung hat eine eindeutige
   `messung_id`. Kommt keine Bestätigung, sendet die Brücke dieselbe Messung später nochmal; der Server
   speichert sie nur einmal.
3. **Die Originalausgabe des Geräts geht immer mit** (`roh`). Was die Brücke daraus liest (`wert`), ist eine
   Hilfe; maßgeblich ist der Rohtext. Kann die Brücke ihn nicht lesen, schickt sie nur `roh`.

## Zwei Arten von Meldungen

| | Messung (`erfassen`) | Live-Wert (`live`) |
|---|---|---|
| Wofür | abgeschlossene Feuchtemessung, stabiles Gewicht zum Übernehmen | Gewichtsanzeige am Terminal, während gewogen wird |
| Gespeichert | ja, dauerhaft (Nachweis) | nein, nur ca. 10 s im Speicher |
| Wann senden | einmal, wenn das Gerät ein Ergebnis ausgibt bzw. die Waage stabil ist | höchstens 2-mal je Sekunde und nur, wenn sich der Wert ändert; sonst alle 5 s |
| Puffern ohne WLAN | ja | nein (veraltete Live-Werte verwerfen) |

## Verbindung und Anmeldung

- `POST`, Inhalt JSON (UTF-8), höchstens 16 KB je Anfrage.
- Basis-URL einstellbar, z. B. `http://192.168.1.50` (Testserver) oder `https://erp.example.de`.
  HTTPS muss gehen, mit einstellbarem CA-Zertifikat (PEM) für ein eigenes Zertifikat im Haus.
- Anmeldung mit API-Schlüssel eines **eigenen Benutzers je Gerät** (nur Recht „Messgerät“):

```
Authorization: token <api_key>:<api_secret>
Content-Type: application/json
Accept: application/json
```

- Zeitlimit je Anfrage: 10 s.

## 1. Messung erfassen

`POST {basis}/api/method/keks_trace.messung.erfassen`

```json
{
  "schnittstelle": 1,
  "geraet": "FEUCHTE-1",
  "messung_id": "FEUCHTE-1-0007-000123",
  "zeitpunkt": "2026-11-01T17:05:12+01:00",
  "art": "feuchte",
  "wert": 4.83,
  "einheit": "%",
  "stabil": true,
  "roh": "MC   4.83 %\r\n",
  "extra": {
    "programm": "Kekse 105",
    "temperatur_c": 105,
    "dauer_s": 420,
    "anfang_g": 5.012,
    "ende_g": 4.770
  },
  "firmware": "1.0.3",
  "verworfen": 0
}
```

| Feld | Pflicht | Typ | Bedeutung |
|---|---|---|---|
| `schnittstelle` | ja | Zahl | immer `1` |
| `geraet` | ja | Text, 1–40 Zeichen, `A-Z 0-9 -` | Gerätename, wie in ERPNext unter „Messgerät“ angelegt |
| `messung_id` | ja | Text, 1–64 Zeichen, `A-Z a-z 0-9 - _` | eindeutig je Gerät, **auch über Neustarts**. Vorschlag: `<geraet>-<Startzähler 4-stellig>-<laufende Nr. 6-stellig>`, Startzähler im NVS hochzählen |
| `zeitpunkt` | ja | ISO 8601 mit Zeitzone, oder `null` | Zeit der Messung laut Brücke (NTP). Ohne gültige Zeit `null`: dann zählt die Empfangszeit des Servers. Nie eine geratene Zeit |
| `art` | ja | `"feuchte"`, `"gewicht"`, `"temperatur"` | Messgröße |
| `wert` | nein | Zahl mit Punkt, oder `null` | gelesener Wert; `null`, wenn die Brücke `roh` nicht sicher lesen kann. **Nie 0 als Ersatz** |
| `einheit` | wenn `wert` | `"%"`, `"g"`, `"kg"`, `"°C"` | Einheit von `wert` |
| `stabil` | ja | true/false | Waage: Stillstand gemeldet. Feuchte: Messung ordnungsgemäß beendet (nicht abgebrochen) |
| `roh` | ja | Text, höchstens 2000 Zeichen | Ausgabe des Geräts **unverändert**, mit Zeilenenden; mehrzeilige Ausgaben (Protokoll) ganz |
| `extra` | nein | Objekt, Werte nur Zahl oder Text | weitere Angaben, die das Gerät liefert (Schlüssel siehe unten) |
| `firmware` | ja | Text | Version der Brücken-Firmware |
| `verworfen` | ja | Zahl | wie viele Messungen seit dem letzten Erfolg verworfen wurden (Puffer voll); normal `0` |

Bekannte Schlüssel in `extra`, sonst frei wählbar in Kleinbuchstaben mit `_`:
- Feuchte: `programm`, `temperatur_c`, `dauer_s`, `anfang_g`, `ende_g`, `anzeige` (`"MC"` Feuchte, `"DC"` Trockenmasse, …).
- Gewicht: `brutto_kg`, `tara_kg`, `netto_kg`, `teilung_g`.

**Antwort bei Erfolg** (HTTP 200; Frappe legt das Ergebnis immer unter `message`):

```json
{ "message": { "ok": true, "messung": "MES-2026-00042", "doppelt": false, "server_zeit": "2026-11-01T17:05:13+01:00" } }
```

`doppelt: true` heißt: diese `messung_id` war schon da, es wurde nichts Neues gespeichert. Für die Brücke
ist das ebenfalls Erfolg: aus dem Puffer löschen.

## 2. Live-Wert

`POST {basis}/api/method/keks_trace.messung.live`

```json
{ "schnittstelle": 1, "geraet": "KRANWAAGE-1", "art": "gewicht", "wert": 12.45, "einheit": "kg", "stabil": false, "roh": "ST,GS,+0012.45kg\r\n" }
```

Gleiche Felder und Regeln wie oben, ohne `messung_id`, `zeitpunkt`, `extra`, `verworfen`, `firmware`.
Antwort: `{ "message": { "ok": true } }`. Fehlgeschlagene Live-Werte **nicht** wiederholen.

## Fehler und Wiederholen

| Antwort | Bedeutung | Brücke tut |
|---|---|---|
| 200 mit `ok: true` | gespeichert (oder schon da) | aus dem Puffer löschen |
| keine Antwort, Zeitüberschreitung, 429, 5xx | Netz oder Server gerade nicht da | Messung behalten, später nochmal: 5 s, 15 s, 60 s, dann alle 5 min |
| 401, 403 | Schlüssel falsch oder Gerät nicht freigegeben | nicht wiederholen bis Neustart oder neue Einstellungen; Fehler anzeigen |
| 404 | Server kennt die Schnittstelle nicht (zu alt) | wie 5xx behandeln, Fehler anzeigen |
| 417 | Daten abgelehnt (z. B. unbekanntes Gerät, Pflichtfeld fehlt) | **nicht** wiederholen, aus dem Puffer nehmen, Fehler anzeigen und zählen |

Bei Fehlern schickt Frappe JSON mit `exc_type` (z. B. `"ValidationError"`) und `_server_messages`
(Liste der Meldungen als JSON-Text); den Text in der Fehleranzeige bzw. im seriellen Log ausgeben.

## Puffer ohne WLAN

- Mindestens 200 Messungen im Flash (übersteht Stromausfall), in der Reihenfolge der Messung senden,
  immer die älteste zuerst, eine nach der anderen.
- Puffer voll: **keine alte Messung überschreiben.** Neue Messungen verwerfen, `verworfen` hochzählen,
  Fehler deutlich anzeigen (LED/Display). Der Zähler geht mit der nächsten erfolgreichen Messung mit.

## Einstellungen der Brücke

Über eine Einstellseite (z. B. Access Point beim ersten Start), gespeichert im NVS:
WLAN-Name und -Passwort, Basis-URL, `api_key`, `api_secret`, `geraet`, optional CA-Zertifikat (PEM),
serielle Parameter des Geräts (Baudrate, Datenbits, Parität, Stoppbits). Das `api_secret` nach dem
Speichern nicht wieder anzeigen.

Zeit per NTP (einstellbarer Server, Standard `pool.ntp.org`, Zeitzone Europe/Berlin). Solange keine gültige
Zeit da ist: `zeitpunkt: null`.

## Selbst testen

```bash
curl -i -X POST "http://192.168.1.50/api/method/keks_trace.messung.erfassen" \
  -H "Authorization: token <api_key>:<api_secret>" \
  -H "Content-Type: application/json" \
  -d '{"schnittstelle":1,"geraet":"FEUCHTE-1","messung_id":"FEUCHTE-1-0001-000001","zeitpunkt":null,"art":"feuchte","wert":4.83,"einheit":"%","stabil":true,"roh":"MC   4.83 %\r\n","firmware":"0.1","verworfen":0}'
```

Zweimal dasselbe schicken: beim zweiten Mal `"doppelt": true`.

## Was der Server damit macht (zur Info, nicht Teil der Brücke)

- Speichert jede Messung unveränderbar (Gerät, Werte, `roh`, Empfangszeit, Absender).
- Am Terminal unter „Prüfung erfassen“ bzw. beim Einwiegen: „Letzte Messung FEUCHTE-1: 4,83 % um 17:05 –
  übernehmen?“. Erst mit der Übernahme hängt die Messung an Charge oder Auftrag; Grenzwerte und Sperren
  wirken wie bei einer von Hand eingegebenen Prüfung.
- Prüfmittelüberwachung: Am Messgerät steht „kalibriert bis“. Ist das überschritten, wird die Messung
  trotzdem gespeichert, aber gekennzeichnet; die Übernahme am Terminal warnt.
