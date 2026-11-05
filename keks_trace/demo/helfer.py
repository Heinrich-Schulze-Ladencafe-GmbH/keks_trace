"""Demo: Buchungshelfer (so würden es die Scanner-Seiten tun): Behälter, Charge, Lagerbuchung, Lieferung."""

import frappe
from frappe.utils import getdate

from keks_trace.demo.konstanten import ROHSTOFF_PREIS


def neuer_traeger(code: str, typ: str) -> str:
	if not frappe.db.exists("Produkttraeger", code):
		frappe.get_doc({"doctype": "Produkttraeger", "code": code, "typ": typ}).insert()
	return code


def neue_charge(item: str, charge_id: str, herstelldatum=None, lieferant: str | None = None) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Batch",
				"item": item,
				"batch_id": charge_id,
				"manufacturing_date": herstelldatum,
				"supplier": lieferant,
			}
		)
		.insert()
		.name
	)


def _lager(ctx, item):
	stufe = _stufe(item)
	if stufe in ("Rohstoff", "Packmittel"):
		return ctx.lager
	if stufe == "Fertigware":
		return ctx.fertig
	return ctx.produktion  # Teige, Füllung, Backware, Rework, lose Ware


def buchen(ctx, zweck: str, datum, zeit: str, eingaenge=(), ausgaenge=(), submit: bool = True):
	"""Lagerbuchung erzeugen.

	eingaenge / ausgaenge: Tupel (Artikel, Charge, Menge) oder (Artikel, Charge, Menge, Behälter oder Silo).
	Bei Entnahme aus einem Silo bleibt die Charge leer (None): das System teilt sie nach FIFO zu.
	Für Wareneingang ("Material Receipt") nur ausgaenge.
	"""
	zeilen = []
	for item, charge, menge, *traeger in eingaenge:
		lager, traeger = _ort(ctx, item, traeger)
		zeilen.append(_zeile(item, charge, menge, traeger, s_warehouse=lager))
	for i, (item, charge, menge, *traeger) in enumerate(ausgaenge):
		lager, traeger = _ort(ctx, item, traeger)
		z = _zeile(item, charge, menge, traeger, t_warehouse=lager)
		if zweck == "Material Receipt":
			z["basic_rate"] = ROHSTOFF_PREIS.get(item, 1)
		if zweck == "Manufacture" and i == 0:
			z["is_finished_item"] = 1
		zeilen.append(z)

	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": zweck,
			"purpose": zweck,
			"company": ctx.company,
			"set_posting_time": 1,
			"posting_date": getdate(datum),
			"posting_time": zeit,
			"items": zeilen,
		}
	)
	se.insert()
	if submit:
		se.submit()
	return se


def _ort(ctx, item, traeger):
	"""Lagerort und Behälter: ein Silo-Name als 4. Element bedeutet Lagerort des Silos, kein Behälter."""
	if traeger and traeger[0] in (ctx.get("silo_lager") or {}):
		return ctx.silo_lager[traeger[0]], []
	return _lager(ctx, item), traeger


def _zeile(item, charge, menge, traeger, s_warehouse=None, t_warehouse=None):
	return {
		"item_code": item,
		"qty": menge,
		"uom": "Kg",
		"stock_uom": "Kg",
		"conversion_factor": 1,
		"transfer_qty": menge,
		"s_warehouse": s_warehouse,
		"t_warehouse": t_warehouse,
		"use_serial_batch_fields": 1,
		"batch_no": charge,
		"kt_traeger": traeger[0] if traeger else None,
	}


def _stufe(item):
	return frappe.get_cached_value("Item", item, "kt_chargen_stufe")


def liefern(ctx, datum, positionen, rate=8.0):
	"""positionen: Liste (Artikel, Charge, Menge)."""
	dn = frappe.get_doc(
		{
			"doctype": "Delivery Note",
			"customer": ctx.kunde,
			"company": ctx.company,
			"set_posting_time": 1,
			"posting_date": getdate(datum),
			"posting_time": "16:00:00",
			"items": [
				{
					"item_code": item,
					"qty": menge,
					"uom": "Kg",
					"conversion_factor": 1,
					"rate": rate,
					"warehouse": ctx.fertig,
					"use_serial_batch_fields": 1,
					"batch_no": charge,
				}
				for item, charge, menge in positionen
			],
		}
	)
	dn.insert()
	dn.submit()
	return dn
