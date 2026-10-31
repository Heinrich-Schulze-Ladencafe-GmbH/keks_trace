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


@frappe.whitelist()
def anlegen(vorrat: int = 1) -> frappe._dict:
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
	ctx.weitere_auftraege = weitere_auftraege(ctx)
	if int(vorrat):
		ctx.vorrat = vorrat_anlegen(ctx)
	frappe.db.commit()
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


# Weitere Kunden mit Herzen-Aufträgen (Demo): (Kunde, {Größe: Stück}, Tage bis Liefertermin, MHD höchstens Monate)
WEITERE = [
	("Markthändler Krause (Demo)", {"18": 400, "25": 150}, 10, 6),
	("Schaustellerbetrieb Lange (Demo)", {"12": 800, "18": 300}, 14, None),
]


def weitere_auftraege(ctx) -> list[str]:
	from keks_trace import demo

	namen = []
	for kunde, groessen, tage, mhd in WEITERE:
		if not frappe.db.exists("Customer", kunde):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": kunde, "customer_group": demo._blatt("Customer Group", "Commercial"),
				 "territory": demo._blatt("Territory", None), "kt_mhd_monate": mhd or 0}
			).insert()  # fmt: skip
		offen = frappe.db.get_value(
			"Sales Order",
			{
				"customer": kunde,
				"po_no": "DEMO-HERZEN",
				"docstatus": 1,
				"status": ["not in", ["Completed", "Closed"]],
			},
		)
		if offen:
			namen.append(offen)
			continue
		termin = add_days(nowdate(), tage)
		so = frappe.get_doc(
			{"doctype": "Sales Order", "customer": kunde, "company": ctx.company, "po_no": "DEMO-HERZEN",
			 "transaction_date": nowdate(), "delivery_date": termin,
			 "items": [{"item_code": f"HZ-{g}", "qty": n, "uom": "Nos", "conversion_factor": 1, "rate": 1.8,
			            "warehouse": ctx.fertig, "delivery_date": termin} for g, n in groessen.items()]}
		)  # fmt: skip
		so.insert()
		so.submit()
		namen.append(so.name)
	return namen


def _charge_mit(station, artikel, menge):
	from keks_trace import terminal

	for c in terminal.lager_chargen(station, artikel):
		if c["menge"] >= menge:
			return c["charge"]
	frappe.throw(f"Kein Los {artikel} mit mindestens {menge} im Lager")


def _bestand(artikel, lager=None) -> float:
	filters = {"item_code": artikel}
	if lager:
		filters["warehouse"] = lager
	return sum(frappe.get_all("Bin", filters=filters, pluck="actual_qty")) or 0


@frappe.whitelist()
def vorrat_anlegen(ctx=None) -> dict:
	"""Alles, was man zum Ausprobieren der Herzen-Terminals braucht, ohne erst selbst zu buchen:
	Puderzucker, Eiweiß und Packmittel im Lager, je ein Karton Folie/Etikett/Schleife angebrochen,
	Zuckerguss im Behälter, Rohlinge und garnierte Herzen aller Größen. Füllt nur auf, was fehlt.

	bench --site keks.localhost execute keks_trace.demo_herzen.vorrat_anlegen
	"""
	from keks_trace import demo, terminal

	ctx = ctx or frappe._dict(pilot.anlegen())
	h = frappe.generate_hash(length=4).upper()
	mhd = add_days(nowdate(), 300)
	ergebnis = {}
	if _bestand("HZ-PUDERZUCKER") < 20:
		terminal.wareneingang("Lager", "HZ-PUDERZUCKER", f"PZ-DEMO-{h}", 100, mhd)
	if _bestand("HZ-EIWEISS") < 2:
		terminal.wareneingang("Lager", "HZ-EIWEISS", f"EW-DEMO-{h}", 10, mhd)
	vorraete = {v["artikel"]: v for v in terminal.vorraete("Herzen Verpackung")}
	for code in PACKMITTEL:
		if _bestand(code) < 1000:
			terminal.wareneingang("Lager", code, f"{code[3:]}-DEMO-{h}", 3000)  # Karton im Lager
		if vorraete.get(code, {}).get("bestand", 0) < 200:
			c = terminal.wareneingang("Lager", code, f"{code[3:]}-DEMO-A{h}", 1000)["charge"]
			terminal.anbrechen("Herzen Verpackung", c)  # Karton am Tisch
	# Zuckerguss: Hauptmischung von heute im Behälter
	guss = frappe.db.get_value("Silo", "Zuckerguss Herzenboden", "warehouse")

	def guss_bereit(kg):
		if _bestand("HZ-GLASUR", guss) >= kg:
			return
		ansatz = max(10, round(kg * 1.2, 1))
		pz = _charge_mit("Herzen Garnieren", "HZ-PUDERZUCKER", round(ansatz * 0.95, 3))
		ew = _charge_mit("Herzen Garnieren", "HZ-EIWEISS", round(ansatz * 0.05, 3))
		terminal.herstellen(
			"Herzen Garnieren", "HZ-GLASUR",
			[{"code": pz, "menge": round(ansatz * 0.95, 3)}, {"code": ew, "menge": round(ansatz * 0.05, 3)}],
		)  # fmt: skip

	# Rohlinge und garnierte Herzen je Größe
	for g, (teig, glasur) in GROESSEN.items():
		if _bestand(f"HZ-ROHLING-{g}") < 100:
			kuebel = demo.neuer_traeger(f"HZK-{g}-{h}", "Teigbehälter")
			t = demo.neue_charge("5812", f"5812-HZ{g}-{h}", add_days(nowdate(), -20))
			demo.buchen(ctx, "Material Receipt", add_days(nowdate(), -20), "05:00:00",
			            ausgaenge=[("5812", t, round(400 * teig, 3), kuebel)])  # fmt: skip
			terminal.herstellen(
				"Backstube", f"HZ-ROHLING-{g}", [{"code": kuebel, "menge": round(400 * teig, 3)}], 400
			)
		if _bestand(f"HZ-GARNIERT-{g}") < 100:
			roh = _charge_mit("Herzen Garnieren", f"HZ-ROHLING-{g}", 200)
			guss_bereit(200 * glasur)
			terminal.herstellen(
				"Herzen Garnieren", f"HZ-GARNIERT-{g}",
				[{"code": roh, "menge": 200}, {"code": "Zuckerguss Herzenboden", "menge": round(200 * glasur, 3)}],
			)  # fmt: skip
		ergebnis[g] = {"rohlinge": _bestand(f"HZ-ROHLING-{g}"), "garniert": _bestand(f"HZ-GARNIERT-{g}")}
	frappe.db.commit()
	for g, e in ergebnis.items():
		print(f"Herz {g} cm: {e['rohlinge']:.0f} Rohlinge, {e['garniert']:.0f} garniert")
	return ergebnis


