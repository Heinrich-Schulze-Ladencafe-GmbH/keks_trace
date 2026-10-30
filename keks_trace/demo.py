"""Demo: drei Produktionstage nach dem echten Ablauf auf einer ERPNext-Instanz.

Aufruf auf dem Server (Firma muss über den Einrichtungsassistenten angelegt sein):

	bench --site <site> execute keks_trace.demo.run

Ablauf: Grundteig (Silo/Säcke) -> Veredelung (weitere Zutaten, Rework) -> Backen
-> Füllen/Glasieren/Schokolieren (gekaufte Schokolade, selbst gemachte Nougatfüllung)
-> lose Ware in Kisten im Lager -> Verpacken -> Lieferung.

Legt Demo-Stammdaten an (Artikel mit Präfix KT-), bucht drei Tage mit Rework und Behältern,
verpackt, liefert an einen Demo-Kunden und gibt die Rückverfolgung aus.
Jeder Lauf erzeugt neue Chargen und Behälter (eindeutiges Kürzel), Stammdaten werden wiederverwendet.
"""

import frappe
from frappe.utils import add_days, flt, formatdate, getdate, now_datetime, nowdate

from keks_trace import silo, sperre

ALLERGENGRUPPEN = {
	"Mürbeteig": "Gluten, Milch",
	"Mürbeteig Nuss": "Gluten, Milch, Haselnuss",
	"Nougat": "Milch, Haselnuss",
	"Kakao-Nougat": "Gluten, Milch, Haselnuss",
	"Nuss-Schoko": "Gluten, Milch, Haselnuss, Soja",
}

# Artikelnummer: (Bezeichnung, Stufe, Allergengruppe, Haltbarkeit in Tagen oder None)
ARTIKEL = {
	# gekauft
	"KT-MEHL": ("Weizenmehl Type 550 (Silo oder Sack)", "Rohstoff", None, 365),
	"KT-DINKEL": ("Dinkelmehl Type 630 (Silo)", "Rohstoff", None, 365),
	"KT-ZUCKER": ("Zucker (Silo)", "Rohstoff", None, 730),
	"KT-BUTTER": ("Butter", "Rohstoff", None, 60),
	"KT-HASELNUSS": ("Haselnüsse gehackt", "Rohstoff", None, 270),
	"KT-KAKAO": ("Kakaopulver", "Rohstoff", None, 540),
	"KT-SCHOKO": ("Zartbitter-Kuvertüre (gekauft)", "Rohstoff", None, 365),
	"KT-FOLIE": ("Verpackungsfolie", "Packmittel", None, None),
	# selbst hergestellt: Zuckersirup (Tank) und Füllung
	"KT-SIRUP": ("Zuckersirup (eigene Herstellung, Tank)", "Halbfabrikat", None, 14),
	"KT-NOUGAT": ("Nougatfüllung (eigene Herstellung)", "Halbfabrikat", "Nougat", 30),
	# Teige: Haltbarkeit = maximale Standzeit
	"KT-GT-MUERBE": ("Grundteig Mürbe", "Grundteig", "Mürbeteig", 3),
	"KT-TV-NUSS": ("Teig Haselnuss (veredelt)", "Teig veredelt", "Mürbeteig Nuss", 2),
	"KT-TV-KAKAO": ("Teig Kakao (veredelt)", "Teig veredelt", "Mürbeteig", 2),
	# gebacken, noch ohne Füllung/Glasur
	"KT-BW-NUSS": ("Nusskeks gebacken", "Backware", "Mürbeteig Nuss", 7),
	"KT-BW-KAKAO": ("Kakaokeks gebacken", "Backware", "Mürbeteig", 7),
	# lose fertige Ware im Lager: Haltbarkeit = maximale Lagerdauer ab Backtag
	"KT-WL-NUSS-SCHOKO": ("Nusskeks mit Schokoboden lose", "Ware lose", "Nuss-Schoko", 180),
	"KT-WL-KAKAO-NOUGAT": ("Kakaokeks mit Nougat lose", "Ware lose", "Kakao-Nougat", 180),
	# Rework: Haltbarkeit = Höchstalter ab ältestem Tag der Kette
	"KT-RW-MUERBE": ("Rework Mürbeteig (Teigreste)", "Rework", "Mürbeteig", 7),
	"KT-RW-NUSS": ("Rework Nusskeks (Bruch)", "Rework", "Mürbeteig Nuss", 7),
	"KT-RW-SCHOKO": ("Rework schokoliert (Bruch)", "Rework", "Nuss-Schoko", 7),
	# verpackt: Haltbarkeit = MHD ab Backtag
	"KT-FW-NUSS-SCHOKO": ("Nuss-Schoko-Keks 200 g", "Fertigware", "Nuss-Schoko", 270),
	"KT-FW-KAKAO-NOUGAT": ("Kakao-Nougat-Keks 200 g", "Fertigware", "Kakao-Nougat", 270),
}

