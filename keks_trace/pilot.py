"""Pilotartikel Honig Lebkuchen: echte Rezepturen 5812 und 5888, Rest Platzhalter.

Echt (aus Rezeptur und Spezifikation):
- Grundteig Honig 100 % (5812): Zitronensäurelösung 1,14 / Weizenmehl 812 lose 109 / Honig Knigge 90 kg
- Honig Moppen (5888): Grundteig 200 / ABC-Trieb 1 / Pottasche gelöst 1 / Palmfett 5 /
  Lebkuchengewürz VCS 0,9 / Acrylaway 0,03 / Karamellzuckersirup 0,65 kg; Backverlust 208,58 -> 188,687 kg
- Honig Lebkuchen Beutel 17846 (Gewicht/Aufbau siehe PLATZHALTER), Karton 17670, EAN Beutel 4032744178468, Karton 04032744176709,
  MHD 32 Monate, Allergene Gluten, Los JWWT
- Verpackung je Beutel: Schlauchbeutel OPP, 2 Etiketten, 1 Clip

PLATZHALTER (ausgedacht, bitte ersetzen): siehe PLATZHALTER unten.

Anlegen:     bench --site <site> execute keks_trace.pilot.anlegen
Durchspielen: bench --site <site> execute keks_trace.pilot.durchspielen
"""

import frappe
from frappe.utils import add_days, flt, nowdate

from keks_trace import demo

PLATZHALTER = {
	"Beutel 17846 netto": "200 g",
	"Aufbau 17846": "20 Beutel je Karton (4 kg), 6 Karton je Lage, 7 Lagen = 42 Karton = 168 kg je Palette (Beispiel)",
	"zweite Beutelgröße": "17847 Honig Lebkuchen 250 g, 20 Beutel je Karton, 48 Karton je Palette, ohne EAN",
	"Zitronensäurelösung 1144": "aus 0,5 kg Zitronensäure 1143 je 1 kg (Wasser nicht chargenpflichtig)",
	"Pottasche gelöst 1145": "aus 0,5 kg Pottasche 1146 je 1 kg",
	"Ruhezeit Grundteig Honig": "120 Tage",
	"Standzeit Honig Moppen Teig": "2 Tage",
	"lose Ware Honig Moppen": "Artikel 5888-LOSE, max. 12 Monate ab Backtag",
	"Gebindegrößen": "Mehl Silo, Honig IBC 1250 kg, Karamell Fass 300 kg, Sackware 25 kg, Gewürz Eimer 10 kg",
	"Packmittel": "9101 Schlauchbeutel OPP, 9102 Etikett, 9103 Clip (Stück)",
	"MHD zählt ab": "Backtag (umstellbar am Artikel)",
}

# Artikel: (Name, Stufe, Lagereinheit, Haltbarkeit Tage, Monate, Allergengruppe)
ARTIKEL = {
	"4974": ("Weizenmehl 812 lose", "Rohstoff", "Kg", 270, None, None),
	"7853": ("Honig, Knigge", "Rohstoff", "Kg", 730, None, None),
	"1143": ("Zitronensäure", "Rohstoff", "Kg", 1095, None, None),
	"1146": ("Pottasche (Kaliumcarbonat)", "Rohstoff", "Kg", 1095, None, None),
	"4150": ("ABC-Trieb", "Rohstoff", "Kg", 730, None, None),
	"6200": ("Palmfett 100 %", "Rohstoff", "Kg", 365, None, None),
	"7171": ("Lebkuchengewürz VCS", "Rohstoff", "Kg", 540, None, None),
	"1700": ("Acrylaway", "Rohstoff", "Kg", 365, None, None),
	"4042": ("Karamellzuckersirup", "Rohstoff", "Kg", 540, None, None),
	"9101": ("Schlauchbeutel OPP 35 µ", "Packmittel", "Nos", None, None, None),
	"9102": ("Etikett Honig Lebkuchen", "Packmittel", "Nos", None, None, None),
	"9103": ("Clip", "Packmittel", "Nos", None, None, None),
	"1144": ("Zitronensäurelösung", "Halbfabrikat", "Kg", 30, None, None),
	"1145": ("Pottasche gelöst", "Halbfabrikat", "Kg", 30, None, None),
	"5812": ("Grundteig Honig 100 %", "Grundteig", "Kg", 120, None, "Honigteig"),
	"5888": ("Honig Moppen Teig", "Teig veredelt", "Kg", 2, None, "Honigteig"),
	"5888-LOSE": ("Honig Moppen lose", "Ware lose", "Kg", None, 12, "Honigteig"),
	"17846": ("Honig Lebkuchen 200 g", "Fertigware", "Kg", None, 32, "Honigteig"),
	"17847": ("Honig Lebkuchen 250 g", "Fertigware", "Kg", None, 32, "Honigteig"),
	"RW-HONIG": ("Rework Honigteig / Bruch", "Rework", "Kg", 14, None, "Honigteig"),
}

