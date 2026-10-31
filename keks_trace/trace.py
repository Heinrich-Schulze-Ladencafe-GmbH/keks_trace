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


def lagerverkauf(chargen: list[str]) -> list[dict]:
	"""Je Charge: an Endverbraucher verkauft und noch vorrätig im Lagerverkauf (Ziel-Lagerorte der Stationen)."""
	lager = [
		z for z in frappe.get_all("Terminal Station", filters={"f_umlagern": 1}, pluck="umlager_ziel") if z
	]
	if not chargen or not lager:
		return []
	zeilen = frappe.db.sql(
		"""
		select sbe.batch_no as charge, sbe.warehouse as lagerort,
			sum(sbe.qty) as bestand,
			sum(if(se.stock_entry_type = 'Abverkauf Lagerverkauf', -sbe.qty, 0)) as verkauft
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		left join `tabStock Entry` se on se.name = sbb.voucher_no and sbb.voucher_type = 'Stock Entry'
		where sbe.batch_no in %(c)s and sbe.warehouse in %(l)s and sbb.is_cancelled = 0 and sbb.docstatus = 1
		group by sbe.batch_no, sbe.warehouse
		""",
		{"c": tuple(chargen), "l": tuple(set(lager))},
		as_dict=True,
	)
	return [z for z in zeilen if flt(z.bestand) > 1e-6 or flt(z.verkauft) > 1e-6]


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

	from keks_trace.palette import paletten_fuer

	chargen = vorwaerts(charge)
	alle = [charge] + [c["charge"] for c in chargen]
	return {
		"start": _details([charge])[0],
		"richtung": "Vorwärts",
		"chargen": chargen,
		"kunden": kunden(alle),
		"paletten": paletten_fuer(alle),
		"lagerverkauf": lagerverkauf(alle),
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
			"kt_backtag as backtag",
			"expiry_date as verfall",
			"supplier as lieferant",
			"batch_qty as bestand",
			"kt_kennzeichen as kennzeichen",
		],
	)
	nach_name = {z.charge: z for z in zeilen}
	return [nach_name[c] for c in chargen if c in nach_name]


_STUFEN_REIHENFOLGE = {
	"Rohstoff": 0,
	"Packmittel": 1,
	"Halbfabrikat": 2,
	"Grundteig": 3,
	"Teig veredelt": 4,
	"Rework": 5,
	"Backware": 6,
	"Ware lose": 7,
	"Fertigware": 8,
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