ROHSTOFF_PREIS = {
	"KT-MEHL": 0.6,
	"KT-DINKEL": 0.9,
	"KT-ZUCKER": 0.9,
	"KT-BUTTER": 6.5,
	"KT-HASELNUSS": 9.0,
	"KT-KAKAO": 7.0,
	"KT-SCHOKO": 8.0,
	"KT-FOLIE": 4.0,
}

# Neue Chargen dieser Artikel sind gesperrt, bis die QS sie freigibt.
FREIGABE_PFLICHT = {"KT-BUTTER", "KT-WL-NUSS-SCHOKO", "KT-WL-KAKAO-NOUGAT"}

# Rezepte (Stücklisten): Ausbringung in kg, Zutaten in kg. Backverlust steckt im Verhältnis.
# (Silo/Tank, Artikel, Nachlauf kg). Jeder Demo-Lauf legt eigene Silos mit seinem Kürzel an,
# damit sich Läufe nicht vermischen. Im Echtbetrieb gibt es jedes Silo genau einmal.
SILOS = [
	("Silo Weizenmehl 550", "KT-MEHL", 100),
	("Silo Dinkelmehl 630", "KT-DINKEL", 100),
	("Silo Zucker", "KT-ZUCKER", 50),
	("Tank Zuckersirup", "KT-SIRUP", 20),
]


def silos_anlegen(ctx, kuerzel) -> dict:
	"""Silos und Tank für einen Demo-Lauf. Gibt {Artikel: Silo-Name} zurück."""
	je_artikel = {}
	for bezeichnung, artikel, nachlauf in SILOS:
		name = f"{bezeichnung} {kuerzel}"
		lager = f"{name} - {ctx.abbr}"
		if not frappe.db.exists("Warehouse", lager):
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": name,
					"company": ctx.company,
					"parent_warehouse": ctx.wurzel,
				}
			).insert()
		if not frappe.db.exists("Silo", name):
			frappe.get_doc(
				{
					"doctype": "Silo",
					"silo_name": name,
					"warehouse": lager,
					"artikel": artikel,
					"nachlauf": nachlauf,
					"typ": "Tank" if bezeichnung.startswith("Tank") else "Silo",
					"kapazitaet": 30000 if bezeichnung.startswith("Silo") else 2000,
				}
			).insert()
		ctx.silo_lager[name] = lager
		je_artikel[artikel] = name
	return je_artikel


REZEPTE = {
	"KT-GT-MUERBE": (100, [("KT-MEHL", 60), ("KT-ZUCKER", 20), ("KT-BUTTER", 20)]),
	"KT-NOUGAT": (30, [("KT-ZUCKER", 10), ("KT-HASELNUSS", 10), ("KT-KAKAO", 5), ("KT-BUTTER", 5)]),
	"KT-TV-NUSS": (60, [("KT-GT-MUERBE", 50), ("KT-HASELNUSS", 10)]),
	"KT-TV-KAKAO": (100, [("KT-GT-MUERBE", 85), ("KT-DINKEL", 5), ("KT-KAKAO", 5), ("KT-SIRUP", 5)]),
	# Wasser wird nicht als Charge geführt, daher Ausbringung größer als Einsatz
	"KT-SIRUP": (100, [("KT-ZUCKER", 60)]),
	"KT-BW-NUSS": (85, [("KT-TV-NUSS", 100)]),
	"KT-BW-KAKAO": (85, [("KT-TV-KAKAO", 100)]),
	"KT-WL-NUSS-SCHOKO": (54, [("KT-BW-NUSS", 48), ("KT-SCHOKO", 6)]),
	"KT-WL-KAKAO-NOUGAT": (100, [("KT-BW-KAKAO", 80), ("KT-NOUGAT", 20)]),
	"KT-FW-NUSS-SCHOKO": (40, [("KT-WL-NUSS-SCHOKO", 40), ("KT-FOLIE", 1)]),
	"KT-FW-KAKAO-NOUGAT": (50, [("KT-WL-KAKAO-NOUGAT", 50), ("KT-FOLIE", 1)]),
}

