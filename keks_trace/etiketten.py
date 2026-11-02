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
	"""Gebinde- und Behälter-Etiketten (Code als Data Matrix, Artikel, Charge, MHD, Menge, Eingang)."""
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
# Rollengröße und Logo
# ---------------------------------------------------------------------------

# Kleinste Rolle (Breite, Höhe in mm), auf die das Layout einer Etikettart noch passt
MINDEST = {"palette": (100, 120), "karton": (90, 50), "gebinde": (95, 60)}
MINDEST_TEST = (80, 50)
GROESSE = {"palette": (105, 148), "karton": (100, 60), "gebinde": (100, 70)}  # wie die Browser-Etiketten


def zu_klein(art: str, breite, hoehe) -> str | None:
	"""Meldung, wenn eine Rolle für die Etikettart zu klein ist, sonst None."""
	mb, mh = MINDEST[art]
	if (breite or 0) + 1e-6 < mb or (hoehe or 0) + 1e-6 < mh:
		return _("{0} braucht eine Rolle von mindestens {1} x {2} mm.").format(_(ARTNAMEN[art]), mb, mh)
	return None


def logo(dpi: int, hoehe_mm: float) -> zpl.Grafik | None:
	"""Logo aus den Einstellungen als Druckergrafik (zwischengespeichert). Fehlt es, None."""
	from keks_trace.utils import einstellung

	url = einstellung("etikett_logo")
	if not url:
		return None
	punkte = round(hoehe_mm * (8 if cint(dpi) == 203 else 12))
	schluessel = f"kt_etikett_logo:{url}:{punkte}"
	gemerkt = frappe.cache.get_value(schluessel)
	if gemerkt:
		return zpl.Grafik(*gemerkt)
	try:
		datei = frappe.get_doc("File", {"file_url": url}).get_full_path()
		g = zpl.bild(datei, punkte)
	except Exception:
		# Ohne Logo drucken ist besser als gar nicht drucken; der Fehler steht im Fehlerprotokoll
		frappe.log_error(title="Etikett: Logo nicht lesbar")
		return None
	frappe.cache.set_value(schluessel, (g.hex, g.je_zeile, g.breite, g.hoehe), expires_in_sec=24 * 3600)
	return g


def _mm(z: zpl.Etikett, punkte: int) -> float:
	return punkte / z.dpmm


# ---------------------------------------------------------------------------
# ZPL-Layouts: Kopf oben, Strichcodes unten am Rand, die Mitte wächst mit der Rolle
# ---------------------------------------------------------------------------


