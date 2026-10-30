"""Genealogie-Kanten und Datumsvererbung beim Buchen.

Für jede Fertigungs- oder Umpackbuchung entsteht pro (Input-Charge, Output-Charge)
eine Kante in `Chargen Genealogie`. Daraus rechnet die Rückverfolgung in beide
Richtungen, auch über mehrere Rework-Generationen.

Datumsregeln für die erzeugten Chargen:
- Ursprungsdatum = ältestes Herstelldatum aller eingeflossenen Teig-/Gebäckchargen
  (Grundteig, Teig veredelt, Rework, Backware, Ware lose). Rohstoffe und Füllungen zählen nicht.
- Rework: Herstelldatum = Ursprungsdatum. Damit zählt das Rework-Alter ab dem ältesten
  Tag in der Kette, und Rework-Ketten sind automatisch auf das Höchstalter begrenzt.
- Backtag: bei Backware der Buchungstag, ebenso bei loser Ware direkt aus dem Ofen (kein Input mit
  Backtag); sonst vom ältesten Input mit Backtag geerbt.
- Komponenten-MHD: frühestes MHD der Füllungen, Glasuren, Schokolade, die nach dem Backen
  aufgebracht werden (Rohstoff/Halbfabrikat in Ware lose oder Fertigware), weitergereicht über Ware lose.
- Ware lose: Verfall (max. Lagerdauer) = min(Backtag + Haltbarkeit, Komponenten-MHD).
- Fertigware: Herstelldatum = Backtag, MHD = min(Backtag + Haltbarkeit, Komponenten-MHD).
  Am Artikel einstellbar: Haltbarkeit in Monaten (kt_mhd_monate) und „MHD zählt ab“ Backtag oder
  Verpackungstag. Tages-Los (mehrere Verpackungen in dieselbe Charge): es gilt immer der älteste
  Backtag und das früheste Komponenten-MHD aller Verpackungen des Tages.
- Sonst: Verfall = Herstelldatum + Haltbarkeit des Artikels (ERPNext-Standardfelder).
"""

import frappe
from frappe.utils import add_days, add_months, formatdate, getdate

from keks_trace.install import KOMPONENTEN_STUFEN, PRODUKTIONS_STUFEN
from keks_trace.silo import vermischung
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

		# Silo/Tank: Chargen, die durch Nachfüllen noch vermischt enthalten sein können (Menge 0).
		for in_charge, in_item, silo in vermischung(doc, eingaenge):
			frappe.get_doc(
				{
					"doctype": "Chargen Genealogie",
					"input_batch": in_charge,
					"input_item": in_item,
					"output_batch": out_charge,
					"output_item": out_item,
					"menge": 0,
					"anteil": 0,
					"stock_entry": doc.name,
					"posting_date": doc.posting_date,
					"quelle": "Silo",
					"silo": silo,
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
	vorher = (
		frappe.db.get_value("Batch", out_charge, "expiry_date")
		if _frueher_gebucht(out_charge, doc.name)
		else None
	)
	werte = daten_berechnen(out_item, eingaenge, getdate(doc.posting_date), out_charge, doc.name)
	frappe.db.set_value("Batch", out_charge, werte)
	neu = werte.get("expiry_date")
	if vorher and neu and getdate(neu) < getdate(vorher):
		frappe.msgprint(
			frappe._(
				"MHD von Los {0} sinkt durch diese Ware von {1} auf {2}. Drucker umstellen und bereits "
				"gedruckte Beutel prüfen."
			).format(
				frappe.db.get_value("Batch", out_charge, "kt_los") or out_charge,
				formatdate(vorher),
				formatdate(neu),
			),
			indicator="orange",
			alert=True,
		)


def _frueher_gebucht(charge, ohne_beleg):
	"""Hat die Charge schon Eingänge aus einer anderen Buchung (Tages-Los mit mehreren Verpackungen)?"""
	return bool(
		frappe.db.exists(
			"Chargen Genealogie",
			{"output_batch": charge, "storniert": 0, "stock_entry": ["!=", ohne_beleg or ""]},
		)
	)


def daten_berechnen(out_item, eingaenge, buchungstag, out_charge=None, ohne_beleg=None) -> dict:
	"""Herstell-, Ursprungs-, Backtag-, Komponenten-MHD und Verfall für eine Output-Charge.

	eingaenge: Liste (Charge, Artikel, Menge). Ist die Output-Charge schon aus früheren Buchungen befüllt
	(Tages-Los), fließen deren Werte mit ein (immer das Ältere/Frühere).
	"""
	buchungstag = getdate(buchungstag)
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

	vorhanden = (
		frappe.db.get_value(
			"Batch",
			out_charge,
			["manufacturing_date", "kt_ursprungsdatum", "kt_backtag", "kt_komponenten_mhd"],
			as_dict=True,
		)
		if out_charge
		else None
	) or frappe._dict()
	if out_charge and _frueher_gebucht(out_charge, ohne_beleg):
		if vorhanden.kt_ursprungsdatum:
			ursprungsdaten.append(getdate(vorhanden.kt_ursprungsdatum))
		if vorhanden.kt_backtag and stufe != "Backware":
			backtage.append(getdate(vorhanden.kt_backtag))
		if vorhanden.kt_komponenten_mhd:
			komponenten_mhd.append(getdate(vorhanden.kt_komponenten_mhd))

	bezug = frappe.get_cached_value("Item", out_item, "kt_mhd_bezug") or "Backtag"
	herstelldatum = getdate(vorhanden.manufacturing_date) if vorhanden.manufacturing_date else buchungstag
	ursprung = min([*ursprungsdaten, herstelldatum])

	if stufe == "Backware" or (stufe == "Ware lose" and not backtage):
		# Backware, oder direkt aus dem Ofen in die Kiste (ohne Füllung): heute gebacken
		backtag = herstelldatum
	else:
		backtag = min(backtage) if backtage else None

	if stufe == "Rework":
		herstelldatum = ursprung
	elif stufe == "Fertigware" and backtag and bezug == "Backtag":
		herstelldatum = backtag

	werte = {
		"manufacturing_date": herstelldatum,
		"kt_ursprungsdatum": min(ursprung, herstelldatum),
		"kt_backtag": backtag,
		"kt_komponenten_mhd": min(komponenten_mhd) if komponenten_mhd else None,
	}

	hat_verfall, tage, monate = frappe.get_cached_value(
		"Item", out_item, ["has_expiry_date", "shelf_life_in_days", "kt_mhd_monate"]
	)
	if hat_verfall and (tage or monate):
		if stufe in ("Ware lose", "Fertigware") and bezug == "Backtag" and backtag:
			basis = backtag
		else:
			basis = herstelldatum
		verfall = getdate(add_months(basis, monate)) if monate else getdate(add_days(basis, tage))
		if werte["kt_komponenten_mhd"]:
			verfall = min(verfall, werte["kt_komponenten_mhd"])
		werte["expiry_date"] = verfall
	return werte
