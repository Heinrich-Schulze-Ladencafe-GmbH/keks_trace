"""Standard-Nummernkreis „Eigener“ anlegen (Basisnummer und Reserveziffer weiter aus den Einstellungen)."""

import frappe


def execute():
	if frappe.db.exists("NVE Nummernkreis", {"standard": 1}):
		return
	if frappe.db.exists("NVE Nummernkreis", "Eigener"):
		frappe.db.set_value("NVE Nummernkreis", "Eigener", {"standard": 1, "aktiv": 1})
		return
	frappe.get_doc(
		{
			"doctype": "NVE Nummernkreis",
			"kreis_name": "Eigener",
			"art": "Eigener",
			"aktiv": 1,
			"standard": 1,
			"bemerkung": "Eigene GS1-Basisnummer aus den Keks Trace Einstellungen.",
		}
	).insert(ignore_permissions=True)
