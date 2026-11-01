"""Einfache Fluss-Grafiken als SVG: Kästen in einem Raster, Pfeile dazwischen."""

from html import escape

NAVY = "#0b2340"
ROT = "#c8102e"
GRAU = "#5b6573"
HELL = "#eef2f7"
GELB = "#fff4d6"
GRUEN = "#e6f4ea"


def svg(knoten, kanten, spalten, zeilen, bw=150, bh=58, gx=62, gy=46, rand=12, notizen=()):
	"""knoten: {id: (spalte, zeile, titel, unter, farbe)}; kanten: (von, nach, text, art) art: '', 'gestrichelt', 'rot'."""
	breite = rand * 2 + spalten * bw + (spalten - 1) * gx
	hoehe = rand * 2 + zeilen * bh + (zeilen - 1) * gy + (24 if notizen else 0)
	pos = {}
	teile = [
		f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {breite} {hoehe}" width="100%" '
		f'font-family="Inter, Arial, sans-serif">',
		"<defs>"
		f'<marker id="p" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{NAVY}"/></marker>'
		f'<marker id="pr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{ROT}"/></marker>'
		"</defs>",
	]
	for k, (s, z, *_rest) in knoten.items():
		x = rand + s * (bw + gx)
		y = rand + z * (bh + gy)
		pos[k] = (x, y)
	# Kanten zuerst (unter den Kästen)
	for von, nach, text, art in kanten:
		(x1, y1), (x2, y2) = pos[von], pos[nach]
		farbe = ROT if art == "rot" else NAVY
		strich = ' stroke-dasharray="5 4"' if art in ("gestrichelt", "rot") else ""
		marke = "pr" if art == "rot" else "p"
		if y1 == y2:  # waagrecht
			if x2 > x1:
				a, b = (x1 + bw, y1 + bh / 2), (x2 - 2, y2 + bh / 2)
			else:
				a, b = (x1, y1 + bh / 2), (x2 + bw + 2, y2 + bh / 2)
			pfad = f"M{a[0]},{a[1]} L{b[0]},{b[1]}"
			tx, ty = (a[0] + b[0]) / 2, a[1] - 6
		elif x1 == x2:  # senkrecht
			if y2 > y1:
				a, b = (x1 + bw / 2, y1 + bh), (x2 + bw / 2, y2 - 2)
			else:
				a, b = (x1 + bw / 2, y1), (x2 + bw / 2, y2 + bh + 2)
			pfad = f"M{a[0]},{a[1]} L{b[0]},{b[1]}"
			tx, ty = a[0] + 6, (a[1] + b[1]) / 2 + 4
		else:  # über Eck: erst senkrecht aus der Unter-/Oberkante, dann waagrecht in die Seite
			if y2 > y1:
				a = (x1 + bw / 2, y1 + bh)
				mitte_y = y2 + bh / 2
			else:
				a = (x1 + bw / 2, y1)
				mitte_y = y2 + bh / 2
			b = (x2 + (bw + 2 if x2 < x1 else -2), mitte_y)
			pfad = f"M{a[0]},{a[1]} L{a[0]},{mitte_y} L{b[0]},{b[1]}"
			tx, ty = (a[0] + b[0]) / 2, mitte_y - 6
		teile.append(f'<path d="{pfad}" fill="none" stroke="{farbe}" stroke-width="1.6"{strich} marker-end="url(#{marke})"/>')
		if text:
			anker = "start" if x1 == x2 else "middle"
			teile.append(
				f'<text x="{tx}" y="{ty}" font-size="10.5" fill="{farbe}" text-anchor="{anker}" '
				f'paint-order="stroke" stroke="#fff" stroke-width="4">{escape(text)}</text>'
			)
	for k, (s, z, titel, unter, farbe) in knoten.items():
		x, y = pos[k]
		fuell = {"gelb": GELB, "gruen": GRUEN, "rot": "#fde8eb"}.get(farbe, HELL)
		rahmen = ROT if farbe == "rot" else NAVY
		teile.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="9" fill="{fuell}" stroke="{rahmen}" stroke-width="1.3"/>')
		teile.append(f'<text x="{x + bw / 2}" y="{y + 23}" font-size="13" font-weight="700" fill="{NAVY}" text-anchor="middle">{escape(titel)}</text>')
		for i, zeile in enumerate(unter.split("|") if unter else []):
			teile.append(f'<text x="{x + bw / 2}" y="{y + 40 + i * 12}" font-size="10" fill="{GRAU}" text-anchor="middle">{escape(zeile)}</text>')
	for i, (farbe, text) in enumerate(notizen):
		x = rand + i * 230
		y = hoehe - 14
		fuell = {"gelb": GELB, "gruen": GRUEN, "rot": "#fde8eb"}.get(farbe, HELL)
		teile.append(f'<rect x="{x}" y="{y - 10}" width="14" height="12" rx="3" fill="{fuell}" stroke="{NAVY}" stroke-width="1"/>')
		teile.append(f'<text x="{x + 20}" y="{y}" font-size="10.5" fill="{GRAU}">{escape(text)}</text>')
	teile.append("</svg>")
	return "\n".join(teile)


