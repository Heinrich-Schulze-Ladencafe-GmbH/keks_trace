"""Kapitel 7 des Testhandbuchs: Funktionen, die nach der ersten Fassung (1.11.2026) dazukamen."""


def kapitel(aufgabe, bild, server):
	t = []
	t.append("""<div class="kapitel"><h2>7 Neu seit dem 1. November</h2>
<p>Diese Funktionen kamen nach der ersten Fassung dazu. Vor dem Test einmal <code>Strg+F5</code> im Browser drücken,
damit die neue Terminal-Seite geladen wird. Die Aufgaben sind mit <b>N</b> nummeriert; QS und Büro können sie
gemeinsam durchgehen.</p>
<table>
<tr><th style="width:12mm">Nr.</th><th>Was</th><th style="width:34mm">Wer testet</th></tr>
<tr><td>N1</td><td>Nachdruck mit Grund und Druckprotokoll</td><td>QS</td></tr>
<tr><td>N2</td><td>Palette ohne Etikett wiederfinden („Wo ist dieses Los?“)</td><td>QS, Lager</td></tr>
<tr><td>N3</td><td>Akte und „Woraus besteht das?“</td><td>QS</td></tr>
<tr><td>N4</td><td>Audit-Ansicht am Handy oder Tablet</td><td>QS</td></tr>
<tr><td>N5</td><td>Datumsfeld mit festem Format</td><td>QS, Lager</td></tr>
<tr><td>N6</td><td>Einwaage wie bei FOBIS: Bestellt / Erledigt / ToDo, Sack und Eimer</td><td>QS, Backstube</td></tr>
<tr><td>N7</td><td>Retour: Unbenutztes von der Linie zurück ins Lager</td><td>QS, Linie</td></tr>
<tr><td>N8</td><td>Hinweis vom Büro am Auftrag</td><td>Büro</td></tr>
<tr><td>N9</td><td>Tagesübersicht</td><td>Büro, Schichtleitung</td></tr>
<tr><td>N10</td><td>Verladung nach Kundenauftrag (Maske wie FOBIS)</td><td>Versand</td></tr>
<tr><td>N11</td><td>Versandkarton mit eigener NVE</td><td>Versand, QS</td></tr>
<tr><td>N12</td><td>Netzbild der Rückverfolgung mit Belegliste</td><td>QS, Büro</td></tr>
<tr><td>N13</td><td>Wareneingang zu einer Bestellung</td><td>Lager, Einkauf</td></tr>
</table>""")
	t.append(aufgabe(
		"N1", "Nachdruck mit Grund und Druckprotokoll",
		"Jeder Etikettendruck ist nachvollziehbar; ein zweiter Druck braucht einen Grund.",
		["Terminal → <b>Info-Scan</b>, eine Palette scannen (oder die NVE abtippen; Leerzeichen und „(00)“ sind erlaubt).",
		 "<b>Etikett drucken</b>. Wurde das Etikett schon gedruckt und hat sich der Inhalt nicht geändert, fragt das Terminal: "
		 "<b>Beschädigt / unleserlich</b> oder <b>Etikett fehlt</b>. Einen Grund wählen.",
		 "In ERPNext: Arbeitsfläche Keks Trace → Paletten → <b>Etikettendruck (Protokoll)</b>."],
		"Im Protokoll steht jeder Druck mit Grund (Erstdruck, Inhalt geändert, Im Ablauf, Beschädigt, Etikett fehlt, "
		"Testdruck), Drucker oder „Browser“, Station, Person und Zeit. Ändern oder löschen geht nicht.",
		"„Erstdruck“, „Inhalt geändert“ und „Im Ablauf“ (Druck gehört zur Buchung) erkennt das System selbst – dafür fragt es nicht."))
	t.append(aufgabe(
		"N2", "Palette ohne Etikett wiederfinden",
		"Das Etikett ist weg. Welche Palette ist es, und wie drucke ich es sicher nach?",
		["Info-Scan → ein <b>Kartonetikett</b> von der Palette scannen (oder das Los eintippen).",
		 "Unten steht <b>Wo ist Los …?</b>: alle offenen Paletten mit diesem Los, je mit „gepackt wann, wo, von wem“, "
		 "letzter Bewegung und letztem Etikettendruck.",
		 "Bei der gesuchten Palette <b>Etikett fehlt – nachdrucken</b>. Das Terminal bittet, die <b>anderen</b> Paletten "
		 "mit dem Los zu scannen – sie müssen ihr Etikett noch haben.",
		 "Wenn alle gescannt sind: <b>Etikett nachdrucken</b>. Sonst <b>Andere nicht erreichbar – trotzdem drucken</b>."],
		"Das Etikett wird gedruckt. Im Protokoll steht, welche anderen Paletten gescannt wurden und welche nicht. Wer aus "
		"Versehen die gesuchte Palette scannt, bekommt eine rote Meldung – dann hat sie ja ein Etikett.",
		"Das Los gilt je Tag und Artikel. Mehrere Paletten mit demselben Los sind deshalb normal – genau dafür ist die Prüfung da."))
	t.append(bild("07_wo_ist_das_los.png", "Bild 7: „Wo ist Los …?“ nach dem Scan eines Kartonetiketts. Je Palette Inhalt, gepackt, zuletzt, Etikett.", "60%"))
	t.append("</div>")

	t.append("<div>")
	t.append(bild("08_etikett_fehlt.png", "Bild 8: Etikett fehlt. Erst die anderen Paletten mit dem Los scannen, dann nachdrucken.", "68%"))
	t.append(aufgabe(
		"N3", "Akte und „Woraus besteht das?“",
		"In Sekunden zeigen, was mit einer Palette passiert ist und woraus ein Los besteht – bis zum Wareneingang.",
		["Info-Scan → Palette scannen → <b>Akte</b>: Lebenslauf (angelegt, gepackt, umgepackt, geliefert, Etiketten), neueste zuerst.",
		 "Oben ein Los antippen: <b>Woraus besteht Los …?</b>",
		 "Zuerst die <b>Rohstoffe und Packmittel</b>: Charge, Wareneingang (Zeit, Station, Lieferant, „direkt in Silo …“), MHD, QS-Freigabe.",
		 "Darunter der <b>Herstellungsweg</b> Stufe für Stufe: Buchung, Station, Person, Prüfungen. Stufen lassen sich auf- und zuklappen.",
		 "Auch für Behälter: Kübel scannen → Akte (Befüllungen mit Charge, geleert, gereinigt)."],
		"Alle Zutaten erscheinen mit ihrer Herkunft. „Möglicherweise enthalten“ steht bei Silo-Chargen, die nur durch "
		"Vermischung im Silo dabei sein können.",
		"Vergleicht mit der Rückverfolgung in ERPNext (Q1): Gleiche Chargen? Sehr lange Ketten (viel Rework) werden am Terminal gekürzt."))
	t.append(bild("09_akte_palette.png", "Bild 9: Akte einer Palette mit Lebenslauf; oben der Knopf zu „Woraus besteht das?“.", "64%"))
	t.append("</div>")

	t.append("<div>")
	t.append(aufgabe(
		"N4", "Audit-Ansicht am Handy oder Tablet",
		"Beim Rundgang mit dem Auditor eine Palette zeigen: was drin ist und woher.",
		[f"Am Handy oder Tablet <code>{server}/akte</code> öffnen und anmelden.",
		 "NVE, Los oder Behälter eintippen (oder mit Handscanner scannen), <b>Zeigen</b>.",
		 "Palette: Akte und je Los „Woraus besteht …?“. Los: direkt die Herkunft und darunter, wo es liegt."],
		"Die Seite passt auf das Handy, nichts ist abgeschnitten. Sie zeigt nur an, ändern geht nicht.",
		"Die Kamera als Scanner geht erst mit HTTPS (später) und dann nur in Chrome auf Android. Am Surface: Handscanner oder eintippen."))
	t.append(f"""<div class="zwei"><div>{bild("10_audit_handy.png", "Bild 10: Audit-Ansicht am Handy: Rohstoffe mit Wareneingang und MHD.", "52%")}</div>
<div>{bild("14_datumsfeld.png", "Bild 11: Datumsfeld – halb eingegeben, gültig mit Wochentag, gibt es nicht, in der Vergangenheit.", "100%")}</div></div>""")
	t.append(aufgabe(
		"N5", "Datumsfeld mit festem Format",
		"Ein MHD kann nicht mehr falsch oder unvollständig gebucht werden.",
		["Terminal Lager → Wareneingang → einen Artikel mit MHD wählen (z. B. Butter).",
		 "Ins MHD nur Ziffern tippen: <code>300628</code>. Dann <code>310227</code> (gibt es nicht) und ein Datum von gestern.",
		 "Jeweils <b>Buchen</b> versuchen."],
		"Gültig: grün „= Freitag, 30.06.2028“. Ungültig, unvollständig, abgelaufen oder über 10 Jahre in der Zukunft: rot, "
		"Buchen geht nicht. Das MHD ist bei Artikeln mit MHD Pflicht.",
		"Dasselbe Feld gilt am Verpackungs-PC für „MHD kürzen“."))
	t.append("</div>")

	t.append("<div>")
	t.append(aufgabe(
		"N6", "Einwaage wie bei FOBIS",
		"Beim Herstellen sehen, was bestellt, erledigt und noch zu tun ist – und in Sack oder Eimer zählen.",
		["Terminal Backstube → Herstellen → ein Rezept wählen, Sollmenge bestätigen.",
		 "Ab Surface-Breite ist die Maske zweispaltig: <b>links</b> die Zutaten mit <b>Bestellt</b>, <b>Erledigt</b>, <b>ToDo</b> "
		 "und Lagerort, darunter die angetippte Zutat groß mit ihren Registrierungen; <b>rechts</b> Herkunft, Eingabe und Ziel.",
		 "Eine Zutat mit Gebinde scannen: Das Terminal fragt „Wie viele Sack?“ und zeigt darunter „= 50 kg“. Umschalten auf kg geht immer.",
		 "Dieselbe Zutat aus zwei Säcken scannen: Erledigt zählt zusammen."],
		"Erledigte Zeilen werden grün, außerhalb der Toleranz orange. Gebucht wird in kg.",
		"Gebinde kommen aus der <b>Maßeinheit-Umrechnung</b> am Artikel (z. B. Sack = 25), der Lagerort aus dem "
		"<b>Quelllager</b> der Stückliste oder dem <b>Standardlager</b> des Artikels. Fehlt beides, steht nichts da – "
		"dann bitte melden, welche Angaben fehlen."))
	t.append(bild("11_einwaage_gebinde.png", "Bild 12: Einwaage: links die Zutaten, rechts Herkunft und Eingabe; Honig gescannt, gefragt wird in Eimern.", "80%"))
	t.append("</div>")

	t.append("<div>")
	t.append(aufgabe(
		"N7", "Retour: Unbenutztes zurück ins Lager",
		"Was an die Linie ging, aber nicht verbraucht wurde, soll nicht als Linienrest verloren gehen.",
		["Terminal an der Linie → <b>An die Linie</b> → <b>Retour ins Lager</b>.",
		 "In der Liste stehen Rohstoffe und Packmittel des laufenden Auftrags mit Menge auf der Linie und „Zurück nach“.",
		 "Eine Zeile antippen, Menge eingeben (z. B. halber Sack), <b>Zurück ins Lager buchen</b>.",
		 "Danach <b>Auftrag beenden</b>: Liegt noch etwas auf der Linie, bietet das Terminal vorher die Retour an."],
		"Die Menge ist wieder im Lager, aus dem sie kam; nur der Rest wird beim Auftragsende als Linienrest ausgebucht. "
		"Silo-Ware geht nicht zurück.", ""))
	t.append(bild("15_retour.png", "Bild 13: Retour gebucht; in der Liste steht nur noch, was auf der Linie bleibt.", "70%"))
	t.append(aufgabe(
		"N8", "Hinweis vom Büro am Auftrag",
		"Eine wichtige Information erreicht die Linie und die Verpackung, ohne Zettel.",
		["Einen <b>Produktionsauftrag</b> öffnen, Feld <b>Hinweis an Linie und Verpackung</b>, z. B. „Mit Clip, neue Folie 2026“. Speichern.",
		 "Oder am <b>Kundenauftrag</b> das Feld <b>Hinweis an Produktion und Verpackung</b> füllen.",
		 "Am Terminal der Linie bzw. am Verpackungs-PC den Auftrag öffnen."],
		"Der Hinweis steht groß und gelb über dem Auftrag: an der Linie, am Verpackungs-PC, an der Packstation, beim "
		"Verpacken nach Kundenauftrag, in den Auftragslisten und in der Tagesübersicht.",
		"Gilt etwas immer (z. B. „mit Clip“ für einen Artikel), gehört es in die Spezifikation, nicht in den Hinweis."))
	t.append("</div>")

	t.append("<div>")
	t.append(bild("12_hinweis_linie.png", "Bild 14: Hinweis über dem laufenden Auftrag an der Linie, darunter der Knopf „Retour ins Lager“.", "64%"))
	t.append(aufgabe(
		"N9", "Tagesübersicht",
		"Auf einen Blick sehen, welche Aufträge heute laufen, offen oder fertig sind.",
		["An jedem Terminal → <b>Tagesübersicht</b>.",
		 "Je Linie: Status, Auftrag, Artikel mit Hinweis, Kunde, bestellt und gebucht mit Balken. Oben die Zähler offen und fertig.",
		 "Mit <b>Vortag</b> und <b>Folgetag</b> blättern."],
		"Heute stehen auch Aufträge von früheren Tagen dabei, die noch freigegeben sind oder laufen („vom …“), damit nichts liegen bleibt.", ""))
	t.append(bild("13_tagesuebersicht.png", "Bild 15: Tagesübersicht mit Status, Hinweis und Fortschritt.", "68%"))
	t.append("</div>")

	t.append("<div>")
	t.append(aufgabe(
		"N10", "Verladung nach Kundenauftrag",
		"Beim Verladen sehen, was bestellt, schon verladen und noch offen ist – wie in FOBIS.",
		["Terminal Versand → <b>Lieferung</b> → Kunde → einen <b>Kundenauftrag</b> wählen.",
		 "Links stehen alle Positionen mit Bestellt, Erledigt, ToDo und Status (Neu, Aktiv, Fertig). Eine Zeile antippen: "
		 "darunter steht sie groß, mit den Registrierungen.",
		 "Rechts unter <b>Herkunft</b> eine Palette, einen Versandkarton oder ein Kartonetikett scannen.",
		 "Mit ✕ eine Registrierung zurücknehmen. Zum Schluss <b>Lieferschein buchen</b>."],
		"ToDo sinkt mit jedem Scan; fertige Positionen werden grün. Ein Artikel, der nicht im Auftrag steht, wird abgelehnt.",
		"Ohne Kundenauftrag bleibt die einfache Lieferung wie bisher."))
	t.append(bild("16_verladung.png", "Bild 16: Verladung: links die Positionen des Auftrags, rechts Herkunft und Ziel.", "80%"))
	t.append(aufgabe(
		"N11", "Versandkarton mit eigener NVE",
		"Ein Karton bekommt eine eigene NVE, kann auf eine Palette mit NVE und einzeln geliefert werden.",
		["ERPNext → Paletten → <b>+ Neuer Versandkarton</b>, Kartons eines Loses laden, Etikett drucken.",
		 "Am Versandkarton <b>Auf eine Palette stellen</b> und die Paletten-NVE scannen.",
		 "Info-Scan auf die Palette: Sie zeigt ihre Versandkartons; ihr Etikett zeigt alles zusammen.",
		 "Einen einzelnen Karton liefern: in der Lieferung seine NVE scannen. Danach die ganze Palette liefern."],
		"Beim einzelnen Karton bleibt die Palette im Lager, der Karton steht nicht mehr auf ihr. Bei der ganzen Palette "
		"stehen im Lieferschein die NVEs der Kartons. Jedes Auf- und Abnehmen steht im Protokoll <b>Versandkarton Zuordnung</b>.",
		"DHL: Lieferung (DHL) → Auftrag → „Pakete als Versandkarton mit NVE“. Je Paket Stück und Gewicht; jede gescannte "
		"Sendungsnummer kommt an den nächsten Karton ohne Nummer."))
	t.append("</div>")

	t.append("<div>")
	t.append(aufgabe(
		"N12", "Netzbild der Rückverfolgung",
		"Auf einen Blick sehen, woraus ein Los besteht und wohin es ging – bis zum Kunden. Für Audit und Rückruf.",
		["Im Browser <code>/netz</code> öffnen oder in der Akte bei einem Los <b>Netzbild: woher und wohin</b>.",
		 "Ein Los, eine Charge oder eine Palette eingeben oder scannen, <b>Zeichnen</b>.",
		 "Einen Kasten anklicken: Der Weg wird blau, der Rest blass. An den Linien steht die Menge; rechts stehen "
		 "Wareneingang, Freigabe, Herstellung, Prüfungen und wo das Los jetzt liegt.",
		 "<b>Von hier aus zeichnen</b>, z. B. bei einem Rohstoff: Dann sieht man alle Kunden, die ihn bekommen haben.",
		 "Unten <b>Belege in der Kette</b>: Einkauf und Verkauf, als CSV oder zum Drucken."],
		"Das gewählte Los steht in der Mitte, links die Herkunft, rechts die Verwendung. Rot heißt gesperrt, orange heißt "
		"Prüfung mit Abweichung, gestrichelt heißt „möglicherweise enthalten“ (Silo). Packmittel sind gebündelt "
		"(„Packmittel (6)“), ein Klick klappt sie auf.",
		"Für den großen Bildschirm oder das Surface gedacht. Am Handy geht es, ist aber eng – dort ist die Akte besser."))
	t.append(bild("17_netzbild.png", "Bild 17: Netzbild. Ein Grundteig ist angeklickt: sein Weg ist hervorgehoben, rechts die Details.", "100%"))
	t.append("</div>")
	t.append("<div>")
	t.append(bild("18_netz_belege.png", "Bild 18: Packmittel aufgeklappt, darunter die Belege in der Kette (Einkauf und Verkauf).", "92%"))
	t.append("</div>")

	t.append("<div>")
	t.append(aufgabe(
		"N13", "Wareneingang zu einer Bestellung",
		"Beim Wareneingang festhalten, zu welcher Bestellung die Lieferung gehört.",
		["Im Büro eine Bestellung (Einkauf) anlegen und buchen, z. B. 100 kg Salz.",
		 "Terminal Lager → <b>Wareneingang</b> → den Artikel wählen.",
		 "Unter <b>Bestellung</b> stehen die offenen Bestellungen mit dem Artikel, mit offener Menge und Termin. "
		 "Gibt es nur eine, ist sie schon gewählt. Die Bestellung setzt den Lieferanten.",
		 "40 kg buchen. Den Wareneingang wieder öffnen: offen sind noch 60 kg.",
		 "Im Netzbild oder in der Akte das Los ansehen."],
		"Die Bestellung steht am Wareneingang, in der Akte und in der Belegliste des Netzbilds. Passt der Lieferant nicht "
		"zur Bestellung oder ist sie geschlossen, bucht das Terminal nicht.",
		"Die Bestellung ist nur ein Verweis. In ERPNext zählt sie den Eingang nicht als geliefert (das tut nur ein "
		"Eingangsbeleg). Ist alles da, die Bestellung im Büro schließen."))
	t.append(bild("19_wareneingang_bestellung.png", "Bild 19: Wareneingang mit Auswahl der offenen Bestellung.", "70%"))
	t.append("</div>")
	return t
