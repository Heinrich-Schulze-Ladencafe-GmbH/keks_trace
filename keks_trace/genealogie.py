"""Genealogie-Kanten und Datumsvererbung beim Buchen.

Für jede Fertigungs- oder Umpackbuchung entsteht pro (Input-Charge, Output-Charge)
eine Kante in `Chargen Genealogie`. Daraus rechnet die Rückverfolgung in beide
Richtungen, auch über mehrere Rework-Generationen.

Datumsregeln für die erzeugten Chargen:
- Ursprungsdatum = ältestes Herstelldatum aller eingeflossenen Produktionschargen
  (Teig, Rework, Backware lose, Fertigware). Rohstoffe zählen nicht.
- Rework: Herstelldatum = Ursprungsdatum. Damit zählt das Rework-Alter ab dem ältesten
  Backtag in der Kette, und Rework-Ketten sind automatisch auf das Höchstalter begrenzt.
- Fertigware: Herstelldatum = ältester Backtag der eingesetzten Backware lose (MHD ab Backtag).
- Verfall/MHD = Herstelldatum + Haltbarkeit des Artikels (ERPNext-Standardfelder).
"""

import frappe
from frappe.utils import add_days, getdate

from keks_trace.install import PRODUKTIONS_STUFEN
from keks_trace.utils import artikel_stufe, ausgangs_zeilen, eingangs_zeilen, zeilen_chargen


def on_submit(doc, method=None):
	if doc.purpose not in ("Manufacture", "Repack"):
		return

	eingaenge = [
		(charge, r.item_code, menge) for r in eingangs_zeilen(doc) for charge, menge in zeilen_chargen(r)
	]
	ausgaenge = [
		(charge, r.item_code, menge) for r in ausgangs_zeilen(doc) for charge, menge in zeilen_chargen(r)
	]
	if not eingaenge or not ausgaenge:
		return

	summe_ein = sum(m for _c, _i, m in eingaenge) or 1
	summe_aus = sum(m for _c, _i, m in ausgaenge) or 1

	for out_charge, out_item, out_menge in ausgaenge:
		anteil_aus = out_menge / summe_aus
		for in_charge, in_item, in_menge in eingaenge:
			frappe.get_doc(
				{
					"doctype": "Chargen Genealogie",
					"input_batch": in_charge,
					"input_item": in_item,
					"output_batch": out_charge,
					"output_item": out_item,
					"menge": in_menge * anteil_aus,
					"anteil": in_menge / summe_ein,
					"stock_entry": doc.name,
					"posting_date": doc.posting_date,
					"quelle": "Buchung",
				}
			).insert(ignore_permissions=True)

		_setze_daten(doc, out_charge, out_item, eingaenge)


def on_cancel(doc, method=None):
	frappe.db.set_value(
		"Chargen Genealogie",
		{"stock_entry": doc.name, "storniert": 0},
		"storniert",
		1,
		update_modified=True,
	)


def _setze_daten(doc, out_charge, out_item, eingaenge):
	buchungstag = getdate(doc.posting_date)
	stufe = artikel_stufe(out_item)

	ursprungsdaten = []
	backtage = []
	for in_charge, in_item, _menge in eingaenge:
		in_stufe = artikel_stufe(in_item)
		if in_stufe not in PRODUKTIONS_STUFEN:
			continue
		ursprung, herstell = frappe.db.get_value(
			"Batch", in_charge, ["kt_ursprungsdatum", "manufacturing_date"]
		)
		datum = ursprung or herstell
		if datum:
			ursprungsdaten.append(getdate(datum))
		if in_stufe == "Backware lose" and herstell:
			backtage.append(getdate(herstell))

	vorhandenes = frappe.db.get_value("Batch", out_charge, "manufacturing_date")
	herstelldatum = getdate(vorhandenes) if vorhandenes else buchungstag
	ursprung = min([*ursprungsdaten, herstelldatum])

	if stufe == "Rework":
		herstelldatum = ursprung
	elif stufe == "Fertigware" and backtage:
		herstelldatum = min(backtage)

	werte = {"manufacturing_date": herstelldatum, "kt_ursprungsdatum": min(ursprung, herstelldatum)}

	hat_verfall, haltbarkeit = frappe.get_cached_value(
		"Item", out_item, ["has_expiry_date", "shelf_life_in_days"]
	)
	if hat_verfall and haltbarkeit:
		werte["expiry_date"] = add_days(herstelldatum, haltbarkeit)

	frappe.db.set_value("Batch", out_charge, werte)
