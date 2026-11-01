# E-Rechnung und DATEV – Testlauf

Stand 1.11.2026, ERPNext 16, Testsystem `keks.localhost`. Demo-Skript: `keks_trace/demo_erechnung.py`.

## Ergebnis

| Schritt | Ergebnis |
|---|---|
| Lieferschein → Rechnung → **XRechnung** (XML) | ✅ geprüft gegen EN 16931 und XRechnung (KoSIT-Schematron in eu_einvoice): 0 Fehler, 0 Warnungen |
| Rechnung → **ZUGFeRD** (PDF/A-3 mit `factur-x.xml`, Profil EN 16931) | ✅ XML im PDF eingebettet |
| **Eingangsrechnung** einlesen (XML oder ZUGFeRD-PDF) | ✅ Lieferant über USt-IdNr., Artikel über Lieferanten-Artikelnr., Einheit über Code erkannt; Eingangsrechnung als Entwurf |
| **DATEV-Export** (EXTF 700: Buchungsstapel, Kontenbeschriftungen, Kunden, Lieferanten) | ✅ ZIP, Belegnummer und Beleglink je Buchung |

## Apps

Beide von ALYF, GPLv3, kostenlos, Zweig `version-16`.

```bash
bench get-app --branch version-16 https://github.com/alyf-de/eu_einvoice
bench get-app --branch version-16 https://github.com/alyf-de/erpnext_datev
bench --site <site> install-app eu_einvoice
bench --site <site> install-app erpnext_datev
sudo apt install ghostscript      # für ZUGFeRD (PDF/A-3)
```

Die Codelisten (Einheiten, Zahlungsarten, Steuerkategorien) importiert eu_einvoice bei der Installation.

## Was im ERP gepflegt sein muss

| Wo | Was | Regel |
|---|---|---|
| Firma | USt-IdNr., E-Mail, Telefon | BT-31, BT-34 |
| Adresse der Firma | „Ist Ihre Firmenadresse“, Straße, PLZ, Ort | BG-5 |
| Kontakt der Firma | Name, E-Mail, Telefon; in der Rechnung „Ansprechpartner Firma“ | BR-DE-5, BR-DE-7 |
| Kunde | Rechnungsadresse mit E-Mail, USt-IdNr., **Käuferreferenz** (Leitweg-ID bei Behörden, sonst z. B. Bestellnummer) | BR-DE-15 |
| Bankkonto | Bankkonto der Firma mit IBAN, Bank mit BIC, verknüpft mit Sachkonto | BR-DE-23 |
| Zahlungsart „Überweisung“ | Typ Bank, Standardkonto je Firma, Code **58** (SEPA-Überweisung) | BT-81 |
| Zahlungsbedingung | mit Zahlungsart Überweisung, Text „Zahlbar innerhalb 30 Tagen ohne Abzug“ | BR-DE-18 |
| Einheiten | Kg → KGM, Nos/Stk → H87, Karton → XCT, Beutel → XBG, Palette → XPX (Common Code „gilt für“ UOM) | BT-130 |
| Rechnung | Profil **XRECHNUNG** (nur XML) oder **EN 16931** (ZUGFeRD-PDF); Steuervorlage gesetzt | |

## Stolpersteine aus dem Testlauf

1. **Steuervorlage muss an der Rechnung stehen.** Fehlt sie, übernimmt ERPNext alle Konten der Artikel-Steuervorlage
   „7 %“ (auch Vorsteuer, innergemeinschaftlicher Erwerb) – 49 % Steuer statt 7 %. Die Schematron-Prüfung hat das
   erkannt (BR-CO-17, BR-S-08). Abhilfe: Steuervorlage am Kunden bzw. als Standard, Artikel-Steuervorlage am Artikel.
2. **Kontenplan mit Nummern.** DATEV braucht SKR03 oder SKR04 mit Kontonummern. Die Testfirma hat den Standardplan
   ohne Nummern; für den Export wurde die Demo-Firma „Keks DATEV Demo GmbH“ mit SKR04 angelegt.
3. **SKR04-Vorlage setzt falsche Standardkonten:** Forderungen 3250 (erhaltene Anzahlungen) statt 1200,
   Verbindlichkeiten 3500 (sonstige) statt 3300. In der Firma umstellen.
4. **Debitoren-/Kreditorennummern fehlen.** Kunden und Lieferanten laufen über Sammelkonten (1200/3300); die Listen
   Kunden/Lieferanten im Export sind leer. Ob Personenkonten (10000 ff., 70000 ff.) nötig sind, entscheidet der
   Steuerberater.
5. **Wareneingang Lagerartikel:** Eingangsrechnung für Mehl bucht gegen 70001 „Wareneingangs-Verrechnungskonto“
   (permanente Inventur). Mit dem Steuerberater klären.
6. **Eingangsrechnung → Steuerzeile ohne Beschreibung:** eu_einvoice füllt das Pflichtfeld nicht; Demo setzt
   „Vorsteuer 7 %“. In der Oberfläche einmal eintippen.
7. **Druckformat:** Standard ist Englisch und zeigt weder USt-IdNr. noch Bankverbindung noch Lieferdatum. Für den
   Betrieb ein deutsches Druckformat anlegen (das XML ist davon unabhängig vollständig).
8. **PDF im Container:** wkhtmltopdf ist hier nicht gepatcht; das Demo-PDF entstand über Chromium. Auf einem normalen
   Bench-Server erzeugt ERPNext das PDF selbst.

## Offene Fragen

- Profil je Kunde: XRECHNUNG (nur XML, Behörden, viele Handelsketten) oder ZUGFeRD (PDF + XML)? Was verlangen die
  Großkunden? EDI-Kunden dürfen bis Ende 2027 bleiben.
- Steuerberater: SKR03 oder SKR04, Berater- und Mandantennummer, Personenkonten ja/nein, Export-Rhythmus.
- Belegbilder: Versand an DATEV Unternehmen Online per E-Mail (in erpnext_datev enthalten) gewünscht?
- Zeitplan: Pflicht zum Ausstellen ab 1.1.2027 (Vorjahresumsatz über 800.000 €). Läuft die Rechnung bis zum Umstieg
  weiter über FOBIS, muss FOBIS das liefern – Anbieter fragen.

## Demo nachspielen

```bash
bench --site keks.localhost execute keks_trace.demo_erechnung.einrichten
bench --site keks.localhost execute keks_trace.demo_erechnung.rechnung                          # XRECHNUNG
bench --site keks.localhost execute keks_trace.demo_erechnung.rechnung --kwargs "{'profil': 'EN 16931'}"
bench --site keks.localhost execute keks_trace.demo_erechnung.zugferd --kwargs "{'rechnung': 'ACC-SINV-…'}"
bench --site keks.localhost execute keks_trace.demo_erechnung.eingang
bench --site keks.localhost execute keks_trace.demo_erechnung.datev
```

`rechnung` nimmt den jüngsten noch nicht berechneten Lieferschein von „KT Demo Handel“.
Beispiel-Eingangsrechnung: `keks_trace/demo_daten/eingangsrechnung_muehle.xml` (fiktive Mühle).