# (Rework-Artikel, Ziel-Teig, max. Anteil %). Schokolierter Bruch hat bewusst keine Regel.
REWORK_REGELN = [
	("KT-RW-MUERBE", "KT-GT-MUERBE", 10),
	("KT-RW-MUERBE", "KT-TV-NUSS", 10),
	("KT-RW-MUERBE", "KT-TV-KAKAO", 10),
	("KT-RW-NUSS", "KT-TV-NUSS", 10),
]


def run(company: str | None = None, kuerzel: str | None = None):
	ctx = stammdaten(company)
	kette = drei_tage_kette(ctx, kuerzel)
	test = frappe.get_doc(
		{"doctype": "Rueckverfolgungstest", "charge": kette.mehl, "anlass": "Jährlicher Test"}
	)
	test.insert()
	test.submit()
	kette.rueckverfolgungstest = test.name
	frappe.db.commit()
	_ausgabe(kette)
	print(f"\n== Rückverfolgungstest {test.name}: {test.ergebnis} in {test.dauer_sekunden} s\n")
	print(test.bericht)
	return kette


# ---------------------------------------------------------------------------
# Stammdaten
# ---------------------------------------------------------------------------


def stammdaten(company: str | None = None) -> frappe._dict:
	company = company or frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {})
	if not company:
		frappe.throw("Keine Firma gefunden. Bitte zuerst den ERPNext-Einrichtungsassistenten abschließen.")
	abbr = frappe.get_cached_value("Company", company, "abbr")

	for gruppe, allergene in ALLERGENGRUPPEN.items():
		if not frappe.db.exists("Allergengruppe", gruppe):
			frappe.get_doc({"doctype": "Allergengruppe", "gruppe": gruppe, "allergene": allergene}).insert()

	item_group = _blatt("Item Group", "Products")
	for code, (name, stufe, gruppe, haltbarkeit) in ARTIKEL.items():
		if frappe.db.exists("Item", code):
			# Demo-Artikel gehören der Demo: Stufe, Allergene und Haltbarkeit auf Stand halten.
			frappe.db.set_value(
				"Item",
				code,
				{
					"kt_chargen_stufe": stufe,
					"kt_allergengruppe": gruppe,
					"has_expiry_date": 1 if haltbarkeit else 0,
					"shelf_life_in_days": haltbarkeit or 0,
					"kt_freigabe_pflicht": 1 if code in FREIGABE_PFLICHT else 0,
				},
			)
			continue
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": item_group,
				"stock_uom": "Kg",
				"is_stock_item": 1,
				"include_item_in_manufacturing": 1,
				"has_batch_no": 1,
				"has_expiry_date": 1 if haltbarkeit else 0,
				"shelf_life_in_days": haltbarkeit or 0,
				"valuation_rate": ROHSTOFF_PREIS.get(code, 0),
				"kt_chargen_stufe": stufe,
				"kt_allergengruppe": gruppe,
				"kt_freigabe_pflicht": 1 if code in FREIGABE_PFLICHT else 0,
			}
		).insert()

	for artikel, (menge, zutaten) in REZEPTE.items():
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
				continue
		bom = frappe.get_doc(
			{
				"doctype": "BOM",
				"item": artikel,
				"quantity": menge,
				"company": company,
				"is_active": 1,
				"is_default": 1,
				"rm_cost_as_per": "Valuation Rate",
				"items": [{"item_code": z, "qty": q, "uom": "Kg"} for z, q in zutaten],
			}
		)
		bom.insert()
		bom.submit()

	for rework, ziel, anteil in REWORK_REGELN:
		if not frappe.db.exists("Rework Regel", {"rework_artikel": rework, "ziel_artikel": ziel}):
			frappe.get_doc(
				{
					"doctype": "Rework Regel",
					"rework_artikel": rework,
					"ziel_artikel": ziel,
					"max_anteil_prozent": anteil,
				}
			).insert()

	wurzel = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["in", ["", None]]}
	)

	lieferant = "KT Demo Mühle"
	if not frappe.db.exists("Supplier", lieferant):
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": lieferant,
				"supplier_group": _blatt("Supplier Group", None),
			}
		).insert()

	kunde = "KT Demo Handel"
	if not frappe.db.exists("Customer", kunde):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": kunde,
				"customer_group": _blatt("Customer Group", "Commercial"),
				"territory": _blatt("Territory", None),
			}
		).insert()

	for station in ("Backstube", "Verpackung", "Lager", "Versand"):
		if not frappe.db.exists("Terminal Station", station):
			frappe.get_doc(
				{
					"doctype": "Terminal Station",
					"station_name": station,
					"typ": station,
					"company": company,
					"rohstofflager": f"Stores - {abbr}",
					"produktionslager": f"Work In Progress - {abbr}",
					"fertiglager": f"Finished Goods - {abbr}",
				}
			).insert()

	return frappe._dict(
		company=company,
		lager=f"Stores - {abbr}",
		produktion=f"Work In Progress - {abbr}",
		fertig=f"Finished Goods - {abbr}",
		lieferant=lieferant,
		kunde=kunde,
		silo_lager={},
		abbr=abbr,
		wurzel=wurzel,
	)


