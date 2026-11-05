"""Demo: Stammdaten anlegen (Lager, Artikel, Rezepte, Silos, Stationen, Prüfpläne) und Prüfungen vorbelegen."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from keks_trace.demo.konstanten import (
	ALLERGENGRUPPEN,
	ARTIKEL,
	AUF_PAPIER,
	BIO_LIEFERANT,
	FREIGABE_PFLICHT,
	KENNZEICHNUNG,
	PRUEFPLAENE,
	REWORK_REGELN,
	REZEPTE,
	ROHSTOFF_PREIS,
	SILOS,
	UMLAGER_LAGER,
	VERPACKUNG,
)


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


def standardlager(company: str) -> tuple[str, str, str]:
	"""Rohstoff-, Produktions- und Fertigwarenlager der Firma, unabhängig von der Sprache der Einrichtung
	(„Stores“ bzw. „Lagerräume“): aus den Standardlagern der Firma, sonst über den übersetzten Namen."""
	c = frappe.get_cached_doc("Company", company)
	ergebnis = []
	for feld, englisch in (
		("default_warehouse", "Stores"),
		("default_wip_warehouse", "Work In Progress"),
		("default_fg_warehouse", "Finished Goods"),
	):
		sprache = frappe.db.get_single_value("System Settings", "language") or "en"
		namen = list({englisch, _(englisch), _(englisch, lang=sprache)})
		lager = c.get(feld) or frappe.db.get_value(
			"Warehouse", {"company": company, "is_group": 0, "warehouse_name": ["in", namen]}
		)
		if not lager:
			frappe.throw(
				f"Firma {company}: kein Lager für {englisch} gefunden (Standardlager an der Firma setzen)."
			)
		ergebnis.append(lager)
	return tuple(ergebnis)


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

	for code, werte in KENNZEICHNUNG.items():
		frappe.db.set_value("Item", code, werte)

	for code, einheiten in VERPACKUNG.items():
		item = frappe.get_doc("Item", code)
		geaendert = False
		for uom, (kg, gtin) in einheiten.items():
			if not any(u.uom == uom for u in item.uoms):
				item.append("uoms", {"uom": uom, "conversion_factor": kg})
				geaendert = True
			if not any(b.barcode == gtin for b in item.barcodes) and not frappe.db.exists(
				"Item Barcode", {"barcode": gtin}
			):
				item.append("barcodes", {"barcode": gtin, "barcode_type": "EAN", "uom": uom})
				geaendert = True
		if not item.sales_uom:
			item.sales_uom = "Karton"
			geaendert = True
		if geaendert:
			item.save()

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

	bio, kontrollstelle = BIO_LIEFERANT
	if not frappe.db.exists("Supplier", bio):
		frappe.get_doc(
			{"doctype": "Supplier", "supplier_name": bio, "supplier_group": _blatt("Supplier Group", None)}
		).insert()
	if getdate(frappe.db.get_value("Supplier", bio, "kt_bio_gueltig_bis") or "2000-01-01") < getdate():
		frappe.db.set_value(
			"Supplier",
			bio,
			{"kt_bio_kontrollstelle": kontrollstelle, "kt_bio_gueltig_bis": add_days(nowdate(), 365)},
		)

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

	verkauf = f"Lagerverkauf - {abbr}"
	if not frappe.db.exists("Warehouse", verkauf):
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "Lagerverkauf",
				"company": company,
				"parent_warehouse": frappe.db.get_value(
					"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["in", ["", None]]}
				),
			}
		).insert()
	roh_lager, wip_lager, fertig_lager = standardlager(company)
	for station in (
		"Backstube",
		"Verpackung",
		"Lager",
		"Versand",
		"Herzen Garnieren",
		"Herzen Verpackung",
		"Lagerverkauf",
	):
		if not frappe.db.exists("Terminal Station", station):
			frappe.get_doc(
				{
					"doctype": "Terminal Station",
					"station_name": station,
					"typ": station,
					"company": company,
					"rohstofflager": roh_lager,
					"produktionslager": wip_lager,
					"fertiglager": fertig_lager,
					"umlager_ziel": verkauf if station == "Lagerverkauf" else None,
				}
			).insert()
	frappe.db.set_value(
		"Terminal Station", "Backstube", "f_wareneingang", 1
	)  # Anlieferung direkt in die Backstube
	# Gescannt wird nur in der Backstube (Rohstoffe, Teige) und bei Paletten/Kartons; sonst schlägt das Terminal vor
	for station in ("Verpackung", "Herzen Garnieren", "Herzen Verpackung"):
		if frappe.db.exists("Terminal Station", station):
			# Rework bucht nur die Backstube (Flussschema F18)
			frappe.db.set_value("Terminal Station", station, {"zutaten_vorschlagen": 1, "f_rework": 0})
	if not frappe.db.get_value("Terminal Station", "Lagerverkauf", "umlager_ziel"):
		frappe.db.set_value("Terminal Station", "Lagerverkauf", "umlager_ziel", verkauf)
	# Am Lager wird das Ziel beim Umlagern gewählt: Fertigwarenlager, Außenlager oder Lagerverkauf
	frappe.db.set_value("Terminal Station", "Lager", "umlager_ziel", None)
	wurzel = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["in", ["", None]]}
	)
	for name in UMLAGER_LAGER:
		if not frappe.db.exists("Warehouse", f"{name} - {abbr}"):
			frappe.get_doc(
				{"doctype": "Warehouse", "warehouse_name": name, "company": company, "parent_warehouse": wurzel}
			).insert()  # fmt: skip
	for lager in [f"{n} - {abbr}" for n in UMLAGER_LAGER] + [fertig_lager, verkauf]:
		frappe.db.set_value("Warehouse", lager, "kt_umlagerziel", 1)
	frappe.db.set_value("Warehouse", verkauf, "kt_lagerverkauf", 1)

	_pruefplaene()

	return frappe._dict(
		company=company,
		lager=roh_lager,
		produktion=wip_lager,
		fertig=fertig_lager,
		lieferant=lieferant,
		kunde=kunde,
		verkauf=verkauf,
		silo_lager={},
		abbr=abbr,
		wurzel=wurzel,
	)


def _pruefplaene():
	for titel in AUF_PAPIER:
		if frappe.db.exists("Pruefplan", titel):
			frappe.db.set_value("Pruefplan", titel, "aktiv", 0)
	for p in PRUEFPLAENE:
		if frappe.db.exists("Pruefplan", p["titel"]):
			continue
		werte = {k: v for k, v in p.items() if k not in ("stationen", "artikel")}
		doc = frappe.get_doc({"doctype": "Pruefplan", **werte})
		for st in p.get("stationen", []):
			if frappe.db.exists("Terminal Station", st):
				doc.append("stationen", {"station": st})
		for a in p.get("artikel", []):
			if frappe.db.exists("Item", a):
				doc.append("artikel", {"artikel": a})
		doc.insert()


def metalldetektor_ok(station: str = "Verpackung"):
	"""Bestandene Metalldetektor-Prüfung erfassen (Demo und Tests)."""
	from keks_trace import haccp

	for p in haccp.fuer_station(station):
		eingabe = (
			{"koerper": {k: True for k in p.koerper()}}
			if p.art == "Prüfkörper"
			else {"ok": True}
			if p.art == "Ja/Nein"
			else {"wert": p.grenze("max_wert") or p.grenze("min_wert")}
		)
		haccp.erfassen(station, p.name, eingabe)


def _blatt(doctype: str, bevorzugt: str | None) -> str:
	"""Ein Nicht-Gruppen-Eintrag eines Baums (Artikelgruppe, Kundengruppe, ...)."""
	if bevorzugt and frappe.db.exists(doctype, {"name": bevorzugt, "is_group": 0}):
		return bevorzugt
	return frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="lft asc")


def pruefungen_altern(*plaene):
	"""Frühere Prüfungen dieser Pläne zurückdatieren, damit der Test nicht von der Uhrzeit abhängt
	(eine OK-Prüfung aus einem Lauf vor wenigen Minuten wäre sonst noch gültig)."""
	frappe.db.sql(
		"update `tabPruefung` set zeitpunkt = date_sub(zeitpunkt, interval 2 day) where pruefplan in %(p)s",
		{"p": tuple(plaene)},
	)
