"""Rückverfolgung vorwärts (wohin ist eine Charge gegangen) und rückwärts (woraus besteht sie).

Beide Richtungen laufen als eine rekursive SQL-Abfrage über `Chargen Genealogie`.
Der Anteil gibt an, welcher Bruchteil der gefundenen Charge (vorwärts) bzw. der
Startcharge (rückwärts) aus der jeweils anderen stammt, über alle Wege summiert.
"""

import frappe
from frappe.utils import flt

MAX_TIEFE = 60

_VORWAERTS = """
with recursive kette (charge, generation, anteil, pfad) as (
	select g.output_batch, 1, g.anteil,
		cast(concat(',', g.input_batch, ',', g.output_batch, ',') as char(8000))
	from `tabChargen Genealogie` g
	where g.input_batch = %(charge)s and g.storniert = 0
	union all
	select g.output_batch, k.generation + 1, k.anteil * g.anteil,
		concat(k.pfad, g.output_batch, ',')
	from `tabChargen Genealogie` g
	join kette k on g.input_batch = k.charge
	where g.storniert = 0
		and k.generation < %(max_tiefe)s
		and locate(cast(concat(',', g.output_batch, ',') as binary), cast(k.pfad as binary)) = 0
)
select charge, min(generation) as generation, sum(anteil) as anteil
from kette
group by charge
"""

_RUECKWAERTS = """
with recursive kette (charge, generation, anteil, pfad) as (
	select g.input_batch, 1, g.anteil,
		cast(concat(',', g.output_batch, ',', g.input_batch, ',') as char(8000))
	from `tabChargen Genealogie` g
	where g.output_batch = %(charge)s and g.storniert = 0
	union all
	select g.input_batch, k.generation + 1, k.anteil * g.anteil,
		concat(k.pfad, g.input_batch, ',')
	from `tabChargen Genealogie` g
	join kette k on g.output_batch = k.charge
	where g.storniert = 0
		and k.generation < %(max_tiefe)s
		and locate(cast(concat(',', g.input_batch, ',') as binary), cast(k.pfad as binary)) = 0
)
select charge, min(generation) as generation, sum(anteil) as anteil
from kette
group by charge
"""


def vorwaerts(charge: str) -> list[dict]:
	return _mit_details(frappe.db.sql(_VORWAERTS, {"charge": charge, "max_tiefe": MAX_TIEFE}, as_dict=True))


def rueckwaerts(charge: str) -> list[dict]:
	return _mit_details(frappe.db.sql(_RUECKWAERTS, {"charge": charge, "max_tiefe": MAX_TIEFE}, as_dict=True))


def kunden(chargen: list[str]) -> list[dict]:
	"""Lieferungen (Lieferscheine) an Kunden, die eine der Chargen enthalten."""
	if not chargen:
		return []
	return frappe.db.sql(
		"""
		select sbe.batch_no as charge, dn.name as lieferschein, dn.customer as kunde,
			dn.customer_name as kundenname, dn.posting_date as lieferdatum,
			sum(abs(sbe.qty)) as menge
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		join `tabDelivery Note` dn on dn.name = sbb.voucher_no
		where sbb.voucher_type = 'Delivery Note'
			and sbb.is_cancelled = 0
			and sbb.docstatus = 1
			and dn.docstatus = 1
			and dn.is_return = 0
			and sbe.batch_no in %(chargen)s
		group by sbe.batch_no, dn.name, dn.customer, dn.customer_name, dn.posting_date
		order by dn.posting_date, dn.name
		""",
		{"chargen": tuple(chargen)},
		as_dict=True,
	)


def rueckverfolgung(charge: str, richtung: str = "Vorwärts") -> dict:
	"""Komplette Rückverfolgung einer Charge inkl. Kunden (vorwärts) bzw. Lieferanten (rückwärts)."""
	if not frappe.db.exists("Batch", charge):
		frappe.throw(frappe._("Charge {0} existiert nicht.").format(charge))

	if richtung == "Rückwärts":
		chargen = rueckwaerts(charge)
		return {
			"start": _details([charge])[0],
			"richtung": richtung,
			"chargen": chargen,
			"lieferanten": [c for c in chargen if c.get("lieferant")],
		}

	chargen = vorwaerts(charge)
	return {
		"start": _details([charge])[0],
		"richtung": "Vorwärts",
		"chargen": chargen,
		"kunden": kunden([charge] + [c["charge"] for c in chargen]),
	}


def _details(chargen: list[str]) -> list[dict]:
	if not chargen:
		return []
	zeilen = frappe.get_all(
		"Batch",
		filters={"name": ["in", chargen]},
		fields=[
			"name as charge",
			"item as artikel",
			"item_name as artikelname",
			"kt_chargen_stufe as stufe",
			"manufacturing_date as herstelldatum",
			"kt_ursprungsdatum as ursprungsdatum",
			"expiry_date as verfall",
			"supplier as lieferant",
			"batch_qty as bestand",
		],
	)
	nach_name = {z.charge: z for z in zeilen}
	return [nach_name[c] for c in chargen if c in nach_name]


_STUFEN_REIHENFOLGE = {
	"Rohstoff": 0,
	"Packmittel": 1,
	"Teig": 2,
	"Rework": 3,
	"Backware lose": 4,
	"Fertigware": 5,
}


def _mit_details(treffer: list[dict]) -> list[dict]:
	info = {d.charge: d for d in _details([t.charge for t in treffer])}
	ergebnis = []
	for t in treffer:
		zeile = dict(info.get(t.charge, {"charge": t.charge}))
		zeile["generation"] = int(t.generation)
		zeile["anteil"] = flt(t.anteil, 6)
		ergebnis.append(zeile)
	ergebnis.sort(
		key=lambda z: (
			z["generation"],
			str(z.get("herstelldatum") or ""),
			_STUFEN_REIHENFOLGE.get(z.get("stufe"), 9),
			z["charge"],
		)
	)
	return ergebnis
