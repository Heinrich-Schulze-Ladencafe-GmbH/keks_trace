"""Akte: Woraus besteht das? Rückverfolgung rückwärts als Baum bis zum Wareneingang."""

import frappe
from frappe import _
from frappe.utils import flt

from keks_trace.akte.basis import EPS, _datum, _person, _zeit

# Obergrenzen, damit ein Los mit viel Rework (viele Generationen) die Seite nicht sprengt
MAX_KNOTEN = 300


MAX_HERKUNFT_TIEFE = 25


MAX_PRUEFUNGEN = 8


ROHSTOFF_STUFEN = ("Rohstoff", "Packmittel")


def _wareneingang(charge: str) -> dict | None:
	"""Erster Zugang der Charge von außen: Wareneingang am Terminal (Stock Entry „Material Receipt“) oder
	Eingangsbeleg im Büro (Purchase Receipt). Beleg, Zeit, Lager bzw. Silo, Station, Lieferant."""
	from keks_trace import silo as silo_modul

	z = frappe.db.sql(
		"""
		select sbb.voucher_type as typ, sbb.voucher_no as beleg, sbb.posting_datetime as zeit,
			sbe.warehouse as lager, sbe.qty as menge
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		left join `tabStock Entry` se on sbb.voucher_type = 'Stock Entry' and se.name = sbb.voucher_no
		where sbe.batch_no = %s and sbb.docstatus = 1 and sbb.is_cancelled = 0 and sbe.qty > 0
			and (sbb.voucher_type = 'Purchase Receipt' or se.purpose = 'Material Receipt')
		order by sbb.posting_datetime, sbb.creation
		limit 1
		""",
		charge,
		as_dict=True,
	)
	if not z:
		return None
	z = z[0]
	lieferant = frappe.db.get_value("Batch", charge, "supplier")
	lieferschein = station = bestellung = None
	if z.typ == "Purchase Receipt":
		pr = (
			frappe.db.get_value(
				"Purchase Receipt", z.beleg, ["supplier", "supplier_delivery_note"], as_dict=True
			)
			or frappe._dict()
		)
		lieferant, lieferschein = pr.supplier or lieferant, pr.supplier_delivery_note
		bestellung = frappe.db.get_value(
			"Purchase Receipt Item", {"parent": z.beleg, "purchase_order": ["is", "set"]}, "purchase_order"
		)
	else:
		station, bestellung = frappe.db.get_value("Stock Entry", z.beleg, ["kt_station", "kt_bestellung"])
	return {
		"beleg": z.beleg,
		"zeit": _zeit(z.zeit),
		"menge": flt(z.menge, 3),
		"lager": z.lager,
		"silo": silo_modul.silo_fuer_lager(z.lager),
		"station": station,
		"lieferant": (frappe.get_cached_value("Supplier", lieferant, "supplier_name") or lieferant)
		if lieferant
		else None,
		"lieferschein": lieferschein,
		"bestellung": bestellung,
	}


def _freigabe(charge: str) -> dict | None:
	f = frappe.get_all(
		"Chargen Sperre",
		filters={"charge": charge},
		fields=["aktion", "zeitpunkt", "nutzer", "grund"],
		order_by="zeitpunkt desc, creation desc",
		limit=1,
	)
	if not f:
		return None
	f = f[0]
	return {"aktion": f.aktion, "zeit": _zeit(f.zeitpunkt), "person": _person(f.nutzer), "grund": f.grund}


def _buchung(stock_entry: str | None) -> dict | None:
	if not stock_entry:
		return None
	se = frappe.db.get_value(
		"Stock Entry",
		stock_entry,
		["name", "posting_date", "posting_time", "kt_station", "owner"],
		as_dict=True,
	)
	if not se:
		return None
	zeit = f"{_datum(se.posting_date)} {str(se.posting_time or '')[:5]}".strip()
	return {"beleg": se.name, "zeit": zeit, "station": se.kt_station, "person": _person(se.owner)}


def _pruefungen(charge: str, beleg: str | None) -> list[dict]:
	zeilen = frappe.get_all(
		"Pruefung",
		or_filters={"charge": charge, **({"beleg": beleg} if beleg else {})},
		fields=["pruefplan", "ergebnis", "wert", "einheit", "zeitpunkt", "station"],
		order_by="zeitpunkt desc",
		limit=MAX_PRUEFUNGEN,
	)
	return [
		{
			"was": z.pruefplan,
			"ergebnis": z.ergebnis,
			"wert": (
				f"{flt(z.wert, 3):g} {z.einheit or ''}".strip().replace(".", ",")
				if z.wert is not None
				else None
			),
			"zeit": _zeit(z.zeitpunkt),
			"station": z.station,
		}
		for z in zeilen
	]


