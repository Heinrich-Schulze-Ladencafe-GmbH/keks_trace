"""Demo Backstraße: Linie, Abschnitte mit Leistung, Stationen, Kübel, drei Großkunden, Planung.

    bench --site keks.localhost execute keks_trace.demo_linie.anlegen

Alle Zahlen sind Demo-Werte (bitte durch echte ersetzen): Leistungen je Abschnitt, Laufzeit 8 h,
Umrüstzeit 30 min, Großkunden A/B/C mit 120.000 / 80.000 / 50.000 Beuteln Honig Lebkuchen 200 g.
"""

import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from keks_trace import demo, pilot, planung

LINIE = "Backstraße"

# (Name, Art, Reihenfolge) - Reihenfolge laut Produktion, bitte mit dem Fließdiagramm abgleichen
ABSCHNITTE = [
	("Formen", "Prozess"),
	("Backen", "Prozess"),
	("Spicken", "Prozess"),
	("Hacken", "Prozess"),
	("Streichen", "Prozess"),
	("Füllen", "Prozess"),
	("Sprühen", "Prozess"),
	("Glasieren", "Prozess"),
	("Trocknen", "Prozess"),
	("Schoko 1", "Prozess"),
	("Kühlen 1", "Prozess"),
	("Streuseln", "Prozess"),
	("Schoko 2", "Prozess"),
	("Kühlen 2", "Prozess"),
	("Manuelles Band", "Verpackungsanlage"),
	("InoTec", "Verpackungsanlage"),
	("Thürlings", "Verpackungsanlage"),
	("Carina", "Verpackungsanlage"),
]

# Demo-Leistungen: Honig Lebkuchen wird geformt, gebacken, glasiert, getrocknet; Engpass Trocknen
LEISTUNG = {
	"17846": [
		("Formen", 300, "kg/h"),
		("Backen", 220, "kg/h"),
		("Glasieren", 180, "kg/h"),
		("Trocknen", 125, "kg/h"),
		("InoTec", 40, "Beutel/min"),
		("Thürlings", 30, "Beutel/min"),
		("Manuelles Band", 30, "Karton/h"),
	],
	"17847": [
		("Formen", 300, "kg/h"),
		("Backen", 220, "kg/h"),
		("Glasieren", 180, "kg/h"),
		("Trocknen", 110, "kg/h"),
		("Carina", 25, "Beutel/min"),
		("Manuelles Band", 25, "Karton/h"),
	],
}

STATIONEN = [
	("Former", "Former"),
	("Nachfüllen Füllung", "Nachfüllen"),
	("Nachfüllen Glasur", "Nachfüllen"),
	("Nachfüllen Schoko 1", "Nachfüllen"),
	("Nachfüllen Schoko 2", "Nachfüllen"),
	("Nachfüllen Streusel", "Nachfüllen"),
	("Packstation", "Packstation"),
	("Paletten-Terminal", "Paletten-Terminal"),
]

GROSSKUNDEN = [
	("Großkunde A (Demo)", 120000, 42),
	("Großkunde B (Demo)", 80000, 70),
	("Großkunde C (Demo)", 50000, 84),
]

KUEBEL = 40

# Jede Verpackungsanlage hat einen eigenen Metalldetektor (CCP, HACCP-Schritt 20)
METALLCHECK_ANLAGEN = ["InoTec", "Thürlings", "Carina", "Manuelles Band"]


def stammdaten() -> frappe._dict:
	ctx = pilot.anlegen()
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
				"umruestzeit_minuten": 30,
				"durchlauf_minuten": 45,
				"lagerort": lager,
				"fertiglager": ctx.fertig,
			}
		).insert()
	# Kalfass verpackt die garnierten Herzen am Herzenboden (eigene Station, nicht an der Backstraße)
	if not frappe.db.exists("Linienabschnitt", "Kalfass"):
		frappe.get_doc(
			{"doctype": "Linienabschnitt", "abschnitt_name": "Kalfass", "art": "Verpackungsanlage",
			 "beschreibung": "Verpackung garnierte Herzen (Herzenboden), Metallcheck Fe 2,8 mm"}
		).insert()  # fmt: skip
	for i, (name, art) in enumerate(ABSCHNITTE, 1):
		if not frappe.db.exists("Linienabschnitt", name):
			frappe.get_doc(
				{
					"doctype": "Linienabschnitt",
					"abschnitt_name": name,
					"art": art,
					"linie": LINIE,
					"reihenfolge": i,
				}
			).insert()
	for anlage in METALLCHECK_ANLAGEN:
		titel = f"Metallcheck {anlage}"
		if not frappe.db.exists("Pruefplan", titel):
			frappe.get_doc(
				{
					"doctype": "Pruefplan",
					"titel": titel,
					"lenkung": "CCP",
					"ausloeser": "Regelmäßig an der Station",
					"intervall_minuten": 60,
					"sperrt_wenn_faellig": 1,
					"verpackungsanlage": anlage,
					"art": "Prüfkörper",
					"frage": f"{anlage}: Prüfkörper durch den Metalldetektor geschickt, erkannt?",
					"pruefkoerper": "Fe 2,5 mm\nBronze 2,5 mm\nMessing 2,5 mm\nEdelstahl 2,5 mm",
					"bei_abweichung": "Sperren",
					"korrekturmassnahme": "Ware seit der letzten OK-Prüfung sperren, Sperrprotokoll, Metalldetektor prüfen lassen",
					"dokument": "HACCP 20 Metallcheck, FO 3.10.12 Prüfprotokoll",
				}
			).insert()
	for artikel, zeilen in LEISTUNG.items():
		item = frappe.get_doc("Item", artikel)
		if not item.get("kt_linienleistung"):
			for abschnitt, leistung, einheit in zeilen:
				item.append(
					"kt_linienleistung", {"abschnitt": abschnitt, "leistung": leistung, "einheit": einheit}
				)
			item.save()
	for name, typ in STATIONEN:
		if not frappe.db.exists("Terminal Station", name):
			frappe.get_doc(
				{
					"doctype": "Terminal Station",
					"station_name": name,
					"typ": typ,
					"company": ctx.company,
					"linie": LINIE,
					"rohstofflager": ctx.lager,
					"produktionslager": ctx.produktion,
					"fertiglager": ctx.fertig,
				}
			).insert()
	for n in range(1, KUEBEL + 1):
		demo.neuer_traeger(f"K-{n:03d}", "Teigbehälter")
	for name, _menge, _tage in GROSSKUNDEN:
		if not frappe.db.exists("Customer", name):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_group": demo._blatt("Customer Group", "Commercial"),
					"territory": demo._blatt("Territory", None),
				}
			).insert()
	return frappe._dict({**ctx, "linie": LINIE, "linienlager": lager})


