"""Paletten: gemeinsame Konstanten und Fehler."""

import frappe
from frappe import _

EPS = 1e-6


# Nummernkreis für eingeschränkte Verwendung (GS1 „02“): taugt zum Testen, nie für Kunden.
TEST_BASISNUMMER = "0200000"


AKTIV = ("Offen", "Geschlossen")


class PalettenFehler(frappe.ValidationError):
	pass


def _fehler(text):
	frappe.throw(text, PalettenFehler, title=_("Palette"))


VERSANDKARTON = "Versandkarton"