def _zutaten(charge: str) -> list[dict]:
	"""Direkte Bestandteile einer Charge, je Eingangscharge zusammengefasst (mehrere Buchungen, Silo-Kante)."""
	je = {}
	for k in frappe.get_all(
		"Chargen Genealogie",
		filters={"output_batch": charge, "storniert": 0},
		fields=["input_batch", "menge", "anteil", "stock_entry", "quelle", "silo"],
		order_by="posting_date asc, creation asc",
	):
		if not k.input_batch or k.input_batch == charge:
			continue
		e = je.setdefault(
			k.input_batch,
			{
				"charge": k.input_batch,
				"menge": 0.0,
				"anteil": 0.0,
				"silo": None,
				"nur_silo": True,
				"buchung": k.stock_entry,
			},
		)
		e["menge"] += flt(k.menge)
		e["anteil"] += flt(k.anteil)
		e["silo"] = e["silo"] or k.silo
		if k.quelle != "Silo" or flt(k.menge) > EPS:
			e["nur_silo"] = False
	return list(je.values())


def _knoten(charge: str) -> dict:
	b = (
		frappe.db.get_value(
			"Batch",
			charge,
			[
				"item",
				"item_name",
				"kt_chargen_stufe",
				"kt_los",
				"manufacturing_date",
				"kt_backtag",
				"expiry_date",
				"kt_status",
				"kt_sperrgrund",
				"kt_kennzeichen",
			],
			as_dict=True,
		)
		or frappe._dict()
	)
	n = {
		"charge": charge,
		"los": b.kt_los or None,
		"artikel": b.item,
		"name": b.item_name or b.item or charge,
		"stufe": b.kt_chargen_stufe,
		"hergestellt": _datum(b.manufacturing_date),
		"backtag": _datum(b.kt_backtag),
		"mhd": _datum(b.expiry_date),
		"gesperrt": b.kt_status == "Gesperrt",
		"sperrgrund": b.kt_sperrgrund if b.kt_status == "Gesperrt" else None,
		"kennzeichen": b.kt_kennzeichen,
	}
	if b.kt_chargen_stufe in ROHSTOFF_STUFEN:
		n["wareneingang"] = _wareneingang(charge)
		n["freigabe"] = _freigabe(charge)
	return n


def herkunft(charge: str) -> dict:
	"""Woraus besteht eine Charge bzw. ein Los: Baum über Chargen Genealogie, dazu alle Rohstoffe flach.

	Jede Charge wird nur einmal aufgeklappt (Rework kann dieselbe Charge über viele Wege enthalten);
	weitere Vorkommen tragen `wiederholt`. „Möglicherweise enthalten“ heißt: nur über die Silo-Vermischung
	(Menge 0, Quelle Silo, siehe silo.py) - lieber eine Charge zu viel als eine zu wenig.
	"""
	if not frappe.db.exists("Batch", charge):
		frappe.throw(_("Charge {0} existiert nicht.").format(charge), frappe.DoesNotExistError)
	frappe.has_permission("Batch", "read", charge, throw=True)
	gesehen: set[str] = set()
	zaehler = {"n": 0, "abgeschnitten": False}
	rohstoffe: dict[str, dict] = {}

	def bauen(c: str, tiefe: int, kante: dict | None) -> dict:
		zaehler["n"] += 1
		n = _knoten(c)
		if kante:
			n["menge"] = flt(kante["menge"], 3)
			n["moeglich"] = kante["nur_silo"]
			n["ueber_silo"] = kante["silo"]
		if n["stufe"] in ROHSTOFF_STUFEN:
			# Rohstoff: in der Liste einmal; „möglicherweise“ nur, wenn er auf keinem Weg sicher enthalten ist
			if r := rohstoffe.get(c):
				r["moeglich"] = r["moeglich"] and n.get("moeglich", False)
				n["wiederholt"] = True
			else:
				rohstoffe[c] = {**n, "moeglich": n.get("moeglich", False)}
			return n
		if c in gesehen:
			n["wiederholt"] = True
			return n
		gesehen.add(c)
		teile = _zutaten(c)
		if teile:
			n["herstellung"] = _buchung(teile[0]["buchung"])
		n["pruefungen"] = _pruefungen(c, teile[0]["buchung"] if teile else None)
		if tiefe >= MAX_HERKUNFT_TIEFE or zaehler["n"] >= MAX_KNOTEN:
			if teile:
				zaehler["abgeschnitten"] = True
				n["abgeschnitten"] = True
			return n
		n["teile"] = [bauen(t["charge"], tiefe + 1, t) for t in teile]
		return n

	baum = bauen(charge, 0, None)
	liste = sorted(
		rohstoffe.values(), key=lambda r: (r["stufe"] != "Rohstoff", r["moeglich"], r["name"], r["charge"])
	)
	return {"baum": baum, "rohstoffe": liste, "abgeschnitten": zaehler["abgeschnitten"]}
