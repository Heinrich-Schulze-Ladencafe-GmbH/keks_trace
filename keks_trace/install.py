"""Zusatzfelder an ERPNext-Standardobjekten.

Die Felder werden bei Installation und bei jedem `bench migrate` angelegt bzw.
aktualisiert. So ist jede Instanz (Test, Produktion) gleich aufgebaut.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Ablauf: Grundteig -> Teig veredelt -> Backware -> Ware lose (gefüllt/glasiert/schokoliert) -> Fertigware.
# Rohstoff/Packmittel werden gekauft, Halbfabrikat = selbst hergestellte Füllung oder Glasur.
CHARGEN_STUFEN = [
	"Rohstoff",
	"Packmittel",
	"Halbfabrikat",
	"Grundteig",
	"Teig veredelt",
	"Rework",
	"Backware",
	"Ware lose",
	"Fertigware",
]

# In diese Stufen darf Rework eingesetzt werden.
REWORK_ZIELE = ["Grundteig", "Teig veredelt"]

# Stufen der Teig-/Gebäckkette. Nur sie zählen für das Ursprungsdatum, damit weder das
# Lieferdatum eines Rohstoffs noch das Datum einer Füllung das Rework-Alter bestimmt.
PRODUKTIONS_STUFEN = ["Grundteig", "Teig veredelt", "Rework", "Backware", "Ware lose", "Fertigware"]

# Zutaten, deren eigenes MHD das MHD der losen Ware und der Fertigware begrenzt,
# wenn sie nach dem Backen aufgebracht werden (Füllung, Glasur, Schokolade).
KOMPONENTEN_STUFEN = ["Rohstoff", "Halbfabrikat"]

CUSTOM_FIELDS = {
	"Item": [
		{
			"fieldname": "kt_chargen_stufe",
			"label": "Chargenstufe",
			"fieldtype": "Select",
			"options": "\n" + "\n".join(CHARGEN_STUFEN),
			"insert_after": "item_group",
			"description": "Wo der Artikel in der Kette steht (Keks Trace).",
		},
		{
			"fieldname": "kt_allergengruppe",
			"label": "Allergengruppe",
			"fieldtype": "Link",
			"options": "Allergengruppe",
			"insert_after": "kt_chargen_stufe",
		},
	],
	"Batch": [
		{
			"fieldname": "kt_chargen_stufe",
			"label": "Chargenstufe",
			"fieldtype": "Data",
			"fetch_from": "item.kt_chargen_stufe",
			"read_only": 1,
			"in_standard_filter": 1,
			"insert_after": "item",
		},
		{
			"fieldname": "kt_ursprungsdatum",
			"label": "Ursprungsdatum",
			"fieldtype": "Date",
			"read_only": 1,
			"insert_after": "manufacturing_date",
			"description": "Ältestes Herstelldatum aller eingeflossenen Teig- und Gebäckchargen (inkl. Rework).",
		},
		{
			"fieldname": "kt_backtag",
			"label": "Backtag",
			"fieldtype": "Date",
			"read_only": 1,
			"insert_after": "kt_ursprungsdatum",
			"description": "Tag, an dem die enthaltene Ware gebacken wurde. Basis für das MHD.",
		},
		{
			"fieldname": "kt_komponenten_mhd",
			"label": "Kürzestes Komponenten-MHD",
			"fieldtype": "Date",
			"read_only": 1,
			"insert_after": "kt_backtag",
			"description": "Frühestes MHD der nach dem Backen aufgebrachten Füllungen, Glasuren, Schokolade.",
		},
	],
	"Stock Entry Detail": [
		{
			"fieldname": "kt_traeger",
			"label": "Behälter / Träger",
			"fieldtype": "Link",
			"options": "Produkttraeger",
			"insert_after": "batch_no",
			"in_list_view": 0,
			"description": "Gescannter Behälter: bei Eingang wird er entleert, bei Ausgang befüllt.",
		},
	],
}


def after_install():
	create_custom_fields(CUSTOM_FIELDS, update=True)
	_lager_einstellungen()


def after_migrate():
	create_custom_fields(CUSTOM_FIELDS, update=True)
	_lager_einstellungen()


def _lager_einstellungen():
	"""Chargenverwaltung muss in ERPNext aktiv sein, sonst lassen sich keine Chargenartikel anlegen."""
	for feld in ("enable_serial_and_batch_no_for_item", "use_serial_batch_fields"):
		if not frappe.db.get_single_value("Stock Settings", feld):
			frappe.db.set_single_value("Stock Settings", feld, 1)