def _blatt(doctype: str, bevorzugt: str | None) -> str:
	"""Ein Nicht-Gruppen-Eintrag eines Baums (Artikelgruppe, Kundengruppe, ...)."""
	if bevorzugt and frappe.db.exists(doctype, {"name": bevorzugt, "is_group": 0}):
		return bevorzugt
	return frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="lft asc")


# ---------------------------------------------------------------------------
# Buchungshelfer (so würden es später die Scanner-Seiten tun)
# ---------------------------------------------------------------------------


def neuer_traeger(code: str, typ: str) -> str:
	if not frappe.db.exists("Produkttraeger", code):
		frappe.get_doc({"doctype": "Produkttraeger", "code": code, "typ": typ}).insert()
	return code


def neue_charge(item: str, charge_id: str, herstelldatum=None, lieferant: str | None = None) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Batch",
				"item": item,
				"batch_id": charge_id,
				"manufacturing_date": herstelldatum,
				"supplier": lieferant,
			}
		)
		.insert()
		.name
	)


def _lager(ctx, item):
	stufe = _stufe(item)
	if stufe in ("Rohstoff", "Packmittel"):
		return ctx.lager
	if stufe == "Fertigware":
		return ctx.fertig
	return ctx.produktion  # Teige, Füllung, Backware, Rework, lose Ware


def buchen(ctx, zweck: str, datum, zeit: str, eingaenge=(), ausgaenge=(), submit: bool = True):
	"""Lagerbuchung erzeugen.

	eingaenge / ausgaenge: Tupel (Artikel, Charge, Menge) oder (Artikel, Charge, Menge, Behälter oder Silo).
	Bei Entnahme aus einem Silo bleibt die Charge leer (None): das System teilt sie nach FIFO zu.
	Für Wareneingang ("Material Receipt") nur ausgaenge.
	"""
	zeilen = []
	for item, charge, menge, *traeger in eingaenge:
		lager, traeger = _ort(ctx, item, traeger)
		zeilen.append(_zeile(item, charge, menge, traeger, s_warehouse=lager))
	for i, (item, charge, menge, *traeger) in enumerate(ausgaenge):
		lager, traeger = _ort(ctx, item, traeger)
		z = _zeile(item, charge, menge, traeger, t_warehouse=lager)
		if zweck == "Material Receipt":
			z["basic_rate"] = ROHSTOFF_PREIS.get(item, 1)
		if zweck == "Manufacture" and i == 0:
			z["is_finished_item"] = 1
		zeilen.append(z)

	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": zweck,
			"purpose": zweck,
			"company": ctx.company,
			"set_posting_time": 1,
			"posting_date": getdate(datum),
			"posting_time": zeit,
			"items": zeilen,
		}
	)
	se.insert()
	if submit:
		se.submit()
	return se


