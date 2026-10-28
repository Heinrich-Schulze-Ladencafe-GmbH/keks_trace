"""Demo: Rework-Kette über drei Tage auf einer ERPNext-Instanz durchspielen.

Aufruf auf dem Server (Firma muss über den Einrichtungsassistenten angelegt sein):

	bench --site <site> execute keks_trace.demo.run

Legt Demo-Stammdaten an (Artikel mit Präfix KT-), bucht drei Produktionstage mit Rework,
verpackt, liefert an einen Demo-Kunden und gibt die Rückverfolgung aus.
Jeder Lauf erzeugt neue Chargen (eindeutiges Kürzel), Stammdaten werden wiederverwendet.
"""

import frappe
from frappe.utils import add_days, flt, formatdate, getdate, now_datetime, nowdate

ALLERGENGRUPPEN = {
	"Butterteig": "Gluten, Milch, Ei",
	"Nussteig": "Gluten, Milch, Ei, Haselnuss",
}

# Artikelnummer: (Bezeichnung, Stufe, Allergengruppe, Haltbarkeit in Tagen oder None, Einheit)
ARTIKEL = {
	"KT-MEHL": ("Weizenmehl Type 550", "Rohstoff", None, 365, "Kg"),
	"KT-ZUCKER": ("Zucker", "Rohstoff", None, 730, "Kg"),
	"KT-BUTTER": ("Butter", "Rohstoff", None, 60, "Kg"),
	"KT-HASELNUSS": ("Haselnüsse gehackt", "Rohstoff", None, 270, "Kg"),
	"KT-FOLIE": ("Verpackungsfolie", "Packmittel", None, None, "Kg"),
	"KT-TEIG-BUTTER": ("Butterkeks-Teig", "Teig", "Butterteig", None, "Kg"),
	"KT-TEIG-NUSS": ("Nusskeks-Teig", "Teig", "Nussteig", None, "Kg"),
	"KT-BACK-BUTTER": ("Butterkeks lose", "Backware lose", "Butterteig", 180, "Kg"),
	"KT-BACK-NUSS": ("Nusskeks lose", "Backware lose", "Nussteig", 180, "Kg"),
	"KT-RW-BUTTER": ("Rework Butterteig/Bruch", "Rework", "Butterteig", 7, "Kg"),
	"KT-RW-NUSS": ("Rework Nussteig/Bruch", "Rework", "Nussteig", 7, "Kg"),
	"KT-FW-BUTTER": ("Butterkeks 200 g verpackt", "Fertigware", "Butterteig", 270, "Kg"),
}

ROHSTOFF_PREIS = {"KT-MEHL": 0.6, "KT-ZUCKER": 0.9, "KT-BUTTER": 6.5, "KT-HASELNUSS": 9.0, "KT-FOLIE": 4.0}

# (Rework-Artikel, Ziel-Teig, max. Anteil %)
REWORK_REGELN = [
	("KT-RW-BUTTER", "KT-TEIG-BUTTER", 10),
	("KT-RW-BUTTER", "KT-TEIG-NUSS", 10),
	("KT-RW-NUSS", "KT-TEIG-NUSS", 10),
]


def run(company: str | None = None, kuerzel: str | None = None):
	ctx = stammdaten(company)
	kette = drei_tage_kette(ctx, kuerzel)
	frappe.db.commit()
	_ausgabe(kette)
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
	for code, (name, stufe, gruppe, haltbarkeit, uom) in ARTIKEL.items():
		if frappe.db.exists("Item", code):
			continue
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": item_group,
				"stock_uom": uom,
				"is_stock_item": 1,
				"include_item_in_manufacturing": 1,
				"has_batch_no": 1,
				"has_expiry_date": 1 if haltbarkeit else 0,
				"shelf_life_in_days": haltbarkeit or 0,
				"valuation_rate": ROHSTOFF_PREIS.get(code, 0),
				"kt_chargen_stufe": stufe,
				"kt_allergengruppe": gruppe,
			}
		).insert()

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

	return frappe._dict(
		company=company,
		lager=f"Stores - {abbr}",
		produktion=f"Work In Progress - {abbr}",
		fertig=f"Finished Goods - {abbr}",
		lieferant=lieferant,
		kunde=kunde,
	)


