"""Demo Herzenboden: garnierte Lebkuchenherzen in Stück, Größen Gr. 3 bis Gr. 11, Varianten je Spruch.

    bench --site keks.localhost execute keks_trace.demo_herzen.anlegen

Ablauf: Rohling backen (Backstraße: Kneter, Verpackungs-PC bucht Rohlinge im Karton ins Lager; vorproduziert
nach Gefühl) -> Lager lagert die Rohlinge an den Herzenboden um (wie für einen Kunden) -> Zuckerglasur kochen (eigene
Rezeptur, Halbfabrikat, max. 2 Tage) -> Garnieren (Herzen Garnieren: Rohling + Glasur) ->
Verpacken auf der Kalfass (Herzen Verpackung: Herz + Folie + Etikett + Schleife, Metallcheck Fe 2,8 mm).
Gezählt wird in Stück. Je Größe eine Vorlage („Lebkuchenherz Gr. 9“) mit Rezept (gleicher Teig, Guss-Richtwert
je Größe), je Spruch eine Variante („Gr. 9 · Ich liebe Dich“, siehe keks_trace.varianten). Der Wunschtext-Herz
(„Sondertext“) ist eine Sonderanfertigung nach Auftrag: nur für den bestellenden Kunden.
"""

import frappe
from frappe.utils import add_days, nowdate

from keks_trace import demo, pilot, varianten

