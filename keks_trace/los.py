"""Los-Nummern für Fertigware und Haltbarkeit in Monaten.

JWWT: Jahr (letzte Ziffer), ISO-Kalenderwoche, ISO-Wochentag (1 = Montag). Ein Los je Artikel
und Tag; alle Verpackungen des Tages gehen in dieselbe Charge. Die Charge heißt intern
<Artikel>-<ISO-Jahr>-<Los>, gedruckt wird nur das Los.
"""

import frappe
from frappe import _
from frappe.utils import add_months, getdate

TAGE_JE_MONAT = 30.44


def jwwt(datum) -> str:
	iso = getdate(datum).isocalendar()
	return f"{iso[0] % 10}{iso[1]:02d}{iso[2]}"


def format_() -> str:
	return frappe.db.get_single_value("Keks Trace Einstellungen", "los_format") or "JWWT"


def mhd_vorgabe(kundenauftrag: str | None, datum, mhd=None):
	"""Kürzeres MHD für den Kunden: Monate am Kundenauftrag, sonst am Kunden, gezählt ab dem Verpackungstag.

	mhd: am Terminal von Hand gekürztes MHD. Es gilt das frühere von beiden. Länger als laut Rohstoffen
	und Haltbarkeit wird das MHD nie (genealogie.daten_berechnen nimmt immer das Frühere).
	"""
	werte = []
	if kundenauftrag:
		monate, kunde = frappe.db.get_value("Sales Order", kundenauftrag, ["kt_mhd_monate", "customer"])
		monate = monate or frappe.db.get_value("Customer", kunde, "kt_mhd_monate")
		if monate:
			werte.append(getdate(add_months(datum, monate)))
	if mhd:
		werte.append(getdate(mhd))
	return min(werte) if werte else None


def tages_charge(artikel: str, datum, vorgabe=None) -> tuple[str, str, bool]:
	"""Los und Charge des Tages. Gibt (Charge, Los, neu_angelegt) zurück.

	Mit gekürztem MHD (vorgabe) gibt es eine eigene Charge je MHD: gleiches Los, anderes MHD auf dem Beutel.
	"""
	los = jwwt(datum)
	name = f"{artikel}-{getdate(datum).isocalendar()[0]}-{los}"
	if vorgabe:
		name += "-M" + getdate(vorgabe).strftime("%y%m%d")
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
			"kt_mhd_vorgabe": getdate(vorgabe) if vorgabe else None,
		}
	).insert()
	return name, los, True


def item_validate(doc, method=None):
	"""Haltbarkeit in Monaten: ERPNext braucht Tage, die genaue Rechnung macht genealogie.daten_berechnen."""
	if doc.get("kt_mhd_monate"):
		doc.has_expiry_date = 1
		doc.shelf_life_in_days = round(doc.kt_mhd_monate * TAGE_JE_MONAT)