def _ort(ctx, item, traeger):
	"""Lagerort und Behälter: ein Silo-Name als 4. Element bedeutet Lagerort des Silos, kein Behälter."""
	if traeger and traeger[0] in (ctx.get("silo_lager") or {}):
		return ctx.silo_lager[traeger[0]], []
	return _lager(ctx, item), traeger


def _zeile(item, charge, menge, traeger, s_warehouse=None, t_warehouse=None):
	return {
		"item_code": item,
		"qty": menge,
		"uom": "Kg",
		"stock_uom": "Kg",
		"conversion_factor": 1,
		"transfer_qty": menge,
		"s_warehouse": s_warehouse,
		"t_warehouse": t_warehouse,
		"use_serial_batch_fields": 1,
		"batch_no": charge,
		"kt_traeger": traeger[0] if traeger else None,
	}


def _stufe(item):
	return frappe.get_cached_value("Item", item, "kt_chargen_stufe")


def liefern(ctx, datum, positionen, rate=8.0):
	"""positionen: Liste (Artikel, Charge, Menge)."""
	dn = frappe.get_doc(
		{
			"doctype": "Delivery Note",
			"customer": ctx.kunde,
			"company": ctx.company,
			"set_posting_time": 1,
			"posting_date": getdate(datum),
			"posting_time": "16:00:00",
			"items": [
				{
					"item_code": item,
					"qty": menge,
					"rate": rate,
					"warehouse": ctx.fertig,
					"use_serial_batch_fields": 1,
					"batch_no": charge,
				}
				for item, charge, menge in positionen
			],
		}
	)
	dn.insert()
	dn.submit()
	return dn


# ---------------------------------------------------------------------------
# Die Kette
# ---------------------------------------------------------------------------


