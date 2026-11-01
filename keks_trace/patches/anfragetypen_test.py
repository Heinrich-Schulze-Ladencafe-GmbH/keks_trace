"""Anfragetypen für Rückmeldungen aus dem Test (Handbuch „Spielen und Fehler melden“)."""

import frappe

TYPEN = {
	"Fehler": "Etwas funktioniert nicht oder rechnet falsch.",
	"Wunsch": "Funktioniert, sollte aber anders sein oder fehlt noch.",
	"Frage": "Unklar, wie etwas gedacht ist.",
}


def execute():
	if not frappe.db.exists("DocType", "Issue Type"):
		return
	for name, beschreibung in TYPEN.items():
		if not frappe.db.exists("Issue Type", name):
			doc = frappe.new_doc("Issue Type")
			doc.description = beschreibung
			doc.insert(set_name=name, ignore_permissions=True)