# Größe: (Teig je Rohling kg, Guss-Richtwert je Herz kg) - Demo-Werte. Gleicher Teig für alle Größen; der Guss
# schwankt mit Schrift und Deko, die Tagesmenge stimmt über „Leer melden“ am Guss-Behälter.
GROESSEN = {
	"3": (0.03, 0.008), "62": (0.04, 0.01), "63": (0.06, 0.014), "64": (0.08, 0.018), "65": (0.1, 0.022),
	"6": (0.12, 0.026), "67": (0.16, 0.032), "9": (0.22, 0.04), "11": (0.35, 0.06),
}  # fmt: skip
STUECKGEWICHT = {g: round(teig + guss + 0.01, 3) for g, (teig, guss) in GROESSEN.items()}  # kg verpackt
LEISTUNG = (800, 25)  # Garnieren Stück/h, Kalfass Stück/min (Demo)
STK_JE_KARTON = {g: max(10, int(6 / teig) // 2 * 2) for g, (teig, _guss) in GROESSEN.items()}  # Rohlinge
BACKSTRASSE = "Backstraße"

SPRUECHE = ["Ich liebe Dich", "Viel Glück", "Oma ist die Beste", "Du bist das Beste"]
SONDER = "Sondertext"  # Wunschtext steht in der Auftragszeile; Sonderanfertigung nach Auftrag
STANDARD = SPRUECHE[0]
ALT = ("12", "18", "25")  # frühere Demo-Größen in cm: werden deaktiviert
PO_NR = "DEMO-HERZEN-GR"  # Bestellnummer der Demo-Aufträge (Größen Gr.)

# Demo-Kundenauftrag: der Kunde bestellt Herzen in Stück, (Größe, Spruch): Stück
AUFTRAG = {("9", "Ich liebe Dich"): 300, ("6", "Viel Glück"): 500, ("11", "Du bist das Beste"): 100}


def rohling(groesse: str) -> str:
	return f"HZ-ROHLING-{groesse}"


def garniert(groesse: str, spruch: str = STANDARD) -> str:
	return varianten.variante(f"HZ-GARNIERT-{groesse}", {"Spruch": spruch})


def herz(groesse: str, spruch: str = STANDARD) -> str:
	return varianten.variante(f"HZ-{groesse}", {"Spruch": spruch})


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


def _einheiten(code, einheiten):
	item = frappe.get_doc("Item", code)
	for uom, faktor in einheiten.items():
		vorhanden = next((u for u in item.uoms if u.uom == uom), None)
		if vorhanden:
			vorhanden.conversion_factor = faktor
		else:
			item.append("uoms", {"uom": uom, "conversion_factor": faktor})
	item.save()


LINIE = "Herzenboden"
HB_LAGER = "Lager Herzenboden"


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
	# Rohlinge kommen per Umlagern aus dem Lager an den Herzenboden (F13), in ein eigenes Lager dort
	# (der Lagerort der Linie gehört den Produktionsaufträgen und wird nicht vorgeschlagen)
	frappe.db.set_value("Warehouse", lager, "kt_umlagerziel", 0)
	if not frappe.db.exists("Warehouse", f"{HB_LAGER} - {ctx.abbr}"):
		frappe.get_doc(
			{"doctype": "Warehouse", "warehouse_name": HB_LAGER, "company": ctx.company,
			 "parent_warehouse": ctx.wurzel, "kt_umlagerziel": 1}
		).insert()  # fmt: skip
	for station in ("Herzen Garnieren", "Herzen Verpackung"):
		if frappe.db.exists("Terminal Station", station):
			frappe.db.set_value("Terminal Station", station, {"linie": LINIE, "f_silo": 1, "f_rework": 0})
			if station == "Herzen Verpackung":  # Pakete gehen auch direkt per DHL raus
				frappe.db.set_value("Terminal Station", station, "f_lieferung", 1)
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
	from keks_trace import demo_linie

	ctx = frappe._dict({**pilot.anlegen(), **demo_linie.stammdaten()})  # Grundteig 5812, Backstraße
	_linie(ctx)
	hb = {"kt_linie": LINIE}
	for code, (name, tage) in ROHSTOFFE.items():
		_artikel(code, name, "Rohstoff", "Kg", tage)
	for code, name in PACKMITTEL.items():
		_artikel(code, name, "Packmittel", "Nos")
	_artikel(
		"HZ-GLASUR", "Zuckerglasur (eigene Herstellung)", "Halbfabrikat", "Kg", 2,
		extra={"kt_mhd_nicht_begrenzend": 1, **hb},
	)  # fmt: skip
	pilot._rezept(ctx.company, "HZ-GLASUR", 10, [("HZ-PUDERZUCKER", 9.5), ("HZ-EIWEISS", 0.5)])
	varianten.merkmal("Spruch", [*SPRUECHE, SONDER])
	_alte_demo_aufraeumen()
	vorlage = {"has_variants": 1, "attributes": [{"attribute": "Spruch"}]}
	garnieren, kalfass = LEISTUNG
	for g, (teig, glasur) in GROESSEN.items():
		# Rohlinge kommen von der Backstraße, im Karton ins Lager (lose Ware, auch direkt verkauft)
		_artikel(f"HZ-ROHLING-{g}", f"Herz-Rohling Gr. {g}", "Ware lose", "Nos", 180,
				 extra={"kt_linie": BACKSTRASSE})  # fmt: skip
		_einheiten(f"HZ-ROHLING-{g}", {"Karton": STK_JE_KARTON[g], "Palette": STK_JE_KARTON[g] * 40})
		rohling_item = frappe.get_doc("Item", f"HZ-ROHLING-{g}")
		if not rohling_item.get("kt_linienleistung"):  # Demo-Leistung der Backstraße für Rohlinge
			rohling_item.append(
				"kt_linienleistung", {"abschnitt": "Backen", "leistung": 3000, "einheit": "Stück/h"}
			)
			rohling_item.save()
		frappe.db.sql(
			"update `tabBatch` set kt_chargen_stufe = 'Ware lose' where item = %s", f"HZ-ROHLING-{g}"
		)
		_artikel(
			f"HZ-GARNIERT-{g}", f"Herz Gr. {g} garniert", "Ware lose", "Nos", 180, extra={**hb, **vorlage}
		)
		_artikel(f"HZ-{g}", f"Lebkuchenherz Gr. {g}", "Fertigware", "Nos", monate=9,
				 extra={"kt_mhd_bezug": "Backtag", "weight_per_unit": STUECKGEWICHT[g], "weight_uom": "Kg",
				        **hb, **vorlage})  # fmt: skip
		item = frappe.get_doc("Item", f"HZ-{g}")
		if not item.get("kt_linienleistung"):
			item.append(
				"kt_linienleistung", {"abschnitt": "Garnieren", "leistung": garnieren, "einheit": "Stück/h"}
			)
			item.append(
				"kt_linienleistung", {"abschnitt": "Kalfass", "leistung": kalfass, "einheit": "Stück/min"}
			)
			item.save()
		pilot._rezept(ctx.company, f"HZ-ROHLING-{g}", 1, [("5812", teig)])
		pilot._rezept(ctx.company, f"HZ-GARNIERT-{g}", 1, [(f"HZ-ROHLING-{g}", 1), ("HZ-GLASUR", glasur)])
		pilot._rezept(
			ctx.company, f"HZ-{g}", 1,
			[(f"HZ-GARNIERT-{g}", 1), ("HZ-FOLIE", 1), ("HZ-ETIKETT", 1), ("HZ-SCHLEIFE", 1)],
		)  # fmt: skip
		for spruch in SPRUECHE:
			herz(g, spruch)  # legt auch das garnierte Herz mit diesem Spruch an, je mit Rezept
		for code in (garniert(g, SONDER), herz(g, SONDER)):
			frappe.db.set_value("Item", code, "kt_nach_auftrag", 1)
	_behaelter(ctx)
	auftrag = kundenauftrag(ctx)
	# Am Herzenboden wird direkt nach Kundenauftrag gearbeitet, ohne Tagesplan
	for pa in frappe.get_all(
		"Produktionsauftrag", {"linie": LINIE, "status": ["in", ["Geplant", "Freigegeben"]]}, pluck="name"
	):
		frappe.db.set_value("Produktionsauftrag", pa, "status", "Abgebrochen")
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
		"Sales Order", {"po_no": PO_NR, "docstatus": 1, "status": ["not in", ["Completed", "Closed"]]}
	)
	if offen:
		return offen
	termin = add_days(nowdate(), 21)
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": ctx.kunde,
			"company": ctx.company,
			"po_no": PO_NR,
			"transaction_date": nowdate(),
			"delivery_date": termin,
			"items": [
				{"item_code": herz(g, spruch), "qty": n, "uom": "Nos", "conversion_factor": 1, "rate": 1.5,
				 "warehouse": ctx.fertig, "delivery_date": termin}
				for (g, spruch), n in AUFTRAG.items()
			],
		}
	)  # fmt: skip
	so.insert()
	so.submit()
	return so.name