def drei_tage_kette(ctx, kuerzel: str | None = None, start=None) -> frappe._dict:
	"""Tag 1-3 nach dem echten Ablauf. Gibt Chargen- und Behälternamen zurück."""
	k = kuerzel or now_datetime().strftime("%y%m%d%H%M%S")
	t1 = getdate(start) if start else getdate(add_days(nowdate(), -2))
	t2, t3 = getdate(add_days(t1, 1)), getdate(add_days(t1, 2))
	c = frappe._dict(kuerzel=k, tag1=t1, tag2=t2, tag3=t3)
	c.silo = silos_anlegen(ctx, k)
	W, Z, D, T = c.silo["KT-MEHL"], c.silo["KT-ZUCKER"], c.silo["KT-DINKEL"], c.silo["KT-SIRUP"]

	# Behälter mit QR-Code
	c.tb1 = neuer_traeger(f"TB1-{k}", "Teigbehälter")
	c.tb2 = neuer_traeger(f"TB2-{k}", "Teigbehälter")
	c.tb3 = neuer_traeger(f"TB3-{k}", "Teigbehälter")
	c.tb4 = neuer_traeger(f"TB4-{k}", "Teigbehälter")
	c.rb1 = neuer_traeger(f"RB1-{k}", "Rework-Behälter")
	c.rb2 = neuer_traeger(f"RB2-{k}", "Rework-Behälter")
	c.kl1 = neuer_traeger(f"KL1-{k}", "Kiste lose Ware")
	c.kl2 = neuer_traeger(f"KL2-{k}", "Kiste lose Ware")
	c.kl3 = neuer_traeger(f"KL3-{k}", "Kiste lose Ware")

	# Wareneingang
	c.mehl = neue_charge("KT-MEHL", f"M-{k}", add_days(t1, -10), ctx.lieferant)
	c.zucker = neue_charge("KT-ZUCKER", f"Z-{k}", add_days(t1, -30), ctx.lieferant)
	c.dinkel = neue_charge("KT-DINKEL", f"D-{k}", add_days(t1, -12), ctx.lieferant)
	c.butter = neue_charge("KT-BUTTER", f"BU-{k}", add_days(t1, -3), ctx.lieferant)
	c.nuss = neue_charge("KT-HASELNUSS", f"HN-{k}", add_days(t1, -20), ctx.lieferant)
	c.kakao = neue_charge("KT-KAKAO", f"KA-{k}", add_days(t1, -40), ctx.lieferant)
	c.schoko = neue_charge("KT-SCHOKO", f"SK-{k}", add_days(t1, -30), ctx.lieferant)
	c.folie = neue_charge("KT-FOLIE", f"F-{k}", add_days(t1, -60), ctx.lieferant)
	buchen(
		ctx,
		"Material Receipt",
		t1,
		"06:00:00",
		ausgaenge=[
			("KT-MEHL", c.mehl, 125, W),
			("KT-ZUCKER", c.zucker, 100, Z),
			("KT-DINKEL", c.dinkel, 6, D),
			("KT-BUTTER", c.butter, 400),
			("KT-HASELNUSS", c.nuss, 200),
			("KT-KAKAO", c.kakao, 50),
			("KT-SCHOKO", c.schoko, 100),
			("KT-FOLIE", c.folie, 20),
		],
	)
	# Kühlware: Wareneingangsprüfung durch die QS
	sperre.freigeben(c.butter, "Wareneingangsprüfung: Temperatur 4 °C, Verpackung unbeschädigt")

	# ---- Tag 1
	# Zuckersirup aus Silozucker in den Tank (Wasser wird nicht als Charge geführt)
	c.sirup = neue_charge("KT-SIRUP", f"SI1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"06:30:00",
		eingaenge=[("KT-ZUCKER", None, 60, Z)],
		ausgaenge=[("KT-SIRUP", c.sirup, 100, T)],
	)
	# Grundteig GT1 (100 kg) in Behälter TB1; Mehl und Zucker aus dem Silo, Charge nach FIFO
	c.gt1 = neue_charge("KT-GT-MUERBE", f"GT1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"07:00:00",
		eingaenge=[
			("KT-MEHL", None, 60, W),
			("KT-ZUCKER", None, 20, Z),
			("KT-BUTTER", c.butter, 20),
		],
		ausgaenge=[("KT-GT-MUERBE", c.gt1, 100, c.tb1)],
	)
	# Nougatfüllung selbst hergestellt
	c.nougat = neue_charge("KT-NOUGAT", f"NO1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"07:30:00",
		eingaenge=[
			("KT-ZUCKER", None, 10, Z),
			("KT-HASELNUSS", c.nuss, 10),
			("KT-KAKAO", c.kakao, 5),
			("KT-BUTTER", c.butter, 5),
		],
		ausgaenge=[("KT-NOUGAT", c.nougat, 30)],
	)
	# Veredelung V1: halber Grundteig + Haselnuss
	c.v1 = neue_charge("KT-TV-NUSS", f"V1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"08:00:00",
		eingaenge=[("KT-GT-MUERBE", c.gt1, 50, c.tb1), ("KT-HASELNUSS", c.nuss, 10)],
		ausgaenge=[("KT-TV-NUSS", c.v1, 60, c.tb2)],
	)
	# Backen
	c.bw1 = neue_charge("KT-BW-NUSS", f"BW1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"09:00:00",
		eingaenge=[("KT-TV-NUSS", c.v1, 60, c.tb2)],
		ausgaenge=[("KT-BW-NUSS", c.bw1, 50)],
	)
	# Schokoboden mit gekaufter Kuvertüre -> lose Ware in Kiste KL1
	c.wl1 = neue_charge("KT-WL-NUSS-SCHOKO", f"WL1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"10:00:00",
		eingaenge=[("KT-BW-NUSS", c.bw1, 48), ("KT-SCHOKO", c.schoko, 6)],
		ausgaenge=[("KT-WL-NUSS-SCHOKO", c.wl1, 54, c.kl1)],
	)
	# Bruch nach dem Backen -> Rework R1 in Rework-Behälter RB1
	c.r1 = neue_charge("KT-RW-NUSS", f"R1-{k}", t1)
	buchen(
		ctx,
		"Repack",
		t1,
		"10:30:00",
		eingaenge=[("KT-BW-NUSS", c.bw1, 2)],
		ausgaenge=[("KT-RW-NUSS", c.r1, 2, c.rb1)],
	)

	# ---- Tag 2
	# Nachfüllen, bevor die Silos leer sind: alte und neue Charge vermischen sich
	c.mehl2 = neue_charge("KT-MEHL", f"M2-{k}", add_days(t2, -5), ctx.lieferant)
	c.zucker2 = neue_charge("KT-ZUCKER", f"Z2-{k}", add_days(t2, -20), ctx.lieferant)
	buchen(
		ctx,
		"Material Receipt",
		t2,
		"06:00:00",
		ausgaenge=[
			("KT-MEHL", c.mehl2, 1000, W),
			("KT-ZUCKER", c.zucker2, 1000, Z),
		],
	)
	# Veredelung V2: zweite Hälfte von GT1 (TB1 wird leer) + Haselnuss + Rework R1 (RB1 wird leer)
	c.v2 = neue_charge("KT-TV-NUSS", f"V2-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"07:00:00",
		eingaenge=[
			("KT-GT-MUERBE", c.gt1, 50, c.tb1),
			("KT-HASELNUSS", c.nuss, 9),
			("KT-RW-NUSS", c.r1, 2, c.rb1),
		],
		ausgaenge=[("KT-TV-NUSS", c.v2, 61, c.tb2)],
	)
	c.bw2 = neue_charge("KT-BW-NUSS", f"BW2-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"08:00:00",
		eingaenge=[("KT-TV-NUSS", c.v2, 61, c.tb2)],
		ausgaenge=[("KT-BW-NUSS", c.bw2, 51)],
	)
	c.wl2 = neue_charge("KT-WL-NUSS-SCHOKO", f"WL2-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"09:00:00",
		eingaenge=[("KT-BW-NUSS", c.bw2, 45), ("KT-SCHOKO", c.schoko, 6)],
		ausgaenge=[("KT-WL-NUSS-SCHOKO", c.wl2, 51, c.kl2)],
	)
	# Zweiter Grundteig GT2 -> Kakao-Veredelung, Teigrest wird Rework R2
	c.gt2 = neue_charge("KT-GT-MUERBE", f"GT2-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"09:30:00",
		eingaenge=[
			("KT-MEHL", None, 60, W),
			("KT-ZUCKER", None, 20, Z),
			("KT-BUTTER", c.butter, 20),
		],
		ausgaenge=[("KT-GT-MUERBE", c.gt2, 100, c.tb3)],
	)
	c.v3 = neue_charge("KT-TV-KAKAO", f"V3-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"10:00:00",
		eingaenge=[
			("KT-GT-MUERBE", c.gt2, 85, c.tb3),
			("KT-DINKEL", None, 5, D),
			("KT-KAKAO", c.kakao, 5),
			("KT-SIRUP", None, 5, T),
		],
		ausgaenge=[("KT-TV-KAKAO", c.v3, 100, c.tb4)],
	)
	c.r2 = neue_charge("KT-RW-MUERBE", f"R2-{k}", t2)
	buchen(
		ctx,
		"Repack",
		t2,
		"10:30:00",
		eingaenge=[("KT-GT-MUERBE", c.gt2, 5, c.tb3)],
		ausgaenge=[("KT-RW-MUERBE", c.r2, 5, c.rb2)],
	)
	c.bw3 = neue_charge("KT-BW-KAKAO", f"BW3-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"11:00:00",
		eingaenge=[("KT-TV-KAKAO", c.v3, 100, c.tb4)],
		ausgaenge=[("KT-BW-KAKAO", c.bw3, 85)],
	)
	# Füllen mit selbst gemachtem Nougat -> lose Ware in Kiste KL3
	c.wl3 = neue_charge("KT-WL-KAKAO-NOUGAT", f"WL3-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"12:00:00",
		eingaenge=[("KT-BW-KAKAO", c.bw3, 80), ("KT-NOUGAT", c.nougat, 20)],
		ausgaenge=[("KT-WL-KAKAO-NOUGAT", c.wl3, 100, c.kl3)],
	)

	# ---- Freigabe loser Ware durch die QS (KL2 wartet noch auf die Freigabe)
	sperre.freigeben(c.wl1, "Sensorik, Feuchte und Bruchanteil in Ordnung")
	sperre.freigeben(c.wl3, "Sensorik, Feuchte und Bruchanteil in Ordnung")

	# ---- Tag 3
	# Dinkelsilo ist leer: Leermeldung trennt die Chargen sauber, dann neue Lieferung
	c.leermeldung_dinkel = silo.leermeldung(D, f"{t3} 05:50:00", "Silo leergefahren")
	c.dinkel2 = neue_charge("KT-DINKEL", f"D2-{k}", add_days(t3, -4), ctx.lieferant)
	buchen(
		ctx,
		"Material Receipt",
		t3,
		"06:00:00",
		ausgaenge=[("KT-DINKEL", c.dinkel2, 500, D)],
	)
	# Neuer Grundteig GT3 mit 5 % Rework R2 (Teigrest vom Vortag)
	c.gt3 = neue_charge("KT-GT-MUERBE", f"GT3-{k}", t3)
	buchen(
		ctx,
		"Manufacture",
		t3,
		"07:00:00",
		eingaenge=[
			("KT-MEHL", None, 57, W),
			("KT-ZUCKER", None, 19, Z),
			("KT-BUTTER", c.butter, 19),
			("KT-RW-MUERBE", c.r2, 5, c.rb2),
		],
		ausgaenge=[("KT-GT-MUERBE", c.gt3, 100)],
	)
	# Verpacken aus dem Lager loser Ware (Kiste KL1 bleibt mit Rest belegt)
	c.l1 = neue_charge("KT-FW-NUSS-SCHOKO", f"L1-{k}", t3)
	buchen(
		ctx,
		"Manufacture",
		t3,
		"08:00:00",
		eingaenge=[("KT-WL-NUSS-SCHOKO", c.wl1, 40, c.kl1), ("KT-FOLIE", c.folie, 1)],
		ausgaenge=[("KT-FW-NUSS-SCHOKO", c.l1, 40)],
	)
	c.l2 = neue_charge("KT-FW-KAKAO-NOUGAT", f"L2-{k}", t3)
	buchen(
		ctx,
		"Manufacture",
		t3,
		"08:30:00",
		eingaenge=[("KT-WL-KAKAO-NOUGAT", c.wl3, 50, c.kl3), ("KT-FOLIE", c.folie, 1)],
		ausgaenge=[("KT-FW-KAKAO-NOUGAT", c.l2, 50)],
	)
	c.lieferschein = liefern(
		ctx, t3, [("KT-FW-NUSS-SCHOKO", c.l1, 30), ("KT-FW-KAKAO-NOUGAT", c.l2, 20)]
	).name
	return c