def warenfluss():
	k = {
		"we": (0, 0, "Wareneingang", "Terminal Lager|Charge = Lieferanten-Charge", "gelb"),
		"silo": (1, 0, "Silo / Gebinde", "Mehl, Zucker, Butter …|Code auf dem Gebinde", ""),
		"gt": (2, 0, "Grundteig", "Backstube / Kneter|in Kübel (Behälter)", ""),
		"tv": (3, 0, "Teig veredelt", "+ Zutaten|in Kübel", ""),
		"bw": (3, 1, "Backen", "Backware|eigene Charge", ""),
		"wl": (2, 1, "Ware lose", "+ Füllung, Schokolade|in Kiste, ggf. Freigabe", ""),
		"vp": (1, 1, "Verpacken", "Los + MHD|nach Kundenauftrag", ""),
		"pal": (0, 1, "Palette", "NVE-Etikett|Inhalt je Los", ""),
		"lief": (0, 2, "Lieferung", "Terminal Versand|Lieferschein", "gruen"),
		"rw": (3, 2, "Rework", "zurück in Grundteig oder|Teig: Regel, Allergene", "gelb"),
	}
	kanten = [
		("we", "silo", "", ""), ("silo", "gt", "", ""), ("gt", "tv", "", ""), ("tv", "bw", "", ""),
		("bw", "wl", "", ""), ("wl", "vp", "", ""), ("vp", "pal", "", ""), ("pal", "lief", "", ""),
		("bw", "rw", "Bruch, Teigrest", "gestrichelt"),
	]  # fmt: skip
	return svg(k, kanten, 4, 3, notizen=[("gelb", "hier wird gescannt bzw. geprüft"), ("gruen", "geht an den Kunden")])


def qs_fluss():
	k = {
		"we": (0, 0, "Wareneingang", "Artikel mit „Freigabe|vor Verwendung“", "gelb"),
		"gesp": (1, 0, "Charge gesperrt", "„Freigabe durch die QS|ausstehend“", "rot"),
		"frei": (2, 0, "QS gibt frei", "Charge → Freigeben|mit Bemerkung", "gruen"),
		"verw": (3, 0, "Verwendung", "Backstube, Linie|Verpackung", ""),
		"pr": (3, 1, "Prüfung am Terminal", "Metalldetektor, Brix,|Temperatur …", "gelb"),
		"abw": (2, 1, "Abweichung", "Lose seit letzter OK-|Prüfung gesperrt", "rot"),
		"tl": (1, 1, "QS Tagesliste", "FEFO, Einwaage,|Prüfung, Sperre", ""),
		"ds": (0, 1, "Durchsicht", "„Tag als durchgesehen|bestätigen“ (Nachweis)", "gruen"),
		"rv": (0, 2, "Rückverfolgung", "vorwärts / rückwärts|Mengenbilanz", ""),
		"rvt": (1, 2, "Rückverfolgungstest", "Protokoll für IFS 4.18|unveränderbar", "gruen"),
		"rr": (1, 3, "Rückruf", "alles vorwärts sperren|+ betroffene Kunden", "rot"),
	}
	kanten = [
		("we", "gesp", "", ""), ("gesp", "frei", "", ""), ("frei", "verw", "", ""), ("verw", "pr", "", ""),
		("pr", "abw", "nicht i. O.", "rot"), ("abw", "tl", "", ""), ("tl", "ds", "", ""),
		("rv", "rvt", "Test", "gestrichelt"), ("rv", "rr", "im Ernstfall", "rot"),
	]  # fmt: skip
	return svg(k, kanten, 4, 4, notizen=[("rot", "gesperrt / Abweichung"), ("gruen", "Nachweis oder freigegeben")])


def buero_fluss():
	k = {
		"auf": (0, 0, "Auftrag", "Kunde, Artikel,|Menge, Liefertermin", "gelb"),
		"plan": (1, 0, "Produktion", "Produktionsplan,|Terminals", ""),
		"pal": (2, 0, "Palette", "Los, MHD, NVE", ""),
		"ls": (3, 0, "Lieferschein", "Terminal Versand", ""),
		"re": (3, 1, "Ausgangsrechnung", "aus dem Lieferschein|Steuer 7 %", "gelb"),
		"er": (2, 1, "E-Rechnung", "XRechnung (XML) oder|ZUGFeRD (PDF)", ""),
		"dv": (1, 1, "DATEV-Export", "Aus- und Eingangs-|rechnungen → Steuerberater", "gruen"),
		"ko": (0, 2, "Kontrakt", "Rahmenauftrag|Menge, Preis fest", "gelb"),
		"be": (1, 2, "Bestellung", "Abruf gegen|den Kontrakt", ""),
		"wei": (2, 2, "Wareneingang", "Terminal Lager", ""),
		"ei": (3, 2, "Eingangsrechnung", "E-Rechnungs-Import|(XML / ZUGFeRD)", ""),
	}
	kanten = [
		("auf", "plan", "", ""), ("plan", "pal", "", ""), ("pal", "ls", "", ""), ("ls", "re", "", ""),
		("re", "er", "", ""), ("er", "dv", "", ""), ("ko", "be", "", ""), ("be", "wei", "", ""), ("wei", "ei", "", ""),
	]  # fmt: skip
	return svg(k, kanten, 4, 3, notizen=[("gelb", "legt das Büro an"), ("gruen", "geht nach draußen")])