def _blatt(doctype: str, bevorzugt: str | None) -> str:
	"""Ein Nicht-Gruppen-Eintrag eines Baums (Artikelgruppe, Kundengruppe, ...)."""
	if bevorzugt and frappe.db.exists(doctype, {"name": bevorzugt, "is_group": 0}):
		return bevorzugt
	return frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="lft asc")


# ---------------------------------------------------------------------------
# Buchungshelfer (so würden es später die Scanner-Seiten tun)
# ---------------------------------------------------------------------------


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


def buchen(ctx, zweck: str, datum, zeit: str, eingaenge=(), ausgaenge=(), submit: bool = True):
	"""Lagerbuchung erzeugen.

	eingaenge / ausgaenge: Listen von (Artikel, Charge, Menge). Für Wareneingang
	("Material Receipt") nur ausgaenge, optional mit Preis als 4. Element.
	"""
	ziel_lager = ctx.fertig if zweck in ("Manufacture", "Repack") else ctx.lager
	zeilen = []
	for item, charge, menge, *_rest in eingaenge:
		zeilen.append(
			_zeile(item, charge, menge, s_warehouse=ctx.lager if _ist_rohstoff(item) else ctx.produktion)
		)
	for i, (item, charge, menge, *rest) in enumerate(ausgaenge):
		lager = ctx.produktion if _stufe(item) in ("Teig", "Rework", "Backware lose") else ziel_lager
		if zweck == "Material Receipt":
			lager = ctx.lager
		z = _zeile(item, charge, menge, t_warehouse=lager)
		if zweck == "Material Receipt":
			z["basic_rate"] = rest[0] if rest else ROHSTOFF_PREIS.get(item, 1)
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


def _zeile(item, charge, menge, s_warehouse=None, t_warehouse=None):
	uom = frappe.get_cached_value("Item", item, "stock_uom")
	return {
		"item_code": item,
		"qty": menge,
		"uom": uom,
		"stock_uom": uom,
		"conversion_factor": 1,
		"transfer_qty": menge,
		"s_warehouse": s_warehouse,
		"t_warehouse": t_warehouse,
		"use_serial_batch_fields": 1,
		"batch_no": charge,
	}


def _stufe(item):
	return frappe.get_cached_value("Item", item, "kt_chargen_stufe")


def _ist_rohstoff(item):
	return _stufe(item) in ("Rohstoff", "Packmittel")


