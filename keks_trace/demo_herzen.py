"""Demo Herzenboden: garnierte Lebkuchenherzen in Stück, drei Größen (Platzhalter).

    bench --site keks.localhost execute keks_trace.demo_herzen.anlegen

Ablauf: Rohling backen (Backstube, aus Grundteig Honig 5812) -> Zuckerglasur kochen (eigene
Rezeptur, Halbfabrikat, max. 2 Tage) -> Garnieren (Herzen Garnieren: Rohling + Glasur) ->
Verpacken auf der Kalfass (Herzen Verpackung: Herz + Folie + Etikett + Schleife, Metallcheck Fe 2,8 mm).
Gezählt wird in Stück; jede Größe ist ein eigener Artikel mit eigener Rezeptur.
"""

import frappe
from frappe.utils import add_days, nowdate

from keks_trace import demo, pilot

# Größe: (Teig je Rohling kg, Glasur je Herz kg) - Platzhalter
GROESSEN = {"12": (0.05, 0.01), "18": (0.12, 0.02), "25": (0.25, 0.04)}

# Leistung je Größe in Stück: Garnieren (Stück/h), Kalfass (Stück/min) - Platzhalter
LEISTUNG = {"12": (1200, 30), "18": (800, 25), "25": (500, 20)}

# Demo-Kundenauftrag: der Kunde bestellt Herzen in Stück
AUFTRAG = {"12": 3000, "18": 2000, "25": 1000}

ROHSTOFFE = {
	"HZ-PUDERZUCKER": ("Puderzucker", 730),
	"HZ-EIWEISS": ("Eiweißpulver", 365),
}
PACKMITTEL = {"HZ-FOLIE": "Folie Herz", "HZ-ETIKETT": "Etikett Herz", "HZ-SCHLEIFE": "Schleife"}


def _artikel(code, name, stufe, uom, tage=None, monate=None, extra=None):
	werte = {
		"item_name": name,
		"kt_chargen_stufe": stufe,
		"has_expiry_date": 1 if (tage or monate) else 0,
		"shelf_life_in_days": tage or 0,
		"kt_mhd_monate": monate or 0,
		"kt_allergengruppe": "Honigteig" if stufe in ("Backware", "Ware lose", "Fertigware") else None,
		**(extra or {}),
	}
	if frappe.db.exists("Item", code):
		item = frappe.get_doc("Item", code)
		item.update(werte)
		item.save()  # validate rechnet Monate in Tage um
		return
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_group": demo._blatt("Item Group", "Products"),
			"stock_uom": uom,
			"is_stock_item": 1,
			"include_item_in_manufacturing": 1,
			"has_batch_no": 1,
			"valuation_rate": 1,
			**werte,
		}
	).insert()


LINIE = "Herzenboden"


def _linie(ctx):
	abbr = frappe.get_cached_value("Company", ctx.company, "abbr")
	lager = f"{LINIE} - {abbr}"
	if not frappe.db.exists("Warehouse", lager):
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": LINIE,
				"company": ctx.company,
				"parent_warehouse": ctx.wurzel,
			}
		).insert()
	if not frappe.db.exists("Linie", LINIE):
		frappe.get_doc(
			{
				"doctype": "Linie",
				"linie_name": LINIE,
				"company": ctx.company,
				"laufzeit_stunden": 8,
				"umruestzeit_minuten": 15,
				"durchlauf_minuten": 0,
				"lagerort": lager,
				"fertiglager": ctx.fertig,
			}
		).insert()
	if not frappe.db.exists("Linienabschnitt", "Garnieren"):
		frappe.get_doc(
			{"doctype": "Linienabschnitt", "abschnitt_name": "Garnieren", "art": "Prozess", "linie": LINIE}
		).insert()
	if not frappe.db.exists("Linienabschnitt", "Kalfass"):
		frappe.get_doc(
			{
				"doctype": "Linienabschnitt",
				"abschnitt_name": "Kalfass",
				"art": "Verpackungsanlage",
				"linie": LINIE,
			}
		).insert()
	frappe.db.set_value("Linienabschnitt", "Kalfass", "linie", LINIE)
	for station in ("Herzen Garnieren", "Herzen Verpackung"):
		if frappe.db.exists("Terminal Station", station):
			frappe.db.set_value("Terminal Station", station, {"linie": LINIE, "f_silo": 1})
			frappe.clear_document_cache("Terminal Station", station)


# Am Herzenboden ohne Scanner: Behälter und offene Kartons am Tisch (Silo-Typ Tank bzw. Vorrat am Tisch)
BEHAELTER = [
	("Zuckerguss Herzenboden", "HZ-GLASUR", "Tank", 1),  # Hauptmischung, morgens frisch; Farbgebinde daraus
	("Folie Herzenboden", "HZ-FOLIE", "Vorrat am Tisch", 0),
	("Etikett Herzenboden", "HZ-ETIKETT", "Vorrat am Tisch", 0),
	("Schleife Herzenboden", "HZ-SCHLEIFE", "Vorrat am Tisch", 0),
]


