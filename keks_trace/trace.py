"""Rückverfolgung vorwärts (wohin ist eine Charge gegangen) und rückwärts (woraus besteht sie).

Beide Richtungen laufen Generation für Generation über `Chargen Genealogie` (siehe _kette).
Der Anteil gibt an, welcher Bruchteil der gefundenen Charge (vorwärts) bzw. der
Startcharge (rückwärts) aus der jeweils anderen stammt, über alle Wege summiert.
"""

import frappe
from frappe.utils import flt

MAX_TIEFE = 60


def _kette(charge: str, vorwaerts: bool) -> list[dict]:
	"""Alle Chargen, die aus `charge` entstanden sind (vorwärts) bzw. in ihr stecken (rückwärts).

	Schritt für Schritt über `Chargen Genealogie`: je Generation eine Abfrage mit allen Chargen der
	vorigen Generation, jede Charge wird nur einmal weiterverfolgt. Der Aufwand wächst damit mit der Zahl
	der betroffenen Chargen, nicht mit der Zahl der Wege dorthin (Rework über viele Generationen bildet
	sehr viele Wege; eine rekursive SQL-Abfrage über alle Wege lief bei Jahren an Daten nicht mehr durch).

	generation = kürzester Abstand; anteil = Anteil über alle Wege summiert (wie viel der Startcharge
	steckt darin bzw. wie viel davon stammt aus ihr), gerechnet in zeitlicher Reihenfolge der Kette.
	"""
	von, nach = ("input_batch", "output_batch") if vorwaerts else ("output_batch", "input_batch")
	generation = {charge: 0}
	kanten = []
	welle = [charge]
	tiefe = 0
	while welle and tiefe < MAX_TIEFE:
		tiefe += 1
		neu = []
		for i in range(0, len(welle), 500):  # über 1.000 wandelt MariaDB IN in eine Tabelle um (langsam)
			for a, b, anteil in frappe.db.sql(
				f"""select {von}, {nach}, anteil from `tabChargen Genealogie`
				where storniert = 0 and {von} in %(c)s""",
				{"c": tuple(welle[i : i + 500])},
			):
				if b == charge:
					continue
				kanten.append((a, b, flt(anteil)))
				if b not in generation:
					generation[b] = tiefe
					neu.append(b)
		welle = neu

	# Anteile in Reihenfolge der Kette aufsummieren (topologisch; Kreise, die es nicht geben sollte,
	# werden nach Generation abgearbeitet statt endlos verfolgt)
	aus, offen = {}, {}
	for a, b, anteil in kanten:
		aus.setdefault(a, []).append((b, anteil))
		offen[b] = offen.get(b, 0) + 1
	anteil = {charge: 1.0}
	bereit = [charge]
	erledigt = set()
	rest = sorted((c for c in generation if c != charge), key=generation.get)
	while True:
		while bereit:
			c = bereit.pop()
			erledigt.add(c)
			for b, a in aus.get(c, ()):
				anteil[b] = anteil.get(b, 0) + anteil.get(c, 0) * a
				offen[b] -= 1
				if offen[b] == 0 and b not in erledigt:
					bereit.append(b)
		haengt = next((c for c in rest if c not in erledigt), None)
		if haengt is None:
			break
		bereit.append(haengt)
	return [
		frappe._dict(charge=c, generation=g, anteil=anteil.get(c, 0))
		for c, g in generation.items()
		if c != charge
	]


def vorwaerts(charge: str) -> list[dict]:
	return _mit_details(_kette(charge, True))


def rueckwaerts(charge: str) -> list[dict]:
	return _mit_details(_kette(charge, False))


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
	zeilen = []
	for i in range(0, len(chargen), 500):
		zeilen += _details_teil(chargen[i : i + 500])
	nach_name = {z.charge: z for z in zeilen}
	return [nach_name[c] for c in chargen if c in nach_name]


def _details_teil(chargen: list[str]) -> list[dict]:
	return frappe.get_all(
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
