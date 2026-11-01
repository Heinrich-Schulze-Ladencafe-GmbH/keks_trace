"""Neue Felder in Keks Trace Einstellungen (Single) mit ihrem Standard füllen, falls leer.

Frappe setzt Standardwerte neuer Felder nicht in schon gespeicherte Singles; das Formular zeigte sonst leer.
"""

import frappe

STANDARD = {
	"fefo_rohstoffe": "Grund Pflicht",
	"rezept_abweichung": "Grund Pflicht",
	"rezept_toleranz_prozent": 5,
	"rezept_toleranz_min": 0.01,
}


def execute():
	for feld, wert in STANDARD.items():
		if not frappe.db.get_single_value("Keks Trace Einstellungen", feld):
			frappe.db.set_single_value("Keks Trace Einstellungen", feld, wert)
