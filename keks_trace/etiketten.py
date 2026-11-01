"""Etiketten: Daten, ZPL-Layouts und Druck auf einen Etikettendrucker im Netz (TCP, Port 9100).

Welcher Drucker an welchem Terminal druckt, steht an der Terminal Station (Abschnitt „Etikettendrucker“).
Ist dort keiner eingetragen, druckt das Terminal wie bisher über den Browser (Seiten unter www/).
Die Browser-Seiten und die ZPL-Etiketten nehmen dieselben Daten (palette.etikett, karton, gebinde).
"""

import socket

import frappe
from frappe import _
from frappe.utils import cint, formatdate, now_datetime

from keks_trace import zpl

PORT = 9100
WARTEZEIT = 5  # Sekunden für Verbindung und Senden

# Etikettart → Feld an der Terminal Station
ARTEN = {
	"palette": "drucker_palette",
	"karton": "drucker_karton",
	"gebinde": "drucker_gebinde",
}
ARTNAMEN = {"palette": "Palettenetikett", "karton": "Kartonlabel", "gebinde": "Gebinde-Etikett"}
MAX_GEBINDE = 200
MAX_KARTON = 500


# ---------------------------------------------------------------------------
# Daten (auch für die Browser-Seiten)
# ---------------------------------------------------------------------------


def karton(station: str) -> dict:
	"""Kartonlabel der Packstation für den laufenden Auftrag."""
	from keks_trace import linienbuchung

	frappe.has_permission("Produktionsauftrag", "read", throw=True)
	d = linienbuchung.packstation(station)
	if not d.get("auftrag"):
		frappe.throw(_("An dieser Station läuft kein Produktionsauftrag."))
	beutel = next((e for e in d["einheiten"] if e["einheit"] == "Beutel"), None)
	gramm = round(beutel["faktor"] * 1000) if beutel else None
	inhalt = f"{d['beutel_je_karton']} x {gramm} g" if d.get("beutel_je_karton") and gramm else d["name"]
	return {**d, "inhalt": inhalt, "ean": d.get("ean_karton")}


def gebinde(codes) -> list[dict]:
	"""Gebinde- und Behälter-Etiketten (Code als QR, Artikel, Charge, MHD, Menge, Eingang)."""
	if isinstance(codes, str):
		codes = codes.split(",")
	codes = [c.strip() for c in (codes or []) if c and c.strip()][:MAX_GEBINDE]
	etiketten = []
	for code in codes:
		frappe.has_permission("Produkttraeger", "read", code, throw=True)
		t = frappe.get_doc("Produkttraeger", code)
		b = (
			frappe.db.get_value(
				"Batch", t.charge, ["item", "item_name", "expiry_date", "supplier"], as_dict=True
			)
			if t.charge
			else None
		) or frappe._dict()
		eingang = frappe.db.get_value("Traeger Belegung", {"traeger": code}, "von", order_by="creation asc")
		etiketten.append(
			{
				"code": code,
				"art": t.gebindeart or t.typ,
				"artikel": b.get("item"),
				"name": b.get("item_name"),
				"charge": t.charge,
				"mhd": formatdate(b.expiry_date) if b.get("expiry_date") else "",
				"lieferant": b.get("supplier") or "",
				"menge": t.menge,
				"einheit": frappe.get_cached_value("Item", b.item, "stock_uom") if b.get("item") else "",
				"eingang": formatdate(eingang) if eingang else "",
			}
		)
	return etiketten


def _zahl(wert) -> str:
	return ("%g" % (wert or 0)).replace(".", ",")


# ---------------------------------------------------------------------------
# ZPL-Layouts (gleiche Größe und Aufteilung wie die Browser-Etiketten)
# ---------------------------------------------------------------------------


