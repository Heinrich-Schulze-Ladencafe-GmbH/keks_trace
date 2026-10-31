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
			"fieldname": "kt_linie",
			"label": "Linie",
			"fieldtype": "Link",
			"options": "Linie",
			"insert_after": "kt_chargen_stufe",
			"description": "Wo der Artikel hergestellt wird (z. B. Backstraße, Herzenboden). Stationen einer Linie zeigen nur ihre Artikel und Aufträge; die Planung plant je Linie nur diese Artikel.",
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
		{
			"fieldname": "kt_mhd_nicht_begrenzend",
			"label": "Begrenzt das MHD des Endprodukts nicht",
			"fieldtype": "Check",
			"insert_after": "kt_mhd_bezug",
			"description": "Für Zutaten nach dem Backen, deren eigene Lagerzeit nur bis zur Verarbeitung gilt (z. B. Zuckerglasur, die antrocknet). Sonst begrenzt ihr MHD das MHD der losen Ware und Fertigware.",
		},
		{
			"fieldname": "kt_linienleistung",
			"label": "Leistung je Linienabschnitt",
			"fieldtype": "Table",
			"options": "Artikel Linienleistung",
			"insert_after": "kt_mhd_bezug",
			"description": "Fertigware: Geschwindigkeit je Abschnitt (Füllen, Glasieren, Trocknen, Schokoladenkühlung, Band, Verpackungsanlagen), in kg/h, Beutel/min, Karton/h oder bei Stückware in Stück/h, Stück/min. Der langsamste bestimmt das Tempo.",
		},
		{
			"fieldname": "kt_leistung_kg_h",
			"label": "Leistung auf der Linie (Lagereinheit je Stunde)",
			"fieldtype": "Float",
			"read_only": 1,
			"insert_after": "kt_linienleistung",
			"description": "Engpass mit der schnellsten Verpackungsanlage, aus der Tabelle berechnet.",
		},
		{
			"fieldname": "kt_engpass",
			"label": "Engpass",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "kt_leistung_kg_h",
		},
		{
			"fieldname": "kt_bio",
			"label": "Bio (EU-Öko)",
			"fieldtype": "Check",
			"insert_after": "kt_freigabe_pflicht",
			"description": "Nur aus Bio-Zutaten herstellbar bzw. nur von Lieferanten mit Öko-Zertifikat annehmbar.",
		},
		{
			"fieldname": "kt_bio_erlaubt",
			"label": "In Bio-Produkten erlaubt",
			"fieldtype": "Check",
			"insert_after": "kt_bio",
			"depends_on": "eval:!doc.kt_bio",
			"description": "Nicht-landwirtschaftliche Zutat, die in Bio verwendet werden darf (Wasser, Salz, Backtriebmittel …).",
		},
		{
			"fieldname": "kt_vegan",
			"label": "Vegan (V-Label)",
			"fieldtype": "Check",
			"insert_after": "kt_bio_erlaubt",
		},
		{
			"fieldname": "kt_vegetarisch",
			"label": "Vegetarisch (V-Label)",
			"fieldtype": "Check",
			"insert_after": "kt_vegan",
			"depends_on": "eval:!doc.kt_vegan",
		},
	],
	"Batch": [
		{
			"fieldname": "kt_mhd_vorgabe",
			"label": "MHD gekürzt auf",
			"fieldtype": "Date",
			"read_only": 1,
			"insert_after": "expiry_date",
			"description": "Kürzeres MHD für Kunde/Auftrag oder am Terminal gekürzt. Das MHD ist das Frühere aus diesem Wert und der Berechnung.",
		},
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
			"fieldname": "kt_kennzeichen",
			"label": "Kennzeichen",
			"fieldtype": "Data",
			"read_only": 1,
			"in_standard_filter": 1,
			"insert_after": "kt_los",
			"description": "Bio / Vegan / Vegetarisch dieser Charge, aus Wareneingang bzw. allen Zutaten abgeleitet.",
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
	"Warehouse": [
		{
			"fieldname": "kt_umlagerziel",
			"label": "Ziel beim Umlagern am Terminal",
			"fieldtype": "Check",
			"insert_after": "warehouse_name",
			"description": "Dieser Lagerort steht am Terminal beim Umlagern zur Auswahl.",
		},
		{
			"fieldname": "kt_lagerverkauf",
			"label": "Lagerverkauf (Endverbraucher)",
			"fieldtype": "Check",
			"insert_after": "kt_umlagerziel",
			"description": "Ware hier ist für den Lagerverkauf: daraus wird nicht an Kunden geliefert und nicht weiter umgelagert.",
		},
	],
	"Customer": [
		{
			"fieldname": "kt_mhd_monate",
			"label": "MHD auf dem Etikett höchstens (Monate)",
			"fieldtype": "Int",
			"insert_after": "customer_group",
			"description": "Leer = volles MHD. Gezählt ab dem Verpackungstag; nie länger als laut Rohstoffen und Haltbarkeit.",
		},
	],
	"Sales Order": [
		{
			"fieldname": "kt_mhd_monate",
			"label": "MHD auf dem Etikett höchstens (Monate)",
			"fieldtype": "Int",
			"insert_after": "po_no",
			"description": "Nur für diesen Auftrag. Leer = Wert am Kunden.",
		},
	],
	"Supplier": [
		{
			"fieldname": "kt_bio_kontrollstelle",
			"label": "Öko-Kontrollstelle (Code)",
			"fieldtype": "Data",
			"insert_after": "supplier_group",
			"description": "z. B. DE-ÖKO-006. Ohne Eintrag wird Bio-Ware dieses Lieferanten nicht angenommen.",
		},
		{
			"fieldname": "kt_bio_gueltig_bis",
			"label": "Öko-Zertifikat gültig bis",
			"fieldtype": "Date",
			"insert_after": "kt_bio_kontrollstelle",
		},
		{
			"fieldname": "kt_bio_zertifikat",
			"label": "Öko-Zertifikat (Datei)",
			"fieldtype": "Attach",
			"insert_after": "kt_bio_gueltig_bis",
		},
	],
	"Stock Entry": [
		{
			"fieldname": "kt_produktionsauftrag",
			"label": "Produktionsauftrag",
			"fieldtype": "Link",
			"options": "Produktionsauftrag",
			"read_only": 1,
			"insert_after": "kt_station",
		},
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
		{
			"fieldname": "kt_anzahl",
			"label": "Gezählt (Anzahl)",
			"fieldtype": "Float",
			"read_only": 1,
			"insert_after": "kt_palette",
			"description": "Am Terminal gezählt, z. B. 20 Karton (Menge im Lieferschein kann in Paletten stehen).",
		},
		{
			"fieldname": "kt_einheit",
			"label": "Gezählt (Einheit)",
			"fieldtype": "Link",
			"options": "UOM",
			"read_only": 1,
			"insert_after": "kt_anzahl",
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
	_stationen_vorbelegen()
	_genauigkeit()


def _einheiten():
	"""Zähleinheiten für Fertigware (Umrechnung in kg steht am Artikel)."""
	# Palette und Lage dürfen gebrochen sein (20 Karton = 0,48 Palette im Lieferschein)
	for uom, ganz in (("Palette", 0), ("Lage", 0), ("Karton", 1), ("Beutel", 1)):
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": ganz}).insert(
				ignore_permissions=True
			)
		elif frappe.db.get_value("UOM", uom, "must_be_whole_number") != ganz:
			frappe.db.set_value("UOM", uom, "must_be_whole_number", ganz)


def _buchungsarten():
	for name in ("Silo Differenz", "Abverkauf Lagerverkauf", "Linienrest"):
		if not frappe.db.exists("Stock Entry Type", name):
			frappe.get_doc({"doctype": "Stock Entry Type", "name": name, "purpose": "Material Issue"}).insert(
				ignore_permissions=True
			)


def _aenderungsprotokoll():
	"""Jede Änderung an Chargen und Artikeln wird mit Vorher/Nachher protokolliert (IFS 2.1.2.1)."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype in ("Batch", "Item"):  # eigene DocTypes haben track_changes bereits
		make_property_setter(
			doctype, None, "track_changes", 1, "Check", for_doctype=True, validate_fields_for_doctype=False
		)


# Aufträge in Paletten: 20 Karton = 0,476190 Palette. Mit 3 Nachkommastellen würden daraus 79,97 kg.
GENAU = {
	"Delivery Note Item": ("qty", "stock_qty", "received_qty"),
	"Sales Invoice Item": ("qty", "stock_qty"),
	"Sales Order Item": ("delivered_qty", "returned_qty", "work_order_qty"),
}


def _genauigkeit():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype, felder in GENAU.items():
		vorhanden = {f.fieldname for f in frappe.get_meta(doctype).fields}
		for feld in felder:
			if feld in vorhanden:
				make_property_setter(
					doctype, feld, "precision", "6", "Select", validate_fields_for_doctype=False
				)


def _stationen_vorbelegen():
	"""Bestehende Stationen ohne Funktionen bekommen die Vorlage ihres Typs (Update auf einstellbare Stationen)."""
	if not frappe.db.has_column("Terminal Station", "f_herstellen"):
		return
	from keks_trace.keks_trace.doctype.terminal_station.terminal_station import FUNKTIONEN, vorbelegen

	for name in frappe.get_all("Terminal Station", pluck="name"):
		s = frappe.get_doc("Terminal Station", name)
		if not any(s.get(f) for f in FUNKTIONEN):
			vorbelegen(s)
			s.save(ignore_permissions=True)


def _lager_einstellungen():
	"""Chargenverwaltung muss in ERPNext aktiv sein, sonst lassen sich keine Chargenartikel anlegen."""
	for feld in ("enable_serial_and_batch_no_for_item", "use_serial_batch_fields"):
		if not frappe.db.get_single_value("Stock Settings", feld):
			frappe.db.set_single_value("Stock Settings", feld, 1)