def liefern(ctx, datum, item, charge, menge, rate=8.0):
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
	"""Tag 1-3 mit Rework. Gibt die Chargennamen zurück."""
	k = kuerzel or now_datetime().strftime("%y%m%d%H%M%S")
	t1 = getdate(start) if start else add_days(nowdate(), -2)
	t2, t3 = add_days(t1, 1), add_days(t1, 2)
	c = frappe._dict(kuerzel=k, tag1=t1, tag2=t2, tag3=t3)

	# Wareneingang (Tag 1): eine Mehlcharge für alle drei Tage.
	c.mehl = neue_charge("KT-MEHL", f"M-{k}", add_days(t1, -10), ctx.lieferant)
	c.zucker = neue_charge("KT-ZUCKER", f"Z-{k}", add_days(t1, -30), ctx.lieferant)
	c.butter = neue_charge("KT-BUTTER", f"BU-{k}", add_days(t1, -3), ctx.lieferant)
	c.folie = neue_charge("KT-FOLIE", f"F-{k}", add_days(t1, -60), ctx.lieferant)
	buchen(
		ctx,
		"Material Receipt",
		t1,
		"06:00:00",
		ausgaenge=[
			("KT-MEHL", c.mehl, 500),
			("KT-ZUCKER", c.zucker, 200),
			("KT-BUTTER", c.butter, 300),
			("KT-FOLIE", c.folie, 20),
		],
	)

	# Tag 1: Teig ohne Rework -> Backen -> Bruch wird Rework R1
	c.teig1 = neue_charge("KT-TEIG-BUTTER", f"T1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"07:00:00",
		eingaenge=[("KT-MEHL", c.mehl, 50), ("KT-ZUCKER", c.zucker, 20), ("KT-BUTTER", c.butter, 30)],
		ausgaenge=[("KT-TEIG-BUTTER", c.teig1, 100)],
	)
	c.back1 = neue_charge("KT-BACK-BUTTER", f"B1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"09:00:00",
		eingaenge=[("KT-TEIG-BUTTER", c.teig1, 100)],
		ausgaenge=[("KT-BACK-BUTTER", c.back1, 85)],
	)
	c.rework1 = neue_charge("KT-RW-BUTTER", f"R1-{k}", t1)
	buchen(
		ctx,
		"Repack",
		t1,
		"10:00:00",
		eingaenge=[("KT-BACK-BUTTER", c.back1, 5)],
		ausgaenge=[("KT-RW-BUTTER", c.rework1, 5)],
	)

	# Tag 2: Teig mit 5 kg Rework R1 (5 %) -> Backen -> Bruch wird Rework R2
	c.teig2 = neue_charge("KT-TEIG-BUTTER", f"T2-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"07:00:00",
		eingaenge=[
			("KT-MEHL", c.mehl, 45),
			("KT-ZUCKER", c.zucker, 20),
			("KT-BUTTER", c.butter, 30),
			("KT-RW-BUTTER", c.rework1, 5),
		],
		ausgaenge=[("KT-TEIG-BUTTER", c.teig2, 100)],
	)
	c.back2 = neue_charge("KT-BACK-BUTTER", f"B2-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"09:00:00",
		eingaenge=[("KT-TEIG-BUTTER", c.teig2, 100)],
		ausgaenge=[("KT-BACK-BUTTER", c.back2, 85)],
	)
	c.rework2 = neue_charge("KT-RW-BUTTER", f"R2-{k}", t2)
	buchen(
		ctx,
		"Repack",
		t2,
		"10:00:00",
		eingaenge=[("KT-BACK-BUTTER", c.back2, 5)],
		ausgaenge=[("KT-RW-BUTTER", c.rework2, 5)],
	)

	# Tag 3: Teig mit Rework R2 -> Backen
	c.teig3 = neue_charge("KT-TEIG-BUTTER", f"T3-{k}", t3)
	buchen(
		ctx,
		"Manufacture",
		t3,
		"07:00:00",
		eingaenge=[
			("KT-MEHL", c.mehl, 45),
			("KT-ZUCKER", c.zucker, 20),
			("KT-BUTTER", c.butter, 30),
			("KT-RW-BUTTER", c.rework2, 5),
		],
		ausgaenge=[("KT-TEIG-BUTTER", c.teig3, 100)],
	)
	c.back3 = neue_charge("KT-BACK-BUTTER", f"B3-{k}", t3)
	buchen(
		ctx,
		"Manufacture",
		t3,
		"09:00:00",
		eingaenge=[("KT-TEIG-BUTTER", c.teig3, 100)],
		ausgaenge=[("KT-BACK-BUTTER", c.back3, 85)],
	)

	# Tag 3: Backware lose vom Tag 1 wird verpackt (MHD ab Backtag 1) und geliefert.
	c.los1 = neue_charge("KT-FW-BUTTER", f"L1-{k}", t3)
	buchen(
		ctx,
		"Manufacture",
		t3,
		"13:00:00",
		eingaenge=[("KT-BACK-BUTTER", c.back1, 40), ("KT-FOLIE", c.folie, 1)],
		ausgaenge=[("KT-FW-BUTTER", c.los1, 40)],
	)
	c.lieferschein = liefern(ctx, t3, "KT-FW-BUTTER", c.los1, 30).name
	return c


def _ausgabe(c):
	from keks_trace.trace import rueckverfolgung

	print(f"\nDemo-Kette {c.kuerzel}: Tag 1 = {formatdate(c.tag1)}, Tag 3 = {formatdate(c.tag3)}")
	for titel, charge, richtung in (
		("Rückruf Mehlcharge (vorwärts)", c.mehl, "Vorwärts"),
		("Reklamation Los L1 (rückwärts)", c.los1, "Rückwärts"),
		("Teig Tag 3 (rückwärts, über 2 Rework-Generationen)", c.teig3, "Rückwärts"),
	):
		r = rueckverfolgung(charge, richtung)
		print(f"\n== {titel}: {charge}")
		for z in r["chargen"]:
			print(
				f"  Gen {z['generation']}  {z['charge']:<22} {z.get('stufe') or '':<14} "
				f"Anteil {flt(z['anteil']) * 100:6.2f} %  hergestellt {formatdate(z.get('herstelldatum'))}"
				f"  Verfall {formatdate(z.get('verfall')) if z.get('verfall') else '-'}"
			)
		for kd in r.get("kunden", []):
			print(
				f"  -> Kunde {kd.kundenname}: Lieferschein {kd.lieferschein} am {formatdate(kd.lieferdatum)}, {flt(kd.menge)} kg {kd.charge}"
			)