def zpl_palette(e: dict, dpi: int = 203) -> str:
	"""Paletten-Etikett A6 hoch (105 x 148 mm): Absender, NVE, Inhalt; unten die Strichcodes, die SSCC zuletzt.

	Sortenrein mit GTIN: Inhalt in zwei GS1-128 ((02)+(37) und (15)+(10)), damit die Striche breit genug
	bleiben (0,5 mm). In einem Code wären es bei 203 dpi nur 0,25 mm.
	"""
	z = zpl.Etikett(105, 148, dpi)
	test = bool(e.get("test"))
	z.text(5, 4, 2.5, "ABSENDER")
	z.text(5, 7, 5, e.get("absender"), breite=56 if test else 95)
	if test:
		z.umgekehrt(63, 3, 37, 9.5, [(4.5, "TEST-NVE"), (2.6, "nicht versenden")])
	z.linie(5, 13.5, 95)
	z.text(5, 15, 2.5, "NVE / SSCC")
	z.text(5, 18.5, 6, e.get("nve"), breite=95)
	kopf = " · ".join(str(x) for x in (e.get("art"), e.get("datum"), e.get("kunde")) if x)
	z.text(5, 25.5, 3.2, kopf, breite=95)
	z.linie(5, 30, 95)
	spalten = ((5, 39, "ARTIKEL"), (45, 15, "LOS"), (61, 17, "MHD"), (79, 21, "ANZAHL"))
	for x, b, titel in spalten:
		z.text(x, 32, 2.3, titel, breite=b)
	y = 35.5
	positionen = e.get("positionen") or []
	for p in positionen[:8]:
		anzahl = f"{p.get('anzahl_text')} {p.get('einheit') or ''}"
		for (x, b, _t), wert in zip(
			spalten, (p.get("name"), p.get("los"), p.get("mhd") or "", anzahl), strict=True
		):
			z.text(x, y, 2.8, wert, breite=b - 1)
		y += 4.2
	if len(positionen) > 8:
		z.text(5, y, 2.8, f"… und {len(positionen) - 8} weitere Positionen", breite=95)
		y += 4.2
	if not positionen:
		z.text(5, y, 2.8, "(leer)")
		y += 4.2
	y += 0.8
	if e.get("bio"):
		oeko = f" · Öko-Kontrollstelle {e['oeko_nr']}" if e.get("oeko_nr") else ""
		z.text(5, y, 3.2, "BIO" + oeko, breite=95)
		y += 4.5
	z.text(5, y, 3.2, f"Gesamt: {e.get('kartons') or ''} · {_zahl(e.get('menge'))} kg", breite=95)
	z.linie(5, 84, 95)
	zeilen = e.get("inhalt_zeilen") or (
		[(e["inhalt_barcode"].replace("Ï", zpl.FNC1), e.get("inhalt_text"))]
		if e.get("inhalt_barcode")
		else []
	)
	for (roh, text), oben in zip(zeilen[:2], (85.5, 101), strict=False):
		z.gs1_128(oben, 11, roh, breite=97)
		z.text(4, oben + 11.5, 3, text, breite=97, mitte=True)
	z.gs1_128(117.5, 23, e["barcode_sscc"], breite=97)
	z.text(4, 141.5, 3.3, e.get("text_sscc"), breite=97, mitte=True)
	return z.zpl()


def zpl_karton(d: dict, anzahl: int = 1, dpi: int = 203) -> str:
	"""Kartonlabel 100 x 60 mm: Name, Inhalt, Los, MHD, Art.-Nr., EAN des Kartons."""
	z = zpl.Etikett(100, 60, dpi)
	z.text(4, 3, 5, d.get("name"), breite=92)
	z.text(4, 9.5, 3.5, " · ".join(str(x) for x in (d.get("inhalt"), d.get("kunde")) if x), breite=92)
	for x, titel, wert in (
		(4, "LOS", d.get("los_vorschau")),
		(36, "MHD", d.get("mhd_vorschau")),
		(68, "ART.-NR.", d.get("artikel")),
	):
		z.text(x, 15, 2.3, titel, breite=30)
		z.text(x, 18, 4.5, wert or "", breite=30)
	if d.get("ean"):
		z.ean(28, 20, d["ean"])
	return z.zpl(anzahl)


def zpl_gebinde(etiketten: list[dict], dpi: int = 203) -> str:
	"""Gebinde-Etikett 100 x 70 mm: QR mit dem Code links, Angaben rechts. Eins je Gebinde."""
	teile = []
	for e in etiketten:
		z = zpl.Etikett(100, 70, dpi)
		z.qr(3, 3, e["code"], groesse_mm=34, version=zpl.qr_version(e["code"]))
		z.text(3, 40, 4.5, e["code"], breite=36, mitte=True)
		x, b = 42, 55
		z.text(x, 4, 4.3, e.get("name") or "", breite=b, zeilen=2)
		z.text(
			x,
			14,
			3,
			" · ".join(str(v) for v in (f"Art.-Nr. {e.get('artikel') or ''}", e.get("art")) if v),
			breite=b,
		)
		y = 19
		for titel, wert in (
			("CHARGE (LIEFERANT)", e.get("charge") or ""),
			("MHD", e.get("mhd") or ""),
			(
				"MENGE · EINGANG",
				f"{_zahl(e.get('menge'))} {e.get('einheit') or ''} · {e.get('eingang') or ''}",
			),
		):
			z.text(x, y, 2.3, titel, breite=b)
			z.text(x, y + 3, 3.8, wert, breite=b)
			y += 9.5
		if e.get("lieferant"):
			z.text(x, y, 2.3, "LIEFERANT", breite=b)
			z.text(x, y + 3, 3.2, e["lieferant"], breite=b)
		teile.append(z.zpl())
	return "".join(teile)


# Zweiter Code auf dem Testetikett: wechselt die Zeichensätze (C → B → C) wie ein Paletteninhalt mit
# ungerader Anzahl und Buchstaben im Los. Gescannt muss genau TEST_GS1_TEXT herauskommen.
TEST_GS1 = "02" + "04032744000011" + "37" + "8" + zpl.FNC1 + "10" + "AB1234"
TEST_GS1_TEXT = "(02) 04032744000011 (37) 8 (10) AB1234"