# Weitere Kunden (Demo): (Kunde, {(Größe, Spruch): Stück}, Tage bis Liefertermin, MHD höchstens Monate).
# Krause: 10 Standardherzen und 3 Sonderherzen mit Wunschtext nach Auftrag.
WEITERE = [
	("Markthändler Krause (Demo)", {("6", "Oma ist die Beste"): 10, ("6", SONDER): 3}, 10, 6),
	("Schaustellerbetrieb Lange (Demo)", {("3", "Viel Glück"): 800, ("9", "Ich liebe Dich"): 300}, 14, None),
]
WUNSCHTEXT = "Für Erna zum 80."
# Freier Vorrat garnierter Standardherzen (Demo): (Größe, Spruch)
VORRAT = [
	("3", "Viel Glück"),
	("6", "Oma ist die Beste"),
	("6", "Viel Glück"),
	("9", "Ich liebe Dich"),
	("11", "Du bist das Beste"),
]


def _alte_demo_aufraeumen():
	"""Frühere Demo in cm (12/18/25): Artikel deaktivieren, offene Demo-Aufträge mit ihnen schließen."""
	from erpnext.selling.doctype.sales_order.sales_order import update_status

	alt = [f"{p}{g}" for g in ALT for p in ("HZ-", "HZ-GARNIERT-", "HZ-ROHLING-")]
	for so in frappe.get_all(
		"Sales Order Item", {"item_code": ["in", alt], "docstatus": 1}, pluck="parent", distinct=True
	):
		if frappe.db.get_value("Sales Order", so, "status") not in ("Completed", "Closed"):
			update_status("Closed", so)
	for code in alt:
		if frappe.db.exists("Item", code):
			frappe.db.set_value("Item", code, "disabled", 1)


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
				"po_no": PO_NR,
				"docstatus": 1,
				"status": ["not in", ["Completed", "Closed"]],
			},
		)
		if offen:
			namen.append(offen)
			continue
		termin = add_days(nowdate(), tage)
		so = frappe.get_doc(
			{"doctype": "Sales Order", "customer": kunde, "company": ctx.company, "po_no": PO_NR,
			 "transaction_date": nowdate(), "delivery_date": termin,
			 "items": [{"item_code": herz(g, spruch), "qty": n, "uom": "Nos", "conversion_factor": 1, "rate": 1.8,
			            "warehouse": ctx.fertig, "delivery_date": termin,
			            "description": WUNSCHTEXT if spruch == SONDER else None}
			           for (g, spruch), n in groessen.items()]}
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
	for g in sorted({g for g, _s in VORRAT}, key=list(GROESSEN).index):
		if _bestand(rohling(g)) < 300:
			rohlinge_backen(ctx, g, max(1, round(600 / STK_JE_KARTON[g])))
	for g, spruch in VORRAT:  # Standardherzen frei auf Vorrat garniert (nicht für einen Auftrag)
		code = garniert(g, spruch)
		if _bestand(code) < 50:
			guss = GROESSEN[g][1]
			roh = _charge_mit("Herzen Garnieren", rohling(g), 100)
			guss_bereit(100 * guss)
			terminal.herstellen(
				"Herzen Garnieren", code,
				[{"code": roh, "menge": 100}, {"code": "Zuckerguss Herzenboden", "menge": round(100 * guss, 3)}],
			)  # fmt: skip
		ergebnis[f"Gr. {g} {spruch}"] = {"rohlinge": _bestand(rohling(g)), "garniert": _bestand(code)}
	frappe.db.commit()
	for name, e in ergebnis.items():
		print(f"{name}: {e['rohlinge']:.0f} Rohlinge, {e['garniert']:.0f} garniert frei")
	return ergebnis


def rohlinge_backen(ctx, groesse: str, kartons: int) -> dict:
	"""Rohlinge auf Lager (nach Gefühl): Produktionsauftrag der Backstraße, am Kneter den Grundteig-Kübel
	auf die Linie (F4), am Verpackungs-PC Kartons auf Palette ins Lager (F6), Auftrag beenden.
	Die Stationen arbeiten danach wieder an ihrem vorherigen Auftrag."""
	from keks_trace import demo, linienbuchung, terminal

	stueck = kartons * STK_JE_KARTON[groesse]
	teig = round(stueck * GROESSEN[groesse][0], 3)
	vorher = {
		st: frappe.db.get_value("Terminal Station", st, "aktueller_auftrag")
		for st in ("Kneter", "Verpackungs-PC")
	}
	pa = frappe.get_doc(
		{"doctype": "Produktionsauftrag", "linie": BACKSTRASSE, "datum": nowdate(), "artikel": f"HZ-ROHLING-{groesse}",
		 "menge": kartons, "einheit": "Karton", "status": "Freigegeben",
		 "bemerkung": "Herzen-Rohlinge auf Lager (Demo)"}
	).insert()  # fmt: skip
	h = frappe.generate_hash(length=4).upper()
	kuebel = demo.neuer_traeger(f"HZK-{groesse}-{h}", "Teigbehälter")
	t = demo.neue_charge("5812", f"5812-HZ{groesse}-{h}", add_days(nowdate(), -20))
	demo.buchen(
		ctx, "Material Receipt", add_days(nowdate(), -20), "05:00:00", ausgaenge=[("5812", t, teig, kuebel)]
	)
	try:
		linienbuchung.waehlen("Kneter", pa.name)
		linienbuchung.zufuehren("Kneter", kuebel)
		linienbuchung.waehlen("Verpackungs-PC", pa.name)
		nve = terminal.palette_neu("Verpackungs-PC")["nve"]
		karton = linienbuchung.palette_fertig("Verpackungs-PC", kartons, "Karton", nve)
		linienbuchung.beenden("Verpackungs-PC", pa.name)
	finally:
		for st, auftrag in vorher.items():
			frappe.db.set_value("Terminal Station", st, "aktueller_auftrag", auftrag)
			frappe.clear_document_cache("Terminal Station", st)
	return {
		"auftrag": pa.name,
		"charge": karton["charge"],
		"palette": nve,
		"stueck": stueck,
		"kuebel": kuebel,
	}


@frappe.whitelist()
def durchlauf(groesse: str = "9", stueck: int = 100, spruch: str = STANDARD) -> dict:
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

	# 2. Backstube: Grundteig in den Kübel (F3); Backstraße: Kneter (F4), Verpackungs-PC Rohlinge im Karton (F6)
	from keks_trace import linienbuchung

	kuebel = demo.neuer_traeger(f"HZK-{h}", "Teigbehälter")
	teig = terminal.herstellen("Backstube", "5812", zeilen_teig, ziel_behaelter=kuebel)
	schritt(
		"Backstube",
		"Backstube",
		f"Grundteig Honig in Kübel {kuebel}",
		f"Charge {teig['charge']}, {teig['menge']} kg",
	)
	kartons = -(-stueck // STK_JE_KARTON[groesse])
	vorher = {
		st: frappe.db.get_value("Terminal Station", st, "aktueller_auftrag")
		for st in ("Kneter", "Verpackungs-PC")
	}
	pa = frappe.get_doc(
		{"doctype": "Produktionsauftrag", "linie": BACKSTRASSE, "datum": nowdate(), "artikel": f"HZ-ROHLING-{groesse}",
		 "menge": kartons, "einheit": "Karton", "status": "Freigegeben"}
	).insert()  # fmt: skip
	try:
		linienbuchung.waehlen("Kneter", pa.name)
		linienbuchung.zufuehren("Kneter", kuebel)
		schritt("Backstraße", "Kneter", f"Kübel {kuebel} auf die Linie", f"Auftrag {pa.name}")
		linienbuchung.waehlen("Verpackungs-PC", pa.name)
		nve_roh = terminal.palette_neu("Verpackungs-PC")["nve"]
		roh_e = linienbuchung.palette_fertig("Verpackungs-PC", kartons, "Karton", nve_roh)
		linienbuchung.beenden("Verpackungs-PC", pa.name)
	finally:
		for st, auftrag in vorher.items():
			frappe.db.set_value("Terminal Station", st, "aktueller_auftrag", auftrag)
			frappe.clear_document_cache("Terminal Station", st)
	schritt(
		"Backstraße",
		"Verpackungs-PC",
		f"Rohlinge Gr. {groesse} im Karton auf Palette ins Lager",
		f"Charge {roh_e['charge']}, {kartons} Karton",
	)
	stueck = kartons * STK_JE_KARTON[groesse]
	herzenboden = f"{HB_LAGER} - {ctx.abbr}"
	terminal.umlagern("Lager", palette=nve_roh, ganz=1, nach=herzenboden)
	schritt("Lager", "Lager", "Rohlinge an den Herzenboden umlagern", f"Palette …{nve_roh[-6:]}")

	# Der Kundenauftrag läuft am Herzenboden durch: garniert und verpackt wird für ihn
	artikel_herz, artikel_garniert = herz(groesse, spruch), garniert(groesse, spruch)
	auftrag = next(
		(
			so
			for so in frappe.get_all(
				"Sales Order Item",
				{"item_code": artikel_herz, "docstatus": 1},
				pluck="parent",
				order_by="creation desc",
			)
			if frappe.db.get_value("Sales Order", so, "status") not in ("Completed", "Closed")
		),
		ctx.herz_auftrag,
	)
	kunde = frappe.db.get_value("Sales Order", auftrag, "customer")

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
	garn_e = terminal.herstellen(
		"Herzen Garnieren", artikel_garniert,
		[{"code": roh_e["charge"], "menge": stueck}, {"code": "Zuckerguss Herzenboden", "menge": guss_menge}],
		kundenauftrag=auftrag,
	)  # fmt: skip
	schritt(
		"Herzenboden",
		"Herzen Garnieren",
		f"Garnieren für {kunde}: Rohlinge + Guss aus dem Behälter",
		f"Charge {garn_e['charge']}, {garn_e['menge']:.0f} Stk",
	)

	# 4. Herzen Verpackung: Kartons an den Tisch, Metallcheck Kalfass, verpacken auf Palette für den Kunden
	for c in pack.values():
		terminal.anbrechen("Herzen Verpackung", c)
	schritt(
		"Herzenboden", "Herzen Verpackung", "Karton Folie, Etikett, Schleife anbrechen", "ab jetzt ohne Scan"
	)
	demo.metalldetektor_ok("Herzen Verpackung")
	schritt("Herzenboden", "Herzen Verpackung", "Metallcheck Kalfass (CCP)", "Prüfkörper erkannt")
	r = terminal.rezept(artikel_herz, menge=stueck, station="Herzen Verpackung")
	zeilen = [{"code": garn_e["charge"], "menge": stueck}] + [
		{"code": z["vorrat"], "menge": z["menge"]} for z in r["zutaten"] if z["vorrat"]
	]
	palette = terminal.palette_neu("Herzen Verpackung", kunde=kunde)["nve"]
	herz_e = terminal.herstellen(
		"Herzen Verpackung",
		artikel_herz,
		zeilen,
		ausbringung=stueck,
		ziel_behaelter=palette,
		kundenauftrag=auftrag,
	)
	schritt(
		"Herzenboden",
		"Herzen Verpackung",
		f"Verpacken für {kunde}",
		f"Los {herz_e['los']}, MHD {herz_e['mhd']}, Palette …{palette[-6:]}",
	)

	# 5. Versand
	ls = terminal.lieferung("Versand", kunde, [{"palette": palette, "ganz": 1}], kundenauftrag=auftrag)
	schritt("Versand", "Versand", "Palette ganz auf den Lieferschein", f"Lieferschein {ls['lieferschein']}")

	# 6. Rückverfolgung
	rueck = rueckverfolgung(herz_e["charge"], "Rückwärts")
	stufen = sorted({c.get("stufe") or "" for c in rueck["chargen"]})
	schritt(
		"QS",
		"Büro",
		f"Rückwärts vom Los {herz_e['los']}",
		f"{len(rueck['chargen'])} Chargen: {', '.join(s for s in stufen if s)}",
	)
	vor = rueckverfolgung(puderzucker, "Vorwärts")
	kunden = sorted({k["kundenname"] for k in vor["kunden"]})
	schritt("QS", "Büro", f"Vorwärts vom Puderzucker {puderzucker}", f"bis Kunde {', '.join(kunden)}")
	frappe.db.commit()
	return {
		"protokoll": protokoll,
		"los": herz_e["los"],
		"charge": herz_e["charge"],
		"palette": palette,
		"lieferschein": ls["lieferschein"],
		"puderzucker": puderzucker,
	}