def _ausgabe(c):
	from keks_trace.trace import rueckverfolgung

	print(f"\nDemo-Kette {c.kuerzel}: Tag 1 = {formatdate(c.tag1)}, Tag 3 = {formatdate(c.tag3)}")
	for titel, charge, richtung in (
		("Rückruf Mehlcharge (vorwärts)", c.mehl, "Vorwärts"),
		("Reklamation Los L2 Kakao-Nougat (rückwärts)", c.l2, "Rückwärts"),
		("Grundteig Tag 3 (rückwärts, mit Rework)", c.gt3, "Rückwärts"),
	):
		r = rueckverfolgung(charge, richtung)
		print(f"\n== {titel}: {charge}")
		for z in r["chargen"]:
			print(
				f"  Gen {z['generation']}  {z['charge']:<20} {z.get('stufe') or '':<14} "
				f"Anteil {flt(z['anteil']) * 100:6.2f} %  hergestellt {formatdate(z.get('herstelldatum'))}"
				f"  Verfall/MHD {formatdate(z.get('verfall')) if z.get('verfall') else '-'}"
			)
		for kd in r.get("kunden", []):
			print(
				f"  -> Kunde {kd.kundenname}: Lieferschein {kd.lieferschein} am {formatdate(kd.lieferdatum)}, "
				f"{flt(kd.menge)} kg {kd.charge}"
			)

	print("\n== Silos und Tank (Bestand rechnerisch / möglicherweise noch enthalten)")
	for name in c.silo.values():
		i = silo.info(name)
		print(
			f"  {name:<22} "
			+ ", ".join(f"{b['charge']} {flt(b['menge']):g}" for b in i["bestand"])
			+ f"  | {', '.join(i['moeglich_enthalten'])}"
		)

	print("\n== Behälter")
	for code in (c.tb1, c.tb2, c.tb3, c.tb4, c.rb1, c.rb2, c.kl1, c.kl2, c.kl3):
		t = frappe.db.get_value("Produkttraeger", code, ["status", "charge", "menge"], as_dict=True)
		print(f"  {code:<20} {t.status:<8} {t.charge or '':<20} {flt(t.menge):g} kg")