def zpl_palette(e: dict, dpi: int = 203, breite=105, hoehe=148, logo_grafik=None) -> str:
	"""Paletten-Etikett (Standard A6 hoch): Logo, Absender, NVE, Inhalt; unten die Strichcodes, SSCC zuletzt.

	Sortenrein mit GTIN: Inhalt in zwei GS1-128 ((02)+(37) und (15)+(10)), damit die Striche breit genug
	bleiben (0,5 mm). In einem Code wären es bei 203 dpi nur 0,25 mm.
	"""
	z = zpl.Etikett(breite, hoehe, dpi)
	w = breite - 10  # nutzbare Breite
	unten = hoehe - 148  # alles ab der Linie über den Strichcodes wandert mit der Höhe
	test = bool(e.get("test"))
	x = 5
	if logo_grafik:
		z.grafik(5, 3, logo_grafik)
		x = 5 + _mm(z, logo_grafik.breite) + 3
	rechts = breite - 5 - (38 if test else 0)
	z.text(x, 4, 2.5, "ABSENDER", breite=rechts - x)
	z.text(x, 7, 5, e.get("absender"), breite=rechts - x)
	if test:
		z.umgekehrt(breite - 42, 3, 37, 9.5, [(4.5, "TEST-NVE"), (2.6, "nicht versenden")])
	z.linie(5, 13.5, w)
	z.text(5, 15, 2.5, "NVE / SSCC")
	z.text(5, 18.5, 6, e.get("nve"), breite=w)
	kopf = " · ".join(str(v) for v in (e.get("art"), e.get("datum"), e.get("kunde")) if v)
	z.text(5, 25.5, 3.2, kopf, breite=w)
	z.linie(5, 30, w)
	spalten, sx = [], 5.0
	for anteil, titel in ((40, "ARTIKEL"), (16, "LOS"), (18, "MHD"), (21, "ANZAHL")):
		b = w * anteil / 95
		spalten.append((sx, b, titel))
		sx += b
	for sx, b, titel in spalten:
		z.text(sx, 32, 2.3, titel, breite=b)
	positionen = e.get("positionen") or []
	fuss = 0.8 + 4.5 + (4.5 if e.get("bio") else 0) + 1
	platz = max(1, int((84 + unten - 35.5 - fuss) / 4.2))  # so viele Zeilen passen
	zeigen = positionen if len(positionen) <= platz else positionen[: platz - 1]
	y = 35.5
	for p in zeigen:
		anzahl = f"{p.get('anzahl_text')} {p.get('einheit') or ''}"
		for (sx, b, _t), wert in zip(
			spalten, (p.get("name"), p.get("los"), p.get("mhd") or "", anzahl), strict=True
		):
			z.text(sx, y, 2.8, wert, breite=b - 1)
		y += 4.2
	if len(zeigen) < len(positionen):
		z.text(5, y, 2.8, f"… und {len(positionen) - len(zeigen)} weitere Positionen", breite=w)
		y += 4.2
	if not positionen:
		z.text(5, y, 2.8, "(leer)")
		y += 4.2
	y += 0.8
	if e.get("bio"):
		oeko = f" · Öko-Kontrollstelle {e['oeko_nr']}" if e.get("oeko_nr") else ""
		z.text(5, y, 3.2, "BIO" + oeko, breite=w)
		y += 4.5
	z.text(5, y, 3.2, f"Gesamt: {e.get('kartons') or ''} · {_zahl(e.get('menge'))} kg", breite=w)
	z.linie(5, 84 + unten, w)
	zeilen = e.get("inhalt_zeilen") or (
		[(e["inhalt_barcode"].replace("Ï", zpl.FNC1), e.get("inhalt_text"))]
		if e.get("inhalt_barcode")
		else []
	)
	for (roh, text), oben in zip(zeilen[:2], (85.5 + unten, 101 + unten), strict=False):
		z.gs1_128(oben, 11, roh, breite=breite - 2)
		z.text(4, oben + 11.5, 3, text, breite=w + 2, mitte=True)
	z.gs1_128(117.5 + unten, 23, e["barcode_sscc"], breite=breite - 2)
	z.text(4, 141.5 + unten, 3.3, e.get("text_sscc"), breite=w + 2, mitte=True)
	return z.zpl()


def zpl_karton(d: dict, anzahl: int = 1, dpi: int = 203, breite=100, hoehe=60, logo_grafik=None) -> str:
	"""Kartonlabel (Standard 100 x 60 mm): Name, Inhalt, Los, MHD, Art.-Nr., Logo oben rechts, EAN unten."""
	z = zpl.Etikett(breite, hoehe, dpi)
	w = breite - 8
	rechts = 0.0
	if logo_grafik:
		rechts = _mm(z, logo_grafik.breite) + 3
		z.grafik(breite - 4 - _mm(z, logo_grafik.breite), 3, logo_grafik)
	z.text(4, 3, 5, d.get("name"), breite=w - rechts)
	z.text(4, 9.5, 3.5, " · ".join(str(x) for x in (d.get("inhalt"), d.get("kunde")) if x), breite=w - rechts)
	spalte = w / 3
	for i, (titel, wert) in enumerate(
		(("LOS", d.get("los_vorschau")), ("MHD", d.get("mhd_vorschau")), ("ART.-NR.", d.get("artikel")))
	):
		z.text(4 + i * spalte, 15, 2.3, titel, breite=spalte - 2)
		z.text(4 + i * spalte, 18, 4.5, wert or "", breite=spalte - 2)
	if d.get("ean"):
		oben = max(24, hoehe - 32)
		z.ean(oben, min(20, hoehe - oben - 8), d["ean"])
	return z.zpl(anzahl)


