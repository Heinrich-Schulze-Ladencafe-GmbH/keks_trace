"""MHD Rohstoffe: welche Chargen laufen bald ab, und was bleibt bei normalem Verbrauch voraussichtlich übrig?

- Je Charge mit Bestand und Lagerort (auch Silo), MHD innerhalb der nächsten N Tage oder schon abgelaufen.
- Übrig am MHD: Verbrauch je Tag (wie im Bericht „Reichweite Rohstoffe“) bis zum MHD, verbraucht nach FEFO
  (früheres MHD zuerst). Was danach von dieser Charge noch da wäre, steht in „Voraussichtlich übrig“.
  Das ist eine Schätzung für Einkauf und QS, keine Buchung.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, nowdate

from keks_trace.keks_trace.report.reichweite_rohstoffe.reichweite_rohstoffe import STUFEN
from keks_trace.keks_trace.report.reichweite_rohstoffe.reichweite_rohstoffe import daten as reichweite


def execute(filters=None):
	filters = frappe._dict(filters or {})
	stufen = STUFEN.get(filters.stufe or "Rohstoff", ("Rohstoff",))
	return _spalten(), daten(
		stufen, int(filters.tage or 60), max(int(filters.verbrauch_tage or 60), 1), filters.artikel
	)


def _spalten():
	return [
		{"fieldname": "artikel", "label": _("Artikel"), "fieldtype": "Link", "options": "Item", "width": 110},
		{"fieldname": "name", "label": _("Bezeichnung"), "fieldtype": "Data", "width": 200},
		{"fieldname": "charge", "label": _("Charge"), "fieldtype": "Link", "options": "Batch", "width": 160},
		{"fieldname": "lieferant", "label": _("Lieferant"), "fieldtype": "Link", "options": "Supplier", "width": 140},
		{"fieldname": "mhd", "label": _("MHD"), "fieldtype": "Date", "width": 100},
		{"fieldname": "tage_bis_mhd", "label": _("Tage bis MHD"), "fieldtype": "Int", "width": 100},
		{"fieldname": "menge", "label": _("Bestand"), "fieldtype": "Float", "precision": 1, "width": 90},
		{"fieldname": "einheit", "label": _("Einheit"), "fieldtype": "Data", "width": 70},
		{"fieldname": "lagerort", "label": _("Lagerort"), "fieldtype": "Link", "options": "Warehouse", "width": 160},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "uebrig", "label": _("Voraussichtlich übrig am MHD"), "fieldtype": "Float", "precision": 1, "width": 150},
	]  # fmt: skip


def daten(stufen, tage=60, verbrauch_tage=60, artikel=None, heute=None) -> list[dict]:
	heute = getdate(heute or nowdate())
	bis = getdate(add_days(heute, tage))
	bedingung = "and b.item = %(artikel)s" if artikel else ""
	zeilen = frappe.db.sql(
		f"""
		select b.item as artikel, i.item_name as name, i.stock_uom as einheit, b.name as charge, b.supplier as lieferant,
			b.expiry_date as mhd, ifnull(b.kt_status, '') as status, sbe.warehouse as lagerort, sum(sbe.qty) as menge
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		join `tabBatch` b on b.name = sbe.batch_no
		join `tabItem` i on i.name = b.item
		where sbb.is_cancelled = 0 and sbb.docstatus = 1 and b.expiry_date is not null
			and i.kt_chargen_stufe in %(stufen)s {bedingung}
		group by b.item, i.item_name, i.stock_uom, b.name, b.supplier, b.expiry_date, b.kt_status, sbe.warehouse
		having sum(sbe.qty) > 0.000001
		""",
		{"stufen": tuple(stufen), "artikel": artikel},
		as_dict=True,
	)
	if not zeilen:
		return []
	pro_tag = {r["artikel"]: flt(r["verbrauch_tag"]) for r in reichweite(stufen, verbrauch_tage, artikel)}
	# FEFO je Artikel: Bestand bis einschließlich dieser Charge, verbraucht ab heute mit Verbrauch je Tag
	je_artikel = defaultdict(list)
	for z in zeilen:
		je_artikel[z.artikel].append(z)
	ergebnis = []
	for art, liste in je_artikel.items():
		liste.sort(key=lambda z: (getdate(z.mhd), z.charge, z.lagerort))
		kumuliert = 0.0
		for z in liste:
			mhd = getdate(z.mhd)
			kumuliert += flt(z.menge)
			tage_bis = date_diff(mhd, heute)
			verbraucht_bis_mhd = pro_tag.get(art, 0.0) * max(tage_bis, 0)
			uebrig = min(flt(z.menge), max(kumuliert - verbraucht_bis_mhd, 0.0))
			if mhd > bis:
				continue
			ergebnis.append(
				{
					"artikel": art,
					"name": z.name,
					"charge": z.charge,
					"lieferant": z.lieferant,
					"mhd": mhd,
					"tage_bis_mhd": tage_bis,
					"menge": flt(z.menge, 3),
					"einheit": "Stk" if z.einheit == "Nos" else z.einheit,
					"lagerort": z.lagerort,
					"status": z.status or _("Frei"),
					"uebrig": flt(uebrig, 3),
				}
			)
	ergebnis.sort(key=lambda z: (z["mhd"], z["name"], z["charge"]))
	return ergebnis
