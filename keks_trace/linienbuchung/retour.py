"""Linie: Retour, Unbenutztes von der Linie zurück ins Lager."""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from keks_trace.linienbuchung.basis import EPS, _fehler, _laufender, _linie, _station
from keks_trace.linienbuchung.rezept import bestand
from keks_trace.utils import artikel_stufe

RETOUR_STUFEN = ("Rohstoff", "Packmittel")


def _herkunft(pa: str, charge: str, linienlager: str) -> str | None:
	"""Lager, aus dem die Charge für diesen Auftrag an die Linie kam (letzte Zuführung)."""
	z = frappe.db.sql(
		"""
		select sed.s_warehouse from `tabStock Entry Detail` sed join `tabStock Entry` se on se.name = sed.parent
		where se.docstatus = 1 and se.kt_produktionsauftrag = %s and sed.batch_no = %s and sed.t_warehouse = %s
			and ifnull(sed.s_warehouse, '') != ''
		order by se.posting_date desc, se.posting_time desc, se.creation desc limit 1
		""",
		(pa, charge, linienlager),
	)
	return z[0][0] if z else None


def retour_liste(station: str) -> list[dict]:
	"""Was vom laufenden Auftrag zurück ins Lager kann: Rohstoffe und Packmittel, nicht aus dem Silo."""
	from keks_trace.silo import silo_fuer_lager

	s = _station(station)
	linie = _linie(s)
	pa = _laufender(s)
	out = []
	for z in bestand(pa.name):
		stufe = artikel_stufe(z["artikel"])
		if stufe not in RETOUR_STUFEN:
			continue
		lager = _herkunft(pa.name, z["charge"], linie.lagerort)
		out.append(
			{
				"charge": z["charge"],
				"artikel": z["artikel"],
				"name": frappe.get_cached_value("Item", z["artikel"], "item_name"),
				"stufe": stufe,
				"menge": flt(z["menge"], 3),
				"einheit": frappe.get_cached_value("Item", z["artikel"], "stock_uom"),
				"ziel": lager,
				"ziel_name": frappe.get_cached_value("Warehouse", lager, "warehouse_name") if lager else None,
				# Mehl kippt niemand zurück ins Silo: Silo-Ware bleibt auf der Linie
				"silo": bool(lager and silo_fuer_lager(lager)),
			}
		)
	return out


def rueckgabe(station: str, charge: str, menge: float) -> dict:
	"""Retour: Menge einer Charge von der Linie zurück in das Lager, aus dem sie kam."""
	s = _station(station)
	linie = _linie(s)
	pa = _laufender(s)
	menge = flt(menge)
	if menge <= EPS:
		_fehler(_("Bitte die Menge eingeben, die zurück ins Lager geht."))
	zeile = next((z for z in retour_liste(s.name) if z["charge"] == charge), None)
	if not zeile:
		_fehler(
			_(
				"Charge {0} liegt für diesen Auftrag nicht auf der Linie (oder ist kein Rohstoff/Packmittel)."
			).format(charge)
		)
	if zeile["silo"] or not zeile["ziel"]:
		_fehler(
			_("{0} kam aus dem Silo bzw. ohne Herkunft an die Linie und kann nicht zurück.").format(
				zeile["name"]
			)
		)
	if menge > zeile["menge"] + EPS:
		_fehler(
			_("Auf der Linie sind nur {0} {1} von Charge {2}.").format(
				flt(zeile["menge"], 3), zeile["einheit"], charge
			)
		)
	jetzt = now_datetime()
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"purpose": "Material Transfer",
			"company": linie.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"kt_produktionsauftrag": pa.name,
			"remarks": _("Retour von der Linie ({0})").format(pa.name),
			"items": [
				{
					"item_code": zeile["artikel"],
					"qty": menge,
					"transfer_qty": menge,
					"uom": zeile["einheit"],
					"stock_uom": zeile["einheit"],
					"conversion_factor": 1,
					"s_warehouse": linie.lagerort,
					"t_warehouse": zeile["ziel"],
					"use_serial_batch_fields": 1,
					"batch_no": charge,
				}
			],
		}
	)
	se.insert()
	se.submit()
	return {
		"name": zeile["name"],
		"charge": charge,
		"menge": flt(menge, 3),
		"einheit": zeile["einheit"],
		"ziel": zeile["ziel_name"],
		"buchung": se.name,
	}
