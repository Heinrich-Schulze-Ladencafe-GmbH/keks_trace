"""Linie: lose Ware vom laufenden Auftrag ins Lager oder Linienlager (F7, F8/F9)."""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, now_datetime, nowdate

from keks_trace import buchung, haccp
from keks_trace import palette as paletten
from keks_trace.linienbuchung.basis import EPS, _fehler, _hat, _laufender, _linie, _station
from keks_trace.linienbuchung.rezept import _verbrauch
from keks_trace.utils import artikel_stufe


def lose_artikel(artikel: str) -> str | None:
	"""Die lose Ware, aus der der Artikel verpackt wird (Honig Lebkuchen 200 g → Honig Moppen lose)."""
	bom = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})
	if not bom:
		return None
	for z in frappe.get_all("BOM Item", {"parent": bom}, ["item_code"], order_by="idx"):
		if artikel_stufe(z.item_code) == "Ware lose":
			return z.item_code
	return None


LOSE_ZIELE = ("lager", "linienlager")


def lose_einheit(artikel: str) -> str:
	"""Lose Ware wird in Kartons gezählt (kg je Karton fest am Artikel), sonst in der Lagereinheit (kg)."""
	return "Karton" if _hat(artikel, "Karton") else frappe.get_cached_value("Item", artikel, "stock_uom")


def lose_fertig(
	station: str,
	anzahl: float,
	einheit: str | None = None,
	ziel: str = "lager",
	palette: str | None = None,
	kiste: str | None = None,
) -> dict:
	"""Verpackungs-PC: Aus dem laufenden Auftrag wird auch lose Ware gemacht, parallel zur
	Verpackungsmaschine abgenommen (F5) oder, wenn die Verpackung nicht nachkommt, ins Linienlager (F6).

	Gezählt wird in Kartons (kg je Karton fest am Artikel). Ziel „lager“: Kartons ins Lager, optional auf
	eine Palette. Ziel „linienlager“: Kartons warten an der Linie und werden später verpackt (F7, Verpackungs-PC
	„Lose Ware verpacken“). Wannen werden nicht gebucht. Verbraucht wird wie bei den Kartons der Teig von der
	Linie und die Füllung aus dem Lager. Jede Buchung ergibt eine eigene Charge (ein Lagerort je Charge)."""

	s = _station(station)
	linie = _linie(s)
	pa = _laufender(s)
	haccp.pruefe_station_frei(s.name)
	artikel = lose_artikel(pa.artikel)
	if not artikel:
		_fehler(_("Zu {0} gibt es keine lose Ware im Rezept.").format(pa.artikel))
	if ziel not in LOSE_ZIELE:
		_fehler(_("Unbekanntes Ziel {0}.").format(ziel))
	einheit = einheit or lose_einheit(artikel)
	anzahl = flt(anzahl)
	kg = flt(anzahl * paletten.faktor(artikel, einheit), 6)
	if kg <= EPS:
		_fehler(_("Bitte die Anzahl eingeben."))
	if ziel == "linienlager":
		if not linie.get("linienlager"):
			_fehler(_("Für die Linie {0} ist kein Linienlager eingerichtet.").format(linie.name))
		if palette:
			_fehler(_("Kartons im Linienlager kommen auf keine Palette, sie werden später verpackt."))
		lager = linie.linienlager
	else:
		lager = linie.fertiglager or buchung._ziel_lager(s, artikel)
	nve = paletten.finde(palette) if palette else None
	if palette and not nve:
		_fehler(_("{0} ist keine Palette.").format(palette))
	if nve:
		paletten._offen(nve)
	behaelter = buchung._ziel_behaelter(kiste) if kiste else None
	zeilen, hinweise, vom_teig = _verbrauch(pa, artikel, kg, linie)
	if not vom_teig:
		_fehler(
			_(
				"Für Auftrag {0} ist noch nichts auf der Linie gebucht. Erst am Kneter die Kübel scannen."
			).format(pa.name)
		)
	charge = buchung._neue_charge(artikel, getdate(nowdate()))
	jetzt = now_datetime()
	ausgabe = buchung._se_zeile(
		{"artikel": artikel, "charge": charge, "menge": kg, "behaelter": behaelter}, t_warehouse=lager
	)
	ausgabe["is_finished_item"] = 1
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Manufacture",
			"purpose": "Manufacture",
			"company": linie.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"kt_produktionsauftrag": pa.name,
			"items": [buchung._se_zeile(z, s_warehouse=z["lager"]) for z in zeilen] + [ausgabe],
		}
	)
	se.insert()
	se.submit()
	if nve:
		paletten.beladen(nve, charge, anzahl, einheit, s.name, "Verpackung", "Stock Entry", se.name)
	b = frappe.db.get_value("Batch", charge, ["expiry_date", "kt_status"], as_dict=True)
	return {
		"charge": charge,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"anzahl": anzahl,
		"einheit": einheit,
		"menge": kg,
		"ziel": ziel,
		"lager": lager,
		"palette": nve,
		"kiste": behaelter,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"gesperrt": b.kt_status == "Gesperrt",
		"buchung": se.name,
		"verbraucht": [
			{
				"name": frappe.get_cached_value("Item", z["artikel"], "item_name"),
				"charge": z.get("charge") or z.get("silo"),
				"menge": flt(z["menge"], 3),
			}
			for z in zeilen
		],
		"hinweise": hinweise + list(se.flags.kt_fifo_warnungen or []),
	}


def im_linienlager(linie: str) -> list[dict]:
	"""Was im Linienlager auf die Verpackung wartet (Kartons lose Ware), älteste zuerst."""
	lager = frappe.get_cached_value("Linie", linie, "linienlager")
	if not lager:
		return []
	zeilen = frappe.db.sql(
		"""
		select sbe.batch_no as charge, b.item as artikel, b.item_name as name, sum(sbe.qty) as menge,
			date(min(sbb.posting_datetime)) as seit
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		join `tabBatch` b on b.name = sbe.batch_no
		where sbe.warehouse = %(lager)s and sbb.docstatus = 1 and sbb.is_cancelled = 0
		group by sbe.batch_no, b.item, b.item_name
		having sum(sbe.qty) > 0.000001
		order by seit, sbe.batch_no
		""",
		{"lager": lager},
		as_dict=True,
	)
	return [
		{
			**z,
			"menge": flt(z.menge, 3),
			"menge_text": paletten.zerlegen(z.artikel, z.menge),
			"seit": formatdate(z.seit),
			"alt": getdate(z.seit) < getdate(nowdate()),
		}
		for z in zeilen
	]
