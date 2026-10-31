"""Produktionsplanung: Kundenaufträge auf Produktionstage der Linie verteilen.

Leistung: Jeder Fertigware-Artikel hat je Linienabschnitt eine Geschwindigkeit (Füllen, Glasieren,
Trocknen, Schokoladenkühlung, manuelles Band, Verpackungsanlagen wie InoTec, Thürlings, Carina).
Der langsamste Abschnitt (Engpass) bestimmt das Tempo. Prozesse gelten immer, von den
Verpackungsanlagen nur die, die der Auftrag nutzt.

Planung: Offene Kundenauftragspositionen (Fertigware) nach Liefertermin werden in Stunden auf die
Arbeitstage der Linie verteilt (Laufzeit pro Tag, Umrüstzeit bei Produktwechsel). Es entstehen
Produktionsaufträge mit Status „Geplant“. Die Produktionsleitung gibt einen Tag frei; erst dann
sieht ihn die Linie.

Grundteig-Bedarf: Rezepturen der geplanten Aufträge bis zur Stufe Grundteig/Teig veredelt
aufgelöst, gegen den Bestand in Kübeln.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, now_datetime, nowdate

from keks_trace import palette

OFFEN = ("Geplant", "Freigegeben", "Läuft")
MINDESTLAUF_H = 0.5  # kürzer wird ein Auftrag am Tagesende nicht angefangen


# ---------------------------------------------------------------------------
# Leistung
# ---------------------------------------------------------------------------


def einheit_text(artikel) -> str:
	"""Lagereinheit des Artikels für Texte: kg bei Teig und Lebkuchen, Stk bei Herzen."""
	uom = frappe.get_cached_value("Item", artikel, "stock_uom")
	return {"Kg": "kg", "Nos": "Stk"}.get(uom, uom)


def _kg_h(artikel, zeile) -> float:
	"""Leistung umgerechnet in Lagereinheit je Stunde (kg/h bei Lebkuchen, Stück/h bei Herzen)."""
	if zeile.einheit == "Beutel/min":
		return flt(zeile.leistung) * 60 * palette.faktor(artikel, "Beutel")
	if zeile.einheit == "Karton/h":
		return flt(zeile.leistung) * palette.faktor(artikel, "Karton")
	if zeile.einheit == "Stück/min":
		return flt(zeile.leistung) * 60 * palette.faktor(artikel, "Nos")
	if zeile.einheit == "Stück/h":
		return flt(zeile.leistung) * palette.faktor(artikel, "Nos")
	return flt(zeile.leistung)


def leistung(artikel: str, anlage: str | None = None) -> tuple[float, str | None, str | None]:
	"""(Leistung in Lagereinheit je Stunde, Engpass, gewählte Verpackungsanlage).

	Ohne Anlage: die schnellste mögliche."""
	zeilen = frappe.get_all(
		"Artikel Linienleistung",
		filters={"parent": artikel, "parenttype": "Item"},
		fields=["abschnitt", "leistung", "einheit"],
	)
	return _engpass(artikel, [frappe._dict(z) for z in zeilen], anlage)


def _engpass(artikel, zeilen, anlage=None):
	art = {a.name: a.art for a in frappe.get_all("Linienabschnitt", fields=["name", "art"])}
	prozesse = [
		(z.abschnitt, _kg_h(artikel, z)) for z in zeilen if art.get(z.abschnitt) != "Verpackungsanlage"
	]
	anlagen = [
		(z.abschnitt, _kg_h(artikel, z)) for z in zeilen if art.get(z.abschnitt) == "Verpackungsanlage"
	]
	if anlage:
		gewaehlt = [a for a in anlagen if a[0] == anlage]
		if anlagen and not gewaehlt:
			frappe.throw(
				_("{0} wird nicht auf {1} verpackt (keine Leistung eingetragen).").format(artikel, anlage)
			)
	else:
		gewaehlt = sorted(anlagen, key=lambda a: -a[1])[:1]
	alle = [x for x in prozesse + gewaehlt if x[1] > 0]
	if not alle:
		return 0.0, None, None
	name, kg = min(alle, key=lambda x: x[1])
	return flt(kg, 3), name, gewaehlt[0][0] if gewaehlt else None


def item_validate(doc, method=None):
	"""Leistung je Abschnitt in Lagereinheit je Stunde umrechnen, Engpass am Artikel speichern."""
	if not doc.get("kt_linienleistung"):
		return
	for z in doc.kt_linienleistung:
		z.kg_h = flt(_kg_h(doc.name, z), 3)
	kg, name, anlage = _engpass(doc.name, doc.kt_linienleistung)
	doc.kt_leistung_kg_h = kg
	doc.kt_engpass = (
		f"{name} ({flt(kg, 1):g} {einheit_text(doc.name)}/h)"
		+ (f", Verpackung {anlage}" if anlage and anlage != name else "")
		if name
		else None
	)


# ---------------------------------------------------------------------------
# Planung
# ---------------------------------------------------------------------------


def _geplant_kg(so_detail) -> float:
	return flt(
		frappe.db.sql(
			"""select coalesce(sum(menge_kg), 0) from `tabProduktionsauftrag`
			where kt_so_detail = %s and status != 'Abgebrochen'""",
			so_detail,
		)[0][0]
	)


def offene_positionen() -> list[dict]:
	"""Kundenauftragspositionen (Fertigware), für die noch nicht genug geplant ist, nach Liefertermin."""
	zeilen = frappe.db.sql(
		"""
		select soi.name as so_detail, so.name as kundenauftrag, so.customer, soi.item_code,
			soi.stock_qty, soi.delivered_qty * soi.conversion_factor as geliefert,
			coalesce(soi.delivery_date, so.delivery_date) as liefertermin
		from `tabSales Order Item` soi
		join `tabSales Order` so on so.name = soi.parent
		join `tabItem` i on i.name = soi.item_code
		where so.docstatus = 1 and so.status not in ('Closed', 'Completed', 'On Hold')
			and i.kt_chargen_stufe = 'Fertigware'
		order by liefertermin, so.name, soi.idx
		""",
		as_dict=True,
	)
	ergebnis = []
	for z in zeilen:
		offen = flt(z.stock_qty) - flt(z.geliefert) - _geplant_kg(z.so_detail)
		if offen > 0.001:
			ergebnis.append({**z, "offen_kg": flt(offen, 3)})
	return ergebnis


def _belegt(linie, datum) -> tuple[float, str | None]:
	"""Schon verplante Stunden an einem Tag (inkl. Umrüstzeiten) und das letzte Produkt."""
	auftraege = frappe.get_all(
		"Produktionsauftrag",
		filters={"linie": linie, "datum": datum, "status": ["!=", "Abgebrochen"]},
		fields=["artikel", "dauer_stunden"],
		order_by="reihenfolge, creation",
	)
	umruesten = flt(frappe.get_cached_value("Linie", linie, "umruestzeit_minuten")) / 60
	stunden, letzt = 0.0, None
	for a in auftraege:
		if letzt and a.artikel != letzt:
			stunden += umruesten
		stunden += flt(a.dauer_stunden)
		letzt = a.artikel
	return stunden, letzt


@frappe.whitelist()
def vorschlag(linie: str, ab: str | None = None, bis_tage: int = 120) -> dict:
	"""Offene Kundenaufträge als Produktionsaufträge (Geplant) auf die Arbeitstage verteilen."""
	frappe.has_permission("Produktionsauftrag", "create", throw=True)
	l = frappe.get_doc("Linie", linie)
	start = getdate(ab or add_days(nowdate(), 1))
	umruesten = flt(l.umruestzeit_minuten) / 60
	angelegt, ohne_leistung = [], []
	ohne_linie = []
	for pos in offene_positionen():
		eigene = frappe.get_cached_value("Item", pos["item_code"], "kt_linie")
		if eigene != linie:
			if not eigene:
				ohne_linie.append(pos["item_code"])
			continue  # gehört zu einer anderen Linie
		kg_h, _engpass_name, anlage = leistung(pos["item_code"])
		if kg_h <= 0:
			ohne_leistung.append(pos["item_code"])
			continue
		offen = pos["offen_kg"]
		tag = start
		for _i in range(int(bis_tage) * 2):
			if offen <= 0.001:
				break
			if not l.ist_arbeitstag(tag):
				tag = add_days(tag, 1)
				continue
			belegt, letzt = _belegt(linie, tag)
			frei = (
				flt(l.laufzeit_stunden) - belegt - (umruesten if letzt and letzt != pos["item_code"] else 0)
			)
			if frei * kg_h < 1 or (frei < MINDESTLAUF_H and frei * kg_h < offen):
				# kein Rest-Schnipsel am Tagesende: lieber am nächsten Tag am Stück
				tag = add_days(tag, 1)
				continue
			kg = min(offen, frei * kg_h)
			# Ganze Kartons planen, wenn der Artikel Kartons kennt
			karton = (
				palette.faktor(pos["item_code"], "Karton") if _hat_einheit(pos["item_code"], "Karton") else 0
			)
			if karton:
				anzahl = max(1, int(kg / karton + 1e-6)) if kg < offen else -(-offen // karton)
				einheit, menge = "Karton", anzahl
				kg = anzahl * karton
			else:
				einheit, menge = frappe.get_cached_value("Item", pos["item_code"], "stock_uom"), flt(kg, 3)
			gleich = frappe.db.get_value(
				"Produktionsauftrag",
				{
					"linie": linie,
					"datum": tag,
					"kt_so_detail": pos["so_detail"],
					"status": "Geplant",
					"einheit": einheit,
				},
			)
			if gleich:
				# gleiche Auftragsposition am selben Tag: zusammenfassen statt zweiter Auftrag
				pa = frappe.get_doc("Produktionsauftrag", gleich)
				pa.menge = flt(pa.menge) + menge
				pa.save()
				offen -= kg
				continue
			pa = frappe.get_doc(
				{
					"doctype": "Produktionsauftrag",
					"linie": linie,
					"datum": tag,
					"reihenfolge": len(frappe.get_all("Produktionsauftrag", {"linie": linie, "datum": tag}))
					+ 1,
					"artikel": pos["item_code"],
					"menge": menge,
					"einheit": einheit,
					"verpackungsanlage": anlage,
					"kundenauftrag": pos["kundenauftrag"],
					"kt_so_detail": pos["so_detail"],
				}
			).insert()
			angelegt.append(pa.name)
			offen -= kg
	return {
		"angelegt": len(angelegt),
		"auftraege": angelegt,
		"ohne_leistung": sorted(set(ohne_leistung)),
		"ohne_linie": sorted(set(ohne_linie)),
	}


def _hat_einheit(artikel, uom) -> bool:
	return bool(frappe.db.exists("UOM Conversion Detail", {"parent": artikel, "uom": uom}))


@frappe.whitelist()
def tag_freigeben(linie: str, datum) -> dict:
	"""Tagesplan freigeben: alle geplanten Aufträge des Tages erscheinen an den Terminals."""
	frappe.has_permission("Produktionsauftrag", "write", throw=True)
	namen = frappe.get_all(
		"Produktionsauftrag", filters={"linie": linie, "datum": datum, "status": "Geplant"}, pluck="name"
	)
	for n in namen:
		frappe.db.set_value(
			"Produktionsauftrag",
			n,
			{
				"status": "Freigegeben",
				"freigegeben_von": frappe.session.user,
				"freigegeben_am": now_datetime(),
			},
		)
	return {"freigegeben": len(namen)}


@frappe.whitelist()
def plan_verwerfen(linie: str, ab: str | None = None) -> dict:
	"""Nur noch nicht freigegebene Aufträge ab einem Tag löschen (z. B. vor einer Neuplanung)."""
	frappe.has_permission("Produktionsauftrag", "delete", throw=True)
	namen = frappe.get_all(
		"Produktionsauftrag",
		filters={"linie": linie, "status": "Geplant", "datum": [">=", ab or nowdate()]},
		pluck="name",
	)
	for n in namen:
		frappe.delete_doc("Produktionsauftrag", n)
	return {"geloescht": len(namen)}


# ---------------------------------------------------------------------------
# Teigbedarf
# ---------------------------------------------------------------------------

VORLAUF_STUFEN = ("Grundteig", "Teig veredelt")


def aufloesen(artikel: str, kg: float, bis_stufen=VORLAUF_STUFEN, tiefe=0) -> dict:
	"""Rezeptur bis zur ersten Vorlauf-Stufe auflösen: {Artikel: kg}."""
	ergebnis = defaultdict(float)
	if tiefe > 8:
		return ergebnis
	bom = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})
	if not bom:
		return ergebnis
	menge = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1
	for z in frappe.get_all("BOM Item", {"parent": bom}, ["item_code", "stock_qty"]):
		bedarf = kg * flt(z.stock_qty) / menge
		stufe = frappe.get_cached_value("Item", z.item_code, "kt_chargen_stufe")
		if stufe in bis_stufen:
			ergebnis[z.item_code] += bedarf
		elif stufe in ("Backware", "Ware lose", "Teig veredelt"):
			for k, v in aufloesen(z.item_code, bedarf, bis_stufen, tiefe + 1).items():
				ergebnis[k] += v
	return ergebnis


def _bestand(artikel) -> float:
	return flt(
		frappe.db.sql(
			"""select coalesce(sum(b.batch_qty), 0) from `tabBatch` b
			where b.item = %s and ifnull(b.kt_status, '') != 'Gesperrt'
				and (b.expiry_date is null or b.expiry_date >= %s)""",
			(artikel, nowdate()),
		)[0][0]
	)


@frappe.whitelist()
def teigbedarf(linie: str, tage: int = 10) -> list[dict]:
	"""Teigbedarf der geplanten/freigegebenen Aufträge der nächsten Tage gegen den Bestand.

	Erst veredelter Teig; nur was davon fehlt, braucht neuen Grundteig.
	"""
	bis = add_days(nowdate(), int(tage))
	bedarf, erster = defaultdict(float), {}
	for pa in frappe.get_all(
		"Produktionsauftrag",
		filters={"linie": linie, "status": ["in", OFFEN], "datum": ["<=", bis]},
		fields=["artikel", "menge_kg", "gebucht_kg", "datum"],
		order_by="datum",
	):
		rest = max(flt(pa.menge_kg) - flt(pa.gebucht_kg), 0)
		for k, v in aufloesen(pa.artikel, rest).items():
			bedarf[k] += v
			erster.setdefault(k, pa.datum)
	for artikel in [
		a for a in bedarf if frappe.get_cached_value("Item", a, "kt_chargen_stufe") == "Teig veredelt"
	]:
		fehlt = bedarf[artikel] - _bestand(artikel)
		if fehlt > 0:
			for k, v in aufloesen(artikel, fehlt, ("Grundteig",)).items():
				bedarf[k] += v
				erster.setdefault(k, erster[artikel])
	ergebnis = []
	for artikel, kg in bedarf.items():
		bestand = _bestand(artikel)
		ergebnis.append(
			{
				"artikel": artikel,
				"artikelname": frappe.get_cached_value("Item", artikel, "item_name"),
				"stufe": frappe.get_cached_value("Item", artikel, "kt_chargen_stufe"),
				"bedarf_kg": flt(kg, 1),
				"bestand_kg": flt(bestand, 1),
				"kuebel": frappe.db.count("Produkttraeger", {"status": "Belegt", "artikel": artikel}),
				"fehlt_kg": flt(max(kg - bestand, 0), 1),
				"benoetigt_ab": erster.get(artikel),
			}
		)
	return sorted(ergebnis, key=lambda z: (z["stufe"] != "Grundteig", z["artikelname"]))
