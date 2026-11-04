"""Netzbild der Rückverfolgung: ein Los in der Mitte, links woraus es besteht, rechts wohin es ging (bis zum Kunden).

Grundlage ist `Chargen Genealogie` wie in trace.py, hier aber mit den Kanten (wer ging in wen, wie viel),
damit die Seite /netz das Netz zeichnen kann. Dazu eine Belegliste (Einkauf und Verkauf) für Audit und Rückruf.
Nur lesen.
"""

import frappe
from frappe import _
from frappe.utils import flt

from keks_trace import akte as akte_modul

# Obergrenze, damit Rework über viele Generationen die Seite nicht sprengt
MAX_KNOTEN = 300
MAX_TIEFE = 25
EPS = 1e-9
ROHSTOFF_STUFEN = ("Rohstoff", "Packmittel")


def _kanten(start: str, vorwaerts: bool, gesehen: set[str]) -> tuple[list[dict], bool]:
	"""Kanten von `start` aus in eine Richtung, Generation für Generation, je Paar zusammengefasst."""
	von, nach = ("input_batch", "output_batch") if vorwaerts else ("output_batch", "input_batch")
	je_paar: dict[tuple[str, str], dict] = {}
	welle, tiefe, abgeschnitten = [start], 0, False
	while welle and tiefe < MAX_TIEFE:
		tiefe += 1
		neu = []
		for i in range(0, len(welle), 500):
			for k in frappe.get_all(
				"Chargen Genealogie",
				filters={von: ["in", welle[i : i + 500]], "storniert": 0},
				fields=["input_batch", "output_batch", "menge", "quelle", "silo"],
			):
				a, b = k.input_batch, k.output_batch
				if not a or not b or a == b:
					continue
				e = je_paar.setdefault(
					(a, b), {"von": a, "nach": b, "menge": 0.0, "nur_silo": True, "silo": None}
				)
				e["menge"] += flt(k.menge)
				e["silo"] = e["silo"] or k.silo
				if k.quelle != "Silo" or flt(k.menge) > EPS:
					e["nur_silo"] = False
				weiter = k[nach]
				if weiter not in gesehen:
					if len(gesehen) >= MAX_KNOTEN:
						abgeschnitten = True
						continue
					gesehen.add(weiter)
					neu.append(weiter)
		welle = neu
	if welle:
		abgeschnitten = True
	# Kanten zu abgeschnittenen Knoten weglassen
	return [e for e in je_paar.values() if e["von"] in gesehen and e["nach"] in gesehen], abgeschnitten


def _knoten(chargen: list[str]) -> dict[str, dict]:
	if not chargen:
		return {}
	felder = [
		"name",
		"item",
		"item_name",
		"kt_chargen_stufe",
		"kt_los",
		"manufacturing_date",
		"expiry_date",
		"kt_status",
		"kt_sperrgrund",
		"supplier",
		"kt_kennzeichen",
	]
	zeilen = []
	for i in range(0, len(chargen), 500):
		zeilen += frappe.get_all("Batch", filters={"name": ["in", chargen[i : i + 500]]}, fields=felder)
	einheiten = dict(
		frappe.get_all(
			"Item",
			filters={"name": ["in", list({z.item for z in zeilen if z.item})]},
			fields=["name", "stock_uom"],
			as_list=True,
		)
	)
	auffaellig = set(
		frappe.get_all(
			"Pruefung", filters={"charge": ["in", chargen], "ergebnis": "Abweichung"}, pluck="charge"
		)
	)
	lieferanten = {z.supplier for z in zeilen if z.supplier}
	lieferant_name = (
		dict(
			frappe.get_all(
				"Supplier",
				filters={"name": ["in", list(lieferanten)]},
				fields=["name", "supplier_name"],
				as_list=True,
			)
		)
		if lieferanten
		else {}
	)
	return {
		z.name: {
			"id": z.name,
			"art": "charge",
			"charge": z.name,
			"los": z.kt_los or None,
			"artikel": z.item,
			"name": z.item_name or z.item or z.name,
			"stufe": z.kt_chargen_stufe,
			"einheit": einheiten.get(z.item),
			"hergestellt": akte_modul._datum(z.manufacturing_date),
			"mhd": akte_modul._datum(z.expiry_date),
			"gesperrt": z.kt_status == "Gesperrt",
			"sperrgrund": z.kt_sperrgrund if z.kt_status == "Gesperrt" else None,
			"auffaellig": z.name in auffaellig,
			"lieferant": lieferant_name.get(z.supplier, z.supplier) if z.supplier else None,
			"kennzeichen": z.kt_kennzeichen,
		}
		for z in zeilen
	}


def _lieferungen(chargen: list[str]) -> list[dict]:
	"""Lieferscheine an Kunden mit einer der Chargen, je Charge und Lieferschein."""
	if not chargen:
		return []
	return frappe.db.sql(
		"""
		select sbe.batch_no as charge, dn.name as lieferschein, dn.customer as kunde,
			dn.customer_name as kundenname, dn.posting_date as datum, dn.po_no as bestellnummer,
			sum(abs(sbe.qty)) as menge
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		join `tabDelivery Note` dn on dn.name = sbb.voucher_no
		where sbb.voucher_type = 'Delivery Note' and sbb.is_cancelled = 0 and sbb.docstatus = 1
			and dn.docstatus = 1 and dn.is_return = 0 and sbe.batch_no in %(c)s
		group by sbe.batch_no, dn.name, dn.customer, dn.customer_name, dn.posting_date, dn.po_no
		order by dn.posting_date, dn.name
		""",
		{"c": tuple(chargen)},
		as_dict=True,
	)


