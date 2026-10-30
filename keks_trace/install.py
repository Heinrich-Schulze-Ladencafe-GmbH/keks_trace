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
		{
			"fieldname": "kt_freigabe_pflicht",
			"label": "Freigabe vor Verwendung",
			"fieldtype": "Check",
			"insert_after": "kt_allergengruppe",
			"description": "Neue Chargen sind gesperrt, bis die QS sie freigibt (z. B. Wareneingangsprüfung, Freigabe loser Ware).",
		},
		{
			"fieldname": "kt_mhd_monate",
			"label": "Haltbarkeit in Monaten",
			"fieldtype": "Int",
			"insert_after": "shelf_life_in_days",
			"description": "Wenn gesetzt, wird das MHD in Monaten gerechnet (statt „Shelf Life In Days“).",
		},
		{
			"fieldname": "kt_mhd_bezug",
			"label": "MHD zählt ab",
			"fieldtype": "Select",
			"options": "\nBacktag\nVerpackungstag",
			"insert_after": "kt_mhd_monate",
			"description": "Für lose Ware und Fertigware. Leer = Backtag.",
		},
	],
	"Batch": [
		{
			"fieldname": "kt_los",
			"label": "Los (Aufdruck)",
			"fieldtype": "Data",
			"read_only": 1,
			"in_standard_filter": 1,
			"in_list_view": 1,
			"insert_after": "batch_id",
			"description": "Los wie auf Beutel und Karton gedruckt (z. B. JWWT). Gleich für alle Verpackungen eines Artikels an einem Tag.",
		},
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
		{
			"fieldname": "kt_status",
			"label": "Sperrstatus",
			"fieldtype": "Select",
			"options": "Freigegeben\nGesperrt",
			"default": "Freigegeben",
			"read_only": 1,
			"in_list_view": 1,
			"in_standard_filter": 1,
			"insert_after": "kt_chargen_stufe",
			"description": "Wird nur über Sperren/Freigeben geändert (Protokoll: Chargen Sperre).",
		},
		{
			"fieldname": "kt_sperrgrund",
			"label": "Sperrgrund",
			"fieldtype": "Small Text",
			"read_only": 1,
			"depends_on": "eval:doc.kt_status=='Gesperrt'",
			"insert_after": "kt_status",
		},
	],
	"Stock Entry": [
		{
			"fieldname": "kt_station",
			"label": "Station (Terminal)",
			"fieldtype": "Link",
			"options": "Terminal Station",
			"read_only": 1,
			"insert_after": "stock_entry_type",
		},
		{
			"fieldname": "kt_kundenauftrag",
			"label": "Kundenauftrag",
			"fieldtype": "Link",
			"options": "Sales Order",
			"read_only": 1,
			"insert_after": "kt_station",
			"description": "Für diesen Kundenauftrag verpackt (Terminal Verpackung).",
		},
	],
	"Delivery Note": [
		{
			"fieldname": "kt_station",
			"label": "Station (Terminal)",
			"fieldtype": "Link",
			"options": "Terminal Station",
			"read_only": 1,
			"insert_after": "customer",
		},
	],
	"Delivery Note Item": [
		{
			"fieldname": "kt_palette",
			"label": "Palette (NVE)",
			"fieldtype": "Link",
			"options": "Palette",
			"insert_after": "batch_no",
			"description": "Ware kommt von dieser Palette. Leer = lose Kartons ohne Palette.",
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
		{
			"fieldname": "kt_silo",
			"label": "Silo / Tank",
			"fieldtype": "Link",
			"options": "Silo",
			"read_only": 1,
			"insert_after": "kt_traeger",
			"description": "Entnahme aus einem Silo: Charge wurde nach FIFO zugeteilt.",
		},
	],
}


def after_install():
	after_migrate()


def after_migrate():
	create_custom_fields(CUSTOM_FIELDS, update=True)
	_lager_einstellungen()
	_aenderungsprotokoll()
	_buchungsarten()
	_einheiten()


def _einheiten():
	"""Zähleinheiten für Fertigware (Umrechnung in kg steht am Artikel)."""
	for uom in ("Karton", "Beutel"):
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": 1}).insert(
				ignore_permissions=True
			)


def _buchungsarten():
	if not frappe.db.exists("Stock Entry Type", "Silo Differenz"):
		frappe.get_doc(
			{"doctype": "Stock Entry Type", "name": "Silo Differenz", "purpose": "Material Issue"}
		).insert(ignore_permissions=True)


def _aenderungsprotokoll():
	"""Jede Änderung an Chargen und Artikeln wird mit Vorher/Nachher protokolliert (IFS 2.1.2.1)."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype in ("Batch", "Item"):  # eigene DocTypes haben track_changes bereits
		make_property_setter(
			doctype, None, "track_changes", 1, "Check", for_doctype=True, validate_fields_for_doctype=False
		)


def _lager_einstellungen():
	"""Chargenverwaltung muss in ERPNext aktiv sein, sonst lassen sich keine Chargenartikel anlegen."""
	for feld in ("enable_serial_and_batch_no_for_item", "use_serial_batch_fields"):
		if not frappe.db.get_single_value("Stock Settings", feld):
			frappe.db.set_single_value("Stock Settings", feld, 1)
