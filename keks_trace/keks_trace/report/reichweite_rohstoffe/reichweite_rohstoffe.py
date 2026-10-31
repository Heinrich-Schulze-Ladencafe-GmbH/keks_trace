"""Reichweite Rohstoffe: Wie lange reicht der Bestand, was ist bestellt, was steht im Kontrakt noch offen,
und was brauchen die offenen Kundenaufträge? Eine Übersicht für den Einkauf (kein Bestellvorschlag).

- Bestand: alle Lagerorte inkl. Silos (ERPNext-Lagerbestand).
- Bestellt: offene Bestellungen, noch nicht geliefert.
- Kontrakt offen: Rahmenaufträge (Einkauf), noch nicht abgerufen, nur gültige.
- Verbrauch/Tag: was in den letzten N Tagen in der Produktion verbraucht wurde, je Tag.
- Bedarf Aufträge: offene Kundenaufträge, noch nicht verpackt, über die Rezepte bis zum Rohstoff
  heruntergerechnet (ohne Zwischenbestände wie lose Ware, also eher zu viel).
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, flt, nowdate

STUFEN = {
	"Rohstoff": ("Rohstoff",),
	"Packmittel": ("Packmittel",),
	"Rohstoff und Packmittel": ("Rohstoff", "Packmittel"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	stufen = STUFEN.get(filters.stufe or "Rohstoff", ("Rohstoff",))
	tage = max(int(filters.tage or 60), 1)
	return _spalten(), daten(stufen, tage, filters.artikel)


def _spalten():
	return [
		{"fieldname": "artikel", "label": _("Artikel"), "fieldtype": "Link", "options": "Item", "width": 120},
		{"fieldname": "name", "label": _("Bezeichnung"), "fieldtype": "Data", "width": 200},
		{"fieldname": "einheit", "label": _("Einheit"), "fieldtype": "Data", "width": 70},
		{"fieldname": "bestand", "label": _("Bestand"), "fieldtype": "Float", "precision": 1, "width": 100},
		{"fieldname": "bestellt", "label": _("Bestellt"), "fieldtype": "Float", "precision": 1, "width": 100},
		{"fieldname": "kontrakt", "label": _("Kontrakt offen"), "fieldtype": "Float", "precision": 1, "width": 110},
		{"fieldname": "verbrauch_tag", "label": _("Verbrauch/Tag"), "fieldtype": "Float", "precision": 1, "width": 110},
		{"fieldname": "reicht_tage", "label": _("Reicht Tage"), "fieldtype": "Int", "width": 95},
		{"fieldname": "reicht_bis", "label": _("Reicht bis"), "fieldtype": "Date", "width": 100},
		{"fieldname": "mit_bestellt_tage", "label": _("Tage inkl. bestellt + Kontrakt"), "fieldtype": "Int", "width": 120},
		{"fieldname": "bedarf_auftraege", "label": _("Bedarf Aufträge"), "fieldtype": "Float", "precision": 1, "width": 120},
		{"fieldname": "frei_nach_auftraegen", "label": _("Bestand + bestellt minus Bedarf"), "fieldtype": "Float", "precision": 1, "width": 140},
	]  # fmt: skip


def daten(stufen, tage=60, artikel=None) -> list[dict]:
	filter_ = {"kt_chargen_stufe": ["in", stufen], "disabled": 0, "is_stock_item": 1}
	if artikel:
		filter_["name"] = artikel
	items = frappe.get_all(
		"Item", filters=filter_, fields=["name", "item_name", "stock_uom"], order_by="item_name"
	)
	if not items:
		return []
	namen = tuple(i.name for i in items)
	bin_ = {
		b.item_code: b
		for b in frappe.db.sql(
			"""select item_code, sum(actual_qty) as bestand, sum(ordered_qty) as bestellt
			from `tabBin` where item_code in %(a)s group by item_code""",
			{"a": namen},
			as_dict=True,
		)
	}
	kontrakt = dict(
		frappe.db.sql(
			"""select boi.item_code, sum(greatest(boi.qty - boi.ordered_qty, 0))
			from `tabBlanket Order Item` boi join `tabBlanket Order` bo on bo.name = boi.parent
			where bo.docstatus = 1 and bo.blanket_order_type = 'Purchasing'
				and (bo.to_date is null or bo.to_date >= %(heute)s) and boi.item_code in %(a)s
			group by boi.item_code""",
			{"a": namen, "heute": nowdate()},
		)
	)
	verbrauch = dict(
		frappe.db.sql(
			"""select sle.item_code, -sum(sle.actual_qty)
			from `tabStock Ledger Entry` sle
			join `tabStock Entry` se on se.name = sle.voucher_no and sle.voucher_type = 'Stock Entry'
			where sle.is_cancelled = 0 and sle.actual_qty < 0 and sle.item_code in %(a)s
				and se.purpose in ('Manufacture', 'Repack', 'Material Issue')
				and sle.posting_date >= %(ab)s
			group by sle.item_code""",
			{"a": namen, "ab": add_days(nowdate(), -tage)},
		)
	)
	bedarf = bedarf_aus_auftraegen(set(stufen))
	zeilen = []
	for i in items:
		b = bin_.get(i.name) or frappe._dict(bestand=0, bestellt=0)
		bestand, bestellt, offen = flt(b.bestand), flt(b.bestellt), flt(kontrakt.get(i.name))
		pro_tag = flt(verbrauch.get(i.name)) / tage
		reicht = int(bestand / pro_tag) if pro_tag > 1e-9 else None
		zeilen.append(
			{
				"artikel": i.name,
				"name": i.item_name,
				"einheit": "Stk" if i.stock_uom == "Nos" else i.stock_uom,
				"bestand": bestand,
				"bestellt": bestellt,
				"kontrakt": offen,
				"verbrauch_tag": pro_tag,
				"reicht_tage": reicht,
				"reicht_bis": add_days(nowdate(), reicht) if reicht is not None else None,
				"mit_bestellt_tage": int((bestand + bestellt + offen) / pro_tag) if pro_tag > 1e-9 else None,
				"bedarf_auftraege": flt(bedarf.get(i.name)),
				"frei_nach_auftraegen": bestand + bestellt - flt(bedarf.get(i.name)),
			}
		)
	zeilen.sort(key=lambda z: (z["reicht_tage"] is None, z["reicht_tage"] or 0, z["name"]))
	return zeilen


def bedarf_aus_auftraegen(stufen: set) -> dict:
	"""Offene Kundenaufträge (noch nicht verpackt) bis auf Rohstoffe/Packmittel herunterrechnen."""
	offen = frappe.db.sql(
		"""
		select soi.parent as auftrag, soi.item_code as artikel, soi.stock_qty as menge
		from `tabSales Order Item` soi join `tabSales Order` so on so.name = soi.parent
		where so.docstatus = 1 and so.status not in ('Completed', 'Closed', 'On Hold')
			and soi.delivered_qty < soi.qty
		""",
		as_dict=True,
	)
	if not offen:
		return {}
	verpackt = {
		(v.auftrag, v.artikel): flt(v.menge)
		for v in frappe.db.sql(
			"""select se.kt_kundenauftrag as auftrag, sed.item_code as artikel, sum(sed.transfer_qty) as menge
			from `tabStock Entry Detail` sed join `tabStock Entry` se on se.name = sed.parent
			where se.docstatus = 1 and se.kt_kundenauftrag in %(a)s and sed.is_finished_item = 1
			group by se.kt_kundenauftrag, sed.item_code""",
			{"a": tuple({o.auftrag for o in offen})},
			as_dict=True,
		)
	}
	bedarf = defaultdict(float)
	for o in offen:
		rest = max(flt(o.menge) - verpackt.get((o.auftrag, o.artikel), 0), 0)
		if rest > 0:
			_aufloesen(o.artikel, rest, stufen, bedarf)
	return bedarf


def _aufloesen(artikel, menge, stufen, bedarf, tiefe=0):
	if tiefe > 10:
		return
	bom = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})
	if not bom:
		return
	basis = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1
	for z in frappe.get_all("BOM Item", {"parent": bom}, ["item_code", "stock_qty"]):
		m = menge * flt(z.stock_qty) / basis
		if frappe.get_cached_value("Item", z.item_code, "kt_chargen_stufe") in stufen:
			bedarf[z.item_code] += m
		else:
			_aufloesen(z.item_code, m, stufen, bedarf, tiefe + 1)