@frappe.whitelist()
def netz(charge: str) -> dict:
	"""Knoten (Chargen und Lieferscheine), Kanten mit Menge, Seite (rück/start/vor) und Belegliste.

	`charge` darf auch ein Scan sein (Los, Kartonetikett, Behälter). Bei einer Palette mit mehreren Losen kommt
	`auswahl` zurück: die Seite fragt, welches Los gezeichnet werden soll.
	"""
	charge = (charge or "").strip()
	if not charge:
		frappe.throw(_("Bitte ein Los, eine Charge oder eine Palette angeben."))
	if not frappe.db.exists("Batch", charge):
		from keks_trace import palette as paletten
		from keks_trace import terminal

		r = terminal.aufloesen(charge)
		if r.get("palette") and not r.get("charge"):
			# alles, was je auf der Palette stand (auch nach dem Versand) und was in ihren Versandkartons ist
			lose = sorted(
				{x["charge"] for x in paletten.info(r["palette"])["positionen_gesamt"]}
				| {b.charge for b in akte_modul._bewegungen(r["palette"]) if b.charge}
			)
			if len(lose) != 1:
				namen = _knoten(lose)
				return {
					"auswahl": [
						{
							"charge": c,
							"name": namen.get(c, {}).get("name"),
							"los": namen.get(c, {}).get("los"),
						}
						for c in lose
					]
				}
			charge = lose[0]
		else:
			charge = r.get("charge")
		if not charge:
			frappe.throw(_("Zu {0} gibt es kein Los.").format(frappe.bold(r.get("code") or "")))
	frappe.has_permission("Batch", "read", charge, throw=True)

	rueck_gesehen, vor_gesehen = {charge}, {charge}
	rueck, ab1 = _kanten(charge, False, rueck_gesehen)
	vor, ab2 = _kanten(charge, True, vor_gesehen)
	alle = list(rueck_gesehen | vor_gesehen)
	knoten = _knoten(alle)
	for c, n in knoten.items():
		n["seite"] = "start" if c == charge else ("vor" if c in vor_gesehen else "rueck")

	kanten = [{**e, "menge": flt(e["menge"], 3)} for e in rueck + vor]
	# Kunden: Lieferscheine des Loses selbst und von allem, was daraus wurde
	lieferungen = _lieferungen(sorted(vor_gesehen))
	for z in lieferungen:
		kid = "LS:" + z.lieferschein
		if kid not in knoten:
			knoten[kid] = {
				"id": kid,
				"art": "kunde",
				"seite": "vor",
				"name": z.kundenname or z.kunde,
				"kunde": z.kunde,
				"lieferschein": z.lieferschein,
				"datum": akte_modul._datum(z.datum),
				"bestellnummer": z.bestellnummer,
			}
		kanten.append(
			{"von": z.charge, "nach": kid, "menge": flt(z.menge, 3), "nur_silo": False, "silo": None}
		)

	# Belegliste wie „Externe Orders“: Einkauf (Wareneingang der Rohstoffe) und Verkauf (Lieferscheine)
	belege = []
	for c in sorted(rueck_gesehen | {charge}):
		n = knoten.get(c)
		if not n or n["stufe"] not in ROHSTOFF_STUFEN:
			continue
		w = akte_modul._wareneingang(c)
		belege.append(
			{
				"art": "Einkauf",
				"beleg": w["beleg"] if w else None,
				"datum": w["zeit"] if w else None,
				"partner": (w or {}).get("lieferant") or n["lieferant"],
				"extern": (w or {}).get("lieferschein"),
				"artikel": n["artikel"],
				"artikelname": n["name"],
				"charge": c,
				"menge": w["menge"] if w else None,
				"einheit": n["einheit"],
			}
		)
	for z in lieferungen:
		n = knoten.get(z.charge, {})
		belege.append(
			{
				"art": "Verkauf",
				"beleg": z.lieferschein,
				"datum": akte_modul._datum(z.datum),
				"partner": z.kundenname or z.kunde,
				"extern": z.bestellnummer,
				"artikel": n.get("artikel"),
				"artikelname": n.get("name"),
				"charge": z.charge,
				"menge": flt(z.menge, 3),
				"einheit": n.get("einheit"),
			}
		)
	return {
		"start": charge,
		"knoten": list(knoten.values()),
		"kanten": kanten,
		"belege": belege,
		"abgeschnitten": ab1 or ab2,
	}


@frappe.whitelist()
def details(charge: str) -> dict:
	"""Details zu einem angeklickten Knoten: Herstellung, Wareneingang, Freigabe, Prüfungen, wo es jetzt liegt."""
	if not charge or not frappe.db.exists("Batch", charge):
		frappe.throw(_("Charge {0} existiert nicht.").format(charge), frappe.DoesNotExistError)
	frappe.has_permission("Batch", "read", charge, throw=True)
	n = akte_modul._knoten(charge)
	teile = akte_modul._zutaten(charge)
	beleg = teile[0]["buchung"] if teile else None
	n["herstellung"] = akte_modul._buchung(beleg)
	n["pruefungen"] = akte_modul._pruefungen(charge, beleg)
	n["fundstellen"] = akte_modul.fundstellen(charge)
	return n