@frappe.whitelist()
def durchlauf(groesse: str = "18", stueck: int = 100) -> dict:
	"""Ein Herz komplett durch alle Abteilungen, so wie es an den Terminals gebucht wird, mit Protokoll.

	Lager (Wareneingang) → Backstube (Grundteig in den Kübel, Rohlinge backen) → Herzen Garnieren
	(Zuckerguss anmischen, garnieren) → Herzen Verpackung (Karton anbrechen, Metallcheck, verpacken auf
	Palette für den Kundenauftrag) → Versand (Lieferschein) → Rückverfolgung vom Los zurück und vom
	Puderzucker vorwärts bis zum Kunden.

	bench --site keks.localhost execute keks_trace.demo_herzen.durchlauf
	"""
	from keks_trace import demo, sperre, terminal
	from keks_trace.trace import rueckverfolgung

	ctx = anlegen(vorrat=0)
	stueck = int(stueck)
	teig_je, guss_je = GROESSEN[groesse]
	h = frappe.generate_hash(length=4).upper()
	mhd = add_days(nowdate(), 300)
	protokoll = []

	def schritt(abteilung, terminal_name, was, ergebnis):
		protokoll.append(
			{"abteilung": abteilung, "terminal": terminal_name, "was": was, "ergebnis": ergebnis}
		)
		print(f"{len(protokoll):>2}. {abteilung:<18} {terminal_name:<18} {was:<44} {ergebnis}")

	def eingang(artikel, menge, mhd_=mhd):
		c = terminal.wareneingang("Lager", artikel, f"{artikel[-6:]}-{h}", menge, mhd_)["charge"]
		if frappe.db.get_value("Batch", c, "kt_status") == "Gesperrt":
			sperre.freigeben(c, "Demo: Wareneingangsprüfung in Ordnung")
		return c

	# 1. Lager: Wareneingang
	rezept_teig = terminal.rezept("5812", menge=round(stueck * teig_je, 3), station="Backstube")
	zeilen_teig, roh = [], {}
	for z in rezept_teig["zutaten"]:
		if z["silo"]:
			zeilen_teig.append({"code": z["silo"], "menge": z["menge"]})
			continue
		if z["stufe"] == "Rohstoff":
			roh[z["artikel"]] = eingang(z["artikel"], z["menge"])
			zeilen_teig.append({"code": roh[z["artikel"]], "menge": z["menge"]})
		else:
			vorhanden = terminal.lager_chargen("Backstube", z["artikel"])
			if vorhanden and vorhanden[0]["menge"] >= z["menge"]:
				zeilen_teig.append({"code": vorhanden[0]["charge"], "menge": z["menge"]})
	puderzucker = eingang("HZ-PUDERZUCKER", 25)
	eiweiss = eingang("HZ-EIWEISS", 2)
	pack = {code: eingang(code, stueck) for code in PACKMITTEL}
	schritt("Lager", "Lager", "Wareneingang Honig, Puderzucker, Eiweiß, Packmittel",
	        f"{len(roh) + 2 + len(pack)} Lieferantenchargen, u. a. Puderzucker {puderzucker}")  # fmt: skip

	# 2. Backstube: Grundteig in den Kübel, Rohlinge backen
	kuebel = demo.neuer_traeger(f"HZK-{h}", "Teigbehälter")
	teig = terminal.herstellen("Backstube", "5812", zeilen_teig, ziel_behaelter=kuebel)
	schritt(
		"Backstube",
		"Backstube",
		f"Grundteig Honig in Kübel {kuebel}",
		f"Charge {teig['charge']}, {teig['menge']} kg",
	)
	rohling = terminal.herstellen(
		"Backstube", f"HZ-ROHLING-{groesse}", [{"code": kuebel, "menge": teig["menge"]}], stueck
	)
	schritt(
		"Backstube",
		"Backstube",
		f"Rohlinge {groesse} cm backen (Kübel leer)",
		f"Charge {rohling['charge']}, {stueck} Stk",
	)

	# 3. Herzen Garnieren: Zuckerguss morgens anmischen (geht in den Behälter), dann garnieren
	guss_menge = round(stueck * guss_je, 3)
	guss = terminal.herstellen(
		"Herzen Garnieren", "HZ-GLASUR",
		[{"code": puderzucker, "menge": round(guss_menge * 0.95, 3)}, {"code": eiweiss, "menge": round(guss_menge * 0.05, 3)}],
	)  # fmt: skip
	schritt(
		"Herzenboden",
		"Herzen Garnieren",
		"Zuckerguss anmischen → Zuckerguss Herzenboden",
		f"Charge {guss['charge']}, {guss['menge']} kg",
	)
	garniert = terminal.herstellen(
		"Herzen Garnieren", f"HZ-GARNIERT-{groesse}",
		[{"code": rohling["charge"], "menge": stueck}, {"code": "Zuckerguss Herzenboden", "menge": guss_menge}],
	)  # fmt: skip
	schritt(
		"Herzenboden",
		"Herzen Garnieren",
		"Garnieren: Rohlinge + Guss aus dem Behälter",
		f"Charge {garniert['charge']}, {garniert['menge']:.0f} Stk",
	)

	# 4. Herzen Verpackung: Kartons an den Tisch, Metallcheck Kalfass, verpacken auf Palette für den Kunden
	for c in pack.values():
		terminal.anbrechen("Herzen Verpackung", c)
	schritt(
		"Herzenboden", "Herzen Verpackung", "Karton Folie, Etikett, Schleife anbrechen", "ab jetzt ohne Scan"
	)
	demo.metalldetektor_ok("Herzen Verpackung")
	schritt("Herzenboden", "Herzen Verpackung", "Metallcheck Kalfass (CCP)", "Prüfkörper erkannt")
	kunde, _groessen, _tage, _mhd = WEITERE[0]
	auftrag = frappe.db.get_value(
		"Sales Order",
		{
			"customer": kunde,
			"po_no": "DEMO-HERZEN",
			"docstatus": 1,
			"status": ["not in", ["Completed", "Closed"]],
		},
	)
	if not frappe.db.exists("Sales Order Item", {"parent": auftrag, "item_code": f"HZ-{groesse}"}):
		auftrag = ctx.herz_auftrag
		kunde = frappe.db.get_value("Sales Order", auftrag, "customer")
	r = terminal.rezept(f"HZ-{groesse}", menge=stueck, station="Herzen Verpackung")
	zeilen = [{"code": garniert["charge"], "menge": stueck}] + [
		{"code": z["vorrat"], "menge": z["menge"]} for z in r["zutaten"] if z["vorrat"]
	]
	palette = terminal.palette_neu("Herzen Verpackung", kunde=kunde)["nve"]
	herz = terminal.herstellen(
		"Herzen Verpackung",
		f"HZ-{groesse}",
		zeilen,
		ausbringung=stueck,
		ziel_behaelter=palette,
		kundenauftrag=auftrag,
	)
	schritt(
		"Herzenboden",
		"Herzen Verpackung",
		f"Verpacken für {kunde}",
		f"Los {herz['los']}, MHD {herz['mhd']}, Palette …{palette[-6:]}",
	)

	# 5. Versand
	ls = terminal.lieferung("Versand", kunde, [{"palette": palette, "ganz": 1}], kundenauftrag=auftrag)
	schritt("Versand", "Versand", "Palette ganz auf den Lieferschein", f"Lieferschein {ls['lieferschein']}")

	# 6. Rückverfolgung
	rueck = rueckverfolgung(herz["charge"], "Rückwärts")
	stufen = sorted({c.get("stufe") or "" for c in rueck["chargen"]})
	schritt(
		"QS",
		"Büro",
		f"Rückwärts vom Los {herz['los']}",
		f"{len(rueck['chargen'])} Chargen: {', '.join(s for s in stufen if s)}",
	)
	vor = rueckverfolgung(puderzucker, "Vorwärts")
	kunden = sorted({k["kundenname"] for k in vor["kunden"]})
	schritt("QS", "Büro", f"Vorwärts vom Puderzucker {puderzucker}", f"bis Kunde {', '.join(kunden)}")
	frappe.db.commit()
	return {
		"protokoll": protokoll,
		"los": herz["los"],
		"charge": herz["charge"],
		"palette": palette,
		"lieferschein": ls["lieferschein"],
		"puderzucker": puderzucker,
	}
