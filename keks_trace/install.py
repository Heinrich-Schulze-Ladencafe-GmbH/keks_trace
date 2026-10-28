"""Zusatzfelder an ERPNext-Standardobjekten.

Die Felder werden bei Installation und bei jedem `bench migrate` angelegt bzw.
aktualisiert. So ist jede Instanz (Test, Produktion) gleich aufgebaut.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CHARGEN_STUFEN = ["Rohstoff", "Packmittel", "Teig", "Rework", "Backware lose", "Fertigware"]

# Stufen der eigenen Produktion. Nur sie zählen für das Ursprungsdatum,
# damit das Lieferdatum eines Rohstoffs nicht das Rework-Alter bestimmt.
PRODUKTIONS_STUFEN = ["Teig", "Rework", "Backware lose", "Fertigware"]

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
			"description": "Ältestes Herstelldatum aller eingeflossenen Produktionschargen (inkl. Rework).",
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
	import frappe

	for feld in ("enable_serial_and_batch_no_for_item", "use_serial_batch_fields"):
		if not frappe.db.get_single_value("Stock Settings", feld):
			frappe.db.set_single_value("Stock Settings", feld, 1)