PREISE = {"4974": 0.45, "7853": 3.2, "1143": 2.0, "1146": 1.8, "4150": 1.5, "6200": 1.6, "7171": 9.0,
          "1700": 60.0, "4042": 1.9, "9101": 0.03, "9102": 0.01, "9103": 0.01}  # fmt: skip

# Rezepte: Artikel -> (Ausbringung, [(Zutat, Menge)]) in Lagereinheit
REZEPTE = {
	"1144": (1, [("1143", 0.5)]),
	"1145": (1, [("1146", 0.5)]),
	"5812": (200.14, [("1144", 1.14), ("4974", 109), ("7853", 90)]),
	"5888": (208.58, [("5812", 200), ("4150", 1), ("1145", 1), ("6200", 5), ("7171", 0.9), ("1700", 0.03), ("4042", 0.65)]),
	"5888-LOSE": (188.687, [("5888", 208.58)]),
	# Fertigware je Karton: 12 x 500 g bzw. 20 x 250 g
	"17846": (4, [("5888-LOSE", 4), ("9101", 20), ("9102", 40), ("9103", 20)]),
	"17847": (5, [("5888-LOSE", 5), ("9101", 20), ("9102", 40), ("9103", 20)]),
}  # fmt: skip

# Fertigware: Einheit -> (kg, EAN oder None)
VERPACKUNG = {
	"17846": {
		"Beutel": (0.2, "4032744178468"),
		"Karton": (4.0, "04032744176709"),
		"Lage": (24.0, None),
		"Palette": (168.0, None),
	},
	"17847": {"Beutel": (0.25, None), "Karton": (5.0, None), "Lage": (40.0, None), "Palette": (240.0, None)},
}

SILO = ("Silo Weizenmehl 812", "4974", 150, 30000)


def anlegen(company: str | None = None) -> frappe._dict:
	ctx = demo.stammdaten(company)  # Stationen, Kunde, Lieferant, Einheiten
	if not frappe.db.exists("Allergengruppe", "Honigteig"):
		frappe.get_doc({"doctype": "Allergengruppe", "gruppe": "Honigteig", "allergene": "Gluten"}).insert()

	gruppe = demo._blatt("Item Group", "Products")
	for code, (name, stufe, uom, tage, monate, allergene) in ARTIKEL.items():
		werte = {
			"item_name": name,
			"kt_chargen_stufe": stufe,
			"kt_allergengruppe": allergene,
			"has_expiry_date": 1 if (tage or monate) else 0,
			"shelf_life_in_days": tage or 0,
			"kt_mhd_monate": monate or 0,
			"kt_mhd_bezug": "Backtag" if stufe in ("Ware lose", "Fertigware") else None,
		}
		if frappe.db.exists("Item", code):
			item = frappe.get_doc("Item", code)
			item.update(werte)
			item.save()
			continue
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_group": gruppe,
				"stock_uom": uom,
				"is_stock_item": 1,
				"include_item_in_manufacturing": 1,
				"has_batch_no": 1,
				"valuation_rate": PREISE.get(code, 0),
				**werte,
			}
		).insert()

	for code, einheiten in VERPACKUNG.items():
		item = frappe.get_doc("Item", code)
		for uom, (kg, ean) in einheiten.items():
			vorhanden = next((u for u in item.uoms if u.uom == uom), None)
			if vorhanden:
				vorhanden.conversion_factor = kg
			else:
				item.append("uoms", {"uom": uom, "conversion_factor": kg})
			ean = (ean.lstrip("0") if ean and len(ean) == 14 else ean) or None  # GTIN-14 mit 0 = EAN-13
			if ean and not frappe.db.exists("Item Barcode", {"barcode": ean}):
				item.append("barcodes", {"barcode": ean, "barcode_type": "EAN", "uom": uom})
		item.sales_uom = "Karton"
		item.save()

	for artikel, (menge, zutaten) in REZEPTE.items():
		_rezept(ctx.company, artikel, menge, zutaten)

	if not frappe.db.exists("Rework Regel", {"rework_artikel": "RW-HONIG", "ziel_artikel": "5888"}):
		frappe.get_doc(
			{
				"doctype": "Rework Regel",
				"rework_artikel": "RW-HONIG",
				"ziel_artikel": "5888",
				"max_anteil_prozent": 5,
			}
		).insert()

	bezeichnung, artikel, nachlauf, kapazitaet = SILO
	lager = f"{bezeichnung} - {ctx.abbr}"
	if not frappe.db.exists("Warehouse", lager):
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": bezeichnung,
				"company": ctx.company,
				"parent_warehouse": ctx.wurzel,
			}
		).insert()
	if not frappe.db.exists("Silo", bezeichnung):
		frappe.get_doc(
			{"doctype": "Silo", "silo_name": bezeichnung, "warehouse": lager, "artikel": artikel,
			 "nachlauf": nachlauf, "kapazitaet": kapazitaet, "typ": "Silo"}
		).insert()  # fmt: skip
	frappe.cache.delete_value("kt_silo_lager")

	for code, typ in [("TB-H1", "Teigbehälter"), ("TB-H2", "Teigbehälter"), ("TB-H3", "Teigbehälter"),
	                  ("KL-H1", "Kiste lose Ware"), ("KL-H2", "Kiste lose Ware"), ("RB-H1", "Rework-Behälter")]:  # fmt: skip
		demo.neuer_traeger(code, typ)

	ctx.auftrag = kundenauftrag(ctx)
	frappe.db.commit()
	print(f"Pilot Honig Lebkuchen angelegt, Kundenauftrag {ctx.auftrag}. PLATZHALTER (bitte prüfen):")
	for k, v in PLATZHALTER.items():
		print(f"  - {k}: {v}")
	return ctx