def zpl_gebinde(etiketten: list[dict], dpi: int = 203, breite=100, hoehe=70) -> str:
	"""Gebinde-Etikett (Standard 100 x 70 mm): Data Matrix mit dem Code links, Angaben rechts. Eins je Gebinde.

	Ohne Logo: das Etikett bleibt im Haus.
	"""
	teile = []
	for e in etiketten:
		z = zpl.Etikett(breite, hoehe, dpi)
		# Data Matrix mit der Nummer (wie am Kübel); intern genügt die Nummer, alles andere holt das System
		z.datamatrix(5, 5, e["code"], groesse_mm=30)
		z.text(3, 40, 4.5, e["code"], breite=36, mitte=True)
		x, b = 42, breite - 45
		z.text(x, 4, 4.3, e.get("name") or "", breite=b, zeilen=2)
		art = " · ".join(str(v) for v in (f"Art.-Nr. {e.get('artikel') or ''}", e.get("art")) if v)
		z.text(x, 14, 3, art, breite=b)
		y = 19
		menge = f"{_zahl(e.get('menge'))} {e.get('einheit') or ''} · {e.get('eingang') or ''}"
		for titel, wert in (
			("CHARGE (LIEFERANT)", e.get("charge") or ""),
			("MHD", e.get("mhd") or ""),
			("MENGE · EINGANG", menge),
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


def zpl_test(drucker: dict, dpi: int = 203, breite=100, hoehe=60, logo_grafik=None) -> str:
	"""Testetikett in Rollengröße: Rahmen 5 mm vom Rand (Maß steht darauf), Logo, Umlaute, zwei Strichcodes.

	Code 1 (SSCC) nur Zeichensatz C. Code 2 mit Wechsel der Zeichensätze: beide scannen und vergleichen.
	"""
	from keks_trace.palette import pruefziffer

	z = zpl.Etikett(breite, hoehe, dpi)
	rb, rh = breite - 10, hoehe - 10
	z.rahmen(5, 5, rb, rh)
	w = rb - 8
	rechts = 0.0
	if logo_grafik:
		rechts = _mm(z, logo_grafik.breite) + 2
		z.grafik(breite - 9 - _mm(z, logo_grafik.breite), 7, logo_grafik)
	z.text(9, 7.5, 4.5, "Testdruck " + str(drucker.get("name") or ""), breite=w - rechts)
	zeit = f"{formatdate(now_datetime())} {now_datetime().strftime('%H:%M')}"
	z.text(9, 13, 3, f"{dpi} dpi · {zeit}", breite=w - rechts)
	z.text(9, 17, 3, f"Rahmen genau {_zahl(rb)} x {_zahl(rh)} mm · ÄÖÜ äöü ß", breite=w - rechts)
	muster = "34012345000000000"  # Muster-SSCC, keine echte Palette
	muster += str(pruefziffer(muster))
	block = (hoehe - 5 - 22) / 2  # zwei gleich hohe Blöcke unter dem Text
	for i, (daten, text) in enumerate(
		(("00" + muster, f"1: (00) {muster}"), (TEST_GS1, "2: " + TEST_GS1_TEXT))
	):
		oben = 22 + i * block
		z.gs1_128(oben, max(5, block - 5), daten, breite=w)
		z.text(9, oben + block - 4.5, 2.8, text, breite=w, mitte=True)
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


def _rolle(drucker: str) -> frappe._dict:
	d = frappe.db.get_value(
		"Etikettendrucker", drucker, ["name", "dpi", "etikett_breite", "etikett_hoehe"], as_dict=True
	)
	if not d:
		frappe.throw(_("Etikettendrucker {0} ist nicht eingerichtet.").format(drucker))
	d.dpi = cint(d.dpi) or 203
	return d


def _bezug(station: str, art: str, nve=None, codes=None) -> dict:
	"""Was gedruckt wird: Palette (geprüft), Gebinde-Liste oder laufender Auftrag der Packstation."""
	if art == "palette":
		from keks_trace import palette

		nr = palette.finde(nve or "")
		if not nr:
			frappe.throw(_("Palette nicht gefunden."), frappe.DoesNotExistError)
		frappe.has_permission("Palette", "read", nr, throw=True)
		return {"palette": nr}
	if art == "gebinde":
		liste = gebinde(codes)
		if not liste:
			frappe.throw(_("Kein Gebinde angegeben."))
		return {"liste": liste, "traeger": [e["code"] for e in liste]}
	return {"karton": karton(station)}


def _grund(art, bezug, grund, geprueft) -> tuple[str | None, str | None]:
	from keks_trace import druckprotokoll

	g = druckprotokoll.grund_bestimmen(art, grund, bezug.get("palette"), bezug.get("traeger", ()))
	bemerkung = druckprotokoll.geprueft_text(geprueft, bezug.get("palette")) if g == "fehlt" else None
	return g, bemerkung


def _grund_noetig(art) -> dict:
	from keks_trace import druckprotokoll

	return {
		"grund_noetig": True,
		"art": art,
		"gruende": [{"wert": k, "text": druckprotokoll.GRUENDE[k]} for k in druckprotokoll.NACHDRUCK],
	}


def vormerken(station: str, art: str, nve=None, codes=None, anzahl=None, grund=None, geprueft=None) -> dict:
	"""Browserdruck (kein Netzwerkdrucker): Grund prüfen und den Druck protokollieren, bevor die Seite öffnet."""
	from keks_trace import druckprotokoll

	if art not in ARTEN:
		frappe.throw(_("Unbekannte Etikettart {0}.").format(art))
	bezug = _bezug(station, art, nve, codes)
	g, bemerkung = _grund(art, bezug, grund, geprueft)
	if not g:
		return _grund_noetig(art)
	stueck = max(1, min(cint(anzahl) or 1, MAX_KARTON)) if art == "karton" else 1
	druckprotokoll.buchen(
		art, g, "Browser", station, palette=bezug.get("palette"), traeger=bezug.get("traeger", ()),
		auftrag=(bezug.get("karton") or {}).get("auftrag"), anzahl=stueck, bemerkung=bemerkung,
	)  # fmt: skip
	return {"ok": True, "grund": druckprotokoll.GRUENDE[g]}


def drucken(station: str, art: str, nve=None, codes=None, anzahl=None, grund=None, geprueft=None) -> dict:
	"""Etikett der Art an den Drucker, der an der Station dafür eingetragen ist, in dessen Rollengröße.

	Ein Nachdruck ohne Anlass braucht einen Grund (druckprotokoll.py): fehlt er, wird nicht gedruckt und die
	Antwort sagt dem Terminal, dass es fragen soll."""
	from keks_trace import druckprotokoll

	if art not in ARTEN:
		frappe.throw(_("Unbekannte Etikettart {0}.").format(art))
	drucker = drucker_der_station(station).get(art)
	if not drucker:
		frappe.throw(
			_("An der Station {0} ist kein Drucker für {1} eingetragen.").format(station, _(ARTNAMEN[art]))
		)
	r = _rolle(drucker)
	if fehler := zu_klein(art, r.etikett_breite, r.etikett_hoehe):
		frappe.throw(
			_("{0} Drucker {1} hat {2} x {3} mm.").format(
				fehler, drucker, _zahl(r.etikett_breite), _zahl(r.etikett_hoehe)
			)
		)
	masse = {"dpi": r.dpi, "breite": r.etikett_breite, "hoehe": r.etikett_hoehe}
	bezug = _bezug(station, art, nve, codes)
	g, bemerkung = _grund(art, bezug, grund, geprueft)
	if not g:
		return _grund_noetig(art)
	nr = bezug.get("palette")
	if art == "palette":
		from keks_trace import palette

		daten, stueck = zpl_palette(palette.etikett(nr), logo_grafik=logo(r.dpi, 10), **masse), 1
	elif art == "karton":
		stueck = max(1, min(cint(anzahl) or 1, MAX_KARTON))
		daten = zpl_karton(bezug["karton"], stueck, logo_grafik=logo(r.dpi, 12), **masse)
	else:
		daten, stueck = zpl_gebinde(bezug["liste"], **masse), len(bezug["liste"])
	senden(drucker, daten)
	druckprotokoll.buchen(
		art, g, drucker, station, palette=nr, traeger=bezug.get("traeger", ()),
		auftrag=(bezug.get("karton") or {}).get("auftrag"), anzahl=stueck, bemerkung=bemerkung,
	)  # fmt: skip
	if art == "palette":
		palette.etikett_gedruckt(nr)  # Inhalt festhalten (Hinweis „neu drucken“ bei Änderung)
	return {"drucker": drucker, "art": art, "etiketten": stueck, "grund": druckprotokoll.GRUENDE[g]}


@frappe.whitelist()
def testdruck(drucker: str) -> dict:
	"""Testetikett aus der Druckermaske (auch bevor der Drucker aktiv geschaltet ist)."""
	frappe.has_permission("Etikettendrucker", "write", drucker, throw=True)
	r = _rolle(drucker)
	mb, mh = MINDEST_TEST
	if (r.etikett_breite or 0) < mb or (r.etikett_hoehe or 0) < mh:
		frappe.throw(_("Der Testdruck braucht eine Rolle von mindestens {0} x {1} mm.").format(mb, mh))
	daten = zpl_test(r, r.dpi, r.etikett_breite, r.etikett_hoehe, logo_grafik=logo(r.dpi, 10))
	senden(drucker, daten, auch_inaktiv=True)
	from keks_trace import druckprotokoll

	druckprotokoll.buchen("test", "test", drucker)
	return {"drucker": drucker}
