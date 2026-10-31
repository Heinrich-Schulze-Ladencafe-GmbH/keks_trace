"""Demo Herzenboden: garnierte Lebkuchenherzen in Stück, drei Größen (Platzhalter).

    bench --site keks.localhost execute keks_trace.demo_herzen.anlegen

Ablauf: Rohling backen (Backstube, aus Grundteig Honig 5812) -> Zuckerglasur kochen (eigene
Rezeptur, Halbfabrikat, max. 2 Tage) -> Garnieren (Herzen Garnieren: Rohling + Glasur) ->
Verpacken auf der Kalfass (Herzen Verpackung: Herz + Folie + Etikett + Schleife, Metallcheck Fe 2,8 mm).
Gezählt wird in Stück; jede Größe ist ein eigener Artikel mit eigener Rezeptur.
"""

import frappe

from keks_trace import demo, pilot

# Größe: (Teig je Rohling kg, Glasur je Herz kg) - Platzhalter
GROESSEN = {"12": (0.05, 0.01), "18": (0.12, 0.02), "25": (0.25, 0.04)}

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
			frappe.db.set_value("Terminal Station", station, "linie", LINIE)
			frappe.clear_document_cache("Terminal Station", station)


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
	frappe.db.commit()
	return ctx
