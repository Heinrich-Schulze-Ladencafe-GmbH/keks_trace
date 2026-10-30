"""Silos und Tanks (Mehl, Zucker, Zuckersirup).

Aus einem Silo wird nicht pro Charge entnommen, sondern einfach dosiert. Deshalb:

1. **Befüllung**: jeder Zugang in den Lagerort des Silos (Wareneingang, Herstellung von Sirup
   in den Tank) bringt eine Charge ins Silo.
2. **Entnahme**: wird bei einer Fertigung aus dem Silo ohne Charge entnommen, teilt das System
   die Menge nach FIFO auf die Chargen im Silo auf. Diese Zuteilung ist rechnerisch.
3. **Vermischung**: wird nachgefüllt, bevor das Silo leer ist, vermischen sich alte und neue
   Charge. Eine rechnerisch verbrauchte Charge gilt deshalb noch so lange als möglicherweise
   enthalten, bis nach ihr die Nachlaufmenge des Silos entnommen wurde. Bis dahin bekommt jede
   Entnahme eine zusätzliche Genealogie-Kante (Quelle „Silo“, Menge 0). Lieber eine Charge zu viel.
4. **Leermeldung**: ist das Silo physisch leer, meldet der Bediener das. Ein rechnerischer Rest
   wird als Silo-Differenz ausgebucht, und ab dann gilt keine alte Charge mehr als enthalten.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from keks_trace.utils import zeilen_menge

EPS = 1e-6
DIFFERENZ_TYP = "Silo Differenz"


def silo_fuer_lager(warehouse: str | None) -> str | None:
	if not warehouse:
		return None
	karte = frappe.cache.get_value("kt_silo_lager")
	if karte is None:
		karte = {
			s.warehouse: s.name
			for s in frappe.get_all("Silo", filters={"aktiv": 1}, fields=["name", "warehouse"])
		}
		frappe.cache.set_value("kt_silo_lager", karte)
	return karte.get(warehouse)


def _zeitpunkt(doc):
	return get_datetime(f"{doc.posting_date} {doc.posting_time or '00:00:00'}")


# ---------------------------------------------------------------------------
# Bestand je Charge im Silo
# ---------------------------------------------------------------------------


def _eintraege(warehouse, bis, ohne_beleg=None):
	return frappe.db.sql(
		"""
		select sbe.batch_no, sbe.qty, sbb.posting_datetime, sbb.voucher_no
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		where sbe.warehouse = %(wh)s and sbb.is_cancelled = 0 and sbb.docstatus = 1
			and sbb.posting_datetime <= %(bis)s and sbb.voucher_no != %(ohne)s
		order by sbb.posting_datetime, sbb.creation
		""",
		{"wh": warehouse, "bis": bis, "ohne": ohne_beleg or ""},
		as_dict=True,
	)


def bestand(warehouse, bis, ohne_beleg=None) -> list[dict]:
	"""Chargen mit Bestand im Silo zum Zeitpunkt, in FIFO-Reihenfolge (erste Befüllung zuerst)."""
	saldo, erster_zugang = defaultdict(float), {}
	for e in _eintraege(warehouse, bis, ohne_beleg):
		saldo[e.batch_no] += flt(e.qty)
		if flt(e.qty) > 0 and e.batch_no not in erster_zugang:
			erster_zugang[e.batch_no] = e.posting_datetime
	chargen = [
		{"charge": c, "menge": flt(m, 6), "befuellt": erster_zugang.get(c)}
		for c, m in saldo.items()
		if m > EPS
	]
	return sorted(chargen, key=lambda c: (c["befuellt"] or get_datetime("1900-01-01"), c["charge"]))


def moeglich_enthalten(silo: str, bis, ohne_beleg=None) -> set[str]:
	"""Chargen, die zum Zeitpunkt physisch noch im Silo sein können (Bestand oder Nachlauf)."""
	s = frappe.get_cached_doc("Silo", silo)
	leer = frappe.db.get_value(
		"Silo Leermeldung", {"silo": silo, "zeitpunkt": ["<=", bis]}, "zeitpunkt", order_by="zeitpunkt desc"
	)
	leer = get_datetime(leer) if leer else None

	saldo, erster_zugang, leer_seit, entnahmen = defaultdict(float), {}, {}, []
	for e in _eintraege(s.warehouse, bis, ohne_beleg):
		menge = flt(e.qty)
		saldo[e.batch_no] += menge
		if menge > 0:
			erster_zugang.setdefault(e.batch_no, e.posting_datetime)
			leer_seit.pop(e.batch_no, None)
		else:
			entnahmen.append((e.posting_datetime, -menge))
			if saldo[e.batch_no] <= EPS:
				leer_seit[e.batch_no] = e.posting_datetime

	ergebnis = set()
	for charge, rest in saldo.items():
		if leer and erster_zugang.get(charge) and erster_zugang[charge] <= leer and rest <= EPS:
			continue  # vor der Leermeldung eingefüllt und aufgebraucht: sicher draußen
		if rest > EPS:
			ergebnis.add(charge)
			continue
		seit = leer_seit.get(charge)
		if not seit or (leer and seit <= leer):
			continue
		danach = sum(m for t, m in entnahmen if t > seit)
		if danach < flt(s.nachlauf) - EPS:
			ergebnis.add(charge)
	return ergebnis


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def zuteilen(doc):
	"""Entnahmen aus Silos ohne Charge nach FIFO auf die Chargen im Silo aufteilen (vor allen Prüfungen)."""
	if doc.purpose not in ("Manufacture", "Repack") or doc.docstatus != 0:
		return
	if not any(silo_fuer_lager(r.s_warehouse) and not r.batch_no and not r.t_warehouse for r in doc.items):
		return

	zeit = _zeitpunkt(doc)
	frei = {}
	neue_zeilen = []
	for r in doc.items:
		silo = silo_fuer_lager(r.s_warehouse) if not r.t_warehouse else None
		if not silo:
			neue_zeilen.append(r)
			continue
		r.kt_silo = silo
		if r.batch_no:
			neue_zeilen.append(r)
			continue
		if r.s_warehouse not in frei:
			# Rückdatierte Entnahme: nie mehr zuteilen, als bis heute noch da ist (sonst negativer Bestand später).
			heute = {
				c["charge"]: c["menge"]
				for c in bestand(r.s_warehouse, get_datetime("2999-12-31"), ohne_beleg=doc.name)
			}
			frei[r.s_warehouse] = [
				{**c, "menge": min(c["menge"], heute.get(c["charge"], 0))}
				for c in bestand(r.s_warehouse, zeit, ohne_beleg=doc.name)
			]
		offen = zeilen_menge(r)
		teile = []
		for c in frei[r.s_warehouse]:
			if offen <= EPS:
				break
			nimm = min(offen, c["menge"])
			if nimm <= EPS:
				continue
			c["menge"] -= nimm
			offen -= nimm
			teile.append((c["charge"], nimm))
		if offen > EPS:
			frappe.throw(
				_("{0}: rechnerisch fehlen {1} {2} {3}. Befüllung gebucht?").format(
					frappe.bold(silo), flt(offen, 3), r.stock_uom or "", r.item_code
				),
				title=_("Silo leer"),
			)
		for charge, menge in teile:
			neue_zeilen.append(_teilzeile(r, charge, menge))

	doc.set("items", [])
	for i, z in enumerate(neue_zeilen, start=1):
		werte = dict(z) if isinstance(z, dict) else z.as_dict()
		for f in ("name", "idx", "parent", "parentfield", "parenttype", "doctype"):
			werte.pop(f, None)
		werte["idx"] = i
		doc.append("items", werte)


def _teilzeile(r, charge, menge):
	werte = r.as_dict()
	cf = flt(r.conversion_factor) or 1
	werte.update(
		{
			"batch_no": charge,
			"use_serial_batch_fields": 1,
			"serial_and_batch_bundle": None,
			"transfer_qty": menge,
			"qty": menge / cf,
			"kt_silo": r.kt_silo,
		}
	)
	return werte


def vermischung(doc, eingaenge):
	"""Zusätzliche Chargen, die bei einer Entnahme aus einem Silo möglicherweise enthalten waren.

	eingaenge: Liste (Charge, Artikel, Menge) der gebuchten Eingänge. Gibt Liste (Charge, Artikel, Silo) zurück.
	"""
	gebucht = {c for c, _i, _m in eingaenge}
	zeit = _zeitpunkt(doc)
	extra = []
	for silo in {
		r.get("kt_silo") or silo_fuer_lager(r.s_warehouse)
		for r in doc.items
		if r.s_warehouse and not r.t_warehouse
	}:
		if not silo:
			continue
		artikel = frappe.get_cached_value("Silo", silo, "artikel")
		for charge in sorted(moeglich_enthalten(silo, zeit, ohne_beleg=doc.name) - gebucht):
			extra.append((charge, artikel, silo))
	return extra


# ---------------------------------------------------------------------------
# Leermeldung
# ---------------------------------------------------------------------------


@frappe.whitelist()
def leermeldung(silo: str, zeitpunkt: str | None = None, bemerkung: str | None = None) -> dict:
	"""Silo bzw. Tank ist physisch leer. Rechnerischen Rest als Silo-Differenz ausbuchen und protokollieren."""
	frappe.has_permission("Stock Entry", "create", throw=True)
	s = frappe.get_doc("Silo", silo)
	zeit = get_datetime(zeitpunkt) if zeitpunkt else now_datetime()
	rest = bestand(s.warehouse, zeit)
	menge = sum(c["menge"] for c in rest)

	se_name = None
	if rest:
		company = frappe.db.get_value("Warehouse", s.warehouse, "company")
		uom = frappe.get_cached_value("Item", s.artikel, "stock_uom")
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": DIFFERENZ_TYP,
				"purpose": "Material Issue",
				"company": company,
				"set_posting_time": 1,
				"posting_date": zeit.date(),
				"posting_time": zeit.time().strftime("%H:%M:%S"),
				"remarks": _("Leermeldung {0}: rechnerischer Rest ausgebucht").format(silo),
				"items": [
					{
						"item_code": s.artikel,
						"s_warehouse": s.warehouse,
						"qty": c["menge"],
						"transfer_qty": c["menge"],
						"uom": uom,
						"stock_uom": uom,
						"conversion_factor": 1,
						"use_serial_batch_fields": 1,
						"batch_no": c["charge"],
						"kt_silo": silo,
					}
					for c in rest
				],
			}
		)
		se.insert()
		se.submit()
		se_name = se.name

	meldung = frappe.get_doc(
		{
			"doctype": "Silo Leermeldung",
			"silo": silo,
			"zeitpunkt": zeit,
			"nutzer": frappe.session.user,
			"rest_rechnerisch": flt(menge, 3),
			"stock_entry": se_name,
			"bemerkung": bemerkung,
		}
	)
	meldung.insert(ignore_permissions=True)
	if s.kapazitaet and menge > flt(s.kapazitaet) * 0.02:
		frappe.msgprint(
			_("Rechnerischer Rest von {0} im {1} ist größer als 2 % der Kapazität. Dosierung prüfen.").format(
				flt(menge, 3), silo
			),
			indicator="orange",
			alert=True,
		)
	return {"leermeldung": meldung.name, "rest": flt(menge, 3), "ausbuchung": se_name}


def info(silo: str) -> dict:
	"""Was ist im Silo? Für Terminals."""
	s = frappe.get_cached_doc("Silo", silo)
	jetzt = now_datetime()
	return {
		"silo": silo,
		"artikel": s.artikel,
		"bestand": bestand(s.warehouse, jetzt),
		"moeglich_enthalten": sorted(moeglich_enthalten(silo, jetzt)),
	}