def kundenauftrag(ctx, neu: bool = False) -> str:
	"""Offener Beispiel-Kundenauftrag: 5 Paletten 200 g und 10 Karton 250 g (Platzhalter-Preise)."""
	if not neu:
		offen = frappe.db.get_value(
			"Sales Order",
			{
				"customer": ctx.kunde,
				"docstatus": 1,
				"status": ["not in", ["Completed", "Closed"]],
				"po_no": "PILOT-PAL",
			},
		)
		if offen:
			return offen
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": ctx.kunde,
			"company": ctx.company,
			"po_no": "PILOT-PAL" if not neu else f"PILOT-PAL-{frappe.generate_hash(length=4)}",
			"transaction_date": nowdate(),
			"delivery_date": add_days(nowdate(), 7),
			"items": [
				{"item_code": "17846", "qty": 5, "uom": "Palette", "conversion_factor": 168, "rate": 1008.0,
				 "warehouse": ctx.fertig, "delivery_date": add_days(nowdate(), 7)},
				{"item_code": "17847", "qty": 10, "uom": "Karton", "conversion_factor": 5, "rate": 24.0,
				 "warehouse": ctx.fertig, "delivery_date": add_days(nowdate(), 7)},
			],
		}
	)  # fmt: skip
	so.insert()
	so.submit()
	return so.name


def _rezept(company, artikel, menge, zutaten):
	vorhanden = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "docstatus": 1})
	if vorhanden:
		alt = {
			(z.item_code, flt(z.qty))
			for z in frappe.get_all("BOM Item", {"parent": vorhanden}, ["item_code", "qty"])
		}
		if (
			alt == {(z, flt(q)) for z, q in zutaten}
			and flt(frappe.db.get_value("BOM", vorhanden, "quantity")) == menge
		):
			return
	bom = frappe.get_doc(
		{
			"doctype": "BOM",
			"item": artikel,
			"quantity": menge,
			"company": company,
			"is_active": 1,
			"is_default": 1,
			"rm_cost_as_per": "Valuation Rate",
			"items": [
				{"item_code": z, "qty": q, "uom": frappe.get_cached_value("Item", z, "stock_uom")}
				for z, q in zutaten
			],
		}
	)
	bom.insert()
	bom.submit()


