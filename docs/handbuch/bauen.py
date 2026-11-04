"""Testhandbuch Keks Trace für QS und Büro: HTML erzeugen (danach mit Chromium als PDF)."""

import pathlib

import flows
import kapitel_neu

HIER = pathlib.Path(__file__).parent
B = (HIER / "bilder").as_uri()
SERVER = "http://192.168.60.40"


def bild(name, text, breite="100%"):
	return f'<figure><img src="{B}/{name}" style="width:{breite}"><figcaption>{text}</figcaption></figure>'


def aufgabe(nr, titel, ziel, schritte, erwartet, tipp=""):
	li = "".join(f"<li>{s}</li>" for s in schritte)
	t = f'<p class="tipp"><b>Tipp:</b> {tipp}</p>' if tipp else ""
	return f"""<section class="aufgabe">
<h3><span class="nr">{nr}</span>{titel}</h3>
<p class="ziel">{ziel}</p>
<ol>{li}</ol>
<p class="erwartet"><b>Das sollte passieren:</b> {erwartet}</p>{t}
</section>"""


CSS = """
@page { size: A4; margin: 18mm 17mm 18mm 17mm; }
:root { --navy:#0b2340; --rot:#c8102e; --grau:#5b6573; --hell:#eef2f7; --linie:#d6dde6; }
* { box-sizing: border-box; }
body { font-family: Inter, Arial, sans-serif; font-size: 10pt; line-height: 1.45; color: #1d2733; margin: 0; }
h1 { font-size: 26pt; color: var(--navy); margin: 0 0 4mm; line-height: 1.1; }
h2 { font-size: 15pt; color: var(--navy); margin: 0 0 3mm; padding-bottom: 1.5mm; border-bottom: 2px solid var(--navy); break-after: avoid; }
h3 { font-size: 11.5pt; color: var(--navy); margin: 0 0 1.5mm; break-after: avoid; }
p { margin: 0 0 2.5mm; }
ul, ol { margin: 0 0 2.5mm; padding-left: 5.5mm; }
li { margin-bottom: 0.8mm; }
code, .code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.8pt; background: var(--hell); padding: 0.3mm 1.2mm; border-radius: 1mm; }
.kapitel { break-before: page; }
.titel { height: 255mm; display: flex; flex-direction: column; }
.titel .logo { width: 34mm; margin-bottom: 14mm; }
.titel .unter { font-size: 14pt; color: var(--grau); margin-bottom: 10mm; }
.titel .kasten { margin-top: auto; border-left: 3px solid var(--rot); padding: 2mm 0 2mm 5mm; color: var(--grau); }
.inhalt { columns: 2; column-gap: 8mm; margin-top: 8mm; font-size: 10.5pt; }
.inhalt div { break-inside: avoid; margin-bottom: 1.5mm; }
.inhalt b { color: var(--navy); display: inline-block; width: 7mm; }
figure { margin: 2mm 0 4mm; break-inside: avoid; }
figure img { border: 1px solid var(--linie); border-radius: 1.5mm; display: block; }
figcaption { font-size: 8.5pt; color: var(--grau); margin-top: 1.2mm; }
.fluss { break-inside: avoid; margin: 2mm 0 5mm; }
.box { border-radius: 1.5mm; padding: 3mm 4mm; margin: 3mm 0 4mm; break-inside: avoid; }
.box.info { background: var(--hell); }
.box.wichtig { background: #fdf0f2; border-left: 3px solid var(--rot); }
.box.ok { background: #e6f4ea; }
.box h3 { margin-bottom: 1mm; }
.aufgabe { border: 1px solid var(--linie); border-radius: 2mm; padding: 3mm 4mm 2mm; margin: 0 0 4mm; break-inside: avoid; }
.aufgabe .nr { display: inline-block; min-width: 9mm; height: 6mm; line-height: 6mm; text-align: center; background: var(--navy); color: #fff; border-radius: 1mm; font-size: 9pt; margin-right: 2.5mm; padding: 0 1.2mm; }
.aufgabe .ziel { color: var(--grau); font-style: italic; }
.aufgabe .erwartet { background: #e6f4ea; padding: 1.5mm 2.5mm; border-radius: 1mm; }
.aufgabe .tipp { font-size: 9pt; color: var(--grau); }
table { width: 100%; border-collapse: collapse; margin: 1mm 0 4mm; font-size: 9.3pt; break-inside: avoid; }
th, td { text-align: left; vertical-align: top; padding: 1.6mm 2mm; border-bottom: 1px solid var(--linie); }
th { background: var(--hell); color: var(--navy); }
.zwei { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }
.bogen td { height: 11mm; }
.bogen td:first-child { width: 42mm; color: var(--navy); font-weight: 600; }
.klein { font-size: 8.8pt; color: var(--grau); }
"""