def grossauftraege(ctx) -> list[str]:
	"""Drei Großkunden bestellen zusammen 250.000 Beutel Honig Lebkuchen 200 g (Demo)."""
	namen = []
	for kunde, beutel, tage in GROSSKUNDEN:
		offen = frappe.db.get_value(
			"Sales Order",
			{
				"customer": kunde,
				"docstatus": 1,
				"po_no": "DEMO-GROSS",
				"status": ["not in", ["Completed", "Closed"]],
			},
		)
		if offen:
			namen.append(offen)
			continue
		termin = add_days(nowdate(), tage)
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": kunde,
				"company": ctx.company,
				"po_no": "DEMO-GROSS",
				"transaction_date": nowdate(),
				"delivery_date": termin,
				"items": [
					{"item_code": "17846", "qty": beutel, "uom": "Beutel", "conversion_factor": 0.2, "rate": 0.65,
					 "warehouse": ctx.fertig, "delivery_date": termin},
				],
			}
		)  # fmt: skip
		so.insert()
		so.submit()
		namen.append(so.name)
	return namen


def kuebel_fuellen(ctx, anzahl: int = 6):
	"""Anfangsbestand: veredelter Honigteig 5888 in Kübeln, unterschiedlich alt (für „ältester zuerst“)."""
	frei = frappe.get_all(
		"Produkttraeger",
		{"typ": "Teigbehälter", "status": "Frei", "code": ["like", "K-%"]},
		pluck="code",
		order_by="code",
	)
	for i, code in enumerate(frei[:anzahl]):
		tag = add_days(nowdate(), -(anzahl - i) // 3)
		charge = demo.neue_charge("5888", f"5888-{getdate(tag).strftime('%y%m%d')}-{code}", tag)
		demo.buchen(ctx, "Material Receipt", tag, "05:00:00", ausgaenge=[("5888", charge, 200, code)])


@frappe.whitelist()
def anlegen(planen: int = 1) -> dict:
	ctx = stammdaten()
	auftraege = grossauftraege(ctx)
	kuebel_fuellen(ctx)
	ergebnis = {"kundenauftraege": auftraege}
	if planen and not frappe.db.exists(
		"Produktionsauftrag", {"linie": LINIE, "status": ["!=", "Abgebrochen"]}
	):
		v = planung.vorschlag(LINIE, ab=nowdate())
		erste = frappe.get_all(
			"Produktionsauftrag", {"linie": LINIE}, pluck="datum", order_by="datum asc", limit=1
		)
		heute = erste[0] if erste else None
		ergebnis.update(v)
		if heute:
			ergebnis["freigegeben"] = planung.tag_freigeben(LINIE, heute)["freigegeben"]
	frappe.db.commit()
	tage = frappe.db.count("Produktionsauftrag", {"linie": LINIE})
	print(f"Backstraße angelegt: {tage} Produktionsaufträge, Kundenaufträge {', '.join(auftraege)}")
	print(
		f"Leistung 17846: {flt(frappe.db.get_value('Item', '17846', 'kt_leistung_kg_h'), 1)} kg/h, Engpass {frappe.db.get_value('Item', '17846', 'kt_engpass')}"
	)
	return ergebnis


def metallcheck_ok(station: str = "Packstation"):
	"""Bestandenen Metallcheck der Anlage erfassen, auf der an der Station gerade verpackt wird (Demo, Tests)."""
	from keks_trace import pruefung

	for p in pruefung.fuer_station(station):
		if p.get("verpackungsanlage"):
			pruefung.erfassen(station, p.name, {"koerper": {k: True for k in p.koerper()}})