def durchspielen():
	"""Einen Produktionstag Honig Lebkuchen über die Terminal-Schnittstelle buchen und zurückverfolgen."""
	from keks_trace import palette, terminal
	from keks_trace.trace import rueckverfolgung

	ctx = anlegen()
	k = frappe.generate_hash(length=4).upper()
	mhd = add_days(nowdate(), 365)

	def we(artikel, menge, gebinde=None, art=None, silo=None):
		return terminal.wareneingang(
			"Lager", artikel, f"{artikel}-{k}", menge, mhd, gebinde=gebinde, gebindeart=art, silo=silo
		)

	mehl = we("4974", 2000, silo=SILO[0])
	honig = we("7853", 1250, 1, "IBC")
	saeure = we("1143", 25, 1, "Sack")
	pott = we("1146", 25, 1, "Sack")
	abc = we("4150", 25, 1, "Sack")
	fett = we("6200", 25, 1, "Karton")
	gewuerz = we("7171", 10, 1, "Eimer")
	acryl = we("1700", 5, 1, "Kanister")
	karamell = we("4042", 300, 1, "Fass")
	folie = we("9101", 1000, 1, "Karton")
	etikett = we("9102", 2000, 1, "Karton")
	clip = we("9103", 1000, 1, "Karton")
	print("Wareneingang: Gebinde", ", ".join(x["gebinde"][0] for x in (honig, saeure, abc, karamell)), "…")

	def herstellen(station, ziel, zeilen, **kw):
		e = terminal.herstellen(station, ziel, [{"code": c, "menge": m} for c, m in zeilen], **kw)
		print(f"  {station}: {e['name']} -> {e['charge']} {e['menge']} kg" + (f" MHD {e['mhd']}" if e["mhd"] else "")
		      + (f" Los {e['los']}" if e.get("los") else "") + (f" Palette {e['palette']}" if e.get("palette") else ""))  # fmt: skip
		for h in e["hinweise"]:
			print("     Hinweis:", h)
		return e

	tb1, tb2, kl = (f"TB-H1-{k}", f"TB-H2-{k}", f"KL-H1-{k}")
	for code, typ in ((tb1, "Teigbehälter"), (tb2, "Teigbehälter"), (kl, "Kiste lose Ware")):
		demo.neuer_traeger(code, typ)

	zs = herstellen("Backstube", "1144", [(saeure["gebinde"][0], 1)], ausbringung=2)
	pg = herstellen("Backstube", "1145", [(pott["gebinde"][0], 0.5)], ausbringung=1)
	herstellen(
		"Backstube",
		"5812",
		[(zs["charge"], 1.14), (SILO[0], 109), (honig["gebinde"][0], 90)],
		ziel_behaelter=tb1,
	)
	tv = herstellen(
		"Backstube", "5888",
		[(tb1, 200), (abc["gebinde"][0], 1), (pg["charge"], 1), (fett["gebinde"][0], 5),
		 (gewuerz["gebinde"][0], 0.9), (acryl["gebinde"][0], 0.03), (karamell["gebinde"][0], 0.65)],
		ziel_behaelter=tb2,
	)  # fmt: skip
	herstellen("Backstube", "5888-LOSE", [(tb2, tv["menge"])], ziel_behaelter=kl)
	p = terminal.palette_neu("Verpackung")["nve"]
	fw = herstellen(
		"Verpackung", "17846",
		[(kl, 80), (folie["gebinde"][0], 400), (etikett["gebinde"][0], 800), (clip["gebinde"][0], 400)],
		anzahl=20, einheit="Karton", ziel_behaelter=p, kundenauftrag=ctx.auftrag,
	)  # fmt: skip
	ls = terminal.lieferung("Versand", ctx.kunde, [{"palette": p, "ganz": 1}], kundenauftrag=ctx.auftrag)
	so = frappe.get_doc("Sales Order", ctx.auftrag)
	print(f"  Kundenauftrag {so.name}: {so.per_delivered:.0f} % geliefert, Status {so.status}")
	print(f"  Versand: Lieferschein {ls['lieferschein']} an {ls['kunde']}, Palette {p}")

	r = rueckverfolgung(mehl["charge"], "Vorwärts")
	print(f"\nVorwärts von Mehl {mehl['charge']}: " + ", ".join(c["charge"] for c in r["chargen"]))
	print("  Kunden:", ", ".join(f"{x.kundenname} {x.lieferschein}" for x in r["kunden"]))
	print("  Paletten:", ", ".join(x.palette for x in r["paletten"]))
	r = rueckverfolgung(fw["charge"], "Rückwärts")
	print(f"Rückwärts von Los {fw['los']} ({fw['charge']}): " + ", ".join(c["charge"] for c in r["chargen"]))
	print(f"Etikett: /nve_etikett?nve={p}  (Inhalt laut System: {palette.info(p)['kartons'] or 'versendet'})")
	frappe.db.commit()
