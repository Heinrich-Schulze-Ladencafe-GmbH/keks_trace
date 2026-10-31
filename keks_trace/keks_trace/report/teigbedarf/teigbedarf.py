"""Teigbedarf: wie viel Grundteig und veredelter Teig die geplanten Aufträge brauchen, gegen den Bestand."""

import frappe
from frappe import _

from keks_trace.planung import teigbedarf


def execute(filters=None):
	f = frappe._dict(filters or {})
	if not f.linie:
		return _spalten(), [], _("Bitte eine Linie wählen.")
	daten = teigbedarf(f.linie, int(f.tage or 10))
	fehlt = [d for d in daten if d["fehlt_kg"] > 0]
	text = (
		_("Vorproduzieren: {0}").format(", ".join(f"{d['artikelname']} {d['fehlt_kg']:g} kg" for d in fehlt))
		if fehlt
		else _("Bestand reicht für die geplanten Aufträge.")
	)
	return _spalten(), daten, text


def _spalten():
	return [
		{"fieldname": "artikel", "label": _("Artikel"), "fieldtype": "Link", "options": "Item", "width": 110},
		{"fieldname": "artikelname", "label": _("Teig"), "fieldtype": "Data", "width": 200},
		{"fieldname": "stufe", "label": _("Stufe"), "fieldtype": "Data", "width": 110},
		{"fieldname": "bedarf_kg", "label": _("Bedarf kg"), "fieldtype": "Float", "width": 100},
		{"fieldname": "bestand_kg", "label": _("Bestand kg"), "fieldtype": "Float", "width": 100},
		{"fieldname": "kuebel", "label": _("Kübel"), "fieldtype": "Int", "width": 70},
		{"fieldname": "fehlt_kg", "label": _("Fehlt kg"), "fieldtype": "Float", "width": 100},
		{"fieldname": "benoetigt_ab", "label": _("Gebraucht ab"), "fieldtype": "Date", "width": 110},
	]
