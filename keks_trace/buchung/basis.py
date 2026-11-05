"""Buchung: gemeinsame Konstanten, Fehler, Silo und Vorrat je Artikel."""

import frappe
from frappe import _

EPS = 1e-6


class TerminalFehler(frappe.ValidationError):
	pass


def _fehler(text):
	frappe.throw(text, TerminalFehler, title=_("Nicht möglich"))


def _silo_je_artikel():
	"""Artikel -> Silo (bei mehreren Silos für einen Artikel das zuletzt angelegte)."""
	return {
		s.artikel: s.name
		for s in frappe.get_all(
			"Silo", filters={"aktiv": 1}, fields=["name", "artikel"], order_by="creation asc"
		)
	}


VORRAT = "Vorrat am Tisch"


def _vorraete():
	"""Artikel -> Vorrat am Tisch (offener Karton, Rolle, Behälter ohne Code)."""
	return {
		s.artikel: s.name
		for s in frappe.get_all("Silo", filters={"aktiv": 1, "typ": VORRAT}, fields=["name", "artikel"])
	}
