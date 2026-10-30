"""Los-Nummern für Fertigware und Haltbarkeit in Monaten.

JWWT: Jahr (letzte Ziffer), ISO-Kalenderwoche, ISO-Wochentag (1 = Montag). Ein Los je Artikel
und Tag; alle Verpackungen des Tages gehen in dieselbe Charge. Die Charge heißt intern
<Artikel>-<ISO-Jahr>-<Los>, gedruckt wird nur das Los.
"""

import frappe
from frappe import _
from frappe.utils import getdate

TAGE_JE_MONAT = 30.44


def jwwt(datum) -> str:
	iso = getdate(datum).isocalendar()
	return f"{iso[0] % 10}{iso[1]:02d}{iso[2]}"


def format_() -> str:
	return frappe.db.get_single_value("Keks Trace Einstellungen", "los_format") or "JWWT"


def tages_charge(artikel: str, datum) -> tuple[str, str, bool]:
	"""Los und Charge des Tages. Gibt (Charge, Los, neu_angelegt) zurück."""
	los = jwwt(datum)
	name = f"{artikel}-{getdate(datum).isocalendar()[0]}-{los}"
	if frappe.db.exists("Batch", name):
		if frappe.db.get_value("Batch", name, "kt_status") == "Gesperrt":
			frappe.throw(
				_("Los {0} von {1} ist gesperrt. Nicht weiter verpacken, QS fragen.").format(los, artikel),
				title=_("Los gesperrt"),
			)
		return name, los, False
	frappe.get_doc(
		{
			"doctype": "Batch",
			"item": artikel,
			"batch_id": name,
			"manufacturing_date": getdate(datum),
			"kt_los": los,
		}
	).insert()
	return name, los, True


def item_validate(doc, method=None):
	"""Haltbarkeit in Monaten: ERPNext braucht Tage, die genaue Rechnung macht genealogie.daten_berechnen."""
	if doc.get("kt_mhd_monate"):
		doc.has_expiry_date = 1
		doc.shelf_life_in_days = round(doc.kt_mhd_monate * TAGE_JE_MONAT)