def html():
	t = []
	t.append(f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Keks Trace – Testhandbuch</title><style>{CSS}</style></head><body>""")

	# ------------------------------------------------------------------ Titel
	t.append(f"""<div class="titel">
<img class="logo" src="{B}/logo.png">
<h1>Keks Trace<br>Testhandbuch</h1>
<div class="unter">Ausprobieren und Fehler melden – für QS und Büro</div>
<div class="inhalt">
<div><b>1</b>Worum es geht</div>
<div><b>2</b>Anmelden und zurechtfinden</div>
<div><b>3</b>Die Abläufe als Bild</div>
<div><b>4</b>Was im Testsystem schon drin ist</div>
<div><b>5</b>Aufgaben für die QS</div>
<div><b>6</b>Aufgaben für das Büro</div>
<div><b>7</b>Neu seit dem 1. November</div>
<div><b>8</b>Fehler melden</div>
<div><b>9</b>Bekannte Grenzen des Tests</div>
<div><b>A</b>Fehlerbogen zum Ausdrucken</div>
</div>
<div class="kasten">Stand 4. November 2026 · Testserver mit ERPNext 16 und Keks Trace<br>
Testfirma „Keks Test GmbH“, alle Daten sind ausgedacht.</div>
</div>""")

	# ------------------------------------------------------------------ 1
	t.append("""<div class="kapitel"><h2>1 Worum es geht</h2>
<p>Keks Trace ist die neue Rückverfolgung für unsere Produktion: von der Lieferanten-Charge über Teig, Rework
und Verpackung bis zum Kunden. Sie läuft in ERPNext. Die Mitarbeiter in der Halle buchen an Terminals
(Tablet oder PC im Browser), QS und Büro arbeiten in der normalen ERPNext-Oberfläche.</p>
<p>Auf dem <b>Testserver</b> könnt ihr alles ausprobieren. Ziel ist eure Rückmeldung, bevor das System in den
echten Betrieb geht: Was fehlt, was ist falsch, was ist umständlich, was versteht man nicht?</p>
<div class="box ok"><h3>Spielregeln</h3><ul>
<li><b>Alles darf.</b> Buchen, sperren, löschen, falsche Werte eingeben: Das ist ein Testsystem. Gerade die
Fehlbedienung ist interessant: Hält das System sie auf, und versteht man die Meldung?</li>
<li><b>Nichts Echtes eintragen.</b> Keine echten Kunden-, Lieferanten- oder Personendaten. Die Testfirma reicht.</li>
<li><b>Jede Auffälligkeit melden</b>, auch Kleinigkeiten und „ich hätte es anders erwartet“ (Kapitel 8).</li>
<li>Der Testserver kann jederzeit neu aufgesetzt werden. Dann sind die Testdaten weg; eure Meldungen
sichert Malte vorher.</li>
</ul></div>
""")

	# ------------------------------------------------------------------ 2
	t.append(f"""<h2 style="margin-top:6mm">2 Anmelden und zurechtfinden</h2>
<table>
<tr><th style="width:38mm">Was</th><th>Adresse und Anmeldung</th></tr>
<tr><td>ERPNext (QS, Büro)</td><td><code>{SERVER}/app</code> · Benutzer <code>Administrator</code> · Passwort von Malte</td></tr>
<tr><td>Terminal (Halle)</td><td><code>{SERVER}/terminal</code> · gleiche Anmeldung, beim ersten Öffnen die Station wählen</td></tr>
<tr><td>Browser</td><td>Chrome oder Edge, am PC oder Tablet. Nur im Firmennetz erreichbar.</td></tr>
</table>
<p>Nach der Anmeldung links <b>Keks Trace</b> wählen. Die Arbeitsfläche bündelt alles, was ihr für den Test
braucht. Ganz oben links: <b>Test und Rückmeldung → Fehler melden</b>.</p>
{bild("01_arbeitsflaeche.png", "Bild 1: Arbeitsfläche Keks Trace. Oben Schnellzugriffe, darunter die Bereiche.", "85%")}
<div class="box info"><h3>Drei Handgriffe, die immer helfen</h3><ul>
<li><b>Suchen</b> (links oben, oder <code>Strg+K</code>): Name einer Maske oder eines Berichts eintippen, z. B. „Charge“, „Auftrag“.</li>
<li><b>Listen filtern:</b> In jeder Liste oben „Filter“ – z. B. Chargen nur mit Chargenstufe „Fertigware“.</li>
<li><b>Zurück zur Übersicht:</b> links auf „Keks Trace“ klicken.</li>
</ul></div>
</div>""")

	t.append(f"""<div><h3>Das Terminal</h3>
<p>Das Terminal ist für die Halle gebaut: große Knöpfe, Bildschirmtastatur, Scanner. Jede Station sieht nur
ihre Knöpfe. Ohne Scanner tippt man Nummern einfach in das Scanfeld und drückt Enter. „Station wechseln“
oben rechts wählt eine andere Station; so könnt ihr alle Bereiche ausprobieren.</p>
{bild("02_terminal_lager.png", "Bild 2: Terminal an der Station Lager. Info-Scan zeigt zu jeder Nummer, was dahintersteckt.", "78%")}
<table>
<tr><th style="width:42mm">Station</th><th>Was man dort tut</th></tr>
<tr><td>Lager</td><td>Wareneingang (ins Silo oder als Gebinde mit Etikett), Umlagern, Paletten, Silo leer melden</td></tr>
<tr><td>Backstube, Kneter</td><td>Grundteig und Teig herstellen (Kübel, Silo, Gebinde scannen), Rework wiegen</td></tr>
<tr><td>Verpackung, Verpackungs-PC, Paletten-Terminal</td><td>Verpacken nach Auftrag, Los und MHD, Palette mit NVE-Etikett, Metallcheck</td></tr>
<tr><td>Herzen Garnieren / Verpackung</td><td>eigene Linie Herzenboden</td></tr>
<tr><td>Versand</td><td>Lieferung: Kunde und Auftrag wählen, Palette oder Kartons scannen → Lieferschein</td></tr>
<tr><td>Lagerverkauf</td><td>Ware in den Lagerverkauf umlagern</td></tr>
</table>
<p class="klein">Überall gibt es den <b>Info-Scan</b>: Charge, Behälter, Silo oder Palette eingeben und sehen, was
darin ist, wie alt es ist und ob es gesperrt ist.</p>
</div>""")

	# ------------------------------------------------------------------ 3
	t.append(f"""<div class="kapitel"><h2>3 Die Abläufe als Bild</h2>
<p>Wer den Fluss kennt, versteht die Aufgaben schneller. Gelb ist, wo gescannt oder geprüft wird.</p>
<h3>Vom Wareneingang zum Kunden</h3>
<div class="fluss">{flows.warenfluss()}</div>
<p>Jeder Schritt erzeugt eine eigene <b>Charge</b> und merkt sich, woraus sie entstanden ist. Daraus rechnet
die Rückverfolgung in beide Richtungen: vom Mehl zu allen Kunden, und vom Karton zurück bis zur
Lieferanten-Charge – auch über Rework und mehrere Tage. Teig und lose Ware liegen in <b>Behältern</b> mit
Code; ein Behälter weiß, was drin ist. Das <b>MHD</b> zählt ab Backtag und wird durch die kürzeste Füllung
begrenzt.</p>
<h3>Der Kreislauf der QS</h3>
<div class="fluss">{flows.qs_fluss()}</div>
<p>Rohstoffe und lose Ware mit „Freigabe vor Verwendung“ sind nach dem Eingang <b>gesperrt</b>, bis die QS sie
freigibt. Prüfungen (CCP/CP) werden am Terminal fällig; eine Abweichung sperrt die betroffenen Lose. Alles
Auffällige eines Tages steht in der <b>QS Tagesliste</b>; die bestätigte Durchsicht ist der Nachweis.</p>
</div>""")

	t.append(f"""<div><h3>Der Weg im Büro</h3>
<div class="fluss">{flows.buero_fluss()}</div>
<p>Oben der Verkauf: Der <b>Auftrag</b> erscheint an den Terminals (Versand, Verpackung), der Versand bucht den
<b>Lieferschein</b>, das Büro macht daraus die <b>Ausgangsrechnung</b> und die <b>E-Rechnung</b>. Unten der
Einkauf: <b>Kontrakt</b> (Rahmenauftrag) mit fester Menge und festem Preis, <b>Bestellungen</b> als Abrufe,
Wareneingang am Terminal, <b>Eingangsrechnung</b> aus der E-Rechnung des Lieferanten. Am Ende gehen
Aus- und Eingangsrechnungen per <b>DATEV-Export</b> an den Steuerberater.</p>

<h2 style="margin-top:6mm">4 Was im Testsystem schon drin ist</h2>
<p>Beim Einrichten wurden mehrere Produktionstage durchgespielt. Ihr findet:</p>
<table>
<tr><th style="width:38mm">Bereich</th><th>Beispiele</th></tr>
<tr><td>Firma</td><td>Keks Test GmbH; für DATEV zusätzlich „Keks DATEV Demo GmbH“ (Kontenplan SKR04 mit Nummern)</td></tr>
<tr><td>Kunden</td><td>KT Demo Handel, Großkunde A/B/C (Demo), Markthändler Krause (Demo), Schaustellerbetrieb Lange (Demo)</td></tr>
<tr><td>Lieferanten</td><td>KT Demo Mühle, KT Bio Mühle (mit Öko-Zertifikat)</td></tr>
<tr><td>Artikel</td><td>Demo-Artikel mit <code>KT-</code> vorn (Mehl, Zucker, Butter, Teige, Nussgebäck …); Honig Moppen (Rezeptur 5888, Artikel 17846);
Herzen in mehreren Größen</td></tr>
<tr><td>Chargen</td><td>Rohstoffe bis Fertigware, mit Rework; eine lose Ware wartet noch auf Freigabe der QS</td></tr>
<tr><td>Aufträge, Lieferungen</td><td>sieben Aufträge, drei gebuchte Lieferscheine; ein Rückverfolgungstest</td></tr>
<tr><td>Prüfpläne</td><td>Metalldetektor und Metallcheck je Anlage (CCP), Brix Sirup, Temperatur Kühlware, Reinigung vor Bio</td></tr>
<tr><td>Einkauf</td><td>Zucker-Kontrakt über 50 t mit zwei Abrufen</td></tr>
</table>
<div class="box info"><h3>Chargen finden</h3>
<p style="margin:0">Liste <b>Charge</b> (Arbeitsfläche → Chargen und Sperren), Filter <b>Chargenstufe</b> = z. B. „Fertigware“ oder
„Rohstoff“. Die Nummern enden mit einer Zahlenfolge (Zeitpunkt der Einrichtung), z. B. <code>L1-261101…</code> für
„Nusskeks mit Schokoboden“ oder <code>M-261101…</code> für Mehl. Fertigware der echten Rezepturen heißt wie
<code>17846-2026-6447</code>: Artikel, Jahr, Los.</p></div>
</div>""")

	# ------------------------------------------------------------------ 5 QS
	t.append('<div class="kapitel"><h2>5 Aufgaben für die QS</h2>')
	t.append("<p>Die Reihenfolge ist ein Vorschlag. Notiert nebenbei, was euch auffällt, und meldet es (Kapitel 8).</p>")
	t.append(aufgabe("Q1", "Rückverfolgung rückwärts und vorwärts",
		"Kann ich in Sekunden sagen, woraus ein Los besteht und wohin eine Rohstoff-Charge gegangen ist?",
		["Arbeitsfläche → <b>Rückverfolgung</b>.",
		 "Charge einer Fertigware wählen (z. B. „Nusskeks mit Schokoboden“, <code>L1-…</code>), Richtung <b>Rückwärts</b>.",
		 "Liste lesen: Stufe, Charge, Artikel, Anteil in %, Herstelldatum, Ursprung, Verfall.",
		 "Dann eine Rohstoff-Charge (Mehl <code>M-…</code>) mit Richtung <b>Vorwärts</b>: bis zu welchen Kunden und Lieferscheinen?"],
		"Rückwärts erscheinen alle Zutaten bis zur Lieferanten-Charge, auch Rework vom Vortag; vorwärts die Kunden mit Lieferschein und Palette (NVE).",
		"Stimmt der Anteil in % mit eurem Gefühl überein? Fehlt eine Zutat, die laut Rezept drin sein müsste?"))
	t.append(bild("04_rueckverfolgung.png", "Bild 3: Rückverfolgung rückwärts eines Fertigwaren-Loses. Oben die Knöpfe für Test und Rückruf.", "82%"))
	t.append(aufgabe("Q2", "Rückverfolgungstest für das Audit (IFS 4.18)",
		"Den jährlichen Test als Nachweis erzeugen.",
		["In der Rückverfolgung eine Charge wählen, oben <b>Rückverfolgungstest protokollieren</b>.",
		 "Anlass wählen (z. B. „Audit“), Test starten.",
		 "Im Protokoll Dauer, vorwärts/rückwärts und die <b>Mengenbilanz</b> je Charge ansehen; buchen."],
		"Ein Protokoll RVT-… mit allen Ergebnissen; nach dem Buchen nicht mehr änderbar.",
		"Passt die Mengenbilanz (Zugang, verbraucht, ausgeliefert, Bestand)? Wo nicht – melden."))
	t.append("</div>")
	t.append('<div>')
	t.append(aufgabe("Q3", "Charge freigeben und sperren",
		"Ware, die auf die QS wartet, freigeben; eine Charge sperren und sehen, was dann passiert.",
		["Liste <b>Charge</b>, Filter Sperrstatus = „Gesperrt“. Die lose Ware „Freigabe durch die QS ausstehend“ öffnen.",
		 "Oben <b>Freigeben</b>, Bemerkung eintragen.",
		 "Eine andere Charge öffnen (z. B. einen Rohstoff), <b>Sperren</b> mit Grund.",
		 "Am Terminal (Station Backstube) diese Charge zum Herstellen scannen, im Info-Scan nachsehen."],
		"Freigegebene Ware ist sofort verwendbar. Gesperrte Ware wird am Terminal rot abgewiesen. Jede Sperre und Freigabe steht im Protokoll <b>Chargen Sperre</b> (wer, wann, warum).",
		"Das Protokoll lässt sich nicht ändern oder löschen – das gehört zum IFS-Nachweis."))
	t.append(bild("03_charge_gesperrt.png", "Bild 4: Gesperrte Charge mit rotem Hinweis. Oben Freigeben, Rückverfolgung, Mengenbilanz.", "72%"))
	t.append(aufgabe("Q4", "Rückruf durchspielen",
		"Eine Rohstoff-Charge ist auffällig: Was ist betroffen, und wie sperre ich alles?",
		["Rückverfolgung, Rohstoff-Charge (z. B. Haselnuss <code>HN-…</code>), Richtung Vorwärts.",
		 "Oben <b>Rückruf: alles vorwärts sperren</b>, Grund eintragen, bestätigen.",
		 "Ergebnis lesen: gesperrte Chargen, Paletten, betroffene Kunden."],
		"Die Charge und alles, in das sie eingeflossen ist, ist gesperrt; ausgelieferte Ware erscheint mit Kunde und Lieferschein.",
		"Danach im Versand-Terminal versuchen, ein betroffenes Los zu liefern."))
	t.append("</div>")
	t.append('<div>')
	t.append(aufgabe("Q5", "Prüfung am Terminal und Abweichung",
		"CCP-Prüfung erfassen, wie es die Halle tun wird.",
		["Terminal, Station <b>Verpackung</b>. Oben steht die fällige Prüfung „Metalldetektor Verpackung“.",
		 "Antippen und einmal mit Ergebnis in Ordnung erfassen – danach kann gebucht werden.",
		 "Noch einmal erfassen, diesmal <b>nicht in Ordnung</b>, Bemerkung schreiben."],
		"Ohne erfasste Prüfung bucht die Station nicht (sperrend). Bei „nicht in Ordnung“ werden die Lose seit der letzten guten Prüfung gesperrt, und die Prüfung ist sofort wieder fällig.",
		"Prüfpläne (Grenzwerte, Intervall, Korrekturmaßnahme) unter Arbeitsfläche → Prüfplan ansehen: Stimmen sie mit eurem HACCP-Plan überein?"))
	t.append(aufgabe("Q6", "QS Tagesliste und Durchsicht",
		"Alles Auffällige eines Tages an einer Stelle sehen und die Durchsicht bestätigen.",
		["Arbeitsfläche → <b>QS Tagesliste</b>, Tag wählen (Von = Bis).",
		 "Einträge lesen: FEFO (jüngere Ware genommen), Einwaage außerhalb der Toleranz, Prüfung, Sperre. „Freigaben offen“ zählt wartende Ware.",
		 "Oben <b>Tag als durchgesehen bestätigen</b>."],
		"Nach Q5 steht die Abweichung in der Liste. Die Durchsicht wird als unveränderbares Protokoll gespeichert, je Tag einmal.",
		"Einträge entstehen erst durch Buchungen. Eigene erzeugen: am Terminal Backstube beim Herstellen eine jüngere Charge scannen, obwohl eine ältere da ist, oder die Einwaage deutlich abweichen lassen – das Terminal fragt dann nach einem Grund."))
	t.append(bild("05_qs_tagesliste.png", "Bild 5: QS Tagesliste. Zähler oben, darunter die Einträge des Tages.", "70%"))
	t.append("</div>")
	t.append('<div>')
	t.append(aufgabe("Q7", "Mengenbilanz und MHD der Rohstoffe",
		"Stimmen die Mengen, und was läuft bald ab?",
		["Arbeitsfläche → <b>Mengenbilanz</b>, eine Charge wählen: Zugang, verbraucht, zu Rework, ausgeliefert, entsorgt, Bestand, Ausbeute.",
		 "Arbeitsfläche → <b>MHD Rohstoffe</b>: was in den nächsten Tagen abläuft und was bei normalem Verbrauch übrig bleibt (rot)."],
		"Die Bilanz geht auf; Abweichungen zwischen Lager und Rückverfolgung werden angezeigt.", ""))
	t.append(aufgabe("Q8", "Wareneingang mit Prüfung",
		"Eine Anlieferung so buchen, wie das Lager es tun wird.",
		["Terminal, Station <b>Lager</b> → Wareneingang.",
		 "Artikel wählen (z. B. Butter), Lieferant, Lieferanten-Charge, MHD, Menge. Kühlware fragt nach der Temperatur.",
		 "Beim MHD nur Ziffern tippen, z. B. <code>300628</code> – die Punkte setzt das Terminal, darunter steht das erkannte Datum mit Wochentag (siehe N5).",
		 "Einmal mit zu hoher Temperatur probieren, einmal mit einer Charge wie „Karton“."],
		"Unplausible Chargen werden abgewiesen; zu warme Ware wird nicht angenommen und die Prüfung protokolliert. Butter ist nach dem Eingang bis zur Freigabe gesperrt.",
		"Mit Scanner: das Etikett des Lieferanten scannen – Artikel, Charge und MHD werden vorbelegt."))
	t.append(aufgabe("Q9", "Etiketten ansehen",
		"Sind Palettenetikett und Gebinde-Etikett vollständig und richtig?",
		["Liste <b>Palette</b>, eine Palette öffnen; am Terminal (Paletten → Palette scannen) <b>Etikett drucken</b>.",
		 "Prüfen: Absender, NVE, Los, MHD, Anzahl, Strichcodes. Ohne GS1-Basisnummer steht „TEST-NVE“ darauf – richtig so."],
		"Etikett im Browser oder auf dem Etikettendrucker; nach Entnahmen meldet das Terminal „Etikett neu drucken“. Ein zweiter Druck ohne Änderung fragt nach dem Grund (siehe N1).", ""))
	t.append("</div>")

	# ------------------------------------------------------------------ 6 Büro
	t.append('<div class="kapitel"><h2>6 Aufgaben für das Büro</h2>')
	t.append(aufgabe("B1", "Auftrag anlegen",
		"Einen Kundenauftrag erfassen und sehen, wo er in der Produktion auftaucht.",
		["Suche „Auftrag“ → <b>Neu</b>. Kunde „KT Demo Handel“, Liefertermin in ein paar Tagen.",
		 "Position: ein Fertigware-Artikel (z. B. Honig Moppen 17846), Menge in Karton oder Palette. Speichern, <b>Buchen</b>.",
		 "Terminal, Station <b>Versand</b> → Lieferung, Kunde wählen: Erscheint der Auftrag mit Restmenge und Termin?"],
		"Der Auftrag steht am Versand (dort sieht man alle Aufträge); die Verpackung sieht ihn, wenn der Artikel zu ihrer Linie gehört. Was geliefert und berechnet ist, führt ERPNext im Auftrag mit.", ""))
	t.append(aufgabe("B2", "Rechnung aus dem Lieferschein und E-Rechnung",
		"Eine Ausgangsrechnung erzeugen, die als XRechnung gültig ist.",
		["Liste <b>Lieferschein</b>, einen gebuchten Lieferschein an „KT Demo Handel“ öffnen.",
		 "Oben <b>Erstellen → Ausgangsrechnung</b>.",
		 "Prüfen bzw. setzen: <b>E-Rechnungs-Profil</b> „XRECHNUNG“, Steuervorlage „Lieferung oder sonstige Leistung im Inland“, Zahlungsbedingung, <b>Kontaktperson des Unternehmens</b> (Pflicht in der XRechnung).",
		 "Speichern. Steht oben „Bitte beachten Sie die Validierungsfehler der E-Rechnung“, die Fehler lesen. Sonst <b>Buchen</b>.",
		 "Menü <b>⋯ → E-Rechnung herunterladen</b>."],
		"Die Steuer beträgt 7 % (Lebensmittel). Die XML-Datei lässt sich herunterladen; ohne Validierungsfehler ist sie gültig nach EN 16931.",
		"Steht bei der Steuer etwas anderes als 7 % (z. B. 49 %), fehlt die Steuervorlage – genau so etwas bitte melden, auch wenn ihr es selbst korrigieren konntet."))
	t.append(aufgabe("B3", "Einkauf: Kontrakt und Reichweite",
		"Wie viel ist vom Kontrakt abgerufen, und wie lange reichen die Rohstoffe?",
		["Arbeitsfläche → <b>Rahmenauftrag (Kontrakt)</b>: den Zucker-Kontrakt öffnen (Menge, abgerufen).",
		 "Eine <b>Bestellung</b> gegen den Kontrakt anlegen (Lieferant KT Demo Mühle, Häkchen „Gegen Rahmenauftrag“).",
		 "Arbeitsfläche → <b>Reichweite Rohstoffe</b>: Bestand, bestellt, Kontrakt offen, Verbrauch je Tag, reicht bis, Bedarf aus offenen Aufträgen."],
		"Der Abruf zählt im Kontrakt mit; die Reichweite berücksichtigt die neue Bestellung.", ""))
	t.append("</div>")
	t.append('<div>')
	t.append(aufgabe("B4", "Eingangsrechnung aus einer E-Rechnung",
		"Eine XRechnung oder ZUGFeRD-PDF eines Lieferanten einlesen.",
		["Suche „E-Rechnungs-Import“ → Neu, Datei anhängen (XML oder ZUGFeRD-PDF; eine Beispieldatei bekommt ihr von Malte).",
		 "Speichern: Lieferant, Positionen und Beträge werden gelesen; erkannte Fehler stehen im Beleg.",
		 "Buchen, dann oben <b>Eingangsrechnung erstellen</b>."],
		"Lieferant über die USt-IdNr., Artikel über die Lieferanten-Artikelnummer erkannt; die Eingangsrechnung entsteht als Entwurf.",
		"In der Steuerzeile fehlt manchmal die Beschreibung (Pflichtfeld) – einmal eintippen, z. B. „Vorsteuer 7 %“."))
	t.append(aufgabe("B5", "DATEV-Export",
		"Einen Buchungsstapel für den Steuerberater erzeugen.",
		["Suche „DATEV“ → Bericht <b>DATEV</b>.",
		 "Firma <b>Keks DATEV Demo GmbH</b> wählen (nur sie hat Kontonummern), Zeitraum, Belegart.",
		 "Oben <b>DATEV-Datei herunterladen</b>."],
		"Eine ZIP-Datei mit Buchungsstapel, Kontenbeschriftungen, Kunden und Lieferanten im DATEV-Format.",
		"Die Testfirma „Keks Test GmbH“ hat einen Kontenplan ohne Nummern; DATEV geht dort nicht – das ist bekannt. Welcher Kontenrahmen (SKR03/04) später gilt, klärt der Steuerberater."))
	t.append(aufgabe("B6", "Stammdaten durchsehen",
		"Sind die Angaben, die wir pflegen müssen, verständlich?",
		["Suche „Element“ (so heißt der Artikel in ERPNext), einen KT-Artikel öffnen.",
		 "Ansehen: Chargenstufe, Allergengruppe, Freigabe vor Verwendung, Haltbarkeit, Einheiten (Karton, Palette), Barcodes, Bio/Vegan.",
		 "Kunde öffnen: Rechnungsadresse, USt-IdNr., Käuferreferenz (für die E-Rechnung)."],
		"Ihr wisst, wo was steht – oder meldet, was unklar ist.", ""))
	t.append(aufgabe("B7", "Lagerverkauf-Abschluss",
		"Den Tagesverkauf der Kasse einlesen.",
		["Arbeitsfläche → <b>Lagerverkauf Abschluss</b> → Neu, Kassenexport (CSV/Excel mit Artikelname und Anzahl) anhängen, „Datei einlesen“.",
		 "Unbekannte Kassennamen einmal einem Artikel zuordnen (<b>Kassenartikel</b>)."],
		"Der Abverkauf wird nach MHD (älteste zuerst) gebucht; gesperrte Lose nie.", ""))
	t.append("</div>")

	# ------------------------------------------------------------------ 7 Neu seit dem 1. November
	t += kapitel_neu.kapitel(aufgabe, bild, SERVER)

	# ------------------------------------------------------------------ 7 Fehler melden
	t.append(f"""<div class="kapitel"><h2>8 Fehler melden</h2>
<p>Jede Rückmeldung kommt als <b>Anfrage</b> in ERPNext. So ist alles an einer Stelle, mit Datum, Bildschirmfoto
und Stand der Bearbeitung. (In ERPNext heißt so ein Eintrag „Anfrage“, gemeint ist hier: eure Meldung.)</p>
<h3>So geht's</h3>
<ol>
<li>Arbeitsfläche Keks Trace → <b>Test und Rückmeldung → Fehler melden (Anfrage)</b> → <b>Neu</b>.</li>
<li><b>Betreff:</b> kurz und eindeutig, mit Art vorn: <code>FEHLER:</code>, <code>WUNSCH:</code> oder <code>FRAGE:</code>.</li>
<li><b>Anfragetyp:</b> Fehler, Wunsch oder Frage. <b>Priorität:</b> High (hoch), wenn Rückverfolgung, Sperre, MHD oder Rechnung
falsch sind; Medium (mittel), wenn etwas nicht geht; Low (niedrig) für Kleinigkeiten.</li>
<li><b>Beschreibung</b> nach dem Muster unten. <b>Bildschirmfoto:</b> unter Windows <code>Win+Umschalt+S</code>, Bereich
markieren, dann in die Beschreibung mit <code>Strg+V</code> einfügen. Klappt das nicht: Bild speichern und rechts
unter <b>Anhänge</b> (+) hochladen.</li>
<li><b>Speichern.</b> Die Anfrage bekommt eine Nummer (ISS-2026-…).</li>
</ol>
{bild("06_anfrage_neu.png", "Bild 6: Neue Anfrage mit Betreff, Anfragetyp und Beschreibung.", "78%")}
</div>""")
	t.append("""<div><h3>Was in eine gute Meldung gehört</h3>
<table>
<tr><th style="width:44mm">Frage</th><th>Beispiel</th></tr>
<tr><td>Wo?</td><td>Station Versand / Maske Ausgangsrechnung / Bericht Rückverfolgung</td></tr>
<tr><td>Was wolltest du tun?</td><td>Palette an KT Demo Handel liefern</td></tr>
<tr><td>Was hast du gemacht?</td><td>Lieferung → Kunde gewählt → Palette 3020000000000000… gescannt → Buchen</td></tr>
<tr><td>Was ist passiert?</td><td>Rote Meldung „…“ (Text abschreiben oder Foto) / Etikett zeigt MHD 30.04.2026</td></tr>
<tr><td>Was hast du erwartet?</td><td>MHD 30.04.2027 wie auf dem Karton</td></tr>
<tr><td>Nummern</td><td>Charge, Palette (NVE), Beleg (z. B. MAT-DN-2026-00003), Uhrzeit</td></tr>
<tr><td>Wiederholbar?</td><td>Ja, zweimal probiert / nur einmal passiert</td></tr>
</table>
<div class="zwei">
<div class="box wichtig"><h3>So hilft es wenig</h3><p style="margin:0">„Lieferung geht nicht.“</p></div>
<div class="box ok"><h3>So hilft es</h3><p style="margin:0">„FEHLER: Lieferung bricht bei gemischter Palette ab. Station Versand, Kunde KT Demo Handel,
Palette 3020…0036, 22:14 Uhr. Meldung: ‚Palette enthält gesperrtes Los‘. Erwartet: nur das gesperrte Los
weglassen. Foto anbei. Zweimal probiert.“</p></div>
</div>
<div class="box info"><h3>In der Halle ohne PC</h3><p style="margin:0">Am Terminal gibt es kein Meldeformular. Mit dem Handy die Meldung auf dem Bildschirm fotografieren und den
<b>Fehlerbogen</b> (letzte Seite) ausfüllen; später als Anfrage eintragen oder an Malte geben. Wichtig sind
Station, Uhrzeit und die gescannten Nummern.</p></div>
<h3>Was mit eurer Meldung passiert</h3>
<p>Malte sieht alle Anfragen in der Liste und setzt den Status: <b>Offen</b> → <b>Beantwortet</b> oder <b>Zurückgestellt</b> →
<b>Geklärt</b>, wenn behoben und eingespielt. Ihr seht in der Liste, was erledigt ist, und könnt es nachtesten.
Nach einem Update einmal <code>Strg+F5</code> im Browser drücken.</p>

<h2 style="margin-top:6mm">9 Bekannte Grenzen des Tests</h2>
<p>Damit niemand Zeit mit Bekanntem verliert – das ist absichtlich so oder noch offen:</p>
<ul>
<li><b>Ein Benutzer für alle</b> (Administrator). Rechte je Rolle (z. B. nur die QS gibt frei) sind gebaut, aber
im Test sieht jeder alles. Eigene Benutzer kommen vor dem echten Betrieb.</li>
<li><b>Ausgedachte Werte:</b> Bei den Pilot-Rezepturen sind Beutelgrößen, Gebinde, Ruhezeiten und Packmittel
Platzhalter. Prüfpläne und Grenzwerte sind Beispiele.</li>
<li><b>Test-NVE:</b> Ohne eingetragene GS1-Basisnummer tragen Paletten „TEST-NVE“.</li>
<li><b>Druckformat der Rechnung</b> ist noch englisch; das XML der E-Rechnung ist davon unabhängig vollständig.</li>
<li><b>Kein E-Mail-Versand</b> und kein HTTPS – der Testserver ist nur im Firmennetz. Deshalb geht in der
Audit-Ansicht <code>/akte</code> am Handy noch keine Kamera: Nummer eintippen oder Handscanner nehmen.</li>
<li><b>Drucker:</b> Direktdruck nur auf Etikettendruckern, die eingetragen und vom Server erreichbar sind
(Port 9100, Firewall); sonst druckt der Browser.</li>
<li><b>Hinweise</b> gibt es nur am Produktions- und am Kundenauftrag – nicht im Wareneingang, nicht im Versand
(bewusst; Allgemeines läuft über das andere Tool).</li>
<li><b>Nicht enthalten:</b> Waagenanbindung, Wareneingang als Eingangsbeleg zur Bestellung (am Terminal nur Verweis, N13), eigene Kasse, CAPA, Schulungsnachweise.</li>
</ul>
</div>""")

	# ------------------------------------------------------------------ Fehlerbogen
	zeilen = ["Name", "Datum, Uhrzeit", "Station / Maske", "Was wolltest du tun?", "Was hast du gemacht?",
		"Was ist passiert? (Meldung)", "Was hast du erwartet?", "Nummern (Charge, NVE, Beleg)",
		"Art", "Wichtigkeit", "Foto gemacht?"]  # fmt: skip
	tr = ""
	for z in zeilen:
		wert = ""
		if z == "Art":
			wert = "☐ Fehler &nbsp;&nbsp; ☐ Wunsch &nbsp;&nbsp; ☐ Frage"
		elif z == "Wichtigkeit":
			wert = "☐ hoch (falsches Ergebnis) &nbsp; ☐ mittel (geht nicht) &nbsp; ☐ niedrig"
		elif z == "Foto gemacht?":
			wert = "☐ ja &nbsp;&nbsp; ☐ nein"
		hoch = ' style="height:20mm"' if z.startswith(("Was ist", "Was hast du gemacht")) else ""
		tr += f"<tr><td>{z}</td><td{hoch}>{wert}</td></tr>"
	t.append(f"""<div class="kapitel"><h2>A Fehlerbogen</h2>
<p class="klein">Für die Halle zum Ausdrucken. Später als Anfrage in ERPNext eintragen oder an Malte geben.</p>
<table class="bogen">{tr}</table>
<p class="klein">Anfrage-Nr. (wird im Büro eingetragen): ______________________</p>
</div>""")

	t.append("</body></html>")
	return "\n".join(t)


if __name__ == "__main__":
	(HIER / "handbuch.html").write_text(html(), encoding="utf-8")
	print("ok")