def zpl_test(drucker: dict, dpi: int = 203) -> str:
	"""Testetikett 100 x 60 mm: Rahmen 90 x 50 mm zum Nachmessen der Auflösung, Umlaute, zwei Strichcodes.

	Code 1 (SSCC) nur Zeichensatz C. Code 2 mit Wechsel der Zeichensätze: beide scannen und vergleichen.
	"""
	from keks_trace.palette import pruefziffer

	z = zpl.Etikett(100, 60, dpi)
	z.rahmen(5, 5, 90, 50)
	z.text(9, 7.5, 4.5, "Testdruck " + str(drucker.get("name") or ""), breite=82)
	zeit = f"{formatdate(now_datetime())} {now_datetime().strftime('%H:%M')}"
	z.text(9, 13, 3, f"{dpi} dpi · {zeit} · Rahmen genau 90 x 50 mm", breite=82)
	z.text(9, 17, 3, "Umlaute: ÄÖÜ äöü ß", breite=82)
	muster = "34012345000000000"  # Muster-SSCC, keine echte Palette
	muster += str(pruefziffer(muster))
	z.gs1_128(21.5, 10, "00" + muster, breite=82)
	z.text(9, 32, 2.8, f"1: (00) {muster}", breite=82, mitte=True)
	z.gs1_128(36.5, 10, TEST_GS1, breite=82)
	z.text(9, 47, 2.8, "2: " + TEST_GS1_TEXT, breite=82, mitte=True)
	return z.zpl()


# ---------------------------------------------------------------------------
# Drucken
# ---------------------------------------------------------------------------


def drucker_der_station(station: str) -> dict:
	"""{art: Druckername} für die aktiven Drucker einer Station; leer heißt Browserdruck."""
	s = frappe.get_cached_doc("Terminal Station", station)
	ergebnis = {}
	for art, feld in ARTEN.items():
		name = s.get(feld)
		ergebnis[art] = name if name and frappe.db.get_value("Etikettendrucker", name, "aktiv") else None
	return ergebnis


def senden(drucker: str, daten: str, auch_inaktiv: bool = False) -> None:
	"""ZPL roh an den Drucker (TCP). Fehler als klare Meldung; nichts wird halb gemerkt."""
	d = frappe.db.get_value("Etikettendrucker", drucker, ["name", "adresse", "port", "aktiv"], as_dict=True)
	if not d:
		frappe.throw(_("Etikettendrucker {0} ist nicht eingerichtet.").format(drucker))
	if not d.aktiv and not auch_inaktiv:
		frappe.throw(_("Etikettendrucker {0} ist ausgeschaltet (nicht aktiv).").format(drucker))
	try:
		with socket.create_connection((d.adresse, cint(d.port) or PORT), timeout=WARTEZEIT) as s:
			s.sendall(daten.encode("utf-8"))
	except OSError:
		frappe.throw(
			_("Drucker {0} antwortet nicht. Ist er an und im Netz? Sonst im Browser drucken.").format(
				drucker
			),
			title=_("Drucker nicht erreichbar"),
		)


def drucken(station: str, art: str, nve=None, codes=None, anzahl=None) -> dict:
	"""Etikett der Art an den Drucker, der an der Station dafür eingetragen ist."""
	if art not in ARTEN:
		frappe.throw(_("Unbekannte Etikettart {0}.").format(art))
	drucker = drucker_der_station(station).get(art)
	if not drucker:
		frappe.throw(
			_("An der Station {0} ist kein Drucker für {1} eingetragen.").format(station, _(ARTNAMEN[art]))
		)
	dpi = cint(frappe.db.get_value("Etikettendrucker", drucker, "dpi")) or 203
	if art == "palette":
		from keks_trace import palette

		nr = palette.finde(nve or "")
		if not nr:
			frappe.throw(_("Palette nicht gefunden."), frappe.DoesNotExistError)
		frappe.has_permission("Palette", "read", nr, throw=True)
		daten, stueck = zpl_palette(palette.etikett(nr), dpi), 1
	elif art == "karton":
		stueck = max(1, min(cint(anzahl) or 1, MAX_KARTON))
		daten = zpl_karton(karton(station), stueck, dpi)
	else:
		liste = gebinde(codes)
		if not liste:
			frappe.throw(_("Kein Gebinde angegeben."))
		daten, stueck = zpl_gebinde(liste, dpi), len(liste)
	senden(drucker, daten)
	if art == "palette":
		palette.etikett_gedruckt(nr)  # Inhalt festhalten (Hinweis „neu drucken“ bei Änderung)
	return {"drucker": drucker, "art": art, "etiketten": stueck}


@frappe.whitelist()
def testdruck(drucker: str) -> dict:
	"""Testetikett aus der Druckermaske (auch bevor der Drucker aktiv geschaltet ist)."""
	frappe.has_permission("Etikettendrucker", "write", drucker, throw=True)
	d = frappe.db.get_value("Etikettendrucker", drucker, ["name", "dpi"], as_dict=True)
	if not d:
		frappe.throw(_("Etikettendrucker {0} ist nicht eingerichtet.").format(drucker))
	senden(drucker, zpl_test(d, cint(d.dpi) or 203), auch_inaktiv=True)
	return {"drucker": drucker}
