"""Genealogie-Kanten und Datumsvererbung beim Buchen.

Für jede Fertigungs- oder Umpackbuchung entsteht pro (Input-Charge, Output-Charge)
eine Kante in `Chargen Genealogie`. Daraus rechnet die Rückverfolgung in beide
Richtungen, auch über mehrere Rework-Generationen.

Datumsregeln für die erzeugten Chargen:
- Ursprungsdatum = ältestes Herstelldatum aller eingeflossenen Teig-/Gebäckchargen
  (Grundteig, Teig veredelt, Rework, Backware, Ware lose). Rohstoffe und Füllungen zählen nicht.
- Rework: Herstelldatum = Ursprungsdatum. Damit zählt das Rework-Alter ab dem ältesten
  Tag in der Kette, und Rework-Ketten sind automatisch auf das Höchstalter begrenzt.
- Backtag: bei Backware der Buchungstag, sonst vom ältesten Input mit Backtag geerbt.
- Komponenten-MHD: frühestes MHD der Füllungen, Glasuren, Schokolade, die nach dem Backen
  aufgebracht werden (Rohstoff/Halbfabrikat in Ware lose oder Fertigware), weitergereicht über Ware lose.
- Ware lose: Verfall (max. Lagerdauer) = min(Backtag + Haltbarkeit, Komponenten-MHD).
- Fertigware: Herstelldatum = Backtag, MHD = min(Backtag + Haltbarkeit, Komponenten-MHD).
- Sonst: Verfall = Herstelldatum + Haltbarkeit des Artikels (ERPNext-Standardfelder).
"""

import frappe
from frappe.utils import add_days, getdate

from keks_trace.install import KOMPONENTEN_STUFEN, PRODUKTIONS_STUFEN
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

	ursprungsdaten, backtage, komponenten_mhd = [], [], []
	for in_charge, in_item, _menge in eingaenge:
		in_stufe = artikel_stufe(in_item)
		ursprung, herstell, backtag, verfall, kmhd = frappe.db.get_value(
			"Batch",
			in_charge,
			["kt_ursprungsdatum", "manufacturing_date", "kt_backtag", "expiry_date", "kt_komponenten_mhd"],
		)
		if in_stufe in PRODUKTIONS_STUFEN and (ursprung or herstell):
			ursprungsdaten.append(getdate(ursprung or herstell))
		if backtag:
			backtage.append(getdate(backtag))
		if stufe in ("Ware lose", "Fertigware"):
			if in_stufe in KOMPONENTEN_STUFEN and verfall:
				komponenten_mhd.append(getdate(verfall))
			if kmhd:
				komponenten_mhd.append(getdate(kmhd))

	vorhandenes = frappe.db.get_value("Batch", out_charge, "manufacturing_date")
	herstelldatum = getdate(vorhandenes) if vorhandenes else buchungstag
	ursprung = min([*ursprungsdaten, herstelldatum])

	if stufe == "Backware":
		backtag = herstelldatum
	else:
		backtag = min(backtage) if backtage else None

	if stufe == "Rework":
		herstelldatum = ursprung
	elif stufe == "Fertigware" and backtag:
		herstelldatum = backtag

	werte = {
		"manufacturing_date": herstelldatum,
		"kt_ursprungsdatum": min(ursprung, herstelldatum),
		"kt_backtag": backtag,
		"kt_komponenten_mhd": min(komponenten_mhd) if komponenten_mhd else None,
	}

	hat_verfall, haltbarkeit = frappe.get_cached_value(
		"Item", out_item, ["has_expiry_date", "shelf_life_in_days"]
	)
	if hat_verfall and haltbarkeit:
		basis = backtag if stufe in ("Ware lose", "Fertigware") and backtag else herstelldatum
		verfall = getdate(add_days(basis, haltbarkeit))
		if werte["kt_komponenten_mhd"]:
			verfall = min(verfall, werte["kt_komponenten_mhd"])
		werte["expiry_date"] = verfall

	frappe.db.set_value("Batch", out_charge, werte)