def _behaelter(ctx):
	for name, artikel, typ, nachlauf in BEHAELTER:
		lager = f"{name} - {ctx.abbr}"
		if not frappe.db.exists("Warehouse", lager):
			frappe.get_doc(
				{"doctype": "Warehouse", "warehouse_name": name, "company": ctx.company, "parent_warehouse": ctx.wurzel}
			).insert()  # fmt: skip
		if not frappe.db.exists("Silo", name):
			frappe.get_doc(
				{"doctype": "Silo", "silo_name": name, "typ": typ, "warehouse": lager, "artikel": artikel,
				 "nachlauf": nachlauf, "aktiv": 1}
			).insert()  # fmt: skip
	frappe.cache.delete_value("kt_silo_lager")


def anlegen() -> frappe._dict:
	ctx = pilot.anlegen()  # Grundteig Honig 5812, Allergengruppe Honigteig
	_linie(ctx)
	herz = {"kt_linie": LINIE}
	for code, (name, tage) in ROHSTOFFE.items():
		_artikel(code, name, "Rohstoff", "Kg", tage)
	for code, name in PACKMITTEL.items():
		_artikel(code, name, "Packmittel", "Nos")
	_artikel(
		"HZ-GLASUR", "Zuckerglasur (eigene Herstellung)", "Halbfabrikat", "Kg", 2,
		extra={"kt_mhd_nicht_begrenzend": 1, **herz},
	)  # fmt: skip
	pilot._rezept(ctx.company, "HZ-GLASUR", 10, [("HZ-PUDERZUCKER", 9.5), ("HZ-EIWEISS", 0.5)])
	for g, (teig, glasur) in GROESSEN.items():
		_artikel(f"HZ-ROHLING-{g}", f"Herz-Rohling {g} cm", "Backware", "Nos", 180)
		_artikel(f"HZ-GARNIERT-{g}", f"Herz {g} cm garniert", "Ware lose", "Nos", 180, extra=herz)
		_artikel(f"HZ-{g}", f"Lebkuchenherz {g} cm", "Fertigware", "Nos", monate=9,
				 extra={"kt_mhd_bezug": "Backtag", **herz})  # fmt: skip
		pilot._rezept(ctx.company, f"HZ-ROHLING-{g}", 1, [("5812", teig)])
		pilot._rezept(ctx.company, f"HZ-GARNIERT-{g}", 1, [(f"HZ-ROHLING-{g}", 1), ("HZ-GLASUR", glasur)])
		pilot._rezept(
			ctx.company, f"HZ-{g}", 1,
			[(f"HZ-GARNIERT-{g}", 1), ("HZ-FOLIE", 1), ("HZ-ETIKETT", 1), ("HZ-SCHLEIFE", 1)],
		)  # fmt: skip
	for g, (garnieren, kalfass) in LEISTUNG.items():
		item = frappe.get_doc("Item", f"HZ-{g}")
		if not item.get("kt_linienleistung"):
			item.append(
				"kt_linienleistung", {"abschnitt": "Garnieren", "leistung": garnieren, "einheit": "Stück/h"}
			)
			item.append(
				"kt_linienleistung", {"abschnitt": "Kalfass", "leistung": kalfass, "einheit": "Stück/min"}
			)
			item.save()
	_behaelter(ctx)
	auftrag = kundenauftrag(ctx)
	if not frappe.db.exists("Produktionsauftrag", {"linie": LINIE}):
		from keks_trace import planung

		planung.vorschlag(LINIE, ab=nowdate())
	frappe.db.commit()
	ctx.herz_auftrag = auftrag
	return ctx


def kundenauftrag(ctx) -> str:
	"""Der Kunde bestellt Herzen in Stück (Demo)."""
	offen = frappe.db.get_value(
		"Sales Order", {"po_no": "DEMO-HERZEN", "docstatus": 1, "status": ["not in", ["Completed", "Closed"]]}
	)
	if offen:
		return offen
	termin = add_days(nowdate(), 21)
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": ctx.kunde,
			"company": ctx.company,
			"po_no": "DEMO-HERZEN",
			"transaction_date": nowdate(),
			"delivery_date": termin,
			"items": [
				{"item_code": f"HZ-{g}", "qty": n, "uom": "Nos", "conversion_factor": 1, "rate": 1.5,
				 "warehouse": ctx.fertig, "delivery_date": termin}
				for g, n in AUFTRAG.items()
			],
		}
	)  # fmt: skip
	so.insert()
	so.submit()
	return so.name
